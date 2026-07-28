"""Alternative renderer: the WORLD vocoder, via the pyworld binding.

Phase 2a candidate — see ALIGN-PLAN.md §4. WORLD is **modified BSD**, the most
permissive of the candidates (no GPL question at all), and unlike the
phase-vocoder options it was designed specifically for high-quality analysis
and resynthesis of *voice* — it's the engine behind a number of singing
synthesizers.

It decomposes the signal into three streams:
    f0  — fundamental frequency contour
    sp  — spectral envelope (carries formants / vowel identity)
    ap  — aperiodicity (breath / noise component)
and resynthesizes from them. That decomposition is a very natural fit for this
project: time-warping means resampling the three streams along the time map,
and pitch-matching means scaling *only* f0 while leaving `sp` untouched — which
preserves formants by construction, rather than as a bolt-on correction.
"""

from __future__ import annotations

from typing import Callable, Optional

import numpy as np

from .align import TimeMap

FRAME_PERIOD_MS = 5.0


def render_aligned_world(
    dub_y: np.ndarray,
    sr: int,
    time_map: TimeMap,
    rho_fn: Optional[Callable[[float], float]] = None,
    f0_floor: float = 60.0,
    f0_ceil: float = 800.0,
    hybrid_unvoiced: bool = True,
    crossfade_ms: float = 15.0,
    bypass_below_cents: float = 0.0,
    frame_period_ms: float = FRAME_PERIOD_MS,
) -> np.ndarray:
    """Same contract as praatrender.render_aligned, backed by WORLD.

    hybrid_unvoiced: keep *real recorded* audio through unvoiced regions
    (breaths, consonants) instead of WORLD's resynthesis of them, crossfading
    at the boundaries. Blind listening put WORLD's only real weakness on
    breaths — which makes sense, since those are near-pure aperiodicity, the
    most parametric of WORLD's three streams. Pitch correction is meaningless
    where there's no pitch, so resynthesising those regions buys nothing and
    costs realism.

    bypass_below_cents: **defaults to 0 (off) — this was tried and rejected.**
    The idea was to also pass real audio through voiced frames needing only a
    tiny correction. Blind listening said it sounds clearly *worse*: WORLD's
    resynthesis and the raw recording have subtly different timbre, so
    switching between them mid-phrase produces audible fluttering seams. The
    unvoiced hybrid works because voiced/unvoiced is a natural perceptual
    boundary that masks the switch; a cents threshold crosses no such
    boundary. Kept as a parameter only to document the dead end.

    frame_period_ms: WORLD's analysis/synthesis hop. Smaller = finer temporal
    tracking at more CPU; 5 ms is WORLD's default.
    """
    import pyworld as pw

    x = np.asarray(dub_y, dtype=np.float64)

    f0, t = pw.harvest(x, sr, f0_floor=f0_floor, f0_ceil=f0_ceil,
                       frame_period=frame_period_ms)
    f0 = pw.stonemask(x, f0, t, sr)
    sp = pw.cheaptrick(x, f0, t, sr)
    ap = pw.d4c(x, f0, t, sr)

    # Output frame grid on the guide timeline; for each output frame, find
    # which source frame to draw from via the time map.
    frame_period_s = frame_period_ms / 1000.0
    out_times = np.arange(0.0, time_map.duration_s, frame_period_s)
    src_times = np.asarray([float(time_map(t_out)) for t_out in out_times])
    src_idx = np.clip(np.round(src_times / frame_period_s).astype(int),
                      0, len(f0) - 1)

    f0_out = f0[src_idx].copy()
    sp_out = sp[src_idx].copy()
    ap_out = ap[src_idx].copy()

    correction_cents = np.zeros(len(out_times))
    if rho_fn is not None:
        ratios = np.asarray([float(rho_fn(t_out)) for t_out in out_times])
        ratios = np.where(np.isfinite(ratios) & (ratios > 0), ratios, 1.0)
        correction_cents = np.abs(1200.0 * np.log2(ratios))
        # Scale f0 only — sp (the spectral envelope) is deliberately left
        # alone, which is what keeps formants put while the pitch moves.
        voiced = f0_out > 0
        f0_out[voiced] = f0_out[voiced] * ratios[voiced]

    y = pw.synthesize(np.ascontiguousarray(f0_out),
                      np.ascontiguousarray(sp_out),
                      np.ascontiguousarray(ap_out),
                      sr, frame_period=frame_period_ms)

    if hybrid_unvoiced:
        # Use WORLD only where it actually earns its keep: voiced *and*
        # actually being corrected by an audible amount.
        needs_world = f0_out > 0
        if bypass_below_cents > 0 and rho_fn is not None:
            needs_world = needs_world & (correction_cents >= bypass_below_cents)
        y = _blend_real_unvoiced(y, x, sr, time_map, out_times, src_times,
                                 voiced_frames=needs_world,
                                 crossfade_ms=crossfade_ms)

    # WORLD's resynthesis can come back hotter than the input and clip on
    # write (observed: peak pinned at exactly 1.0). Scale back if needed —
    # a pure gain change, so it costs nothing in quality.
    peak = float(np.max(np.abs(y))) if y.size else 0.0
    if peak > 0.98:
        y = y * (0.98 / peak)

    n_target = int(round(time_map.duration_s * sr))
    if len(y) >= n_target:
        y = y[:n_target]
    else:
        y = np.pad(y, (0, n_target - len(y)))
    return y.astype(np.float32)


def _resample_source_to_output(x: np.ndarray, sr: int, out_times: np.ndarray,
                               src_times: np.ndarray, n_out: int) -> np.ndarray:
    """Plain time-warped source: read `x` at the warped position for each
    output sample. Pitch rides along with the warp, which is fine here because
    this only ever gets used in unvoiced regions (no pitch to preserve) and
    the warp ratios involved are within a few percent of 1.0.
    """
    out_idx = np.arange(n_out) / sr
    src_at = np.interp(out_idx, out_times, src_times)
    src_pos = src_at * sr
    base = np.floor(src_pos).astype(int)
    frac = src_pos - base
    base = np.clip(base, 0, len(x) - 2)
    return (1.0 - frac) * x[base] + frac * x[base + 1]


def _blend_real_unvoiced(y_world: np.ndarray, x: np.ndarray, sr: int,
                         time_map: TimeMap, out_times: np.ndarray,
                         src_times: np.ndarray, voiced_frames: np.ndarray,
                         crossfade_ms: float) -> np.ndarray:
    """Crossfade real (time-warped) source audio into unvoiced regions."""
    n_out = len(y_world)
    y_real = _resample_source_to_output(x, sr, out_times, src_times, n_out)

    # Per-frame voicing -> per-sample mask (1 = use WORLD, 0 = use real audio).
    frame_times = out_times[:len(voiced_frames)]
    sample_times = np.arange(n_out) / sr
    mask = np.interp(sample_times, frame_times,
                     voiced_frames.astype(float),
                     left=float(voiced_frames[0]), right=float(voiced_frames[-1]))

    # Smooth the mask so transitions are crossfades, not hard switches.
    win = max(1, int(round(crossfade_ms / 1000.0 * sr)) | 1)
    kernel = np.ones(win) / win
    mask = np.convolve(np.pad(mask, (win // 2, win // 2), mode="edge"),
                       kernel, mode="valid")[:n_out]
    mask = np.clip(mask, 0.0, 1.0)

    return mask * y_world + (1.0 - mask) * y_real
