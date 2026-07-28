"""Time alignment: DTW warp path between a guide and a dub vocal take.

Produces a monotone map g(t_guide) -> t_dub telling the renderer which
source-audio instant to play at each point on the guide's timeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

from .audio import DEFAULT_SR

DEFAULT_HOP = 256
DEFAULT_N_MELS = 40


@dataclass
class TimeMap:
    """A monotone guide-time -> dub-time mapping, plus the raw warp path for
    diagnostics/plotting."""

    guide_times: np.ndarray     # (n,) seconds, strictly increasing
    dub_times: np.ndarray       # (n,) seconds, matched 1:1 with guide_times
    path_guide_s: np.ndarray    # raw DTW path, guide side (seconds)
    path_dub_s: np.ndarray      # raw DTW path, dub side (seconds)

    def __call__(self, t: np.ndarray | float) -> np.ndarray | float:
        """g(t_guide) -> t_dub, linearly interpolated; clamped at the ends."""
        return np.interp(t, self.guide_times, self.dub_times)

    def inverse(self, t: np.ndarray | float) -> np.ndarray | float:
        """g^-1(t_dub) -> t_guide. Valid because g is enforced monotone."""
        return np.interp(t, self.dub_times, self.guide_times)

    @property
    def duration_s(self) -> float:
        return float(self.guide_times[-1])

    def mean_abs_shift_ms(self) -> float:
        """How far, on average, the raw DTW path sits from perfect sync —
        a quick numeric proxy for "how out of time was the dub" and "how
        much did we move it"."""
        return float(np.mean(np.abs(self.path_dub_s - self.path_guide_s)) * 1000.0)


def extract_features(
    y: np.ndarray,
    sr: int,
    hop_length: int = DEFAULT_HOP,
    n_mels: int = DEFAULT_N_MELS,
) -> np.ndarray:
    """Per-frame features for DTW: normalized log-mel + a delta-energy band.

    Each mel band is z-scored across time (so level differences between the
    guide and dub takes don't drive the alignment path), and a delta-energy
    row is appended since the ear (and DTW) mostly cares about onsets.
    """
    import librosa

    y = np.asarray(y, dtype=float)
    S = librosa.feature.melspectrogram(
        y=y, sr=sr, hop_length=hop_length, n_fft=1024, n_mels=n_mels, power=2.0,
    )
    log_s = np.log1p(S)

    mean = log_s.mean(axis=1, keepdims=True)
    std = log_s.std(axis=1, keepdims=True) + 1e-6
    feat = (log_s - mean) / std

    energy = log_s.sum(axis=0)
    delta_energy = np.diff(energy, prepend=energy[0])
    delta_energy = (delta_energy - delta_energy.mean()) / (delta_energy.std() + 1e-6)

    return np.vstack([feat, delta_energy[np.newaxis, :]])


def _dtw_path(
    feat_guide: np.ndarray,
    feat_dub: np.ndarray,
    hop_length: int,
    sr: int,
    max_shift_s: float,
) -> np.ndarray:
    """Banded DTW between two feature matrices (d, n). Returns the warp path
    as an (n_steps, 2) array of (guide_frame, dub_frame), start-to-end order.
    """
    import librosa

    n_guide, n_dub = feat_guide.shape[1], feat_dub.shape[1]
    hop_dt = hop_length / sr
    band_frames = max(1, int(round(max_shift_s / hop_dt)))
    band_rad = band_frames / max(n_guide, n_dub)

    _, wp = librosa.sequence.dtw(
        X=feat_guide, Y=feat_dub, metric="cosine",
        global_constraints=True, band_rad=band_rad,
        backtrack=True,
    )
    return wp[::-1]  # librosa returns end-to-start; flip to start-to-end


def compute_time_map(
    guide_y: np.ndarray,
    dub_y: np.ndarray,
    sr: int,
    hop_length: int = DEFAULT_HOP,
    max_shift_s: float = 0.2,
    tightness: float = 0.8,
    smooth_s: float = 0.06,
) -> TimeMap:
    """Align `dub_y` onto `guide_y`'s timeline.

    tightness: 0 = don't move anything (identity map, dub plays as recorded),
               1 = follow the raw DTW path exactly. Values in between blend
               toward identity and are also hard-clamped to `max_shift_s`.
    """
    feat_guide = extract_features(guide_y, sr, hop_length)
    feat_dub = extract_features(dub_y, sr, hop_length)

    wp = _dtw_path(feat_guide, feat_dub, hop_length, sr, max_shift_s)

    hop_dt = hop_length / sr
    path_guide_s = wp[:, 0] * hop_dt
    path_dub_s = wp[:, 1] * hop_dt

    # Collapse to one dub-time per guide-frame (DTW paths can have repeats on
    # either axis) by averaging dub time for each guide frame, then resample
    # onto a uniform guide-time grid covering the full guide duration.
    guide_frame_idx = wp[:, 0]
    uniq_frames, first_pos = np.unique(guide_frame_idx, return_index=True)
    dub_per_guide_frame = np.array([
        path_dub_s[guide_frame_idx == f].mean() for f in uniq_frames
    ])
    guide_t_uniq = uniq_frames * hop_dt

    guide_duration = (feat_guide.shape[1]) * hop_dt
    dub_duration = (feat_dub.shape[1]) * hop_dt

    grid = np.arange(0.0, guide_duration, hop_dt)
    raw_map = np.interp(grid, guide_t_uniq, dub_per_guide_frame,
                        left=dub_per_guide_frame[0], right=dub_per_guide_frame[-1])

    # Smooth (median-ish via convolution) to remove per-frame DTW jitter.
    if smooth_s > 0:
        win = max(1, int(round(smooth_s / hop_dt)) | 1)  # odd
        kernel = np.ones(win) / win
        pad = win // 2
        padded = np.pad(raw_map, (pad, pad), mode="edge")
        raw_map = np.convolve(padded, kernel, mode="valid")

    # Blend toward identity by `tightness`, then hard-clamp the deviation.
    identity = grid.copy()
    blended = (1.0 - tightness) * identity + tightness * raw_map
    deviation = np.clip(blended - identity, -max_shift_s, max_shift_s)
    final_map = identity + deviation

    # Enforce monotonicity (strictly non-decreasing) and stay inside the dub's
    # actual duration.
    final_map = np.maximum.accumulate(final_map)
    final_map = np.clip(final_map, 0.0, dub_duration - hop_dt)

    return TimeMap(
        guide_times=grid,
        dub_times=final_map,
        path_guide_s=path_guide_s,
        path_dub_s=path_dub_s,
    )
