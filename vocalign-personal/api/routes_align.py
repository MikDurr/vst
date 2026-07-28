"""The /api/align endpoint — two takes in, one aligned wav out.

Thin wrapper over vocalign.align_takes; all the DSP decisions live there and
in ALIGN-PLAN.md.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from vocalign import RENDERERS, align_takes

router = APIRouter(prefix="/api")

MAX_UPLOAD_BYTES = 100 * 1024 * 1024


@router.post("/align")
async def align(
    guide_file: UploadFile = File(...),
    dub_file: UploadFile = File(...),
    tightness: float = Form(0.85),
    max_shift_s: float = Form(0.4),
    pitch_strength: float = Form(0.5),
    nearest_octave: bool = Form(True),
    renderer: str = Form("praat"),
):
    """Render `dub_file` time-aligned onto `guide_file`'s timeline, optionally
    pitch-matched too. Returns a 44.1 kHz WAV.

    Defaults mirror the settings chosen by blind listening: praat renderer,
    pitch_strength 0.5 (full 1.0 lock sounds noticeably more processed).
    """
    if renderer not in RENDERERS:
        raise HTTPException(400, f"renderer must be one of {list(RENDERERS)}")
    if not 0.0 <= tightness <= 1.0:
        raise HTTPException(400, "tightness must be between 0 and 1")
    if not 0.0 <= pitch_strength <= 1.0:
        raise HTTPException(400, "pitch_strength must be between 0 and 1")
    if max_shift_s <= 0:
        raise HTTPException(400, "max_shift_s must be positive")

    guide_bytes = await guide_file.read()
    dub_bytes = await dub_file.read()
    for name, data in (("guide", guide_bytes), ("dub", dub_bytes)):
        if not data:
            raise HTTPException(400, f"{name} file is empty")
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, f"{name} file exceeds {MAX_UPLOAD_BYTES // (1024*1024)}MB")

    guide_ext = Path(guide_file.filename or "").suffix.lower() or ".wav"
    dub_ext = Path(dub_file.filename or "").suffix.lower() or ".wav"

    # align_takes works on paths (it loads each input twice — once at analysis
    # rate, once at full render rate), so stage the uploads on disk.
    with tempfile.TemporaryDirectory(prefix="vpa_align_") as tmp:
        tmp = Path(tmp)
        guide_path = tmp / f"guide{guide_ext}"
        dub_path = tmp / f"dub{dub_ext}"
        out_path = tmp / "aligned.wav"
        guide_path.write_bytes(guide_bytes)
        dub_path.write_bytes(dub_bytes)

        try:
            result = align_takes(
                guide_path, dub_path, out_path,
                tightness=tightness,
                max_shift_s=max_shift_s,
                pitch_strength=pitch_strength,
                nearest_octave=nearest_octave,
                renderer=renderer,
            )
        except (RuntimeError, ValueError) as e:
            raise HTTPException(400, f"Alignment failed: {e}") from e

        wav = out_path.read_bytes()

    # Metrics ride along in headers so the UI can show them without a second
    # request or a multipart response.
    return Response(
        content=wav,
        media_type="audio/wav",
        headers={
            "X-Align-Duration-S": f"{result.duration_s:.3f}",
            "X-Align-Mean-Shift-Ms": f"{result.mean_abs_shift_ms:.1f}",
            "X-Align-Pitch-Matched": "1" if result.pitch_matched else "0",
            "X-Align-Renderer": result.renderer,
            "X-Align-Channels": str(result.n_channels),
            "Access-Control-Expose-Headers":
                "X-Align-Duration-S, X-Align-Mean-Shift-Ms, "
                "X-Align-Pitch-Matched, X-Align-Renderer, X-Align-Channels",
            "Content-Disposition": 'attachment; filename="aligned.wav"',
        },
    )
