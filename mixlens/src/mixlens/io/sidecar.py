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


def register_paths(paths: list[Path], style: str, references_dir: str | Path) -> list[RefEntry]:
    """Append any of `paths` (files under `references_dir`) not already in
    references.yaml. Returns just the newly added entries. Doesn't analyze
    anything -- `build-envelopes` picks registered files up later."""
    references_dir = Path(references_dir)
    refs_yaml_path = references_dir / "references.yaml"
    existing_paths = {e.path for e in load_references_yaml(references_dir)}

    new_entries: list[RefEntry] = []
    for p in paths:
        try:
            rel = p.resolve().relative_to(references_dir.resolve())
        except ValueError:
            continue
        rel_str = str(rel)
        if rel_str in existing_paths:
            continue
        new_entries.append(RefEntry(path=rel_str, style=style, artist="", title=p.stem, note=""))
        existing_paths.add(rel_str)

    if new_entries:
        data = yaml.safe_load(refs_yaml_path.read_text()) if refs_yaml_path.exists() else []
        data = (data or []) + [
            {"path": e.path, "style": e.style, "artist": e.artist, "title": e.title, "note": e.note}
            for e in new_entries
        ]
        refs_yaml_path.write_text(yaml.dump(data, sort_keys=False, allow_unicode=True))
    return new_entries


def register_references(patterns: list[str], style: str, references_dir: str | Path) -> list[RefEntry]:
    """Glob `patterns` (relative to the cwd) and register the matches. Used by
    `mixlens ref add`."""
    paths = [p for pattern in patterns for p in sorted(Path().glob(pattern))]
    return register_paths(paths, style, references_dir)


def update_reference_meta(references_dir: str | Path, path: str, artist: str, title: str, note: str) -> None:
    """Edit artist/title/note for one registered reference."""
    refs_yaml_path = Path(references_dir) / "references.yaml"
    data = yaml.safe_load(refs_yaml_path.read_text()) or []
    for row in data:
        if row["path"] == path:
            row.update({"artist": artist, "title": title, "note": note})
    refs_yaml_path.write_text(yaml.dump(data, sort_keys=False, allow_unicode=True))
