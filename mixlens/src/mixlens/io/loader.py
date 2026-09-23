"""WAV loading, resampling, and length/alignment checks."""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly


def load_wav(path: str | Path, target_sr: int | None = None) -> tuple[np.ndarray, int]:
    """Load an audio file as float32, shape (channels, samples), always 2D.

    Mono files are returned as (1, n). If `target_sr` is given and differs
    from the file's rate, the signal is resampled with `resample_poly`.
    """
    data, sr = sf.read(str(path), dtype="float32", always_2d=True)
    audio = data.T  # (channels, samples)
    if target_sr is not None and sr != target_sr:
        audio = resample_audio(audio, sr, target_sr)
        sr = target_sr
    return audio, sr


def resample_audio(audio: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    if sr_in == sr_out:
        return audio
    g = np.gcd(sr_in, sr_out)
    up, down = sr_out // g, sr_in // g
    return np.stack(
        [resample_poly(ch, up, down).astype(np.float32) for ch in audio], axis=0
    )


def to_mono(audio: np.ndarray) -> np.ndarray:
    """Average channels down to mono, shape (samples,)."""
    return audio.mean(axis=0)


def check_alignment(stems: dict[str, np.ndarray], tolerance_samples: int = 0) -> None:
    """Raise if stems differ in length beyond `tolerance_samples`.

    Per spec 1.1, all four stems should be the same length, starting at bar 1.
    """
    lengths = {name: audio.shape[-1] for name, audio in stems.items()}
    lo, hi = min(lengths.values()), max(lengths.values())
    if hi - lo > tolerance_samples:
        raise ValueError(f"Stem lengths misaligned beyond tolerance: {lengths}")


def audio_hash(path: str | Path) -> str:
    """Content hash of a file, used to skip re-analysis of unchanged stems."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def stems_hash(paths: dict[str, Path]) -> str:
    h = hashlib.sha256()
    for name in sorted(paths):
        h.update(name.encode())
        h.update(audio_hash(paths[name]).encode())
    return h.hexdigest()
