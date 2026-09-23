"""Core types shared across pipeline, features, and checks (spec section 6)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from mixlens.config import Config


@dataclass(frozen=True)
class FeatureRow:
    feature: str
    value: float
    band: str = ""


@dataclass(frozen=True)
class CheckResultRow:
    check: str
    level: str
    value: float
    t_sec: float | None
    stem: str


# An extractor takes (vocal_audio, inst_audio, sr, config) and returns
# FeatureRows. It's run once on the Demucs pair (reference path) and once on
# the true stems (internal path, output suffixed "_true" by the registry).
Extractor = Callable[[np.ndarray, np.ndarray, int, Config], "list[FeatureRow]"]
