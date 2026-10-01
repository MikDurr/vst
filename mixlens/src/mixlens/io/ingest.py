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
    mixes_dir: Path, song: str, version: str, style: str, bpm: float, stems: dict[str, bytes],
    instrumental: bool = False,
) -> Path:
    """Write the stems as `{song}__{version}__{stem}.wav` (normalised to 24-bit
    WAV) and create/update `song.yaml`. Existing sections are kept. An
    instrumental only needs `mix`; any other stems given are saved too."""
    song = validate_name("Song", song)
    version = validate_name("Version", version)
    missing = [s for s in (("mix",) if instrumental else STEM_NAMES) if s not in stems]
    if missing:
        raise ValueError(f"Missing stems: {', '.join(missing)}")

    song_dir = mixes_dir / song
    song_dir.mkdir(parents=True, exist_ok=True)
    for stem in (s for s in STEM_NAMES if s in stems):
        _to_wav24(stems[stem], song_dir / f"{song}__{version}__{stem}.wav")

    yaml_path = song_dir / "song.yaml"
    existing = yaml.safe_load(yaml_path.read_text()) if yaml_path.exists() else {}
    existing = existing or {}
    existing.update({"song": song, "style": style, "bpm": float(bpm), "instrumental": bool(instrumental)})
    existing.setdefault("sections", {})
    yaml_path.write_text(yaml.dump(existing, sort_keys=False))
    return song_dir


def save_sections(song_dir: Path, bars: dict[str, tuple[int, int]]) -> None:
    """Store sections given as first/last bar. The analysis works in seconds, so
    both are written (seconds computed from the song's BPM)."""
    from mixlens.io.sidecar import seconds_from_bars

    yaml_path = song_dir / "song.yaml"
    data = yaml.safe_load(yaml_path.read_text()) or {}
    bpm = float(data.get("bpm", 120))
    data["section_bars"] = {k: [int(a), int(b)] for k, (a, b) in bars.items()}
    data["sections"] = {k: [round(s, 3) for s in seconds_from_bars(int(a), int(b), bpm)] for k, (a, b) in bars.items()}
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


# Checked in order: "vox_wet"/"vox_dry" contain "vox", and "instrumental"
# contains "mix"-like words in some exports, so the specific names go first.
_STEM_HINTS = [
    ("vox_wet", ("voxwet", "wet", "reverb", "verb", "delay", "fx_return", "returns")),
    ("vox_dry", ("voxdry", "dry", "vocal", "vox", "lead")),
    ("inst", ("inst", "instrumental", "backing", "music", "beat", "band")),
    ("mix", ("mix", "master", "full", "bounce", "final")),
]


def guess_stem(filename: str) -> str | None:
    """Best-guess which of the four stems a file is from its name, or None."""
    from mixlens.io.stems import FILENAME_RE

    name = Path(filename).name
    m = FILENAME_RE.match(name if name.lower().endswith(".wav") else Path(name).stem + ".wav")
    if m:
        return m["stem"]
    flat = re.sub(r"[\s\-.]+", "_", Path(name).stem.lower())
    squashed = flat.replace("_", "")
    tokens = set(flat.split("_"))
    if tokens & {"vox", "vocal", "vocals", "voc"} and tokens & {"full", "all", "combined", "complete", "total"}:
        return "vox_full"
    for stem, hints in _STEM_HINTS:
        if any(h in flat or h in squashed for h in hints):
            return stem
    return None


def guess_song_version(filenames: list[str]) -> tuple[str, str] | None:
    """If files follow `{song}__{version}__{stem}`, return (song, version)."""
    from mixlens.io.stems import FILENAME_RE

    for f in filenames:
        m = FILENAME_RE.match(Path(f).stem + ".wav")
        if m:
            return m["song"], m["version"]
    return None


def assign_stems(filenames: list[str]) -> dict[str, str | None]:
    """Map filename -> stem guess, dropping duplicate guesses (first wins) so
    two files never claim the same slot."""
    taken: set[str] = set()
    out: dict[str, str | None] = {}
    for f in filenames:
        g = guess_stem(f)
        if g in taken:
            g = None
        if g:
            taken.add(g)
        out[f] = g
    return out


def derive_wet(full_bytes: bytes, dry_bytes: bytes, max_offset_ms: float = 0.0) -> tuple[bytes, list[str]]:
    """Build `vox_wet` as `vox_full - vox_dry`.

    `vox_full` is the vocal tracks plus their reverb/delay returns; `vox_dry`
    is the same vocal with the returns muted, so the difference is the returns
    alone. Only valid if both bounces are sample-aligned and identical apart
    from the returns, so this refuses misaligned input and warns when the
    result looks like the dry vocal didn't cancel (e.g. random reverb
    modulation, or a plug-in that changes when the sends are muted).

    Returns (24-bit WAV bytes, warnings).
    """
    import numpy as np

    full, sr_f = sf.read(io.BytesIO(full_bytes), dtype="float64", always_2d=True)
    dry, sr_d = sf.read(io.BytesIO(dry_bytes), dtype="float64", always_2d=True)
    if sr_f != sr_d:
        raise ValueError(f"vox_full is {sr_f} Hz but vox_dry is {sr_d} Hz: bounce both at the same sample rate.")

    if full.shape[1] != dry.shape[1]:
        ch = max(full.shape[1], dry.shape[1])
        full = np.repeat(full, ch, axis=1) if full.shape[1] == 1 else full
        dry = np.repeat(dry, ch, axis=1) if dry.shape[1] == 1 else dry

    tol = int(0.01 * sr_f)
    if abs(len(full) - len(dry)) > tol:
        raise ValueError(
            f"vox_full and vox_dry differ in length by {abs(len(full) - len(dry)) / sr_f:.2f}s: "
            "bounce both over the same range."
        )
    n = min(len(full), len(dry))
    full, dry = full[:n], dry[:n]

    offset = _best_lag(full.mean(axis=1), dry.mean(axis=1), sr_f)
    if abs(offset) > int(max_offset_ms / 1000.0 * sr_f):
        raise ValueError(
            f"vox_full and vox_dry are offset by {offset} samples ({offset / sr_f * 1000:.1f} ms), "
            "so subtracting would leave garbage. Bounce both from the same start point."
        )

    wet = full - dry
    warnings: list[str] = []

    def rms(x):
        return float(np.sqrt(np.mean(x ** 2)) + 1e-12)

    if rms(wet) > rms(dry) * 2:
        warnings.append("The derived wet is much louder than the dry vocal. Check the reverb returns aren't also in vox_dry.")
    if rms(wet) < rms(full) * 1e-3:
        warnings.append("The derived wet is almost silent: vox_full and vox_dry look identical (were the returns muted in both?).")
    a, b = wet.mean(axis=1), dry.mean(axis=1)
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    corr = abs(float(np.dot(a, b))) / denom if denom > 0 else 0.0
    if corr > 0.5:
        warnings.append(
            f"The derived wet still correlates strongly with the dry vocal ({corr:.2f}): the dry didn't fully cancel. "
            "Plug-ins with random modulation or different settings between bounces cause this; bounce vox_wet directly instead."
        )

    buf = io.BytesIO()
    sf.write(buf, wet.astype("float32"), sr_f, format="WAV", subtype="PCM_24")
    return buf.getvalue(), warnings


def _first_onset(x, frac: float = 0.02) -> int:
    """Index of the first sample above `frac` of the signal's own peak."""
    import numpy as np

    peak = float(np.max(np.abs(x))) if len(x) else 0.0
    if peak <= 0:
        return 0
    return int(np.argmax(np.abs(x) > frac * peak))


def _best_lag(full, dry, sr: int, seconds: float = 10.0, max_lag: int = 128, onset_tol_ms: float = 5.0) -> int:
    """How far `dry` must shift to best cancel inside `full` (0 when aligned).

    Reverb tails bias a plain cross-correlation, so this instead (1) compares
    first onsets to catch gross offsets -- a reverb can't start before the dry
    vocal -- and (2) picks the small integer lag whose subtraction leaves the
    least residual energy.
    """
    import numpy as np

    onset_gap = _first_onset(full) - _first_onset(dry)
    if abs(onset_gap) > int(onset_tol_ms / 1000.0 * sr):
        return onset_gap

    # analyse the loudest stretch rather than a possibly-silent intro
    n = min(len(full), len(dry), int(seconds * sr))
    hop = max(1, sr // 2)
    starts = range(0, max(1, min(len(full), len(dry)) - n + 1), hop)
    start = max(starts, key=lambda s: float(np.sum(dry[s:s + n] ** 2)))
    f, d = full[start:start + n], dry[start:start + n]
    if not (np.any(f) and np.any(d)):
        return 0

    best, best_res = 0, None
    for lag in range(-max_lag, max_lag + 1):
        shifted = np.roll(d, lag)
        res = float(np.sum((f[max_lag:-max_lag] - shifted[max_lag:-max_lag]) ** 2))
        if best_res is None or res < best_res:
            best, best_res = lag, res
    return best
