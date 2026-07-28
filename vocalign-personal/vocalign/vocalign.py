"""Align a dub take onto a guide take, optionally matching its pitch too.
Two audio files in, one wav out.

Renderer default is **praat**, chosen by blind listening at 44.1 kHz. It was
briefly ruled out while the project was targeting an AU plugin (Praat can't be
embedded), but the delivery form is now a standalone app (ALIGN-PLAN.md §8),
so the embedding constraint is gone. `world` remains the best *embeddable*
option if that ever changes back.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from .align import DEFAULT_HOP, TimeMap, compute_time_map
from .audio import DEFAULT_SR, load_audio, load_audio_multichannel
from .matchpitch import build_pitch_ratio_fn
from .pitch import DEFAULT_FMAX_NOTE, DEFAULT_FMIN_NOTE, extract_pitch_from_samples
from .praatrender import estimate_pitch_range, render_aligned


@dataclass
class AlignResult:
    out_path: Path
    duration_s: float
    mean_abs_shift_ms: float
    pitch_matched: bool
    renderer: str = "praat"
    n_channels: int = 1


# Phase 2a: swappable renderers, identical pipeline either side of them, so an
# A/B is purely a rendering-quality comparison. See ALIGN-PLAN.md §4.
RENDERERS = ("praat", "rubberband", "signalsmith", "world")


def align_takes(
    guide_path: str | Path,
    dub_path: str | Path,
    out_path: str | Path,
    sr: int = DEFAULT_SR,
    tightness: float = 0.8,
    max_shift_s: float = 0.2,
    pitch_strength: float = 0.0,
    nearest_octave: bool = True,
    fmin_note: str = DEFAULT_FMIN_NOTE,
    fmax_note: str = DEFAULT_FMAX_NOTE,
    renderer: str = "praat",
    render_sr: int = 44100,
) -> AlignResult:
    """Render `dub_path`, time-aligned onto `guide_path`'s timeline (and,
    if pitch_strength > 0, pitch-matched to it too), to `out_path`.

    Two sample rates on purpose:
      `sr`        — analysis rate (time map, pitch curves). 22.05k is plenty;
                    pitch and alignment live well below 11 kHz, and this is
                    the slow half of the pipeline.
      `render_sr` — output rate. Must be full-bandwidth: everything above
                    sr/2 is *gone* from the rendered audio otherwise, which
                    strips the air off a vocal and reads as dull/robotic.

    The analysis products are sample-rate independent (TimeMap is in seconds,
    rho_fn takes seconds), so they transfer to the render rate for free.
    """
    import soundfile as sf

    guide_y, sr = load_audio(guide_path, sr=sr)
    dub_y, _ = load_audio(dub_path, sr=sr)

    time_map = compute_time_map(
        guide_y, dub_y, sr,
        hop_length=DEFAULT_HOP, max_shift_s=max_shift_s, tightness=tightness,
    )

    dub_curve = extract_pitch_from_samples(
        dub_y, sr, source=str(dub_path), fmin_note=fmin_note, fmax_note=fmax_note,
    )
    dub_f0 = dub_curve.freq_array
    dub_times = np.asarray(dub_curve.times, dtype=float)

    guide_curve = extract_pitch_from_samples(
        guide_y, sr, source=str(guide_path), fmin_note=fmin_note, fmax_note=fmax_note,
    )

    # Narrow Praat's pitch floor/ceiling to what this take actually contains,
    # rather than one generic wide range for every voice — see
    # praatrender.estimate_pitch_range for why that matters.
    pitch_floor, pitch_ceiling = estimate_pitch_range(dub_f0, guide_curve.freq_array)

    rho_fn = None
    pitch_matched = pitch_strength > 0.0
    if pitch_matched:
        rho_fn = build_pitch_ratio_fn(
            guide_freq_hz=guide_curve.freq_array,
            guide_times=np.asarray(guide_curve.times, dtype=float),
            dub_freq_hz=dub_f0,
            dub_times=dub_times,
            tau_fn=time_map,
            out_duration_s=time_map.duration_s,
            strength=pitch_strength,
            nearest_octave=nearest_octave,
        )

    if renderer not in RENDERERS:
        raise ValueError(f"Unknown renderer {renderer!r}; expected one of {RENDERERS}")

    # Reload the dub at full bandwidth for rendering, preserving its channel
    # layout. Analysis above ran on a mono sum (pitch and alignment are
    # inherently mono concepts); rendering must not be mono, or a stereo take
    # loses its width/panning on the way through.
    dub_render_y, r_sr = load_audio_multichannel(dub_path, sr=render_sr)

    def _render_channel(ch: np.ndarray) -> np.ndarray:
        if renderer == "praat":
            return render_aligned(ch, r_sr, time_map, rho_fn=rho_fn,
                                  pitch_floor=pitch_floor, pitch_ceiling=pitch_ceiling)
        if renderer == "rubberband":
            from .rbrender import render_aligned_rb
            return render_aligned_rb(ch, r_sr, time_map, rho_fn=rho_fn)
        if renderer == "signalsmith":
            from .ssrender import render_aligned_ss
            return render_aligned_ss(ch, r_sr, time_map, rho_fn=rho_fn)
        from .worldrender import render_aligned_world
        return render_aligned_world(ch, r_sr, time_map, rho_fn=rho_fn)

    if dub_render_y.ndim == 1:
        out_audio = _render_channel(dub_render_y)
        n_channels = 1
    else:
        # Same time_map and rho_fn for every channel, so they stay in sync.
        rendered = [_render_channel(dub_render_y[c]) for c in range(dub_render_y.shape[0])]
        n = min(len(r) for r in rendered)
        out_audio = np.stack([r[:n] for r in rendered], axis=-1)  # (samples, channels)
        n_channels = dub_render_y.shape[0]

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out_path), out_audio, r_sr)

    return AlignResult(
        out_path=out_path,
        duration_s=time_map.duration_s,
        mean_abs_shift_ms=time_map.mean_abs_shift_ms(),
        pitch_matched=pitch_matched,
        renderer=renderer,
        n_channels=n_channels,
    )
