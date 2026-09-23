"""Parse song.yaml and references/references.yaml sidecar files."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class SongInfo:
    song: str
    style: str
    bpm: float
    sections: dict[str, tuple[float, float]]


@dataclass(frozen=True)
class RefEntry:
    path: str
    style: str
    artist: str
    title: str
    note: str = ""


def load_song_yaml(directory: str | Path) -> SongInfo:
    p = Path(directory) / "song.yaml"
    if not p.exists():
        raise FileNotFoundError(f"No song.yaml in {directory}")
    data = yaml.safe_load(p.read_text()) or {}
    sections_raw = data.get("sections", {}) or {}
    sections = {name: (float(rng[0]), float(rng[1])) for name, rng in sections_raw.items()}
    return SongInfo(
        song=data["song"],
        style=data["style"],
        bpm=float(data["bpm"]),
        sections=sections,
    )


def load_references_yaml(references_dir: str | Path) -> list[RefEntry]:
    p = Path(references_dir) / "references.yaml"
    if not p.exists():
        return []
    data = yaml.safe_load(p.read_text()) or []
    entries = []
    for row in data:
        entries.append(
            RefEntry(
                path=row["path"],
                style=row["style"],
                artist=row.get("artist", ""),
                title=row.get("title", ""),
                note=row.get("note", ""),
            )
        )
    return entries


def bar_from_seconds(t_sec: float, bpm: float) -> float:
    """4/4 bar number, per spec section 2: bar = t * bpm / 240 + 1."""
    return t_sec * bpm / 240.0 + 1.0
