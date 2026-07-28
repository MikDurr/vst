"""The Quick engine: 2-stem separation with no model and no torch.

REPET-SIM foreground/background separation, ported from the vocal-pitch-analyzer
`isolate_vocals_samples` helper it grew out of. The accompaniment in most songs
repeats; the lead vocal doesn't. So a nearest-neighbour median filter over
similar STFT frames estimates the *background*, and the vocal is what's left.

It is not close to Demucs and isn't meant to be — it exists so the app does
something useful in the seconds before a model has downloaded, and on machines
where a 2 GB torch install isn't wanted. Expect audible burble on the vocal and
vocal bleed in the instrumental: fine as a guide track, not a release stem.

Two things differ from the analyser version it came from, both because this
writes files someone will drop into a DAW rather than a mono buffer for pitch
tracking: it works at the file's own sample rate, and it preserves the stereo
image by deriving one mask from the mono sum and applying it to each channel.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

ProgressFn = Callable[[float, str], None]

# Long enough to span a bar or two at most tempos, so the "similar frames" a
# median is taken over are genuinely different repetitions rather than
# neighbours inside the same note.
_SIM_WINDOW_S = 2.0
# Softmask exponent and margin. margin>1 biases each mask toward its own
# source; 10 on the background side is deliberately lopsided, because leaving
# accompaniment out of the vocal matters more here than the reverse.
_MARGIN_BG = 10
_POWER = 2

# The mask is *analysed* on a coarser time grid than it is *applied* on.
#
# nn_filter is the whole cost of this engine — it compares every frame to every
# other, so it grows with the square of the frame count. On a 3:20 track at
# hop 512 that is 19k frames and 72 seconds of the ~115 second run. Halving the
# analysis hop rate cuts it to 25s.
#
# What it costs: measured against a full-resolution run of the same track, the
# resulting vocal differs by ~12 dB down on the signal — audible if you A/B
# closely, immaterial for what this engine is for. The frequency axis is
# untouched, which is the part that would actually matter; a REPET-SIM mask
# tracks repetition over seconds, so it is smooth in time by construction and
# interpolates back up cleanly. Set _ANALYSIS_HOP = _RENDER_HOP to opt out.
_RENDER_HOP = 512
_ANALYSIS_HOP = 1024


class QuickError(RuntimeError):
    """The Quick engine could not process this input."""


def _stretch_time(mask: np.ndarray, n_frames: int) -> np.ndarray:
    """Resample a mask along time onto an `n_frames` grid.

    Linear rather than nearest-neighbour: a nearest resample would step the
    mask in blocks, and a mask that changes discontinuously between adjacent
    STFT frames is exactly what produces musical-noise burble.
    """
    if mask.shape[1] == n_frames:
        return mask
    src = np.linspace(0.0, 1.0, mask.shape[1])
    dst = np.linspace(0.0, 1.0, n_frames)
    out = np.empty((mask.shape[0], n_frames), dtype=np.float32)
    for k in range(mask.shape[0]):
        out[k] = np.interp(dst, src, mask[k])
    return out


@dataclass(frozen=True)
class QuickResult:
    vocals: Path
    accompaniment: Path
    sr: int
    elapsed_s: float


def separate_quick(
    input_path: Path,
    out_dir: Path,
    *,
    progress: ProgressFn | None = None,
) -> QuickResult:
    """Split into vocals + accompaniment, written as WAVs into `out_dir`."""
    import librosa      # deferred: ~1.5s of import cost, only paid on demand
    import soundfile as sf

    started = time.monotonic()
    input_path = Path(input_path).expanduser()
    if not input_path.exists():
        raise QuickError(f"Input file not found: {input_path}")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if progress:
        progress(0.05, "Loading audio…")
    # sr=None keeps the file's own rate — resampling a stem that's going back
    # into a session would force the DAW to resample it right back.
    y, sr = librosa.load(str(input_path), sr=None, mono=False)
    y = np.atleast_2d(np.asarray(y, dtype=np.float32))

    mono = y.mean(axis=0)
    if progress:
        progress(0.15, "Analysing repetition…")

    mag = np.abs(librosa.stft(mono, hop_length=_ANALYSIS_HOP))
    n_frames = mag.shape[1]
    if n_frames < 6:
        raise QuickError(
            "Clip is too short to separate — REPET-SIM needs a few seconds of "
            "audio to find repetition."
        )

    # nn_filter requires width < (n_frames - 1) // 2 and an odd width; clamp for
    # short clips rather than failing on them.
    width = min(
        int(librosa.time_to_frames(_SIM_WINDOW_S, sr=sr, hop_length=_ANALYSIS_HOP)),
        (n_frames - 3) // 2,
    )
    width = max(1, width | 1)

    S_bg = librosa.decompose.nn_filter(mag, aggregate=np.median, metric="cosine", width=width)
    S_bg = np.minimum(mag, S_bg)
    if progress:
        progress(0.55, "Building masks…")

    mask_coarse = librosa.util.softmask(mag - S_bg, _MARGIN_BG * S_bg, power=_POWER)

    # One mask, applied per channel: masking each channel independently would
    # let the two sides diverge and smear the stereo image.
    mask_v: np.ndarray | None = None
    voc_ch, acc_ch = [], []
    for ci, ch in enumerate(y):
        S = librosa.stft(ch, hop_length=_RENDER_HOP)
        if mask_v is None:
            mask_v = _stretch_time(mask_coarse, S.shape[1])
        n = min(S.shape[1], mask_v.shape[1])
        voc_ch.append(
            librosa.istft(S[:, :n] * mask_v[:, :n], hop_length=_RENDER_HOP, length=ch.shape[0])
        )
        acc_ch.append(
            librosa.istft(
                S[:, :n] * (1.0 - mask_v[:, :n]), hop_length=_RENDER_HOP, length=ch.shape[0]
            )
        )
        if progress:
            progress(0.55 + 0.35 * (ci + 1) / len(y), "Rendering stems…")

    vocals = np.stack(voc_ch).T.squeeze()
    accomp = np.stack(acc_ch).T.squeeze()

    voc_path = out_dir / "vocals.wav"
    acc_path = out_dir / "no_vocals.wav"
    sf.write(voc_path, vocals, sr, subtype="FLOAT")
    sf.write(acc_path, accomp, sr, subtype="FLOAT")
    if progress:
        progress(1.0, "Done")

    return QuickResult(
        vocals=voc_path,
        accompaniment=acc_path,
        sr=sr,
        elapsed_s=time.monotonic() - started,
    )
