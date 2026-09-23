"""Load and validate config.yaml into a typed Config dataclass."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.yaml"


@dataclass(frozen=True)
class Config:
    """Thin typed wrapper around the parsed config.yaml dict.

    Feature/check modules pull nested values out of `raw` by dotted path via
    `get()` rather than exploding every field into its own dataclass field,
    since the spec expects new config knobs to need no code changes.
    """

    raw: dict[str, Any]
    path: Path
    text_hash: str = field(compare=False)

    def get(self, dotted_path: str, default: Any = None) -> Any:
        node: Any = self.raw
        for part in dotted_path.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    @property
    def sample_rate(self) -> int:
        return int(self.get("sample_rate", 44100))

    @property
    def loudness_target_lufs(self) -> float:
        return float(self.get("loudness_target_lufs", -14.0))


def load_config(path: str | Path | None = None) -> Config:
    cfg_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    text = cfg_path.read_text()
    raw = yaml.safe_load(text) or {}
    _validate(raw)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return Config(raw=raw, path=cfg_path, text_hash=digest)


def _validate(raw: dict[str, Any]) -> None:
    required_top = ["sample_rate", "stft", "csi", "space", "sheen", "peaks", "deviation"]
    missing = [k for k in required_top if k not in raw]
    if missing:
        raise ValueError(f"config.yaml missing required sections: {missing}")
    for band_key in ("tonal", "transient"):
        block = raw["stft"].get(band_key)
        if not block or "n_fft" not in block or "hop" not in block:
            raise ValueError(f"config.yaml stft.{band_key} needs n_fft and hop")
