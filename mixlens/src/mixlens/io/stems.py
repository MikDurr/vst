"""Parse `{song}__{version}__{stem}.wav` filenames into a StemSet."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from mixlens.io.loader import check_alignment, load_wav

STEM_NAMES = ("mix", "vox_dry", "vox_wet", "inst")
FILENAME_RE = re.compile(r"^(?P<song>.+)__(?P<version>[^_]+(?:_[^_]+)*?)__(?P<stem>mix|vox_dry|vox_wet|inst)\.wav$")


@dataclass(frozen=True)
class StemSet:
    song: str
    version: str
    sr: int
    mix: np.ndarray
    vox_dry: np.ndarray
    vox_wet: np.ndarray
    inst: np.ndarray
    paths: dict[str, Path]

    def as_dict(self) -> dict[str, np.ndarray]:
        return {"mix": self.mix, "vox_dry": self.vox_dry, "vox_wet": self.vox_wet, "inst": self.inst}


def parse_stem_filename(path: Path) -> tuple[str, str, str]:
    m = FILENAME_RE.match(path.name)
    if not m:
        raise ValueError(
            f"Filename '{path.name}' doesn't match '{{song}}__{{version}}__{{stem}}.wav'"
        )
    return m["song"], m["version"], m["stem"]


def find_stem_set(directory: str | Path, version: str) -> dict[str, Path]:
    """Locate the four stems for a given version inside `directory`."""
    directory = Path(directory)
    found: dict[str, Path] = {}
    for p in directory.glob("*.wav"):
        try:
            _song, ver, stem = parse_stem_filename(p)
        except ValueError:
            continue
        if ver == version:
            found[stem] = p
    missing = [s for s in STEM_NAMES if s not in found]
    if missing:
        raise FileNotFoundError(
            f"Missing stems {missing} for version '{version}' in {directory}"
        )
    return found


def load_stem_set(directory: str | Path, version: str, target_sr: int = 44100) -> StemSet:
    paths = find_stem_set(directory, version)
    song, _ver, _stem = parse_stem_filename(next(iter(paths.values())))
    audio: dict[str, np.ndarray] = {}
    sr_used = target_sr
    for stem_name, p in paths.items():
        a, sr = load_wav(p, target_sr=target_sr)
        audio[stem_name] = a
        sr_used = sr
    check_alignment(audio, tolerance_samples=int(0.01 * sr_used))
    return StemSet(
        song=song,
        version=version,
        sr=sr_used,
        mix=audio["mix"],
        vox_dry=audio["vox_dry"],
        vox_wet=audio["vox_wet"],
        inst=audio["inst"],
        paths=paths,
    )
