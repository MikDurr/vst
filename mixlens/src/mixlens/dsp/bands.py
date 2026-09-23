"""1/3-octave and ERB band edges, and band energy from an STFT."""
from __future__ import annotations

import numpy as np

EPS = 1e-12


def third_octave_edges(low_hz: float, high_hz: float) -> list[tuple[float, float, float]]:
    """Standard 1/3-octave band centers from `low_hz` to `high_hz`.

    Returns a list of (low, center, high) in Hz. Centers follow the base-10
    IEC series: f_c = 1000 * 10^(n/10).
    """
    centers = []
    n = 0
    while True:
        fc = 1000.0 * (10 ** (n / 10.0))
        if fc > high_hz * 1.5:
            break
        if fc >= low_hz / 1.5:
            centers.append(fc)
        n += 1
    n = -1
    while True:
        fc = 1000.0 * (10 ** (n / 10.0))
        if fc < low_hz / 1.5:
            break
        centers.insert(0, fc)
        n -= 1
    edges = []
    factor = 10 ** (1 / 20.0)  # half-band-width multiplier
    for fc in centers:
        lo, hi = fc / factor, fc * factor
        if hi < low_hz or lo > high_hz:
            continue
        edges.append((max(lo, low_hz), fc, min(hi, high_hz)))
    return edges


def erb_hz_to_scale(f_hz: np.ndarray | float) -> np.ndarray | float:
    """Glasberg & Moore ERB-rate scale."""
    return 21.4 * np.log10(1 + 0.00437 * np.asarray(f_hz))


def erb_scale_to_hz(erb: np.ndarray | float) -> np.ndarray | float:
    return (10 ** (np.asarray(erb) / 21.4) - 1) / 0.00437


def erb_band_edges(low_hz: float, high_hz: float, n_bands: int) -> list[tuple[float, float]]:
    """`n_bands` equal-width bands on the ERB-rate scale between low/high Hz."""
    lo_erb, hi_erb = erb_hz_to_scale(low_hz), erb_hz_to_scale(high_hz)
    bounds_erb = np.linspace(lo_erb, hi_erb, n_bands + 1)
    bounds_hz = erb_scale_to_hz(bounds_erb)
    return [(float(bounds_hz[i]), float(bounds_hz[i + 1])) for i in range(n_bands)]


def stft_mag(audio: np.ndarray, sr: int, n_fft: int, hop: int) -> tuple[np.ndarray, np.ndarray]:
    """Magnitude STFT of a mono signal. Returns (freqs, magnitude[frames, bins])."""
    import librosa

    S = librosa.stft(audio.astype(np.float32), n_fft=n_fft, hop_length=hop, window="hann")
    mag = np.abs(S).T  # (frames, bins)
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    return freqs, mag


def band_energy(freqs: np.ndarray, power: np.ndarray, low_hz: float, high_hz: float) -> np.ndarray:
    """Sum power spectral bins within [low_hz, high_hz) per frame.

    `power` has shape (frames, bins), aligned with `freqs` (bins,).
    """
    mask = (freqs >= low_hz) & (freqs < high_hz)
    if not mask.any():
        return np.zeros(power.shape[0], dtype=np.float64)
    return power[:, mask].sum(axis=1)


def energy_to_db(energy: np.ndarray) -> np.ndarray:
    return 10.0 * np.log10(np.maximum(energy, EPS))


def band_energy_db(freqs: np.ndarray, mag: np.ndarray, low_hz: float, high_hz: float) -> np.ndarray:
    power = mag ** 2
    return energy_to_db(band_energy(freqs, power, low_hz, high_hz))


def band_energy_db_mean(freqs: np.ndarray, mag: np.ndarray, low_hz: float, high_hz: float) -> float:
    """dB of the *mean power* across frames in a band, not the mean of per-frame
    dB values. Use this (not `band_energy_db(...).mean()`) whenever a window can
    contain near-silent frames -- averaging log values first lets a handful of
    near-zero frames (e.g. before/after a short transient) drag the whole
    estimate toward -inf even though most of the window's energy is real.
    """
    power = mag ** 2
    mean_energy = band_energy(freqs, power, low_hz, high_hz).mean()
    return float(energy_to_db(np.array([mean_energy]))[0])
