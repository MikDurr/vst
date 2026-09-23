"""vir_{phone,mono}, csi_{phone,mono}, and their deltas from the full-range value (section 3.5)."""
from __future__ import annotations

import numpy as np

from mixlens.config import Config
from mixlens.dsp.sims import mono_fold, phone_sim
from mixlens.features.masking import compute_csi
from mixlens.features.vocal import _vir_series
from mixlens.types import FeatureRow


def extract_translation(
    vocal: np.ndarray,
    inst: np.ndarray,
    sr: int,
    cfg: Config,
    vir_full: float,
    csi_full: float,
) -> list[FeatureRow]:
    hp_hz = cfg.get("translation.phone_hp_hz", 300.0)
    lp_hz = cfg.get("translation.phone_lp_hz", 8000.0)
    order = cfg.get("translation.butterworth_order", 4)
    active_lu = cfg.get("active_threshold_lu", 30.0)

    rows: list[FeatureRow] = []

    # phone sim
    v_phone = phone_sim(vocal, sr, hp_hz, lp_hz, order)[None, :]
    i_phone = phone_sim(inst, sr, hp_hz, lp_hz, order)[None, :]
    _t, vir_phone_series, mask = _vir_series(v_phone, i_phone, sr, active_lu)
    active_vals = vir_phone_series[mask]
    vir_phone = float(np.median(active_vals)) if len(active_vals) else 0.0
    csi_phone, _p10, _ = compute_csi(v_phone, i_phone, sr, cfg)

    rows.append(FeatureRow(feature="vir_phone", value=vir_phone))
    rows.append(FeatureRow(feature="csi_phone", value=csi_phone))
    rows.append(FeatureRow(feature="vir_phone_delta", value=vir_phone - vir_full))
    rows.append(FeatureRow(feature="csi_phone_delta", value=csi_phone - csi_full))

    # mono sim
    v_mono_fold = mono_fold(vocal)[None, :]
    i_mono_fold = mono_fold(inst)[None, :]
    _t2, vir_mono_series, mask2 = _vir_series(v_mono_fold, i_mono_fold, sr, active_lu)
    active_vals2 = vir_mono_series[mask2]
    vir_mono = float(np.median(active_vals2)) if len(active_vals2) else 0.0
    csi_mono, _p10b, _ = compute_csi(v_mono_fold, i_mono_fold, sr, cfg)

    rows.append(FeatureRow(feature="vir_mono", value=vir_mono))
    rows.append(FeatureRow(feature="csi_mono", value=csi_mono))
    rows.append(FeatureRow(feature="vir_mono_delta", value=vir_mono - vir_full))
    rows.append(FeatureRow(feature="csi_mono_delta", value=csi_mono - csi_full))

    return rows
