"""Dynamics verdict: references first, rule of thumb without, per band and per section."""
import numpy as np

from mixlens.compare.dynamics import BALANCED, OPEN, SQUASHED, TIGHT, VERY_OPEN, summarize_dynamics
from mixlens.compare.envelope import Envelope
from mixlens.features.microdynamics import extract_section_dynamics

from conftest import stereo

SR = 44100


def env(feature, med, spread, band=""):
    # iqr = 1.349 * spread so the robust z is exactly (x - med) / spread
    return Envelope("dream", feature, band, med, med - 1.28 * spread, med + 1.28 * spread, 1.349 * spread, 12)


ENVS = {
    ("st_crest", ""): env("st_crest", 10.0, 1.0), ("plr", ""): env("plr", 10.0, 1.0),
    ("transient_ratio", ""): env("transient_ratio", 8.0, 1.0), ("crest", ""): env("crest", 12.0, 1.0),
    ("band_crest", "low"): env("band_crest", 10.0, 1.0, "low"), ("band_crest", "mid"): env("band_crest", 10.0, 1.0, "mid"),
    ("band_crest", "high"): env("band_crest", 10.0, 1.0, "high"), ("pump_depth", ""): env("pump_depth", 3.0, 1.0),
}


def values(shift):
    base = {("st_crest", ""): 10.0, ("plr", ""): 10.0, ("transient_ratio", ""): 8.0, ("crest", ""): 12.0}
    return {k: v + shift for k, v in base.items()}


def test_verdict_follows_how_far_from_the_references():
    got = {s: summarize_dynamics(values(s), ENVS).verdict for s in (-3, -1.0, 0, 1.0, 3)}
    assert got == {-3: SQUASHED, -1.0: TIGHT, 0: BALANCED, 1.0: OPEN, 3: VERY_OPEN}


def test_summary_explains_itself_with_numbers_and_an_action():
    s = summarize_dynamics(values(-3), ENVS)
    assert s.basis == "references" and s.position < 0.3
    assert any("Micro-dynamics" in d and "dB" in d for d in s.drivers)
    assert "limiter" in s.advice


def test_without_references_it_uses_plr_and_says_so():
    s = summarize_dynamics({("plr", ""): 5.0}, {})
    assert s.basis == "rule of thumb" and s.verdict == SQUASHED and "rule of thumb" in s.headline
    assert summarize_dynamics({("plr", ""): 10.0}, {}).verdict == BALANCED
    assert summarize_dynamics({("lufs_i", ""): -10.0}, {}) is None  # nothing to judge on


def test_one_squashed_band_is_named():
    v = values(0)
    v.update({("band_crest", "low"): 10.0, ("band_crest", "mid"): 10.0, ("band_crest", "high"): 7.0})
    s = summarize_dynamics(v, ENVS)
    assert s.verdict == BALANCED and "high range is the squashed part" in s.advice
    assert [b.status for b in s.bands] == ["in range", "in range", "squashed"]


def test_vocal_and_pumping_findings():
    v = values(0)
    v.update({("vox_crest", ""): 2.0, ("pump_depth", ""): 6.0})
    envs = {**ENVS, ("vox_crest", ""): env("vox_crest", 8.0, 1.0)}
    s = summarize_dynamics(v, envs)
    assert s.pumping.status == "pumping" and any("vocal is flatter" in x for x in s.vocal)


def test_sections_flag_the_one_the_limiter_hits_hardest():
    v = values(0)
    v.update({("st_crest_section", "verse"): 10.5, ("st_crest_section", "hook"): 7.0,
              ("lufs_section", "verse"): -14.0, ("lufs_section", "hook"): -9.0})
    s = summarize_dynamics(v, ENVS)
    by = {r["section"]: r for r in s.sections}
    assert by["hook"]["status"] == "squashed" and by["verse"]["status"] == "in range"
    assert "hook is 3.5 dB more squashed than the verse" in s.section_note


def test_section_extractor_sees_a_limited_section():
    rng = np.random.default_rng(0)
    n = SR * 4
    dynamic = np.zeros(n // 2)
    dynamic[::2000] = 0.8                                     # sparse peaks over a quiet floor: high crest
    dynamic += 0.02 * rng.standard_normal(n // 2)
    squashed = np.clip(0.5 * np.sign(rng.standard_normal(n // 2)) * 0.9 + 0.05 * rng.standard_normal(n // 2), -0.6, 0.6)
    audio = stereo(np.concatenate([dynamic, squashed]).astype(np.float32))
    from conftest import CONFIG_PATH
    from mixlens.config import load_config
    rows = {(r.feature, r.band): r.value for r in extract_section_dynamics(audio, SR, load_config(CONFIG_PATH), {"a": (0.0, 2.0), "b": (2.0, 4.0), "tiny": (0.0, 0.1)})}
    assert rows[("st_crest_section", "a")] > rows[("st_crest_section", "b")] + 3
    assert ("lufs_section", "a") in rows and not any(b == "tiny" for _f, b in rows)


def test_two_squashed_bands_read_naturally():
    v = values(0)
    v.update({("band_crest", "low"): 10.0, ("band_crest", "mid"): 7.0, ("band_crest", "high"): 7.0})
    assert "mid and high ranges are the squashed part" in summarize_dynamics(v, ENVS).advice
