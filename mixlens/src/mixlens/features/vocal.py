"""vir_med/iqr/{section}, vox_consistency, vox_harsh, vox_sib."""
from __future__ import annotations

import numpy as np

from mixlens.config import Config
from mixlens.dsp.bands import band_energy_db, stft_mag
from mixlens.dsp.loudness import momentary_lufs_series
from mixlens.dsp.segments import active_mask
from mixlens.io.loader import to_mono
from mixlens.types import FeatureRow

EPS = 1e-12


def _vir_series(vocal: np.ndarray, inst: np.ndarray, sr: int, active_lu: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Returns (times, vir_values, active_mask) over active frames only."""
    v_mono, i_mono = to_mono(vocal), to_mono(inst)
    times, v_lufs = momentary_lufs_series(v_mono, sr, hop_s=0.1)
    _t2, i_lufs = momentary_lufs_series(i_mono, sr, hop_s=0.1)
    n = min(len(v_lufs), len(i_lufs))
    times, v_lufs, i_lufs = times[:n], v_lufs[:n], i_lufs[:n]
    _at, mask = active_mask(v_mono, sr, active_lu, hop_s=0.1)
    mask = mask[:n]
    vir = v_lufs - i_lufs
    return times, vir, mask


def extract_vir(vocal: np.ndarray, inst: np.ndarray, sr: int, cfg: Config, sections: dict[str, tuple[float, float]] | None = None) -> list[FeatureRow]:
    active_lu = cfg.get("active_threshold_lu", 30.0)
    times, vir, mask = _vir_series(vocal, inst, sr, active_lu)
    active_vir = vir[mask]
    rows = []
    if len(active_vir):
        rows.append(FeatureRow(feature="vir_med", value=float(np.median(active_vir))))
        q75, q25 = np.percentile(active_vir, [75, 25])
        rows.append(FeatureRow(feature="vir_iqr", value=float(q75 - q25)))
    else:
        rows.append(FeatureRow(feature="vir_med", value=0.0))
        rows.append(FeatureRow(feature="vir_iqr", value=0.0))

    if sections:
        for name, (start, end) in sections.items():
            in_section = (times >= start) & (times < end) & mask
            vals = vir[in_section]
            if len(vals):
                rows.append(FeatureRow(feature="vir_section", value=float(np.median(vals)), band=name))
    return rows


def extract_vox_consistency(vocal: np.ndarray, inst: np.ndarray, sr: int, cfg: Config) -> list[FeatureRow]:
    active_lu = cfg.get("active_threshold_lu", 30.0)
    v_mono = to_mono(vocal)
    times, v_lufs = momentary_lufs_series(v_mono, sr, hop_s=0.1)
    _at, mask = active_mask(v_mono, sr, active_lu, hop_s=0.1)
    active_vals = v_lufs[mask[: len(v_lufs)]]
    std = float(np.std(active_vals)) if len(active_vals) else 0.0
    return [FeatureRow(feature="vox_consistency", value=std)]


def extract_vox_tone(vocal: np.ndarray, sr: int, cfg: Config) -> list[FeatureRow]:
    n_fft = cfg.get("stft.tonal.n_fft", 4096)
    hop = cfg.get("stft.tonal.hop", 1024)
    v_mono = to_mono(vocal)
    freqs, mag = stft_mag(v_mono, sr, n_fft, hop)
    mag_mean = mag.mean(axis=0, keepdims=True)

    db_200_1k = band_energy_db(freqs, mag_mean, 200, 1000)[0]
    db_2_5k = band_energy_db(freqs, mag_mean, 2000, 5000)[0]
    db_5_10k = band_energy_db(freqs, mag_mean, 5000, 10000)[0]

    return [
        FeatureRow(feature="vox_harsh", value=float(db_2_5k - db_200_1k)),
        FeatureRow(feature="vox_sib", value=float(db_5_10k - db_200_1k)),
    ]
