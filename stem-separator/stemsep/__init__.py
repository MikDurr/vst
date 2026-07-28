"""stemsep — standalone stem separation.

Splits a mix into vocals / drums / bass / other (Demucs), or into vocals +
instrumental with no model at all (the Quick engine).

Grew out of the Demucs wrapper in vocal-pitch-analyzer's vpa/audio.py, which
only ever needed a mono vocal to hand to a pitch tracker. This is the separator
as its own tool: all four stems, real sample rates, stereo preserved, and a UI.
"""

from .quick import QuickError, QuickResult, separate_quick
from .separate import (
    DEFAULT_MODEL,
    FOUR_STEMS,
    MODELS,
    SeparationError,
    SeparationResult,
    Stem,
    best_device,
    demucs_available,
    separate,
)

__all__ = [
    "DEFAULT_MODEL",
    "FOUR_STEMS",
    "MODELS",
    "QuickError",
    "QuickResult",
    "SeparationError",
    "SeparationResult",
    "Stem",
    "best_device",
    "demucs_available",
    "separate",
    "separate_quick",
]
