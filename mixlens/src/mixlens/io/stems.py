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
    vox_dry: np.ndarray | None
    vox_wet: np.ndarray | None
    inst: np.ndarray | None
    paths: dict[str, Path]

    def as_dict(self) -> dict[str, np.ndarray]:
        """The stems that exist (an instrumental song only has `mix`, maybe `inst`)."""
        all_stems = {"mix": self.mix, "vox_dry": self.vox_dry, "vox_wet": self.vox_wet, "inst": self.inst}
        return {k: v for k, v in all_stems.items() if v is not None}


def parse_stem_filename(path: Path) -> tuple[str, str, str]:
    m = FILENAME_RE.match(path.name)
    if not m:
        raise ValueError(
            f"Filename '{path.name}' doesn't match '{{song}}__{{version}}__{{stem}}.wav'"
        )
    return m["song"], m["version"], m["stem"]


INSTRUMENTAL_REQUIRED = ("mix",)


def required_stems(instrumental: bool) -> tuple[str, ...]:
    """An instrumental has no vocal stems; only the full mix is needed."""
    return INSTRUMENTAL_REQUIRED if instrumental else STEM_NAMES


def find_stem_set(directory: str | Path, version: str, required: tuple[str, ...] = STEM_NAMES) -> dict[str, Path]:
    """Locate a version's stems inside `directory`; every name in `required` must exist."""
    directory = Path(directory)
    found: dict[str, Path] = {}
    for p in directory.glob("*.wav"):
        try:
            _song, ver, stem = parse_stem_filename(p)
        except ValueError:
            continue
        if ver == version:
            found[stem] = p
    missing = [s for s in required if s not in found]
    if missing:
        raise FileNotFoundError(
            f"Missing stems {missing} for version '{version}' in {directory}"
        )
    return found


def load_stem_set(
    directory: str | Path, version: str, target_sr: int = 44100, instrumental: bool = False
) -> StemSet:
    paths = find_stem_set(directory, version, required=required_stems(instrumental))
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
        vox_dry=audio.get("vox_dry"),
        vox_wet=audio.get("vox_wet"),
        inst=audio.get("inst"),
        paths=paths,
    )
