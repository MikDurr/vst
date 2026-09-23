"""CSI: clicks over noise at known SNRs -- a loud click should survive, a
buried one shouldn't."""
import numpy as np
from scipy.signal import butter, sosfiltfilt

from mixlens.features.masking import compute_csi

from conftest import stereo

SR = 44100


def _click_train(n_clicks: int, click_amp: float, sr: int, duration: float, seed: int = 0) -> np.ndarray:
    """Broadband 2-6kHz noise bursts, like real consonants -- a pure tone would
    only ever occupy one ERB band and can't meaningfully test band survival."""
    rng = np.random.default_rng(seed)
    n = int(duration * sr)
    signal = np.zeros(n, dtype=np.float32)
    positions = np.linspace(0.1 * sr, n - 0.1 * sr, n_clicks).astype(int)
    click_len = int(0.01 * sr)
    sos = butter(4, [2000, 6000], btype="bandpass", fs=sr, output="sos")
    for i, pos in enumerate(positions):
        raw = rng.standard_normal(click_len).astype(np.float32)
        burst = sosfiltfilt(sos, raw) * np.hanning(click_len)
        burst = burst / (np.max(np.abs(burst)) + 1e-9) * click_amp
        signal[pos : pos + click_len] += burst.astype(np.float32)
    return signal


def _noise(sr: int, duration: float, amp: float, seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return (amp * rng.standard_normal(int(duration * sr))).astype(np.float32)


def test_csi_high_when_vocal_clearly_above_masker(cfg):
    vocal = stereo(_click_train(8, 0.8, SR, 2.0))
    inst = stereo(_noise(SR, 2.0, 0.02))
    csi, csi_p10, scores = compute_csi(vocal, inst, SR, cfg)
    assert csi > 0.5
    assert len(scores) > 0


def test_csi_low_when_vocal_buried(cfg):
    vocal = stereo(_click_train(8, 0.05, SR, 2.0))
    inst = stereo(_noise(SR, 2.0, 0.4))
    csi, csi_p10, scores = compute_csi(vocal, inst, SR, cfg)
    assert csi < 0.5


def test_csi_decreases_as_masker_grows(cfg):
    vocal = stereo(_click_train(8, 0.3, SR, 2.0))
    quiet_inst = stereo(_noise(SR, 2.0, 0.01))
    loud_inst = stereo(_noise(SR, 2.0, 0.3))
    csi_quiet, _p1, _s1 = compute_csi(vocal, quiet_inst, SR, cfg)
    csi_loud, _p2, _s2 = compute_csi(vocal, loud_inst, SR, cfg)
    assert csi_quiet >= csi_loud
