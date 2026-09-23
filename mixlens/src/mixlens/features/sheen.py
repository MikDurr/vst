"""air_ratio, presence_ratio, hf_density, hf_flatness, side_mid_air, vox_air_ratio (reference path)."""
from __future__ import annotations

import numpy as np

from mixlens.config import Config
from mixlens.dsp.bands import band_energy, band_energy_db, stft_mag
from mixlens.dsp.loudness import normalize_to_lufs, windowed_crest_db
from mixlens.io.loader import to_mono
from mixlens.types import FeatureRow

EPS = 1e-12


def _band_ratio_db(freqs, mag_mean, lo1, hi1, lo2, hi2) -> float:
    db1 = band_energy_db(freqs, mag_mean, lo1, hi1)[0]
    db2 = band_energy_db(freqs, mag_mean, lo2, hi2)[0]
    return float(db1 - db2)


def extract_sheen(mix: np.ndarray, sr: int, cfg: Config) -> list[FeatureRow]:
    target_lufs = cfg.get("loudness_target_lufs", -14.0)
    n_fft = cfg.get("stft.tonal.n_fft", 4096)
    hop = cfg.get("stft.tonal.hop", 1024)

    air_lo, air_hi = cfg.get("sheen.air_low_hz", 10000.0), cfg.get("sheen.air_high_hz", 16000.0)
    pres_lo, pres_hi = cfg.get("sheen.presence_low_hz", 4000.0), cfg.get("sheen.presence_high_hz", 10000.0)
    ref_lo, ref_hi = cfg.get("sheen.ref_low_hz", 1000.0), cfg.get("sheen.ref_high_hz", 4000.0)
    hf_hz = cfg.get("sheen.hf_hz", 4000.0)
    hf_win_ms = cfg.get("sheen.hf_density_window_ms", 100.0)
    side_mid_air_hz = cfg.get("sheen.side_mid_air_hz", 8000.0)

    normed = normalize_to_lufs(mix, sr, target_lufs)
    mono = to_mono(normed)
    freqs, mag = stft_mag(mono, sr, n_fft, hop)
    mag_mean = mag.mean(axis=0, keepdims=True)

    air_ratio = _band_ratio_db(freqs, mag_mean, air_lo, air_hi, ref_lo, ref_hi)
    presence_ratio = _band_ratio_db(freqs, mag_mean, pres_lo, pres_hi, ref_lo, ref_hi)

    hf_density = _hf_crest_median(mono, sr, hf_hz, hf_win_ms)
    hf_flatness = _hf_flatness(freqs, mag, hf_hz)

    rows = [
        FeatureRow(feature="air_ratio", value=air_ratio),
        FeatureRow(feature="presence_ratio", value=presence_ratio),
        FeatureRow(feature="hf_density", value=hf_density),
        FeatureRow(feature="hf_flatness", value=hf_flatness),
    ]

    if normed.shape[0] >= 2:
        left, right = normed[0], normed[1]
        mid, side = (left + right) / 2.0, (left - right) / 2.0
        freqs_m, mag_m = stft_mag(mid, sr, n_fft, hop)
        _f, mag_s = stft_mag(side, sr, n_fft, hop)
        e_mid = band_energy(freqs_m, (mag_m ** 2).mean(axis=0, keepdims=True), side_mid_air_hz, freqs_m[-1])[0]
        e_side = band_energy(freqs_m, (mag_s ** 2).mean(axis=0, keepdims=True), side_mid_air_hz, freqs_m[-1])[0]
        rows.append(FeatureRow(feature="side_mid_air", value=float(10.0 * np.log10(max(e_side, EPS) / max(e_mid, EPS)))))

    return rows


def extract_vox_air_ratio(vocal: np.ndarray, sr: int, cfg: Config) -> list[FeatureRow]:
    target_lufs = cfg.get("loudness_target_lufs", -14.0)
    n_fft = cfg.get("stft.tonal.n_fft", 4096)
    hop = cfg.get("stft.tonal.hop", 1024)
    air_lo, air_hi = cfg.get("sheen.air_low_hz", 10000.0), cfg.get("sheen.air_high_hz", 16000.0)
    ref_lo, ref_hi = cfg.get("sheen.ref_low_hz", 1000.0), cfg.get("sheen.ref_high_hz", 4000.0)

    normed = normalize_to_lufs(vocal, sr, target_lufs)
    mono = to_mono(normed)
    freqs, mag = stft_mag(mono, sr, n_fft, hop)
    mag_mean = mag.mean(axis=0, keepdims=True)
    ratio = _band_ratio_db(freqs, mag_mean, air_lo, air_hi, ref_lo, ref_hi)
    return [FeatureRow(feature="vox_air_ratio", value=ratio)]


def _hf_crest_median(mono: np.ndarray, sr: int, hf_hz: float, win_ms: float) -> float:
    """Short-term (100ms) crest factor of the >hf_hz band, median. Lower = denser."""
    from scipy.signal import butter, sosfiltfilt

    sos = butter(4, hf_hz, btype="highpass", fs=sr, output="sos")
    hf = sosfiltfilt(sos, mono)
    return windowed_crest_db(hf, sr, win_ms)


def _hf_flatness(freqs: np.ndarray, mag: np.ndarray, hf_hz: float) -> float:
    """Median spectral flatness (geometric/arithmetic mean of power) above hf_hz."""
    mask = freqs >= hf_hz
    if not mask.any():
        return 0.0
    power = mag[:, mask] ** 2 + EPS
    geo_mean = np.exp(np.mean(np.log(power), axis=1))
    arith_mean = np.mean(power, axis=1)
    flatness = geo_mean / np.maximum(arith_mean, EPS)
    return float(np.median(flatness))
