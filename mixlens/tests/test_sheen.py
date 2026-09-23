"""Sheen features: shaped noise with known band ratios. Recovers ratios
within 0.5 dB (spec M3 exit criterion)."""
import numpy as np
from scipy.signal import butter, sosfiltfilt

from mixlens.dsp.bands import band_energy_db, stft_mag
from mixlens.features.sheen import _hf_flatness

from conftest import stereo

SR = 44100


def _band_limited_noise(sr: int, duration: float, lo: float, hi: float, rms: float, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(duration * sr)
    noise = rng.standard_normal(n).astype(np.float32)
    sos = butter(6, [max(lo, 1.0), min(hi, sr / 2 * 0.999)], btype="bandpass", fs=sr, output="sos")
    filtered = sosfiltfilt(sos, noise)
    # Normalize by RMS (power), not peak: two bands of different bandwidth
    # have different peak/RMS ratios, so peak-normalizing wouldn't produce a
    # precisely known *power* ratio between them.
    current_rms = np.sqrt(np.mean(filtered ** 2)) + 1e-12
    filtered = filtered / current_rms * rms
    return filtered.astype(np.float32)


def test_band_ratio_recovers_known_relative_level(cfg):
    # Build a signal with a known, precisely controlled energy ratio between
    # two disjoint bands, then measure it back via band_energy_db.
    low_band = _band_limited_noise(SR, 2.0, 1000, 4000, rms=0.1)
    high_band = _band_limited_noise(SR, 2.0, 10000, 16000, rms=0.1 * 10 ** (-3 / 20.0), seed=1)  # -3 dB target
    mono = low_band + high_band

    n_fft, hop = 4096, 1024
    freqs, mag = stft_mag(mono, SR, n_fft, hop)
    mag_mean = mag.mean(axis=0, keepdims=True)
    db_low = band_energy_db(freqs, mag_mean, 1000, 4000)[0]
    db_high = band_energy_db(freqs, mag_mean, 10000, 16000)[0]

    measured_ratio = db_high - db_low
    assert abs(measured_ratio - (-3.0)) < 0.5


def test_hf_flatness_higher_for_noise_than_tone():
    n_fft, hop = 4096, 1024
    noise = _band_limited_noise(SR, 2.0, 4000, 16000, rms=0.3)
    t = np.arange(int(2.0 * SR)) / SR
    tone = (0.3 * np.sin(2 * np.pi * 8000 * t)).astype(np.float32)

    freqs_n, mag_n = stft_mag(noise, SR, n_fft, hop)
    freqs_t, mag_t = stft_mag(tone, SR, n_fft, hop)

    flat_noise = _hf_flatness(freqs_n, mag_n, 4000.0)
    flat_tone = _hf_flatness(freqs_t, mag_t, 4000.0)
    assert flat_noise > flat_tone
