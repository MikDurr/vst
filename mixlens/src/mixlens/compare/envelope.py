"""Build/load style envelopes (per feature/band: median, p10, p90, IQR, n) and
run the leave-one-out reference audit (spec section 1.2)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Envelope:
    style: str
    feature: str
    band: str
    med: float
    p10: float
    p90: float
    iqr: float
    n: int


def build_envelopes(features_df: pd.DataFrame) -> list[Envelope]:
    """`features_df` columns: style, feature, band, value (one row per ref x feature x band)."""
    envelopes = []
    group_cols = ["style", "feature", "band"]
    for (style, feature, band), group in features_df.groupby(group_cols):
        vals = group["value"].to_numpy()
        if len(vals) == 0:
            continue
        med = float(np.median(vals))
        p10, p25, p75, p90 = np.percentile(vals, [10, 25, 75, 90])
        envelopes.append(
            Envelope(style=style, feature=feature, band=band, med=med, p10=float(p10), p90=float(p90), iqr=float(p75 - p25), n=len(vals))
        )
    return envelopes


def envelopes_to_df(envelopes: list[Envelope]) -> pd.DataFrame:
    return pd.DataFrame([e.__dict__ for e in envelopes])


def leave_one_out_audit(features_df: pd.DataFrame, style: str, deviation_fn) -> pd.DataFrame:
    """For each reference in `style`, build an envelope from the OTHER references
    and score this one against it. `deviation_fn(value, envelope) -> level` from
    compare.deviation. Returns a DataFrame with ref_id, n_flags, flagged features.
    """
    style_df = features_df[features_df["style"] == style]
    ref_ids = style_df["entity_id"].unique()
    results = []
    for ref_id in ref_ids:
        held_out = style_df[style_df["entity_id"] == ref_id]
        others = style_df[style_df["entity_id"] != ref_id]
        env = build_envelopes(others.assign(style=style))
        env_lookup = {(e.feature, e.band): e for e in env}

        flags = []
        for _idx, row in held_out.iterrows():
            key = (row["feature"], row["band"])
            if key not in env_lookup:
                continue
            level = deviation_fn(row["value"], env_lookup[key])
            if level == "flag":
                flags.append(f"{row['feature']}[{row['band']}]" if row["band"] else row["feature"])
        results.append({"entity_id": ref_id, "n_flags": len(flags), "flagged": flags})
    return pd.DataFrame(results)
