"""Regret analysis: Cliff's delta ranking between held_up/regret groups, and your signature."""
from __future__ import annotations

import numpy as np
import pandas as pd

MIN_LABELED_PER_GROUP = 5


def cliffs_delta(a: np.ndarray, b: np.ndarray) -> float:
    """Cliff's delta: P(a > b) - P(a < b), in [-1, 1]."""
    a, b = np.asarray(a), np.asarray(b)
    if len(a) == 0 or len(b) == 0:
        return 0.0
    gt = sum(1 for x in a for y in b if x > y)
    lt = sum(1 for x in a for y in b if x < y)
    return (gt - lt) / (len(a) * len(b))


def compare_groups(features_df: pd.DataFrame, labels_df: pd.DataFrame) -> pd.DataFrame:
    """features_df: entity_id, feature, band, value (versions only).
    labels_df: version_id (=entity_id), rating in {held_up, neutral, regret}.

    Returns a DataFrame ranked by |delta|, one row per (feature, band), with
    held_up/regret medians and Cliff's delta. Requires >=5 labeled versions
    per group (spec section 4); raises otherwise.
    """
    held_ids = labels_df[labels_df["rating"] == "held_up"]["version_id"].tolist()
    regret_ids = labels_df[labels_df["rating"] == "regret"]["version_id"].tolist()
    if len(held_ids) < MIN_LABELED_PER_GROUP or len(regret_ids) < MIN_LABELED_PER_GROUP:
        raise ValueError(
            f"Need >= {MIN_LABELED_PER_GROUP} labeled mixes in each of held_up/regret; "
            f"have {len(held_ids)} held_up, {len(regret_ids)} regret."
        )

    rows = []
    for (feature, band), group in features_df.groupby(["feature", "band"]):
        held_vals = group[group["entity_id"].isin(held_ids)]["value"].to_numpy()
        regret_vals = group[group["entity_id"].isin(regret_ids)]["value"].to_numpy()
        if len(held_vals) == 0 or len(regret_vals) == 0:
            continue
        delta = cliffs_delta(regret_vals, held_vals)
        rows.append(
            {
                "feature": feature,
                "band": band,
                "held_up_median": float(np.median(held_vals)),
                "regret_median": float(np.median(regret_vals)),
                "delta": delta,
                "direction": "higher in regret" if delta > 0 else "lower in regret",
            }
        )
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.reindex(df["delta"].abs().sort_values(ascending=False).index).reset_index(drop=True)
    return df


def find_signature(deviation_results_by_version: dict[int, list], threshold: float = 0.75) -> pd.DataFrame:
    """Features where >= `threshold` of your mixes deviate in the same
    direction (high or low, i.e. level != "ok"), across all labeled versions.

    `deviation_results_by_version`: {version_id: [DeviationResult, ...]}.
    """
    from collections import defaultdict

    counts: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: {"high": 0, "low": 0, "total": 0})
    for _version_id, results in deviation_results_by_version.items():
        for r in results:
            key = (r.feature, r.band)
            counts[key]["total"] += 1
            if r.direction in ("high", "low"):
                counts[key][r.direction] += 1

    rows = []
    for (feature, band), c in counts.items():
        total = c["total"]
        if total == 0:
            continue
        for direction in ("high", "low"):
            frac = c[direction] / total
            if frac >= threshold:
                rows.append({"feature": feature, "band": band, "direction": direction, "fraction": frac, "n": total})
    return pd.DataFrame(rows)
