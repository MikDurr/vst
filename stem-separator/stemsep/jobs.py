"""In-process job registry.

A Demucs run on CPU takes minutes, which is far too long to hold a request
open: browsers and proxies time out, and the user gets no progress. So a
separation is a job — POST starts one and returns an id, the UI polls it, and
the stems are served from the job's directory afterwards.

Deliberately in-memory and single-process. This is a local tool for one person
on one machine; a real queue would mean running Redis to coordinate a user with
themselves. The consequence is that restarting the API loses running jobs, and
that's fine — the stems are on disk under a temp dir anyway.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .quick import QuickError, separate_quick
from .separate import SeparationError, separate

Status = Literal["queued", "running", "done", "error", "cancelled"]

# Jobs hold their stems on disk. Sweep anything older than this on each new
# submission, so a long session doesn't quietly fill the disk with 100 MB WAVs.
_TTL_S = 60 * 60 * 6


@dataclass
class Job:
    id: str
    source_name: str
    engine: str
    dir: Path
    status: Status = "queued"
    progress: float = 0.0
    message: str = "Queued"
    error: str | None = None
    stems: list[str] = field(default_factory=list)
    device: str = ""
    elapsed_s: float = 0.0
    created: float = field(default_factory=time.time)
    _proc: subprocess.Popen | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "id": self.id,
                "source_name": self.source_name,
                "engine": self.engine,
                "status": self.status,
                "progress": round(self.progress, 4),
                "message": self.message,
                "error": self.error,
                "stems": list(self.stems),
                "device": self.device,
                "elapsed_s": round(self.elapsed_s, 2),
            }

    def stem_path(self, name: str) -> Path | None:
        # Guard against `..` and absolute paths in the URL segment — this value
        # comes straight off the wire and is used to build a filesystem path.
        if name not in self.stems:
            return None
        p = self.dir / "stems" / f"{name}.wav"
        return p if p.exists() else None


class JobStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(tempfile.gettempdir()) / "stemsep-jobs"
        self.root.mkdir(parents=True, exist_ok=True)
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    # --- lifecycle --------------------------------------------------------

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def _sweep(self) -> None:
        cutoff = time.time() - _TTL_S
        with self._lock:
            stale = [j for j in self._jobs.values() if j.created < cutoff and j.status != "running"]
            for j in stale:
                self._jobs.pop(j.id, None)
        for j in stale:
            shutil.rmtree(j.dir, ignore_errors=True)

    def submit(
        self,
        *,
        audio: bytes,
        filename: str,
        engine: str,
        model: str,
        two_stems: str | None,
        shifts: int,
        device: str | None,
    ) -> Job:
        self._sweep()
        job_id = uuid.uuid4().hex[:12]
        jdir = self.root / job_id
        (jdir / "stems").mkdir(parents=True, exist_ok=True)

        suffix = Path(filename).suffix.lower() or ".wav"
        src = jdir / f"source{suffix}"
        src.write_bytes(audio)

        job = Job(id=job_id, source_name=filename, engine=engine, dir=jdir)
        with self._lock:
            self._jobs[job_id] = job

        t = threading.Thread(
            target=self._run,
            args=(job, src, model, two_stems, shifts, device),
            daemon=True,
            name=f"stemsep-{job_id}",
        )
        t.start()
        return job

    def cancel(self, job: Job) -> bool:
        """Kill a running job. Returns False if it had already finished."""
        with job._lock:
            if job.status not in ("queued", "running"):
                return False
            job.status = "cancelled"
            job.message = "Cancelled"
            proc = job._proc
        if proc and proc.poll() is None:
            proc.kill()
        return True

    def delete(self, job: Job) -> None:
        self.cancel(job)
        with self._lock:
            self._jobs.pop(job.id, None)
        shutil.rmtree(job.dir, ignore_errors=True)

    # --- worker -----------------------------------------------------------

    def _run(
        self,
        job: Job,
        src: Path,
        model: str,
        two_stems: str | None,
        shifts: int,
        device: str | None,
    ) -> None:
        def report(frac: float, msg: str) -> None:
            with job._lock:
                if job.status == "cancelled":
                    return
                job.progress = frac
                job.message = msg

        def register(proc: subprocess.Popen) -> None:
            with job._lock:
                job._proc = proc

        with job._lock:
            if job.status == "cancelled":
                return
            job.status = "running"
            job.message = "Starting…"

        started = time.monotonic()
        try:
            if job.engine == "quick":
                res = separate_quick(src, job.dir / "stems", progress=report)
                stems = ["vocals", "no_vocals"]
                dev = "cpu"
                elapsed = res.elapsed_s
            else:
                res = separate(
                    src,
                    job.dir / "stems",
                    model=model,
                    two_stems=two_stems,
                    shifts=shifts,
                    device=device,
                    progress=report,
                    register_proc=register,
                )
                stems = [s.name for s in res.stems]
                dev = res.device
                elapsed = res.elapsed_s
        except (SeparationError, QuickError) as e:
            with job._lock:
                if job.status != "cancelled":
                    job.status = "error"
                    job.error = str(e)
                    job.message = "Failed"
                job.elapsed_s = time.monotonic() - started
            return
        except Exception as e:  # unexpected — still needs to reach the UI
            with job._lock:
                if job.status != "cancelled":
                    job.status = "error"
                    job.error = f"{type(e).__name__}: {e}"
                    job.message = "Failed"
                job.elapsed_s = time.monotonic() - started
            return

        with job._lock:
            if job.status == "cancelled":
                return
            job.stems = stems
            job.device = dev
            job.elapsed_s = elapsed
            job.progress = 1.0
            job.status = "done"
            job.message = "Done"


store = JobStore()
