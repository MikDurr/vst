"""side_mid_{band}, corr_{band}: stereo width and phase correlation per band."""
from __future__ import annotations

import numpy as np

from mixlens.config import Config
from mixlens.dsp.bands import band_energy, stft_mag
from mixlens.types import FeatureRow

EPS = 1e-12


def _mid_side(audio: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if audio.shape[0] < 2:
        mono = audio[0]
        return mono, np.zeros_like(mono)
    left, right = audio[0], audio[1]
    mid = (left + right) / 2.0
    side = (left - right) / 2.0
    return mid, side


def extract_stereo(mix: np.ndarray, sr: int, cfg: Config) -> list[FeatureRow]:
    n_fft = cfg.get("stft.tonal.n_fft", 4096)
    hop = cfg.get("stft.tonal.hop", 1024)
    bands = cfg.get("side_mid_bands", [])

    mid, side = _mid_side(mix)
    freqs, mag_mid = stft_mag(mid, sr, n_fft, hop)
    _freqs, mag_side = stft_mag(side, sr, n_fft, hop)
    power_mid = (mag_mid ** 2).mean(axis=0)
    power_side = (mag_side ** 2).mean(axis=0)

    rows = []
    for b in bands:
        lo, hi = b["low"], b["high"] if b["high"] > 0 else freqs[-1]
        e_mid = band_energy(freqs, power_mid[None, :], lo, hi)[0]
        e_side = band_energy(freqs, power_side[None, :], lo, hi)[0]
        ratio_db = 10.0 * np.log10(max(e_side, EPS) / max(e_mid, EPS))
        rows.append(FeatureRow(feature="side_mid", value=float(ratio_db), band=b["name"]))

    if mix.shape[0] >= 2:
        for b in bands:
            lo, hi = b["low"], b["high"] if b["high"] > 0 else sr / 2
            corr = _band_correlation(mix[0], mix[1], sr, lo, hi, n_fft, hop)
            rows.append(FeatureRow(feature="corr", value=float(corr), band=b["name"]))

    return rows


def _band_correlation(left: np.ndarray, right: np.ndarray, sr: int, lo: float, hi: float, n_fft: int, hop: int) -> float:
    from scipy.signal import butter, sosfiltfilt

    nyq = sr / 2.0
    lo_c = max(lo, 1.0)
    hi_c = min(hi, nyq * 0.999)
    if hi_c <= lo_c:
        return 0.0
    if lo_c <= 1.0:
        sos = butter(2, hi_c, btype="lowpass", fs=sr, output="sos")
    else:
        sos = butter(2, [lo_c, hi_c], btype="bandpass", fs=sr, output="sos")
    l_f = sosfiltfilt(sos, left)
    r_f = sosfiltfilt(sos, right)
    num = np.sum(l_f * r_f)
    denom = np.sqrt(np.sum(l_f ** 2) * np.sum(r_f ** 2))
    return float(num / denom) if denom > EPS else 0.0
