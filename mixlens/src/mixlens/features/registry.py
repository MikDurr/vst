"""Runs extractors -> list[FeatureRow] on the Demucs pair (reference path) and
the true-stem pair (internal path, suffixed `_true`). Wet/dry extractors run
only on the internal path, on the full StemSet."""
from __future__ import annotations

import numpy as np

from mixlens.config import Config
from mixlens.features.dynamics import extract_dynamics
from mixlens.features.masking import compute_csi, extract_csi, extract_masking_groups
from mixlens.features.microdynamics import extract_vox_crest, extract_vox_floor_true, extract_whole_mix_microdynamics
from mixlens.features.sheen import extract_sheen, extract_vox_air_ratio
from mixlens.features.space import extract_space
from mixlens.features.stereo import extract_stereo
from mixlens.features.tonal import extract_ltas
from mixlens.features.translation import extract_translation
from mixlens.features.vocal import _vir_series, extract_vir, extract_vox_consistency, extract_vox_tone
from mixlens.features.wetdry import extract_wetdry
from mixlens.io.stems import StemSet
from mixlens.types import FeatureRow


def extract_whole_mix(mix: np.ndarray, sr: int, cfg: Config) -> list[FeatureRow]:
    """Features that only need the full mix bounce (section 3.1)."""
    rows: list[FeatureRow] = []
    rows += extract_ltas(mix, sr, cfg)
    rows += extract_dynamics(mix, sr, cfg)
    rows += extract_stereo(mix, sr, cfg)
    rows += extract_sheen(mix, sr, cfg)
    rows += extract_whole_mix_microdynamics(mix, sr, cfg)
    return rows


def extract_vocal_inst_pair(
    vocal: np.ndarray,
    inst: np.ndarray,
    sr: int,
    cfg: Config,
    sections: dict[str, tuple[float, float]] | None = None,
    include_translation: bool = True,
) -> list[FeatureRow]:
    """Features needing a vocal/instrumental pair: VIR, blend, space, sheen, translation.

    Used both for the reference (Demucs) path and, suffixed `_true` by
    `extract_internal_path`, the internal (true-stem) path.
    """
    rows: list[FeatureRow] = []
    rows += extract_vir(vocal, inst, sr, cfg, sections=sections)
    rows += extract_vox_consistency(vocal, inst, sr, cfg)
    rows += extract_vox_tone(vocal, sr, cfg)
    rows += extract_csi(vocal, inst, sr, cfg)
    rows += extract_masking_groups(vocal, inst, sr, cfg)
    rows += extract_space(vocal, inst, sr, cfg)
    rows += extract_vox_air_ratio(vocal, sr, cfg)
    rows += extract_vox_crest(vocal, sr, cfg)

    if include_translation:
        vir_full = next((r.value for r in rows if r.feature == "vir_med"), 0.0)
        csi_full = next((r.value for r in rows if r.feature == "csi"), 0.0)
        rows += extract_translation(vocal, inst, sr, cfg, vir_full, csi_full)

    return rows


def extract_reference_path(
    mix: np.ndarray,
    vocal_demucs: np.ndarray,
    inst_demucs: np.ndarray,
    sr: int,
    cfg: Config,
    sections: dict[str, tuple[float, float]] | None = None,
) -> list[FeatureRow]:
    """Full reference-path feature set: whole-mix features plus vocal/inst pair
    features computed on the Demucs split (yours or a reference track)."""
    rows = extract_whole_mix(mix, sr, cfg)
    rows += extract_vocal_inst_pair(vocal_demucs, inst_demucs, sr, cfg, sections=sections)
    return rows


def extract_internal_path(stems: StemSet, cfg: Config, sections: dict[str, tuple[float, float]] | None = None) -> list[FeatureRow]:
    """Internal-path features from your true stems, suffixed `_true`, plus the
    wet/dry-only features that only exist on this path (section 3.4)."""
    true_vocal = stems.vox_dry + stems.vox_wet
    pair_rows = extract_vocal_inst_pair(true_vocal, stems.inst, stems.sr, cfg, sections=sections)
    suffixed = [FeatureRow(feature=f"{r.feature}_true", value=r.value, band=r.band) for r in pair_rows]
    suffixed += extract_wetdry(stems, cfg)
    suffixed += extract_vox_floor_true(stems, cfg)
    return suffixed


def extract_all(
    stems: StemSet,
    cfg: Config,
    vocal_demucs: np.ndarray | None = None,
    inst_demucs: np.ndarray | None = None,
    sections: dict[str, tuple[float, float]] | None = None,
) -> list[FeatureRow]:
    """Full analysis of a mix version: whole-mix + reference path (if Demucs
    split provided) + internal path (from true stems)."""
    rows = extract_whole_mix(stems.mix, stems.sr, cfg)
    if vocal_demucs is not None and inst_demucs is not None:
        rows += extract_vocal_inst_pair(vocal_demucs, inst_demucs, stems.sr, cfg, sections=sections)
    rows += extract_internal_path(stems, cfg, sections=sections)
    return rows
