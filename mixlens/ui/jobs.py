"""Background jobs. Streamlit aborts a running script the moment you click
anything, so a long analysis started from a button dies if you switch pages.
Running it in a worker thread lets it finish regardless, and `render_banner`
shows progress and the "see results" link on every page."""
from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable

import streamlit as st


@dataclass
class Job:
    id: str
    kind: str                 # "analyze" | "references"
    label: str
    song: str | None = None
    version: str | None = None
    status: str = "running"   # running | done | error
    detail: str = ""
    error: str = ""
    done_label: str = ""
    started: float = field(default_factory=time.time)
    finished: float | None = None


@st.cache_resource
def _registry() -> dict:
    # One worker: analyses queue instead of fighting over the CPU.
    return {"jobs": {}, "lock": threading.Lock(), "pool": ThreadPoolExecutor(max_workers=1)}


def submit(kind: str, label: str, fn: Callable[[], str], song: str | None = None, version: str | None = None,
           done_label: str = "") -> Job:
    reg = _registry()
    job = Job(id=uuid.uuid4().hex[:8], kind=kind, label=label, song=song, version=version, done_label=done_label)
    with reg["lock"]:
        reg["jobs"][job.id] = job

    def run() -> None:
        try:
            detail = fn() or ""
            with reg["lock"]:
                job.detail, job.status = detail, "done"
        except Exception as e:  # surfaced to the user, not swallowed
            with reg["lock"]:
                job.error, job.status = f"{type(e).__name__}: {e}", "error"
        finally:
            job.finished = time.time()

    reg["pool"].submit(run)
    return job


def all_jobs() -> list[Job]:
    reg = _registry()
    with reg["lock"]:
        return sorted(reg["jobs"].values(), key=lambda j: j.started)


def running() -> list[Job]:
    return [j for j in all_jobs() if j.status == "running"]


def is_running(kind: str, song: str | None = None, version: str | None = None) -> bool:
    return any(j.kind == kind and (song is None or j.song == song) and (version is None or j.version == version)
               for j in running())


def _dismiss(job_id: str) -> None:
    st.session_state.setdefault("_dismissed_jobs", set()).add(job_id)


def _see_results(job: Job) -> None:
    _dismiss(job.id)
    if job.kind == "analyze" and job.song:
        st.session_state["nav_target"] = "Compare"
        st.session_state["cmp_song"] = job.song
        st.session_state["cmp_version"] = job.version
    elif job.kind == "references":
        st.session_state["nav_target"] = "References"


def _fmt(seconds: float) -> str:
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def render_banner() -> None:
    """Progress and results for background work, shown on every page."""
    import theme

    active = bool(running())

    @st.fragment(run_every=2 if active else None)
    def banner() -> None:
        dismissed = st.session_state.setdefault("_dismissed_jobs", set())
        now_running = bool(running())
        if active and not now_running:
            st.rerun()  # last job just finished: leave polling mode and refresh the page
        finished = [j for j in all_jobs() if j.status != "running" and j.id not in dismissed]
        stale = {j.id for j in finished[:-1]}  # only the newest finished job gets a banner
        for job in all_jobs():
            if job.id in dismissed or job.id in stale:
                continue
            if job.status == "running":
                theme.job_card("running", job.label, f"Running for {_fmt(time.time() - job.started)}. "
                               "You can keep using the app; it carries on in the background.")
            elif job.status == "done":
                theme.job_card("done", job.done_label or job.label, job.detail or "Finished.")
                c1, c2, _ = st.columns([1.2, 1, 6])
                if c1.button("See results", key=f"jr_{job.id}", type="primary"):
                    _see_results(job)
                    st.rerun(scope="app")  # the fragment alone can't change the page
                if c2.button("Dismiss", key=f"jd_{job.id}"):
                    _dismiss(job.id)
                    st.rerun(scope="app")
            else:
                theme.job_card("error", job.label, job.error)
                if st.button("Dismiss", key=f"jd_{job.id}"):
                    _dismiss(job.id)
                    st.rerun(scope="app")

    banner()
