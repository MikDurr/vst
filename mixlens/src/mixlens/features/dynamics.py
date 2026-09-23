"""lufs_i, lra, plr, crest (whole mix)."""
from __future__ import annotations

import numpy as np

from mixlens.config import Config
from mixlens.dsp.loudness import crest_factor_db, integrated_lufs, loudness_range, true_peak_dbtp
from mixlens.types import FeatureRow


def extract_dynamics(mix: np.ndarray, sr: int, cfg: Config) -> list[FeatureRow]:
    lufs_i = integrated_lufs(mix, sr)
    lra = loudness_range(mix, sr)
    dbtp, _up = true_peak_dbtp(mix, oversample=cfg.get("peaks.oversample_factor", 4))
    plr = dbtp - lufs_i
    crest = crest_factor_db(mix)
    return [
        FeatureRow(feature="lufs_i", value=float(lufs_i)),
        FeatureRow(feature="lra", value=float(lra)),
        FeatureRow(feature="plr", value=float(plr)),
        FeatureRow(feature="crest", value=float(crest)),
    ]
