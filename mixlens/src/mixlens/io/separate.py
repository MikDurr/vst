"""Demucs wrapper (htdemucs), cached by audio hash."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

from mixlens.io.loader import audio_hash, load_wav

DEMUCS_MODEL = "htdemucs"


def _demucs_cmd() -> list[str]:
    """Prefer `python -m demucs.separate`; fall back to a `demucs` script on PATH."""
    check = subprocess.run(
        [sys.executable, "-c", "import demucs"], capture_output=True
    )
    if check.returncode == 0:
        return [sys.executable, "-m", "demucs.separate"]
    script = shutil.which("demucs")
    if script:
        return [script]
    raise RuntimeError("Demucs is not installed. `pip install demucs torch`.")


def demucs_available() -> bool:
    try:
        _demucs_cmd()
        return True
    except RuntimeError:
        return False


def separate(
    audio_path: str | Path,
    cache_dir: str | Path,
    two_stems: str = "vocals",
    model: str = DEMUCS_MODEL,
) -> dict[str, Path]:
    """Split `audio_path` into vocals/no_vocals via Demucs, cached by content hash.

    Returns {"vocals": path, "accompaniment": path}.
    """
    audio_path = Path(audio_path)
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    h = audio_hash(audio_path)
    entry_dir = cache_dir / h
    vocals_path = entry_dir / "vocals.wav"
    accomp_path = entry_dir / "no_vocals.wav"
    if vocals_path.exists() and accomp_path.exists():
        return {"vocals": vocals_path, "accompaniment": accomp_path}

    entry_dir.mkdir(parents=True, exist_ok=True)
    work_dir = entry_dir / "_work"
    work_dir.mkdir(exist_ok=True)

    cmd = [
        *_demucs_cmd(),
        "-n",
        model,
        "--two-stems",
        two_stems,
        "-o",
        str(work_dir),
        str(audio_path),
    ]
    subprocess.run(cmd, check=True)

    stem_dir = work_dir / model / audio_path.stem
    shutil.copyfile(stem_dir / f"{two_stems}.wav", vocals_path)
    no_vox_name = "no_" + two_stems + ".wav"
    shutil.copyfile(stem_dir / no_vox_name, accomp_path)
    shutil.rmtree(work_dir, ignore_errors=True)

    return {"vocals": vocals_path, "accompaniment": accomp_path}


def separate_array(
    audio: np.ndarray,
    sr: int,
    cache_dir: str | Path,
    tag: str,
    two_stems: str = "vocals",
    model: str = DEMUCS_MODEL,
) -> dict[str, np.ndarray]:
    """Convenience wrapper: write `audio` to a temp WAV, separate, load back.

    `tag` should be a stable identifier (e.g. "{song}__{version}__mix") used
    only for the temp filename; caching itself is content-hash based.
    """
    cache_dir = Path(cache_dir)
    tmp_dir = cache_dir / "_tmp_inputs"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / f"{tag}.wav"
    sf.write(str(tmp_path), audio.T, sr)

    paths = separate(tmp_path, cache_dir, two_stems=two_stems, model=model)
    out = {}
    for key, p in paths.items():
        a, _sr = load_wav(p, target_sr=sr)
        out[key] = a
    return out
