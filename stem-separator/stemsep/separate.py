"""Demucs stem separation, driven as a subprocess.

Demucs is imported as a CLI rather than a library on purpose. The library API
pulls torch into *this* process, which means the FastAPI worker holds a couple
of GB resident for the whole session even when nobody is separating anything —
and a torch that segfaults on an MPS edge case takes the API down with it. A
subprocess gives us memory back at the end of every job, a hard kill for
cancellation, and progress for free on stderr.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".aiff", ".aif"}
VIDEO_EXTS = {".mov", ".mp4", ".mkv", ".avi", ".webm"}

# Models worth exposing. Bigger bags of models sound better and cost linearly
# more time, so the UI states the multiplier rather than hiding it.
MODELS: dict[str, dict] = {
    "htdemucs": {
        "label": "htdemucs",
        "note": "Default hybrid transformer. Best quality-per-second.",
    },
    "htdemucs_ft": {
        "label": "htdemucs ft",
        "note": "Fine-tuned; a touch cleaner, roughly 4x the time.",
    },
    "mdx_extra": {
        "label": "mdx extra",
        "note": "MDX winner; often better bass, worse vocals.",
    },
}
DEFAULT_MODEL = "htdemucs"

# The 4 sources every supported model produces, in the order we want them shown.
FOUR_STEMS = ("vocals", "drums", "bass", "other")

# Progress lines look like " 45%|████▌     | 90.0/200.0 [00:10<00:12, 8.8seconds/s]".
_PCT = re.compile(rb"(\d{1,3})%\|")
# Demucs announces its own bar count: "Selected model is a bag of 4 models.
# You will see that many progress bars per track." Reading it beats a hardcoded
# table, which would quietly go wrong the first time a model's bag size changed.
_BAG = re.compile(rb"bag of (\d+) models")
# Everything before this line is setup — on a first run, that includes the
# model download, which has a tqdm bar of its own and would otherwise be
# misread as separation progress that mysteriously restarts.
_SEPARATING = re.compile(rb"Separating track")

ProgressFn = Callable[[float, str], None]


class SeparationError(RuntimeError):
    """Demucs could not be run, or exited non-zero."""


@dataclass(frozen=True)
class Stem:
    name: str
    path: Path


@dataclass(frozen=True)
class SeparationResult:
    stems: tuple[Stem, ...]
    model: str
    device: str
    elapsed_s: float


def _demucs_cmd() -> list[str]:
    """The command prefix that runs Demucs.

    `sys.executable -m demucs.separate` is preferred over the `demucs` console
    script: it guarantees we run the Demucs installed in *this* venv, not
    whichever one happens to be earlier on PATH.
    """
    probe = subprocess.run(
        [sys.executable, "-c", "import demucs"],
        capture_output=True,
    )
    if probe.returncode == 0:
        return [sys.executable, "-m", "demucs.separate"]
    script = shutil.which("demucs")
    if script:
        return [script]
    raise SeparationError(
        "Demucs is not installed in this environment. Install it with "
        "`pip install -r requirements.txt` (it pulls in PyTorch, ~2 GB), "
        "or use the Quick engine, which needs no model."
    )


def demucs_available() -> bool:
    try:
        _demucs_cmd()
        return True
    except SeparationError:
        return False


def best_device() -> str:
    """Pick the fastest device Demucs can actually use here.

    On Apple silicon MPS is several times faster than CPU, but some torch
    builds still fall over on the ops Demucs uses, so the UI keeps an override
    and jobs retry on CPU if an MPS run dies (see `separate`).
    """
    try:
        import torch  # noqa: PLC0415 — deferred: importing torch costs ~2s
    except Exception:
        return "cpu"
    try:
        if torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    try:
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


def _stream_progress(proc: subprocess.Popen, progress: ProgressFn | None) -> str:
    """Consume Demucs' stderr, reporting overall progress. Returns the tail.

    tqdm redraws its bar with carriage returns and never emits a newline until
    the bar completes, so this reads raw bytes and splits on both \\r and \\n
    rather than iterating lines — otherwise the first progress update would
    only arrive when the pass was already over.

    Two bars can appear. On a first run Demucs downloads the model weights with
    a tqdm bar of its own before it starts, and a bagged model then prints one
    separation bar per model in the bag. Both are reported, but as distinct
    phases: rolling them together is what makes a progress bar appear to jump
    backwards. Note that `--shifts` does *not* add bars — Demucs folds the
    extra passes into one bar's total, so the bar simply advances more slowly.
    """
    tail: list[str] = []
    total_bars = 1
    done_bars = 0
    last_pct = -1
    downloading = False
    separating = False
    buf = b""
    assert proc.stdout is not None
    while True:
        chunk = proc.stdout.read(256)
        if not chunk:
            break
        buf += chunk
        parts = re.split(rb"[\r\n]", buf)
        buf = parts.pop()  # last piece may be a partial line
        for part in parts:
            if not part.strip():
                continue

            bag = _BAG.search(part)
            if bag:
                total_bars = max(1, int(bag.group(1)))
            if _SEPARATING.search(part):
                separating = True
                last_pct = -1

            m = _PCT.search(part)
            if not m:
                text = part.decode("utf-8", "replace").strip()
                tail.append(text)
                del tail[:-40]  # keep only enough context for an error message
                continue

            pct = int(m.group(1))
            if not separating:
                # Weights download. Report it as its own phase and hold overall
                # progress at zero — the real work hasn't started.
                downloading = True
                if progress:
                    progress(0.0, f"Downloading model — {pct}%")
                continue
            if downloading:
                downloading = False
            # A drop means the previous bar finished and the next model in the
            # bag began.
            if pct < last_pct:
                done_bars = min(done_bars + 1, total_bars - 1)
            last_pct = pct
            overall = (done_bars + pct / 100) / total_bars
            label = (
                "Separating…"
                if total_bars == 1
                else f"Separating — model {done_bars + 1}/{total_bars}"
            )
            if progress:
                progress(min(0.99, overall), label)

    if buf.strip():
        tail.append(buf.decode("utf-8", "replace").strip())
    return "\n".join(tail)


def separate(
    input_path: Path,
    out_dir: Path,
    *,
    model: str = DEFAULT_MODEL,
    two_stems: str | None = None,
    shifts: int = 0,
    device: str | None = None,
    progress: ProgressFn | None = None,
    register_proc: Callable[[subprocess.Popen], None] | None = None,
) -> SeparationResult:
    """Split `input_path` into stems written flat into `out_dir`.

    `two_stems="vocals"` gives vocals + no_vocals instead of the full four.
    `shifts` is Demucs' shift-trick averaging: 0 is off, higher is slightly
    cleaner and linearly slower. `register_proc` receives the live process so a
    caller can cancel the job by killing it.
    """
    if model not in MODELS:
        raise SeparationError(f"Unknown model '{model}'. Choose one of {list(MODELS)}.")
    input_path = Path(input_path).expanduser()
    if not input_path.exists():
        raise SeparationError(f"Input file not found: {input_path}")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    device = device or best_device()

    # Demucs always nests its output one level under `-o`, as <out>/<model>/,
    # so give it a staging dir of its own and move the stems up afterwards
    # rather than leaving a model-named folder in the caller's directory.
    stage = out_dir / "_demucs"
    stage.mkdir(parents=True, exist_ok=True)

    cmd = [
        *_demucs_cmd(),
        "-n", model,
        "-o", str(stage),
        # Drop the per-track subfolder from the default
        # <model>/<track name>/<stem>.wav layout — otherwise finding the files
        # again means guessing how Demucs sanitised the track name.
        "--filename", "{stem}.{ext}",
        "-d", device,
    ]
    if shifts:
        cmd += ["--shifts", str(shifts)]
    if two_stems:
        cmd += [f"--two-stems={two_stems}"]
    cmd.append(str(input_path))

    if progress:
        progress(0.0, f"Loading {model} on {device}…")

    started = time.monotonic()
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "COLUMNS": "80"}
    try:
        # Merged, not split: Demucs puts its status lines ("bag of N models",
        # "Separating track") on stdout but its tqdm bars on stderr, and the
        # bars can only be interpreted in the context of the lines. Reading one
        # of the two streams loses half the picture, and reading both
        # separately would need a second thread to avoid deadlocking on a full
        # pipe buffer.
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
        )
    except OSError as e:
        raise SeparationError(f"Could not start Demucs: {e}") from e

    if register_proc:
        register_proc(proc)
    tail = _stream_progress(proc, progress)
    code = proc.wait()

    if code != 0:
        if code < 0:
            raise SeparationError("Cancelled.")
        raise SeparationError(f"Demucs exited with code {code}.\n{tail}".strip())

    wanted: Iterable[str] = (two_stems, f"no_{two_stems}") if two_stems else FOUR_STEMS
    stems: list[Stem] = []
    for name in wanted:
        # rglob rather than a fixed <stage>/<model>/<name>.wav: bagged models
        # and future layout changes both move that path around, and there is
        # exactly one file per stem name under the staging dir either way.
        found = next(stage.rglob(f"{name}.wav"), None)
        if not found:
            continue
        dest = out_dir / f"{name}.wav"
        shutil.move(str(found), dest)
        stems.append(Stem(name=name, path=dest))
    shutil.rmtree(stage, ignore_errors=True)

    if not stems:
        raise SeparationError(
            f"Demucs finished but wrote no stems into {stage}.\n{tail}".strip()
        )
    if progress:
        progress(1.0, "Done")
    return SeparationResult(
        stems=tuple(stems),
        model=model,
        device=device,
        elapsed_s=time.monotonic() - started,
    )
