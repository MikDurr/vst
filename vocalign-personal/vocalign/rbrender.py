"""Alternative renderer: Rubber Band Library, via its CLI's time/pitch maps.

Phase 2a candidate — see ALIGN-PLAN.md §4. Praat (praatrender.py) is the
current quality baseline but can't be embedded in a plugin; this is one of the
embeddable alternatives being A/B'd against it.

Rubber Band exposes exactly the two time-varying controls this pipeline needs:
  --timemap  <source_sample> <target_sample>   per line
  --pitchmap <source_sample> <semitones>       per line
which map cleanly onto our TimeMap and pitch-ratio function respectively.

Licence note: Rubber Band is GPL, or paid commercial for proprietary
distribution. Personal, non-distributed use never triggers GPL obligations,
so GPL is fine for this project's stated scope.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from .align import TimeMap


def render_aligned_rb(
    dub_y: np.ndarray,
    sr: int,
    time_map: TimeMap,
    rho_fn: Optional[Callable[[float], float]] = None,
    map_dt: float = 0.05,
    crispness: int = 5,
    formant_preserve: bool = True,
) -> np.ndarray:
    """Same contract as praatrender.render_aligned, backed by Rubber Band.

    map_dt: spacing of time/pitch map points. Kept coarse for the same reason
    the Praat duration tier is coarse — real drift between two takes changes
    over syllables, not milliseconds, and a jittery map is what produces
    "gargle" artifacts.
    """
    import soundfile as sf

    with tempfile.TemporaryDirectory(prefix="vpa_rb_") as tmp:
        tmp = Path(tmp)
        in_wav, out_wav = tmp / "in.wav", tmp / "out.wav"
        sf.write(str(in_wav), np.asarray(dub_y, dtype=np.float32), sr)

        dub_duration = len(dub_y) / sr
        grid_dub = np.arange(0.0, dub_duration, map_dt)
        guide_at = time_map.inverse(grid_dub)  # dub_time -> guide_time

        timemap_path = tmp / "timemap.txt"
        with open(timemap_path, "w") as f:
            for t_dub, t_guide in zip(grid_dub, guide_at):
                f.write(f"{int(round(t_dub * sr))} {int(round(t_guide * sr))}\n")

        # -D is REQUIRED alongside -M: "When supplying a time map you must
        # specify an overall stretch factor using -t, -T, or -D as well, to
        # determine the total output duration." Without it the timemap is
        # silently ignored and the output comes back unaligned.
        # -3 selects the R3 ("finer") engine — substantially higher quality
        # than the default R2, and worth the extra CPU here since rendering is
        # offline anyway.
        cmd = ["rubberband", "-3", "-M", str(timemap_path),
               "-D", f"{time_map.duration_s:.6f}", f"-c{crispness}"]
        if formant_preserve:
            cmd.append("-F")

        if rho_fn is not None:
            pitchmap_path = tmp / "pitchmap.txt"
            with open(pitchmap_path, "w") as f:
                for t_dub in grid_dub:
                    t_guide = float(time_map.inverse(t_dub))
                    ratio = rho_fn(t_guide)
                    ratio = ratio if np.isfinite(ratio) and ratio > 0 else 1.0
                    semitones = 12.0 * np.log2(ratio)
                    f.write(f"{int(round(t_dub * sr))} {semitones:.4f}\n")
            cmd += ["--pitchmap", str(pitchmap_path)]

        cmd += [str(in_wav), str(out_wav)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0 or not out_wav.exists():
            raise RuntimeError(
                f"rubberband failed (exit {proc.returncode}):\n{proc.stderr[-2000:]}"
            )

        y, _ = sf.read(str(out_wav), dtype="float32")
        if y.ndim > 1:
            y = y.mean(axis=1)

    n_target = int(round(time_map.duration_s * sr))
    if len(y) >= n_target:
        y = y[:n_target]
    else:
        y = np.pad(y, (0, n_target - len(y)))
    return y.astype(np.float32)
