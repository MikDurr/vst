"""Audio/video input handling: load a take, extract audio from video."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Tuple

import numpy as np

DEFAULT_SR = 22050
AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac"}
VIDEO_EXTS = {".mov", ".mp4", ".mkv", ".avi", ".webm"}



def _require(tool: str) -> str:
    path = shutil.which(tool)
    if path is None:
        raise RuntimeError(
            f"'{tool}' not found on PATH. Install it and try again "
            f"(e.g. `brew install {tool}`)."
        )
    return path


def extract_audio_from_video(video_path: Path, out_wav: Path, sr: int = DEFAULT_SR) -> Path:
    """Extract a mono WAV audio track from a video file via ffmpeg."""
    ffmpeg = _require("ffmpeg")
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg, "-y", "-i", str(video_path),
        "-vn",                 # drop video
        "-ac", "1",            # mono
        "-ar", str(sr),        # resample
        "-loglevel", "error",
        str(out_wav),
    ]
    subprocess.run(cmd, check=True)
    return out_wav



def load_audio_multichannel(
    input_path: str | Path,
    sr: int = DEFAULT_SR,
) -> Tuple[np.ndarray, int]:
    """Load audio preserving its channel layout.

    Returns (samples, sr) where samples is 1-D for mono or (channels, samples)
    for multichannel. Used for *rendering*: analysis (pitch, alignment) is
    inherently mono and uses load_audio, but collapsing to mono on the render
    path would throw away a stereo take's width and panning — and can
    partially phase-cancel hard-panned content.
    """
    import librosa

    input_path = Path(input_path).expanduser()
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    y, sr_out = librosa.load(str(input_path), sr=sr, mono=False)
    return y, sr_out


def load_audio(
    input_path: str | Path,
    sr: int = DEFAULT_SR,
    workdir: Path | None = None,
) -> Tuple[np.ndarray, int]:
    """Load any supported audio/video file as a mono waveform.

    Handles video extraction, then returns (samples, sample_rate). Uses a
    temp workdir for intermediates.
    """
    import librosa  # deferred: keep import cost out of --help

    input_path = Path(input_path).expanduser()
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    ext = input_path.suffix.lower()
    if ext not in AUDIO_EXTS and ext not in VIDEO_EXTS:
        raise ValueError(
            f"Unsupported file type '{ext}'. Supported: "
            f"{sorted(AUDIO_EXTS | VIDEO_EXTS)}"
        )

    owns_workdir = workdir is None
    workdir = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="vpa_"))
    try:
        source = input_path
        if ext in VIDEO_EXTS:
            source = extract_audio_from_video(input_path, workdir / "extracted.wav", sr)

        y, sr_out = librosa.load(str(source), sr=sr, mono=True)
        return y, sr_out
    finally:
        if owns_workdir:
            shutil.rmtree(workdir, ignore_errors=True)
