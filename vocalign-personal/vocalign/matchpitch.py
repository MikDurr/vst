"""Match Pitch: derive a pitch-ratio curve that pulls the dub's pitch toward
the guide's, on the guide's own timeline (i.e. *after* time alignment).
"""

from __future__ import annotations

from typing import Callable

import numpy as np


def _fold_to_nearest_octave(cents: np.ndarray) -> np.ndarray:
    """Fold an interval to (-600, 600] cents so an octave double/drop (or a
    deliberate harmony) isn't collapsed onto the guide's exact pitch."""
    out = np.asarray(cents, dtype=float).copy()
    out = np.mod(out + 600.0, 1200.0) - 600.0
    return out


def build_pitch_ratio_fn(
    guide_freq_hz: np.ndarray,
    guide_times: np.ndarray,
    dub_freq_hz: np.ndarray,
    dub_times: np.ndarray,
    tau_fn: Callable[[float], float],
    out_duration_s: float,
    strength: float = 1.0,
    nearest_octave: bool = True,
    smooth_s: float = 0.05,
    grid_dt: float = 0.01,
) -> Callable[[float], float]:
    """Build rho(t_out) = pitch ratio to apply at each output-timeline instant.

    strength: 0 = no correction (ratio 1.0 everywhere), 1 = fully snap dub's
              pitch onto the guide's, wherever both are confidently voiced.
    """
    grid = np.arange(0.0, out_duration_s, grid_dt)

    # np.interp doesn't propagate NaN across unvoiced gaps, so gate voicing
    # via nearest-frame lookup instead of interpolating frequency directly.
    guide_voiced = np.array([
        _nearest_finite(guide_freq_hz, guide_times, t) for t in grid
    ])

    dub_t_src = np.array([tau_fn(t) for t in grid])
    dub_voiced = np.array([
        _nearest_finite(dub_freq_hz, dub_times, t) for t in dub_t_src
    ])

    both_voiced = np.isfinite(guide_voiced) & np.isfinite(dub_voiced)

    shift_cents = np.zeros_like(grid)
    with np.errstate(divide="ignore", invalid="ignore"):
        interval = 1200.0 * np.log2(guide_voiced / dub_voiced)
    if nearest_octave:
        interval = _fold_to_nearest_octave(interval)
    shift_cents[both_voiced] = strength * interval[both_voiced]

    # Hold the last valid shift across unvoiced gaps instead of snapping to 0,
    # so a plosive or breath mid-word doesn't yank the pitch back and forth.
    shift_cents = _forward_fill(shift_cents, both_voiced)

    if smooth_s > 0:
        win = max(1, int(round(smooth_s / grid_dt)) | 1)
        kernel = np.ones(win) / win
        pad = win // 2
        padded = np.pad(shift_cents, (pad, pad), mode="edge")
        shift_cents = np.convolve(padded, kernel, mode="valid")

    ratio_grid = np.power(2.0, shift_cents / 1200.0)

    def rho_fn(t: float) -> float:
        return float(np.interp(t, grid, ratio_grid))

    return rho_fn


def _nearest_finite(freq_hz: np.ndarray, times: np.ndarray, t: float) -> float:
    idx = int(np.searchsorted(times, t))
    idx = min(max(idx, 0), len(times) - 1)
    return float(freq_hz[idx])


def _forward_fill(values: np.ndarray, valid_mask: np.ndarray) -> np.ndarray:
    out = values.copy()
    last = 0.0
    for i in range(len(out)):
        if valid_mask[i]:
            last = out[i]
        else:
            out[i] = last
    return out
