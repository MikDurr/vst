"""Save files uploaded through the UI into the layout the pipeline expects."""
from __future__ import annotations

import io
import re
from pathlib import Path

import soundfile as sf
import yaml

from mixlens.io.sidecar import RefEntry, register_paths
from mixlens.io.stems import STEM_NAMES

NAME_RE = re.compile(r"^[A-Za-z0-9-]+$")
AUDIO_TYPES = ["wav", "flac", "aif", "aiff", "mp3", "m4a", "ogg"]


def validate_name(label: str, value: str) -> str:
    """Song/version names go into `{song}__{version}__{stem}.wav`, so they can't
    contain underscores or path characters."""
    value = value.strip()
    if not NAME_RE.match(value):
        raise ValueError(f"{label} may only contain letters, digits and '-' (no spaces or underscores).")
    return value


def _to_wav24(data: bytes, dest: Path) -> None:
    audio, sr = sf.read(io.BytesIO(data), dtype="float32", always_2d=True)
    sf.write(str(dest), audio, sr, subtype="PCM_24")


def save_stems(
    mixes_dir: Path, song: str, version: str, style: str, bpm: float, stems: dict[str, bytes]
) -> Path:
    """Write the four stems as `{song}__{version}__{stem}.wav` (normalised to
    24-bit WAV) and create/update `song.yaml`. Existing sections are kept."""
    song = validate_name("Song", song)
    version = validate_name("Version", version)
    missing = [s for s in STEM_NAMES if s not in stems]
    if missing:
        raise ValueError(f"Missing stems: {', '.join(missing)}")

    song_dir = mixes_dir / song
    song_dir.mkdir(parents=True, exist_ok=True)
    for stem in STEM_NAMES:
        _to_wav24(stems[stem], song_dir / f"{song}__{version}__{stem}.wav")

    yaml_path = song_dir / "song.yaml"
    existing = yaml.safe_load(yaml_path.read_text()) if yaml_path.exists() else {}
    existing = existing or {}
    existing.update({"song": song, "style": style, "bpm": float(bpm)})
    existing.setdefault("sections", {})
    yaml_path.write_text(yaml.dump(existing, sort_keys=False))
    return song_dir


def save_sections(song_dir: Path, sections: dict[str, tuple[float, float]]) -> None:
    yaml_path = song_dir / "song.yaml"
    data = yaml.safe_load(yaml_path.read_text()) or {}
    data["sections"] = {k: [float(a), float(b)] for k, (a, b) in sections.items()}
    yaml_path.write_text(yaml.dump(data, sort_keys=False))


def save_references(references_dir: Path, style: str, files: list[tuple[str, bytes]]) -> list[RefEntry]:
    """Write uploaded reference songs untouched (the spec says not to trim or
    normalise them) into references/<style>/ and register them."""
    style_dir = references_dir / style
    style_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, data in files:
        dest = style_dir / Path(name).name
        dest.write_bytes(data)
        paths.append(dest)
    return register_paths(paths, style, references_dir)
