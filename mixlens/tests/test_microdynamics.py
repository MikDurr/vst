"""Micro-dynamics: crest factor drops under heavy compression; pumping shows up
as a measurable dip after kick onsets."""
import numpy as np

from mixlens.dsp.loudness import windowed_crest_db
from mixlens.features.microdynamics import _pump_depth, _transient_ratio

from conftest import stereo

SR = 44100


def _compress(mono: np.ndarray, threshold: float = 0.1, ratio: float = 8.0) -> np.ndarray:
    """A crude static compressor: enough to flatten crest factor for a test signal."""
    out = np.copy(mono)
    above = np.abs(out) > threshold
    sign = np.sign(out[above])
    excess = np.abs(out[above]) - threshold
    out[above] = sign * (threshold + excess / ratio)
    return out


def test_windowed_crest_drops_under_compression():
    rng = np.random.default_rng(0)
    n = int(2.0 * SR)
    window_ms = 50.0
    window_samples = int(window_ms / 1000.0 * SR)
    bursts = np.zeros(n, dtype=np.float32)
    # a loud transient inside every window -> high crest factor throughout
    for pos in range(0, n - 200, window_samples):
        bursts[pos : pos + 200] = 0.9
    bursts += 0.01 * rng.standard_normal(n).astype(np.float32)

    crest_uncompressed = windowed_crest_db(bursts, SR, window_ms=window_ms)
    crest_compressed = windowed_crest_db(_compress(bursts, threshold=0.05, ratio=20.0), SR, window_ms=window_ms)
    assert crest_compressed < crest_uncompressed


def test_transient_ratio_positive_for_percussive_signal(cfg):
    n = int(2.0 * SR)
    mono = np.zeros(n, dtype=np.float32)
    t_decay = np.arange(int(0.4 * SR)) / SR
    envelope = np.exp(-t_decay * 15.0)
    carrier = np.sin(2 * np.pi * 150 * t_decay)
    click = (envelope * carrier).astype(np.float32)
    for pos in (int(0.2 * SR), int(1.0 * SR), int(1.6 * SR)):
        end = min(pos + len(click), n)
        mono[pos:end] += click[: end - pos]

    ratio = _transient_ratio(mono, SR, cfg)
    assert ratio > 3.0  # attack should read clearly louder than the 100-300ms-later tail


def test_pump_depth_detects_sidechain_style_ducking(cfg):
    n = int(2.5 * SR)
    # Sharp, compact kicks -- a long, smeared low-frequency transient makes
    # onset detection late and jittery enough to swallow the baseline window.
    kick = np.zeros(n, dtype=np.float32)
    kick_positions = [0.1, 0.7, 1.3, 1.9]
    for posf in kick_positions:
        pos = int(posf * SR)
        t = np.arange(int(0.015 * SR)) / SR
        kick[pos : pos + len(t)] += (np.exp(-t * 200) * np.sin(2 * np.pi * 80 * t)).astype(np.float32)

    t_full = np.arange(n) / SR
    bed = 0.3 * np.sin(2 * np.pi * 1000 * t_full).astype(np.float32)
    gain = np.ones(n, dtype=np.float32)
    for posf in kick_positions:
        # Duck starts ~60ms after the kick, past onset-detection latency, so
        # the pre-onset baseline window reliably lands before any ducking.
        pos = int((posf + 0.06) * SR)
        dip_len = int(0.2 * SR)
        end = min(pos + dip_len, n)
        ramp_down = int(0.02 * SR)
        gain[pos : pos + ramp_down] = np.linspace(1.0, 0.15, ramp_down)
        gain[pos + ramp_down : end] = np.linspace(0.15, 1.0, end - pos - ramp_down)
    ducked = kick + bed * gain

    depth = _pump_depth(ducked, SR, cfg)
    assert depth > 3.0
