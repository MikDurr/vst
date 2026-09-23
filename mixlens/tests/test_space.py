"""Space features: dry burst + synthetic exponential tail. Recovers decay
within 10% (spec M3 exit criterion)."""
import numpy as np

from mixlens.dsp.segments import active_mask, find_phrase_ends
from mixlens.features.space import _fit_slope_db_per_s

from conftest import stereo

SR = 44100


def _burst_with_tail(sr: int, burst_dur: float, tail_dur: float, decay_db_per_s: float, gap_dur: float = 1.0) -> np.ndarray:
    """A loud tone, then silence, then an exponentially decaying tail at a known dB/s rate."""
    t_burst = np.arange(int(burst_dur * sr)) / sr
    burst = 0.5 * np.sin(2 * np.pi * 300 * t_burst)

    t_tail = np.arange(int(tail_dur * sr)) / sr
    amp_db = -decay_db_per_s * t_tail
    amp = 10 ** (amp_db / 20.0) * 0.5
    carrier = np.sin(2 * np.pi * 300 * t_tail)
    tail = amp * carrier

    gap = np.zeros(int(gap_dur * sr))
    return np.concatenate([burst, tail, gap]).astype(np.float32)


def test_phrase_end_detected_after_burst(cfg):
    active_lu = cfg.get("active_threshold_lu", 30.0)
    signal = _burst_with_tail(SR, 0.6, 0.4, decay_db_per_s=40.0)
    at_times, mask = active_mask(signal, SR, active_lu, hop_s=0.05)
    ends = find_phrase_ends(
        signal, SR, at_times, mask,
        drop_db=cfg.get("space.phrase_end_drop_db", 15.0),
        window_ms=cfg.get("space.phrase_end_window_ms", 100.0),
        active_min_ms=cfg.get("space.active_min_ms", 500.0),
    )
    assert len(ends) >= 1
    # Burst ends at 0.6s; at 40dB/s decay, a 15dB drop takes ~0.375s, so the
    # drop should register somewhere around 0.6-1.0s (into the tail/gap).
    assert 0.6 < ends[0] < 1.05


def test_decay_slope_recovers_known_rate_within_10_percent():
    decay_rate = 60.0  # dB/s
    tail_dur = 0.3
    t_tail = np.arange(int(tail_dur * SR)) / SR
    amp_db = -decay_rate * t_tail
    slope = _fit_slope_db_per_s(t_tail, amp_db)
    assert slope is not None
    assert abs(slope - (-decay_rate)) < 0.1 * decay_rate
