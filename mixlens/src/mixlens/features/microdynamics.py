"""Micro-dynamics: st_crest, transient_ratio, band_crest_{low,mid,high}, pump_depth
(whole mix); vox_crest (vocal); vox_floor_true (internal path, true dry stem)."""
from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfiltfilt

from mixlens.config import Config
from mixlens.dsp.loudness import windowed_crest_db
from mixlens.dsp.segments import active_mask, envelope_db, strong_onsets
from mixlens.io.loader import to_mono
from mixlens.io.stems import StemSet
from mixlens.types import FeatureRow

EPS = 1e-12


def _bandpass(mono: np.ndarray, sr: int, lo: float, hi: float) -> np.ndarray:
    nyq = sr / 2.0
    lo_c, hi_c = max(lo, 1.0), min(hi, nyq * 0.999)
    if lo_c <= 1.0:
        sos = butter(4, hi_c, btype="lowpass", fs=sr, output="sos")
    elif hi_c >= nyq * 0.999:
        sos = butter(4, lo_c, btype="highpass", fs=sr, output="sos")
    else:
        sos = butter(4, [lo_c, hi_c], btype="bandpass", fs=sr, output="sos")
    return sosfiltfilt(sos, mono)


def _transient_ratio(mono: np.ndarray, sr: int, cfg: Config) -> float:
    """Level at each strong onset minus level 100-300ms later. Catches drums
    and plucks losing their attack."""
    pct = cfg.get("microdynamics.onset_percentile", 80.0)
    post_start = cfg.get("microdynamics.transient_post_start_ms", 100.0) / 1000.0
    post_end = cfg.get("microdynamics.transient_post_end_ms", 300.0) / 1000.0
    onsets = strong_onsets(mono, sr, pct)
    env_t, env_db = envelope_db(mono, sr, hop_s=0.005, win_s=0.015)

    ratios = []
    for t in onsets:
        onset_mask = (env_t >= t) & (env_t < t + 0.02)
        later_mask = (env_t >= t + post_start) & (env_t < t + post_end)
        if onset_mask.any() and later_mask.any():
            ratios.append(float(np.max(env_db[onset_mask]) - np.median(env_db[later_mask])))
    return float(np.median(ratios)) if ratios else 0.0


def _pump_depth(mono: np.ndarray, sr: int, cfg: Config) -> float:
    """Median dip in the 200Hz-8kHz level 50-300ms after each kick onset (<120Hz).
    Catches audible pumping from a bus compressor or sidechain."""
    kick_hz = cfg.get("microdynamics.kick_band_hz", 120.0)
    lo = cfg.get("microdynamics.pump_measure_low_hz", 200.0)
    hi = cfg.get("microdynamics.pump_measure_high_hz", 8000.0)
    onset_pct = cfg.get("microdynamics.onset_percentile", 80.0)
    baseline_ms = cfg.get("microdynamics.pump_baseline_ms", 50.0)
    win_start = cfg.get("microdynamics.pump_window_start_ms", 50.0)
    win_end = cfg.get("microdynamics.pump_window_end_ms", 300.0)

    kick_band = _bandpass(mono, sr, 20.0, kick_hz)
    onsets = strong_onsets(kick_band, sr, onset_pct)
    measure_band = _bandpass(mono, sr, lo, hi)
    env_t, env_db = envelope_db(measure_band, sr, hop_s=0.005, win_s=0.015)

    dips = []
    for t in onsets:
        baseline_mask = (env_t >= max(0.0, t - baseline_ms / 1000.0)) & (env_t < t)
        window_mask = (env_t >= t + win_start / 1000.0) & (env_t < t + win_end / 1000.0)
        if baseline_mask.any() and window_mask.any():
            baseline = np.median(env_db[baseline_mask])
            dip_min = np.min(env_db[window_mask])
            dips.append(float(baseline - dip_min))
    return float(np.median(dips)) if dips else 0.0


def extract_whole_mix_microdynamics(mix: np.ndarray, sr: int, cfg: Config) -> list[FeatureRow]:
    window_ms = cfg.get("microdynamics.window_ms", 50.0)
    mono = to_mono(mix)

    rows = [
        FeatureRow(feature="st_crest", value=windowed_crest_db(mono, sr, window_ms)),
        FeatureRow(feature="transient_ratio", value=_transient_ratio(mono, sr, cfg)),
        FeatureRow(feature="pump_depth", value=_pump_depth(mono, sr, cfg)),
    ]
    for band in cfg.get("microdynamics.bands", []):
        banded = _bandpass(mono, sr, band["low"], band["high"])
        rows.append(FeatureRow(feature="band_crest", value=windowed_crest_db(banded, sr, window_ms), band=band["name"]))
    return rows


def extract_vox_crest(vocal: np.ndarray, sr: int, cfg: Config) -> list[FeatureRow]:
    """Short-term crest on the vocal stem. Catches an over-flattened or uncontrolled vocal."""
    window_ms = cfg.get("microdynamics.window_ms", 50.0)
    mono = to_mono(vocal)
    return [FeatureRow(feature="vox_crest", value=windowed_crest_db(mono, sr, window_ms))]


def extract_vox_floor_true(stems: StemSet, cfg: Config) -> list[FeatureRow]:
    """Level of vox_dry in the gaps between phrases, relative to the phrases.

    Needs the true dry stem: the Demucs vocal carries reverb in its gaps, so
    this can't be measured on the reference path. Catches upward compression
    (e.g. OTT) lifting breaths, mouth noise, and the noise floor into the gaps.
    """
    active_lu = cfg.get("active_threshold_lu", 30.0)
    dry_mono = to_mono(stems.vox_dry)
    _at_times, mask = active_mask(dry_mono, stems.sr, active_lu, hop_s=0.1)
    _env_t, env_db = envelope_db(dry_mono, stems.sr, hop_s=0.1, win_s=0.1)
    n = min(len(mask), len(env_db))
    mask, env_db = mask[:n], env_db[:n]
    gap_levels = env_db[~mask]
    active_levels = env_db[mask]
    if len(gap_levels) == 0 or len(active_levels) == 0:
        return [FeatureRow(feature="vox_floor_true", value=0.0)]
    return [FeatureRow(feature="vox_floor_true", value=float(np.median(gap_levels) - np.median(active_levels)))]
