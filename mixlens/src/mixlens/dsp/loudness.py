"""Momentary/short-term/integrated loudness, LRA, true peak — via pyloudnorm + oversampling."""
from __future__ import annotations

import numpy as np
import pyloudnorm as pyln
from scipy.signal import resample_poly

EPS = 1e-12


def _as_2d_samples_channels(audio: np.ndarray) -> np.ndarray:
    """pyloudnorm wants (samples, channels); our convention is (channels, samples)."""
    if audio.ndim == 1:
        return audio[:, None]
    return audio.T


def integrated_lufs(audio: np.ndarray, sr: int) -> float:
    meter = pyln.Meter(sr)
    x = _as_2d_samples_channels(audio)
    val = meter.integrated_loudness(x)
    return float(val) if np.isfinite(val) else -70.0


def _block_loudness(audio: np.ndarray, sr: int, window_s: float, hop_s: float) -> tuple[np.ndarray, np.ndarray]:
    """Gated-free sliding block loudness (K-weighted RMS in LUFS), for momentary/short-term.

    Returns (times, lufs) sampled every `hop_s`, each block `window_s` wide.
    """
    x = _as_2d_samples_channels(audio)
    x_weighted = _k_weight(x, sr)
    n = x_weighted.shape[0]
    win = int(round(window_s * sr))
    hop = int(round(hop_s * sr))
    if n < win:
        return np.array([0.0]), np.array([-70.0])
    starts = np.arange(0, n - win + 1, hop)
    times = starts / sr + window_s / 2.0
    vals = np.empty(len(starts))
    channel_weights = [1.0] * x.shape[1]
    for i, s in enumerate(starts):
        block = x_weighted[s : s + win]
        ms = np.mean(block ** 2, axis=0)
        z = float(np.sum(np.asarray(channel_weights) * ms))
        vals[i] = -0.691 + 10.0 * np.log10(z) if z > EPS else -70.0
    return times, vals


def _k_weight(x: np.ndarray, sr: int) -> np.ndarray:
    """Apply the ITU-R BS.1770 K-weighting filters, reusing pyloudnorm's own
    (high-shelf + high-pass) filter stages so this matches `integrated_lufs`."""
    meter = pyln.Meter(sr)
    y = x.copy()
    for _name, filter_stage in meter._filters.items():
        for ch in range(y.shape[1]):
            y[:, ch] = filter_stage.apply_filter(y[:, ch])
    return y


def momentary_lufs_series(audio: np.ndarray, sr: int, hop_s: float = 0.1) -> tuple[np.ndarray, np.ndarray]:
    """400ms momentary loudness, hopped every `hop_s` (default 100ms)."""
    return _block_loudness(audio, sr, window_s=0.4, hop_s=hop_s)


def short_term_lufs_series(audio: np.ndarray, sr: int, hop_s: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """3s short-term loudness, hopped every `hop_s` (default 1s)."""
    return _block_loudness(audio, sr, window_s=3.0, hop_s=hop_s)


def loudness_range(audio: np.ndarray, sr: int) -> float:
    """LRA: gated short-term loudness, 95th minus 10th percentile (EBU R128 style, simplified)."""
    _times, st = short_term_lufs_series(audio, sr, hop_s=1.0)
    st = st[np.isfinite(st)]
    if len(st) == 0:
        return 0.0
    abs_gated = st[st > -70.0]
    if len(abs_gated) == 0:
        return 0.0
    rel_threshold = np.mean(abs_gated) - 20.0
    rel_gated = abs_gated[abs_gated > rel_threshold]
    if len(rel_gated) == 0:
        rel_gated = abs_gated
    p10, p95 = np.percentile(rel_gated, [10, 95])
    return float(p95 - p10)


def true_peak_dbtp(audio: np.ndarray, oversample: int = 4) -> tuple[float, np.ndarray]:
    """4x-oversampled true peak in dBTP, plus the oversampled signal (for isp_overs)."""
    up = resample_poly(audio, oversample, 1, axis=-1)
    peak = np.max(np.abs(up)) if up.size else 0.0
    dbtp = 20.0 * np.log10(max(peak, EPS))
    return float(dbtp), up


def crest_factor_db(audio: np.ndarray) -> float:
    """Peak-to-RMS ratio in dB, across all channels."""
    x = audio.reshape(-1)
    peak = np.max(np.abs(x)) if x.size else EPS
    rms = np.sqrt(np.mean(x ** 2)) if x.size else EPS
    return float(20.0 * np.log10(max(peak, EPS) / max(rms, EPS)))


def windowed_crest_db(mono: np.ndarray, sr: int, window_ms: float) -> float:
    """Median crest factor (peak/RMS, dB) over non-overlapping `window_ms` windows.

    Shared by st_crest, band_crest_{low,mid,high}, vox_crest, and sheen's
    hf_density (all "short-term crest of a band" measurements at different
    window sizes and band edges).
    """
    win = max(1, int(round(window_ms / 1000.0 * sr)))
    n = len(mono)
    if n < win:
        return 0.0
    crests = []
    for start in range(0, n - win + 1, win):
        block = mono[start : start + win]
        peak = np.max(np.abs(block))
        rms = np.sqrt(np.mean(block ** 2))
        if rms > EPS and peak > EPS:
            crests.append(20.0 * np.log10(peak / rms))
    return float(np.median(crests)) if crests else 0.0


def normalize_to_lufs(audio: np.ndarray, sr: int, target_lufs: float) -> np.ndarray:
    current = integrated_lufs(audio, sr)
    if not np.isfinite(current):
        return audio
    gain_db = target_lufs - current
    gain = 10.0 ** (gain_db / 20.0)
    return audio * gain
