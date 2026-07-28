"""Alternative renderer: Signalsmith Stretch, via the python-stretch binding.

Phase 2a candidate — see ALIGN-PLAN.md §4. MIT-licensed and header-only C++11,
so it is by far the easiest of the candidates to embed in a plugin later; the
open question is purely whether it sounds good enough on voice, since it is a
phase-vocoder-family algorithm rather than PSOLA.

Unlike Praat and Rubber Band it has no "map" concept — it's a streaming
processor whose time/pitch factors are set as you go. So time-varying
modification is done by chunking the source and setting the factors per chunk.
"""

from __future__ import annotations

from typing import Callable, Optional

import numpy as np

from .align import TimeMap


def render_aligned_ss(
    dub_y: np.ndarray,
    sr: int,
    time_map: TimeMap,
    rho_fn: Optional[Callable[[float], float]] = None,
    chunk_s: float = 0.05,
) -> np.ndarray:
    """Same contract as praatrender.render_aligned, backed by Signalsmith.

    chunk_s: how often the time/pitch factors are updated. Same reasoning as
    the other renderers' map spacing — coarse enough that the factors don't
    jitter, fine enough to track real drift.
    """
    import python_stretch as ps

    dub_y = np.asarray(dub_y, dtype=np.float32)
    dub_duration = len(dub_y) / sr

    stretch = ps.Signalsmith.Stretch()
    stretch.preset(1, float(sr))
    stretch.reset()

    grid_dub = np.arange(0.0, dub_duration, chunk_s)
    out_chunks = []

    for i, t_dub in enumerate(grid_dub):
        start = int(round(t_dub * sr))
        end = int(round(min(t_dub + chunk_s, dub_duration) * sr))
        if end <= start:
            continue
        chunk = dub_y[start:end]

        # Local stretch factor: how much guide-time this slice of dub-time
        # should occupy. Rubber Band/Praat get this from a map; here we
        # compute it per chunk and hand it to the streaming processor.
        t_dub_end = min(t_dub + chunk_s, dub_duration)
        g0 = float(time_map.inverse(t_dub))
        g1 = float(time_map.inverse(t_dub_end))
        span_dub = max(t_dub_end - t_dub, 1e-6)
        time_factor = float(np.clip((g1 - g0) / span_dub, 0.5, 2.0))
        stretch.setTimeFactor(1.0 / time_factor)  # binding: >1 = faster

        if rho_fn is not None:
            ratio = rho_fn(g0)
            ratio = ratio if np.isfinite(ratio) and ratio > 0 else 1.0
            stretch.setTransposeSemitones(float(12.0 * np.log2(ratio)))

        block = chunk.reshape(1, -1)
        out = stretch.process(block)
        if out.size:
            out_chunks.append(out[0].copy())

    y = np.concatenate(out_chunks) if out_chunks else np.zeros(1, dtype=np.float32)

    n_target = int(round(time_map.duration_s * sr))
    if len(y) >= n_target:
        y = y[:n_target]
    else:
        y = np.pad(y, (0, n_target - len(y)))
    return y.astype(np.float32)
