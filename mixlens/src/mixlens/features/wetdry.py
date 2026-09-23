"""wet_dry_true, csi_wash_drop_true, duck_depth_true, predelay_true, wet_bright_true (internal path only)."""
from __future__ import annotations

import numpy as np

from mixlens.config import Config
from mixlens.dsp.loudness import integrated_lufs
from mixlens.dsp.segments import active_mask, envelope_db
from mixlens.features.masking import compute_csi
from mixlens.io.loader import to_mono
from mixlens.io.stems import StemSet
from mixlens.types import FeatureRow

EPS = 1e-12


def extract_wetdry(stems: StemSet, cfg: Config) -> list[FeatureRow]:
    sr = stems.sr
    dry, wet = stems.vox_dry, stems.vox_wet
    dry_mono, wet_mono = to_mono(dry), to_mono(wet)

    wet_dry = integrated_lufs(wet, sr) - integrated_lufs(dry, sr)

    csi_wash_drop = _csi_wash_drop(stems, cfg)
    duck_depth = _duck_depth(dry_mono, wet_mono, sr, cfg)
    predelay = _predelay(dry_mono, wet_mono, sr, cfg)
    wet_bright = _wet_bright(dry_mono, wet_mono, sr)

    return [
        FeatureRow(feature="wet_dry_true", value=float(wet_dry)),
        FeatureRow(feature="csi_wash_drop_true", value=float(csi_wash_drop)),
        FeatureRow(feature="duck_depth_true", value=float(duck_depth)),
        FeatureRow(feature="predelay_true", value=float(predelay)),
        FeatureRow(feature="wet_bright_true", value=float(wet_bright)),
    ]


def _csi_wash_drop(stems: StemSet, cfg: Config) -> float:
    """CSI with wet counted as signal minus CSI with wet counted as masker."""
    dry_plus_wet = stems.vox_dry + stems.vox_wet
    csi_signal, _p10, _ = compute_csi(dry_plus_wet, stems.inst, stems.sr, cfg)
    csi_masked, _p10b, _ = compute_csi(stems.vox_dry, stems.inst + stems.vox_wet, stems.sr, cfg)
    return csi_signal - csi_masked


def _duck_depth(dry_mono: np.ndarray, wet_mono: np.ndarray, sr: int, cfg: Config) -> float:
    """Wet level in dry-gap frames minus wet level in dry-active frames (100ms windows).
    Positive = reverb ducks under the dry vocal and blooms in the gaps."""
    active_lu = cfg.get("active_threshold_lu", 30.0)
    at_times, mask = active_mask(dry_mono, sr, active_lu, hop_s=0.1)
    wet_env_t, wet_env_db = envelope_db(wet_mono, sr, hop_s=0.1, win_s=0.1)
    n = min(len(mask), len(wet_env_db))
    mask, wet_db = mask[:n], wet_env_db[:n]
    gap_levels = wet_db[~mask]
    active_levels = wet_db[mask]
    if len(gap_levels) == 0 or len(active_levels) == 0:
        return 0.0
    return float(np.median(gap_levels) - np.median(active_levels))


def _predelay(dry_mono: np.ndarray, wet_mono: np.ndarray, sr: int, cfg: Config) -> float:
    """Median time (ms) from each dry onset to the wet envelope reaching half its local max."""
    from mixlens.dsp.segments import detect_onsets

    onsets = detect_onsets(dry_mono, sr)
    wet_env_t, wet_env_db = envelope_db(wet_mono, sr, hop_s=0.002, win_s=0.008)
    wet_lin = 10 ** (wet_env_db / 20.0)

    delays = []
    for t_onset in onsets:
        window_mask = (wet_env_t >= t_onset) & (wet_env_t < t_onset + 0.3)
        if not window_mask.any():
            continue
        local = wet_lin[window_mask]
        local_t = wet_env_t[window_mask]
        local_max = np.max(local)
        if local_max <= EPS:
            continue
        half_idx = np.argmax(local >= local_max / 2.0)
        delays.append((local_t[half_idx] - t_onset) * 1000.0)

    return float(np.median(delays)) if delays else 0.0


def _wet_bright(dry_mono: np.ndarray, wet_mono: np.ndarray, sr: int) -> float:
    """Centroid of vox_wet minus centroid of vox_dry, in octaves."""
    import librosa

    def centroid_octaves(mono: np.ndarray) -> float | None:
        if not np.any(np.abs(mono) > EPS):
            return None
        c = librosa.feature.spectral_centroid(y=mono.astype(np.float32), sr=sr)
        val = float(np.mean(c))
        return float(np.log2(val / 20.0)) if val > 0 else None

    c_dry = centroid_octaves(dry_mono)
    c_wet = centroid_octaves(wet_mono)
    if c_dry is None or c_wet is None:
        return 0.0
    return c_wet - c_dry
