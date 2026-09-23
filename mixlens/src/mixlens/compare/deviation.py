"""Robust z-score, ok/watch/flag levels, and hint matching (spec section 4)."""
from __future__ import annotations

from dataclasses import dataclass

from mixlens.compare.envelope import Envelope
from mixlens.config import Config

EPS = 1e-9


@dataclass(frozen=True)
class DeviationResult:
    feature: str
    band: str
    value: float
    z: float
    level: str  # "ok" | "watch" | "flag"
    direction: str  # "low" | "high" | "ok"


def robust_z(value: float, envelope: Envelope) -> float:
    """z = (x - median) / (IQR / 1.349)."""
    scale = envelope.iqr / 1.349
    if scale < EPS:
        return 0.0
    return (value - envelope.med) / scale


def classify_level(value: float, envelope: Envelope, cfg: Config) -> str:
    watch_z = cfg.get("deviation.watch_z", 1.5)
    flag_z = cfg.get("deviation.flag_z", 2.5)
    if envelope.p10 <= value <= envelope.p90:
        return "ok"
    z = abs(robust_z(value, envelope))
    if z > flag_z:
        return "flag"
    if z > watch_z:
        return "watch"
    return "ok"


def evaluate(value: float, envelope: Envelope, cfg: Config) -> DeviationResult:
    z = robust_z(value, envelope)
    level = classify_level(value, envelope, cfg)
    direction = "ok" if level == "ok" else ("high" if z > 0 else "low")
    return DeviationResult(feature=envelope.feature, band=envelope.band, value=value, z=z, level=level, direction=direction)


def evaluate_all(values: dict[tuple[str, str], float], envelopes: dict[tuple[str, str], Envelope], cfg: Config) -> list[DeviationResult]:
    results = []
    for key, value in values.items():
        env = envelopes.get(key)
        if env is None:
            continue
        results.append(evaluate(value, env, cfg))
    return results


def match_hints(results: list[DeviationResult], hint_rules: list[dict], extra_values: dict[str, float] | None = None) -> list[dict]:
    """Match config.yaml hint rules against deviation results.

    Each rule has `conditions`: a list of {feature, direction[, threshold]}.
    `direction` is "low"/"high" (deviation direction), "low_abs"/"high_abs"
    (sign/magnitude of the raw value, for features like duck_depth_true that
    aren't compared to an envelope), "below"/"above" (raw value vs a numeric
    threshold, e.g. csi_phone_delta), or "gap_below" (raw value at least
    `threshold` below another feature's raw value, e.g. csi_p10 well under
    csi -- needs an "other" key naming that second feature).
    """
    by_feature = {r.feature: r for r in results}
    extra_values = extra_values or {}
    matched = []
    for rule in hint_rules:
        ok = True
        for cond in rule["conditions"]:
            feat = cond["feature"]
            direction = cond["direction"]
            if direction in ("low", "high"):
                r = by_feature.get(feat)
                if r is None or r.level == "ok" or r.direction != direction:
                    ok = False
                    break
            elif direction in ("low_abs", "high_abs"):
                val = extra_values.get(feat)
                if val is None:
                    ok = False
                    break
                if direction == "low_abs" and not (val <= 0):
                    ok = False
                    break
                if direction == "high_abs" and not (val > 0):
                    ok = False
                    break
            elif direction in ("below", "above"):
                val = extra_values.get(feat)
                threshold = cond.get("threshold", 0.0)
                if val is None:
                    ok = False
                    break
                if direction == "below" and not (val < threshold):
                    ok = False
                    break
                if direction == "above" and not (val > threshold):
                    ok = False
                    break
            elif direction == "gap_below":
                val = extra_values.get(feat)
                other_val = extra_values.get(cond.get("other"))
                threshold = cond.get("threshold", 0.0)
                if val is None or other_val is None or not (val <= other_val - threshold):
                    ok = False
                    break
        if ok:
            matched.append({"id": rule["id"], "message": rule["message"]})
    return matched
