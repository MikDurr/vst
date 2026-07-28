"""Render a time-aligned (and optionally pitch-matched) dub using Praat's
PSOLA engine via parselmouth.

An earlier from-scratch PSOLA renderer (no true glottal-pulse epoch
detection) produced audible artifacts (robotic/phasey texture) on real
singing, confirmed by ear. Praat's PSOLA is a decades-refined reference
implementation built for exactly this (pitch/duration manipulation of real
voice recordings) — reuse it rather than re-deriving epoch detection from
scratch.
"""

from __future__ import annotations

from typing import Callable, Optional

import numpy as np

from .align import TimeMap

DEFAULT_PITCH_FLOOR = 55.0    # ~A1
DEFAULT_PITCH_CEILING = 800.0  # generous headroom above C5 for belts/falsetto


def estimate_pitch_range(*freq_arrays: np.ndarray,
                         floor_bounds=(40.0, 300.0),
                         ceiling_bounds=(300.0, 1000.0)) -> tuple[float, float]:
    """A floor/ceiling narrow enough to avoid octave errors, wide enough to
    cover this take. Generic wide defaults (e.g. 55-800Hz for every voice)
    give Praat's own pitch tracker more room to grab a subharmonic or
    overtone by mistake — which shows up as isolated wobble/glitches once
    that wrong-octave point gets locked to a pitch-matched target. Percentiles
    (not min/max) so a stray unvoiced/noise frame pinned to the analysis
    floor doesn't blow the range out.
    """
    all_valid = np.concatenate([
        a[np.isfinite(a) & (a > 0)] for a in freq_arrays if a is not None and len(a)
    ]) if freq_arrays else np.array([])

    if all_valid.size < 10:
        return DEFAULT_PITCH_FLOOR, DEFAULT_PITCH_CEILING

    p5, p95 = np.percentile(all_valid, [5, 95])
    floor = float(np.clip(p5 / 1.2, *floor_bounds))
    ceiling = float(np.clip(p95 * 1.5, *ceiling_bounds))
    return floor, ceiling


def render_aligned(
    dub_y: np.ndarray,
    sr: int,
    time_map: TimeMap,
    rho_fn: Optional[Callable[[float], float]] = None,
    pitch_floor: float = DEFAULT_PITCH_FLOOR,
    pitch_ceiling: float = DEFAULT_PITCH_CEILING,
    duration_grid_dt: float = 0.01,
) -> np.ndarray:
    """Time-align `dub_y` onto `time_map`'s guide timeline, optionally
    pitch-matching it too (if `rho_fn` is given), via Praat's PSOLA.

    rho_fn(t_guide) -> pitch ratio to apply at guide-timeline instant t_guide
    (as produced by matchpitch.build_pitch_ratio_fn). None = timing only.
    """
    import parselmouth
    from parselmouth.praat import call

    snd = parselmouth.Sound(np.asarray(dub_y, dtype=np.float64), sampling_frequency=sr)
    manip = call(snd, "To Manipulation", 0.01, pitch_floor, pitch_ceiling)

    dur_tier = call(manip, "Extract duration tier")
    _fill_duration_tier(dur_tier, time_map, dub_duration_s=snd.duration,
                        grid_dt=duration_grid_dt)
    call([manip, dur_tier], "Replace duration tier")

    if rho_fn is not None:
        pitch_tier = call(manip, "Extract pitch tier")
        _scale_pitch_tier(pitch_tier, rho_fn, time_map)
        call([manip, pitch_tier], "Replace pitch tier")

    resynth = call(manip, "Get resynthesis (overlap-add)")
    y = resynth.values[0].astype(np.float32)

    # Trim/pad to exactly the guide's duration (duration-tier resynthesis
    # lands close but not bit-exact).
    n_target = int(round(time_map.duration_s * sr))
    if len(y) >= n_target:
        y = y[:n_target]
    else:
        y = np.pad(y, (0, n_target - len(y)))
    return y


def _fill_duration_tier(dur_tier, time_map: TimeMap, dub_duration_s: float,
                        grid_dt: float,
                        deriv_baseline_s: float = 0.15,
                        smooth_s: float = 0.20,
                        point_spacing_s: float = 0.05) -> None:
    """Add (source_time, ratio) points: ratio = d(guide_time)/d(dub_time),
    i.e. "how many guide-seconds this instant of dub-source should become" —
    exactly Praat's DurationTier convention (>1 = play slower/longer).

    The ratio curve is deliberately smooth and sparse: real tempo drift
    between two vocal takes changes slowly (over syllables/phrases, not
    milliseconds), so a fine-grained, noisy derivative here just makes the
    engine constantly speed up and slow down in tiny bursts — the classic
    PSOLA "gargle" artifact. A wide-baseline derivative, a further smoothing
    pass, and sparse points (Praat linearly interpolates between them) all
    push in the same direction: no fast wobble in the stretch amount.
    """
    from parselmouth.praat import call

    grid = np.arange(0.0, dub_duration_s, grid_dt)
    guide_at = time_map.inverse(grid)   # dub_time -> guide_time, monotone

    # Wide-baseline central difference instead of adjacent-sample gradient —
    # far less sensitive to sub-sample jitter in the underlying warp curve.
    half = max(1, int(round(deriv_baseline_s / grid_dt / 2)))
    padded = np.pad(guide_at, (half, half), mode="edge")
    ratio = (padded[2 * half:] - padded[:-2 * half]) / (2 * half * grid_dt)

    # Smooth again, then clip to a sensible range for a personal vocal take
    # (no legitimate double-track needs a >2x local stretch; clipping tighter
    # also kills any residual noise spikes).
    win = max(1, int(round(smooth_s / grid_dt)) | 1)
    kernel = np.ones(win) / win
    ratio = np.convolve(np.pad(ratio, (win // 2, win // 2), mode="edge"),
                        kernel, mode="valid")
    ratio = np.clip(ratio, 0.5, 2.0)

    # Sparse points: Praat interpolates linearly between them, which itself
    # bounds how fast the stretch amount can change.
    step = max(1, int(round(point_spacing_s / grid_dt)))
    sparse_t = grid[::step]
    sparse_r = ratio[::step]

    call(dur_tier, "Add point", 1e-6, float(sparse_r[0]))
    for t, r in zip(sparse_t, sparse_r):
        call(dur_tier, "Add point", float(max(t, 1e-6)), float(r))
    call(dur_tier, "Add point", dub_duration_s, float(sparse_r[-1]))


def _scale_pitch_tier(pitch_tier, rho_fn: Callable[[float], float], time_map: TimeMap,
                      median_window_points: int = 3) -> None:
    """Multiply each existing pitch-tier point's frequency by rho_fn evaluated
    at the *output* (guide) time that source instant maps to.

    Praat's own frame-to-frame F0 estimate has some natural jitter and the
    occasional octave-error blip, same as any pitch tracker. Median-filtering
    the raw values first (before scaling) removes those isolated errors and
    quiets the fine jitter that otherwise reads as a "wobbly"/robotic texture
    once it's locked to a target — without flattening real, slower vibrato.
    """
    from parselmouth.praat import call
    from scipy.ndimage import median_filter

    n = int(call(pitch_tier, "Get number of points"))
    times, freqs = [], []
    for i in range(1, n + 1):
        times.append(call(pitch_tier, "Get time from index", i))
        freqs.append(call(pitch_tier, "Get value at index", i))

    call(pitch_tier, "Remove points between", -1.0, max(times, default=0.0) + 1.0)
    if not freqs:
        return

    freqs = median_filter(np.asarray(freqs, dtype=float), size=median_window_points,
                          mode="nearest")

    for t_dub, f_hz in zip(times, freqs):
        t_guide = float(time_map.inverse(t_dub))
        ratio = rho_fn(t_guide)
        ratio = ratio if np.isfinite(ratio) and ratio > 0 else 1.0
        call(pitch_tier, "Add point", t_dub, float(f_hz) * ratio)
