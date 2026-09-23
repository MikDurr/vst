"""Top-level orchestration: analyze_version() and analyze_reference()."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from mixlens.checks.peaks import flat_top_ratio, run_peak_checks
from mixlens.compare.deviation import DeviationResult, evaluate, match_hints
from mixlens.config import Config
from mixlens.db.repo import Repo
from mixlens.features.registry import extract_all, extract_whole_mix, extract_vocal_inst_pair
from mixlens.io.loader import audio_hash, load_wav, stems_hash
from mixlens.io.separate import separate_array
from mixlens.io.sidecar import RefEntry, SongInfo, load_song_yaml
from mixlens.io.stems import StemSet, load_stem_set
from mixlens.types import FeatureRow

DEMUCS_CACHE_DIRNAME = ".demucs_cache"


def _demucs_split(mix: np.ndarray, sr: int, cache_dir: Path, tag: str) -> tuple[np.ndarray, np.ndarray]:
    """Split into (vocal, accompaniment), each shape (channels, samples)."""
    split = separate_array(mix, sr, cache_dir, tag)
    return split["vocals"], split["accompaniment"]


def run_checks_only(mix_dir: str | Path, version: str, cfg: Config) -> tuple[list, SongInfo]:
    """`mixlens check`: peak safety only, fast -- no Demucs, no feature extraction."""
    from mixlens.io.stems import find_stem_set

    mix_dir = Path(mix_dir)
    song = load_song_yaml(mix_dir)
    paths = find_stem_set(mix_dir, version)
    mix, sr = load_wav(paths["mix"], target_sr=cfg.sample_rate)
    results = run_peak_checks(mix, sr, cfg, song.bpm)
    return results, song


def analyze_version(
    mix_dir: str | Path,
    version: str,
    cfg: Config,
    repo: Repo,
    cache_root: str | Path,
    force: bool = False,
) -> dict:
    """Full analysis: peak checks + all features (reference path via Demucs +
    internal path from your true stems). Skips re-analysis when the stem
    content hash is unchanged from what's stored (unless `force`)."""
    mix_dir = Path(mix_dir)
    cache_root = Path(cache_root)
    song = load_song_yaml(mix_dir)
    stems = load_stem_set(mix_dir, version, target_sr=cfg.sample_rate)

    current_hash = stems_hash(stems.paths)
    stored_hash = repo.get_version_stem_hash(song.song, version)
    if not force and stored_hash == current_hash:
        return {"skipped": True, "reason": "unchanged stems", "song": song.song, "version": version}

    repo.upsert_song(song.song, song.style, song.bpm)
    version_id = repo.upsert_version(song.song, version, current_hash, cfg.text_hash)

    check_results = run_peak_checks(mix=stems.mix, sr=stems.sr, cfg=cfg, bpm=song.bpm, extra_stems=stems.as_dict())
    repo.insert_checks(version_id, check_results)

    demucs_cache = cache_root / DEMUCS_CACHE_DIRNAME
    vocal_demucs, inst_demucs = _demucs_split(stems.mix, stems.sr, demucs_cache, f"{song.song}__{version}__mix")

    feature_rows = extract_all(
        stems, cfg, vocal_demucs=vocal_demucs, inst_demucs=inst_demucs, sections=song.sections
    )
    flat_top = flat_top_ratio(stems.mix, cfg)
    feature_rows = feature_rows + [FeatureRow(feature="flat_top_ratio", value=flat_top)]

    repo.insert_features("version", version_id, feature_rows)

    return {
        "skipped": False,
        "song": song.song,
        "version": version,
        "version_id": version_id,
        "n_checks": len(check_results),
        "n_features": len(feature_rows),
    }


def analyze_reference(ref: RefEntry, references_dir: str | Path, cfg: Config, repo: Repo, cache_root: str | Path) -> dict:
    """Split a reference track and extract its reference-path features."""
    references_dir = Path(references_dir)
    cache_root = Path(cache_root)
    audio_path = references_dir / ref.path
    if not audio_path.exists():
        raise FileNotFoundError(f"Reference audio not found: {audio_path}")

    h = audio_hash(audio_path)
    ref_id = repo.upsert_ref(ref.path, ref.style, ref.artist, ref.title, h, ref.note)

    mix, sr = load_wav(audio_path, target_sr=cfg.sample_rate)
    demucs_cache = cache_root / DEMUCS_CACHE_DIRNAME
    vocal, inst = _demucs_split(mix, sr, demucs_cache, f"ref__{Path(ref.path).stem}__{h[:8]}")

    rows = extract_whole_mix(mix, sr, cfg)
    rows += extract_vocal_inst_pair(vocal, inst, sr, cfg, include_translation=False)

    repo.insert_features("ref", ref_id, rows)
    return {"ref_id": ref_id, "path": ref.path, "style": ref.style, "n_features": len(rows)}


def score_version_against_envelopes(
    repo: Repo, version_id: int, style: str, cfg: Config
) -> list[DeviationResult]:
    """Compare a version's stored features against its style's envelopes."""
    envelopes = repo.get_envelopes(style)
    features = repo.get_features(entity="version", entity_id=version_id)
    results = []
    for _idx, row in features.iterrows():
        key = (row["feature"], row["band"])
        env = envelopes.get(key)
        if env is None:
            continue
        results.append(evaluate(row["value"], env, cfg))
    return results


def build_hints(results: list[DeviationResult], repo: Repo, version_id: int, cfg: Config) -> list[dict]:
    hint_rules = cfg.get("hints", [])
    features = repo.get_features(entity="version", entity_id=version_id)
    extra_values = {row["feature"]: row["value"] for _i, row in features.iterrows() if row["band"] == ""}
    return match_hints(results, hint_rules, extra_values=extra_values)
