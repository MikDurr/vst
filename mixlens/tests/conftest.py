import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import numpy as np
import pytest

from mixlens.config import load_config

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.yaml"


@pytest.fixture(scope="session")
def cfg():
    return load_config(CONFIG_PATH)


def sine(freq: float, duration: float, sr: int, amplitude: float = 0.5, phase: float = 0.0) -> np.ndarray:
    t = np.arange(int(duration * sr)) / sr
    return (amplitude * np.sin(2 * np.pi * freq * t + phase)).astype(np.float32)


def stereo(mono: np.ndarray) -> np.ndarray:
    return np.stack([mono, mono], axis=0)
