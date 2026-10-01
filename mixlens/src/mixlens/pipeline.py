"""Top-level orchestration: analyze_version() and analyze_reference()."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from mixlens.checks.peaks import flat_top_ratio, run_peak_checks
from mixlens.compare.deviation import DeviationResult, evaluate, match_hints
from mixlens.config import Config
from mixlens.db.repo import Repo
from mixlens.features.microdynamics import extract_section_dynamics
from mixlens.features.registry import extract_all, extract_vocal_inst_pair, extract_whole_mix
from mixlens.io.loader import audio_hash, load_wav, stems_hash
from mixlens.features.mixbalance import extract_mix_balance
from mixlens.io.separate import separate4_array
from mixlens.io.sidecar import RefEntry, SongInfo, load_song_yaml
from mixlens.io.stems import StemSet, find_stem_set, load_stem_set, required_stems
from mixlens.types import FeatureRow

DEMUCS_CACHE_DIRNAME = ".demucs_cache"
MIN_REFERENCES = 3  # fewer than this and a reference 'range' is nearly a single point

# Reference tracks usually have vocals. To compare an instrumental against them
# fairly, each reference also gets a derived row measured on its Demucs
# accompaniment (vocals removed), filed under this style suffix so the existing
# per-style envelope machinery works on it unchanged.
INSTRUMENTAL_SUFFIX = "::instrumental"
ACCOMPANIMENT_TAG = "#accompaniment"


def _demucs_stems(mix: np.ndarray, sr: int, cache_dir: Path, tag: str) -> dict[str, np.ndarray]:
    """drums / bass / other / vocals, each shape (channels, samples)."""
    return separate4_array(mix, sr, cache_dir, tag)


def _accompaniment_stems(stems: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    return {k: stems[k] for k in ("drums", "bass", "other")}


def _split_vocal_accompaniment(stems: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    """(vocals, everything else) from the 4-stem split."""
    return stems["vocals"], stems["drums"] + stems["bass"] + stems["other"]


def run_checks_only(mix_dir: str | Path, version: str, cfg: Config) -> tuple[list, SongInfo]:
    """`mixlens check`: peak safety only, fast -- no Demucs, no feature extraction."""
    mix_dir = Path(mix_dir)
    song = load_song_yaml(mix_dir)
    paths = find_stem_set(mix_dir, version, required=required_stems(song.instrumental))
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
    stems = load_stem_set(mix_dir, version, target_sr=cfg.sample_rate, instrumental=song.instrumental)

    current_hash = stems_hash(stems.paths)
    stored_hash = repo.get_version_stem_hash(song.song, version)
    if not force and stored_hash == current_hash:
        return {"skipped": True, "reason": "unchanged stems", "song": song.song, "version": version}

    repo.upsert_song(song.song, song.style, song.bpm, instrumental=song.instrumental)
    version_id = repo.upsert_version(song.song, version, current_hash, cfg.text_hash)

    check_results = run_peak_checks(mix=stems.mix, sr=stems.sr, cfg=cfg, bpm=song.bpm, extra_stems=stems.as_dict())
    repo.insert_checks(version_id, check_results)

    demucs_cache = cache_root / DEMUCS_CACHE_DIRNAME
    split = _demucs_stems(stems.mix, stems.sr, demucs_cache, f"{song.song}__{version}__mix")
    if song.instrumental:
        # No vocal anywhere: whole-mix measurements, plus how the drums, bass
        # and everything else sit together. Measured exactly like a reference's
        # vocals-removed version so the two are comparable.
        accompaniment = _accompaniment_stems(split)
        feature_rows = extract_whole_mix(stems.mix, stems.sr, cfg)
        feature_rows += extract_section_dynamics(stems.mix, stems.sr, cfg, song.sections)
        feature_rows += extract_mix_balance(sum(accompaniment.values()), accompaniment, stems.sr, cfg)
    else:
        vocal_demucs, inst_demucs = _split_vocal_accompaniment(split)
        feature_rows = extract_all(
            stems, cfg, vocal_demucs=vocal_demucs, inst_demucs=inst_demucs, sections=song.sections
        )
        feature_rows += extract_mix_balance(stems.mix, split, stems.sr, cfg)
    flat_top = flat_top_ratio(stems.mix, cfg)
    if not song.instrumental:
        feature_rows += extract_section_dynamics(stems.mix, stems.sr, cfg, song.sections)
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
    split = _demucs_stems(mix, sr, demucs_cache, f"ref__{Path(ref.path).stem}__{h[:8]}")
    vocal, inst = _split_vocal_accompaniment(split)

    rows = extract_whole_mix(mix, sr, cfg)
    rows += extract_vocal_inst_pair(vocal, inst, sr, cfg, include_translation=False)
    rows += extract_mix_balance(mix, split, sr, cfg)
    repo.insert_features("ref", ref_id, rows)

    # The same measurements on the vocals-removed accompaniment (drums, bass and
    # everything else), for comparing instrumentals against this reference.
    accompaniment = _accompaniment_stems(split)
    acc_id = repo.upsert_ref(
        ref.path + ACCOMPANIMENT_TAG, ref.style + INSTRUMENTAL_SUFFIX, ref.artist, ref.title, h, ref.note
    )
    repo.insert_features(
        "ref", acc_id,
        extract_whole_mix(inst, sr, cfg) + extract_mix_balance(sum(accompaniment.values()), accompaniment, sr, cfg),
    )
    return {"ref_id": ref_id, "path": ref.path, "style": ref.style, "n_features": len(rows)}


def build_style_envelopes(repo: Repo, style: str) -> dict[str, int]:
    """(Re)build the envelope for `style` and its accompaniment variant.
    Returns {envelope style key: number of entries} for whatever got built."""
    from mixlens.compare.envelope import build_envelopes

    built: dict[str, int] = {}
    for key in (style, style + INSTRUMENTAL_SUFFIX):
        df = repo.get_features_for_style(key, entity="ref")
        if df.empty:
            repo.replace_envelopes(key, [])  # last reference removed: don't keep a stale range
            continue
        envelopes = build_envelopes(df)
        repo.replace_envelopes(key, envelopes)
        built[key] = len(envelopes)
    return built


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


def reference_range_key(style: str, instrumental: bool, refs_have_vocals: bool = True) -> str:
    """Which reference range a song is compared against. Instrumentals use the
    references measured with vocals removed, unless the references are
    themselves instrumentals."""
    return style + INSTRUMENTAL_SUFFIX if instrumental and refs_have_vocals else style


def recommendations_for(repo: Repo, cfg: Config, version_id: int, range_key: str):
    """(recommendations, deviation results, has a reference range) for one analyzed version."""
    from mixlens.compare.recommend import recommend

    features = repo.get_features(entity="version", entity_id=version_id)
    values = {(r["feature"], r["band"]): float(r["value"]) for _i, r in features.iterrows()}
    envelopes = repo.get_envelopes(range_key)
    results = [evaluate(v, envelopes[k], cfg) for k, v in values.items() if k in envelopes]
    rules = {r["id"]: r for r in cfg.get("hints", [])}
    scalars = {f: v for (f, b), v in values.items() if b == ""}
    hints = match_hints(results, list(rules.values()), extra_values=scalars)
    recs = recommend(repo.get_checks(version_id), values, results, hints, rules, bool(envelopes))
    n_refs = min((e.n for e in envelopes.values()), default=0)
    if envelopes and n_refs < MIN_REFERENCES:
        from mixlens.compare.recommend import NOTE, Recommendation

        recs.append(Recommendation(
            NOTE, f"Only {n_refs} reference{'s' if n_refs != 1 else ''} in this set",
            "With so few, the 'normal range' is almost a single point, so nothing can show up as out of range and the "
            "comparisons below can't be trusted.",
            f"Add more references for this style (at least {MIN_REFERENCES}, ideally 8 to 20), then measure them."))
    return recs, results, bool(envelopes)
