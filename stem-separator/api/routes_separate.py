"""The /api/separate endpoints.

Job-shaped rather than request/response: a Demucs run is minutes long, so the
UI submits, polls, and then fetches each stem. All the DSP lives in stemsep.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response

from stemsep import DEFAULT_MODEL, MODELS, best_device, demucs_available
from stemsep.jobs import store
from stemsep.separate import AUDIO_EXTS, VIDEO_EXTS

router = APIRouter(prefix="/api")

MAX_UPLOAD_BYTES = 300 * 1024 * 1024   # stems of a full song get big
MAX_SHIFTS = 10
ENGINES = {"demucs", "quick"}
DEVICES = {"cpu", "mps", "cuda"}


@router.get("/health")
def health():
    """Also tells the UI which engines it can actually offer.

    Demucs is an optional install (it drags in torch), so the UI has to be able
    to grey out the model controls and explain why rather than letting someone
    submit a job that will certainly fail.
    """
    return {
        "status": "ok",
        "demucs": demucs_available(),
        "device": best_device(),
        "models": [{"id": k, **v} for k, v in MODELS.items()],
        "default_model": DEFAULT_MODEL,
    }


@router.post("/separate")
async def start_separation(
    file: UploadFile = File(...),
    engine: str = Form("demucs"),
    model: str = Form(DEFAULT_MODEL),
    mode: str = Form("four"),         # "four" | "two"
    shifts: int = Form(0),
    # Optional[str] rather than `str | None`: FastAPI evaluates these
    # annotations at import time, and the venv runs 3.9 (the newest Python with
    # torch wheels for this Mac), where the `|` form isn't valid in a signature.
    device: Optional[str] = Form(None),
):
    """Queue a separation. Returns the job id to poll."""
    if engine not in ENGINES:
        raise HTTPException(400, f"engine must be one of {sorted(ENGINES)}")
    if engine == "demucs" and not demucs_available():
        raise HTTPException(
            409,
            "Demucs is not installed in the API's environment. Run "
            "`pip install -r requirements.txt`, or choose the Quick engine.",
        )
    if model not in MODELS:
        raise HTTPException(400, f"model must be one of {list(MODELS)}")
    if mode not in ("four", "two"):
        raise HTTPException(400, "mode must be 'four' or 'two'")
    if not 0 <= shifts <= MAX_SHIFTS:
        raise HTTPException(400, f"shifts must be between 0 and {MAX_SHIFTS}")
    if device and device not in DEVICES:
        raise HTTPException(400, f"device must be one of {sorted(DEVICES)}")

    name = file.filename or "track.wav"
    ext = Path(name).suffix.lower()
    if ext not in AUDIO_EXTS and ext not in VIDEO_EXTS:
        raise HTTPException(
            400,
            f"Unsupported file type '{ext or '(none)'}'. "
            f"Supported: {', '.join(sorted(AUDIO_EXTS | VIDEO_EXTS))}",
        )

    data = await file.read()
    if not data:
        raise HTTPException(400, "File is empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")

    job = store.submit(
        audio=data,
        filename=name,
        engine=engine,
        model=model,
        # The Quick engine is inherently 2-stem; `mode` only applies to Demucs.
        two_stems="vocals" if (engine == "demucs" and mode == "two") else None,
        shifts=shifts if engine == "demucs" else 0,
        device=device,
    )
    return job.snapshot()


@router.get("/jobs/{job_id}")
def job_status(job_id: str):
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "No such job — the API may have restarted.")
    return job.snapshot()


@router.delete("/jobs/{job_id}")
def cancel_job(job_id: str):
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "No such job")
    store.delete(job)
    return {"deleted": job_id}


@router.get("/jobs/{job_id}/stems/{name}")
def get_stem(job_id: str, name: str):
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "No such job")
    path = job.stem_path(name)
    if not path:
        raise HTTPException(404, f"No stem '{name}' in this job")
    return FileResponse(
        path,
        media_type="audio/wav",
        filename=f"{Path(job.source_name).stem} - {name}.wav",
    )


@router.get("/jobs/{job_id}/zip")
def get_all_stems(job_id: str):
    """Every stem in one download — the normal way you'd move these to a DAW."""
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "No such job")
    if job.status != "done":
        raise HTTPException(409, "Job is not finished")

    base = Path(job.source_name).stem
    buf = io.BytesIO()
    # ZIP_STORED, not DEFLATE: these are float WAVs of full-length audio, which
    # barely compress, and deflating 200 MB just to save a percent would add
    # seconds to the click.
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for name in job.stems:
            path = job.stem_path(name)
            if path:
                z.write(path, f"{base}/{base} - {name}.wav")

    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{base} - stems.zip"'},
    )
