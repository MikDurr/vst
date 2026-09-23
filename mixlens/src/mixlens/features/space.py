"""vox_tail_{level,decay,bright}, inst_decay, space_contrast, vox_attack (reference path)."""
from __future__ import annotations

import numpy as np

from mixlens.config import Config
from mixlens.dsp.segments import active_mask, envelope_db, find_phrase_ends, strong_onsets
from mixlens.io.loader import to_mono
from mixlens.types import FeatureRow

EPS = 1e-12


def _spectral_centroid_octaves(mono: np.ndarray, sr: int, start_s: float, end_s: float, n_fft: int = 1024) -> float | None:
    import librosa

    start, end = int(start_s * sr), int(end_s * sr)
    if end - start < n_fft // 2 or end > len(mono) or start < 0:
        return None
    seg = mono[start:end]
    centroid = librosa.feature.spectral_centroid(y=seg.astype(np.float32), sr=sr, n_fft=min(n_fft, len(seg)))
    c = float(np.mean(centroid))
    if c <= 0:
        return None
    return float(np.log2(c / 20.0))  # octaves above 20 Hz, a stable reference floor


def _fit_slope_db_per_s(times: np.ndarray, db_vals: np.ndarray) -> float | None:
    finite = np.isfinite(db_vals)
    if finite.sum() < 2:
        return None
    t, v = times[finite], db_vals[finite]
    slope, _intercept = np.polyfit(t, v, 1)
    return float(slope)


def extract_space(vocal: np.ndarray, inst: np.ndarray, sr: int, cfg: Config) -> list[FeatureRow]:
    active_lu = cfg.get("active_threshold_lu", 30.0)
    drop_db = cfg.get("space.phrase_end_drop_db", 15.0)
    window_ms = cfg.get("space.phrase_end_window_ms", 100.0)
    active_min_ms = cfg.get("space.active_min_ms", 500.0)
    tail_start_ms = cfg.get("space.tail_window_start_ms", 150.0)
    tail_end_ms = cfg.get("space.tail_window_end_ms", 400.0)
    decay_window_ms = cfg.get("space.decay_window_ms", 300.0)
    onset_pct = cfg.get("space.strong_onset_percentile", 80.0)
    attack_ms = cfg.get("space.attack_window_ms", 10.0)
    attack_lo = cfg.get("space.attack_low_hz", 2000.0)
    attack_hi = cfg.get("space.attack_high_hz", 8000.0)

    v_mono, i_mono = to_mono(vocal), to_mono(inst)
    at_times, mask = active_mask(v_mono, sr, active_lu, hop_s=0.1)
    phrase_ends = find_phrase_ends(v_mono, sr, at_times, mask, drop_db, window_ms, active_min_ms)

    env_t, env_db = envelope_db(v_mono, sr, hop_s=0.005, win_s=0.015)

    tail_levels, tail_decays, tail_brights = [], [], []
    for pe in phrase_ends:
        phrase_win_mask = (env_t >= max(0.0, pe - 0.3)) & (env_t < pe)
        phrase_level = np.mean(env_db[phrase_win_mask]) if phrase_win_mask.any() else None

        tail_win_mask = (env_t >= pe + tail_start_ms / 1000.0) & (env_t < pe + tail_end_ms / 1000.0)
        if tail_win_mask.any() and phrase_level is not None:
            tail_levels.append(float(np.mean(env_db[tail_win_mask]) - phrase_level))

        decay_win_mask = (env_t >= pe) & (env_t < pe + decay_window_ms / 1000.0)
        slope = _fit_slope_db_per_s(env_t[decay_win_mask], env_db[decay_win_mask])
        if slope is not None:
            tail_decays.append(slope)

        phrase_centroid = _spectral_centroid_octaves(v_mono, sr, max(0.0, pe - 0.3), pe)
        tail_centroid = _spectral_centroid_octaves(v_mono, sr, pe + tail_start_ms / 1000.0, pe + tail_end_ms / 1000.0)
        if phrase_centroid is not None and tail_centroid is not None:
            tail_brights.append(tail_centroid - phrase_centroid)

    onsets = strong_onsets(i_mono, sr, onset_pct)
    inst_env_t, inst_env_db = envelope_db(i_mono, sr, hop_s=0.005, win_s=0.015)
    inst_decays = []
    for t_onset in onsets:
        decay_win_mask = (inst_env_t >= t_onset) & (inst_env_t < t_onset + decay_window_ms / 1000.0)
        slope = _fit_slope_db_per_s(inst_env_t[decay_win_mask], inst_env_db[decay_win_mask])
        if slope is not None:
            inst_decays.append(slope)

    v_onsets_hz = strong_onsets(v_mono, sr, onset_pct)
    attacks = []
    if len(v_onsets_hz):
        from mixlens.dsp.bands import band_energy_db_mean, stft_mag

        n_fft = cfg.get("stft.transient.n_fft", 1024)
        hop = cfg.get("stft.transient.hop", 256)
        freqs, mag = stft_mag(v_mono, sr, n_fft, hop)
        frame_times = np.arange(mag.shape[0]) * hop / sr
        for t_onset in v_onsets_hz:
            pre_mask = (frame_times >= t_onset - attack_ms / 1000.0) & (frame_times < t_onset)
            post_mask = (frame_times >= t_onset) & (frame_times < t_onset + attack_ms / 1000.0)
            if pre_mask.any() and post_mask.any():
                pre_db = band_energy_db_mean(freqs, mag[pre_mask], attack_lo, attack_hi)
                post_db = band_energy_db_mean(freqs, mag[post_mask], attack_lo, attack_hi)
                attacks.append(post_db - pre_db)

    med_tail_decay = float(np.median(tail_decays)) if tail_decays else 0.0
    med_inst_decay = float(np.median(inst_decays)) if inst_decays else 0.0

    rows = [
        FeatureRow(feature="vox_tail_level", value=float(np.median(tail_levels)) if tail_levels else 0.0),
        FeatureRow(feature="vox_tail_decay", value=med_tail_decay),
        FeatureRow(feature="vox_tail_bright", value=float(np.median(tail_brights)) if tail_brights else 0.0),
        FeatureRow(feature="inst_decay", value=med_inst_decay),
        FeatureRow(feature="space_contrast", value=med_inst_decay - med_tail_decay),
        FeatureRow(feature="vox_attack", value=float(np.median(attacks)) if attacks else 0.0),
    ]
    return rows
