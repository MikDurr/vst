"""History page: vir_med, csi, space_contrast, air_ratio, true_peak across versions."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from plots import history_line_figure

TRACKED_FEATURES = ["vir_med", "csi", "space_contrast", "air_ratio", "true_peak"]


def render(repo, cfg) -> None:
    st.header("History")

    versions_df = repo.get_all_versions()
    if versions_df.empty:
        st.info("No analyzed versions yet.")
        return

    songs = sorted(versions_df["song_id"].unique())
    song = st.selectbox("Song", songs)
    song_versions = versions_df[versions_df["song_id"] == song].sort_values("version_id")

    rows = []
    for _idx, v in song_versions.iterrows():
        feats = repo.get_features(entity="version", entity_id=int(v["version_id"]))
        checks = repo.get_checks(int(v["version_id"]))
        for feature in TRACKED_FEATURES:
            if feature == "true_peak":
                sub = checks[checks["check_name"] == "true_peak"]
                if not sub.empty:
                    rows.append({"version": v["version"], "feature": "true_peak", "value": sub.iloc[0]["value"]})
            else:
                sub = feats[(feats["feature"] == feature) & (feats["band"] == "")]
                if not sub.empty:
                    rows.append({"version": v["version"], "feature": feature, "value": sub.iloc[0]["value"]})

    if not rows:
        st.info("No tracked features found for this song yet.")
        return

    df = pd.DataFrame(rows)
    cols = st.columns(2)
    for i, feature in enumerate(TRACKED_FEATURES):
        if feature not in df["feature"].values:
            continue
        with cols[i % 2]:
            st.plotly_chart(history_line_figure(df, feature), use_container_width=True)
