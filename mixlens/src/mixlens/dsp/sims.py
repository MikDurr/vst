"""Translation simulations: phone (bandlimited mono) and mono fold-down."""
from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfiltfilt


def mono_fold(audio: np.ndarray) -> np.ndarray:
    """L+R fold-down to a single channel, shape (samples,)."""
    if audio.ndim == 1:
        return audio
    return audio.mean(axis=0)


def phone_sim(audio: np.ndarray, sr: int, hp_hz: float, lp_hz: float, order: int) -> np.ndarray:
    """4th-order Butterworth HP + LP, mono sum -- simulates phone-speaker playback."""
    mono = mono_fold(audio)
    sos_hp = butter(order, hp_hz, btype="highpass", fs=sr, output="sos")
    sos_lp = butter(order, lp_hz, btype="lowpass", fs=sr, output="sos")
    y = sosfiltfilt(sos_hp, mono)
    y = sosfiltfilt(sos_lp, y)
    return y.astype(np.float32)
