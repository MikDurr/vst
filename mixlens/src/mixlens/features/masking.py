"""csi/csi_p10 (consonant survival index) and mask_{body,presence,air}."""
from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfiltfilt

from mixlens.config import Config
from mixlens.dsp.bands import band_energy_db, band_energy_db_mean, erb_band_edges, stft_mag
from mixlens.dsp.segments import detect_onsets
from mixlens.io.loader import to_mono
from mixlens.types import FeatureRow

EPS = 1e-12


def _highpass(mono: np.ndarray, sr: int, hp_hz: float) -> np.ndarray:
    sos = butter(4, hp_hz, btype="highpass", fs=sr, output="sos")
    return sosfiltfilt(sos, mono)


def compute_csi(
    vocal: np.ndarray,
    inst: np.ndarray,
    sr: int,
    cfg: Config,
    n_erb_bands: int = 4,
) -> tuple[float, float, list[float]]:
    """Returns (csi, csi_p10, per-onset scores)."""
    hp_hz = cfg.get("csi.hp_hz", 2000.0)
    window_ms = cfg.get("csi.window_ms", 40.0)
    margin_db = cfg.get("csi.margin_db", 6.0)
    erb_low = cfg.get("csi.erb_low_hz", 2000.0)
    erb_high = cfg.get("csi.erb_high_hz", 6000.0)
    n_fft = cfg.get("stft.transient.n_fft", 1024)
    hop = cfg.get("stft.transient.hop", 256)

    v_mono = to_mono(vocal)
    i_mono = to_mono(inst)
    v_hp = _highpass(v_mono, sr, hp_hz)
    onset_times = detect_onsets(v_hp, sr, hop=hop)

    freqs_v, mag_v = stft_mag(v_mono, sr, n_fft, hop)
    freqs_i, mag_i = stft_mag(i_mono, sr, n_fft, hop)
    frame_times = np.arange(mag_v.shape[0]) * hop / sr

    bands = erb_band_edges(erb_low, erb_high, n_erb_bands)
    window_s = window_ms / 1000.0

    scores = []
    for t_onset in onset_times:
        frame_mask = (frame_times >= t_onset) & (frame_times < t_onset + window_s)
        if not frame_mask.any():
            continue
        v_frames = mag_v[frame_mask]
        i_frames = mag_i[frame_mask]
        survive_count = 0
        for lo, hi in bands:
            v_db = band_energy_db_mean(freqs_v, v_frames, lo, hi)
            i_db = band_energy_db_mean(freqs_i, i_frames, lo, hi)
            if v_db >= i_db - margin_db:
                survive_count += 1
        scores.append(survive_count / len(bands))

    if not scores:
        return 0.0, 0.0, []
    scores_arr = np.array(scores)
    return float(scores_arr.mean()), float(np.percentile(scores_arr, 10)), scores


def extract_csi(vocal: np.ndarray, inst: np.ndarray, sr: int, cfg: Config) -> list[FeatureRow]:
    csi, csi_p10, _scores = compute_csi(vocal, inst, sr, cfg)
    return [
        FeatureRow(feature="csi", value=csi),
        FeatureRow(feature="csi_p10", value=csi_p10),
    ]


def extract_masking_groups(vocal: np.ndarray, inst: np.ndarray, sr: int, cfg: Config) -> list[FeatureRow]:
    """mask_{body,presence,air}: median of inst dB minus vocal dB per group. Info only."""
    n_fft = cfg.get("stft.tonal.n_fft", 4096)
    hop = cfg.get("stft.tonal.hop", 1024)
    v_mono, i_mono = to_mono(vocal), to_mono(inst)
    freqs, mag_v = stft_mag(v_mono, sr, n_fft, hop)
    _f2, mag_i = stft_mag(i_mono, sr, n_fft, hop)

    rows = []
    for group in cfg.get("mask_groups", []):
        lo, hi = group["low"], group["high"]
        v_db = band_energy_db(freqs, mag_v, lo, hi)
        i_db = band_energy_db(freqs, mag_i, lo, hi)
        diff = i_db - v_db
        rows.append(FeatureRow(feature="mask", value=float(np.median(diff)), band=group["name"]))
    return rows
