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

    _render_diff(repo, song, song_versions)


def _render_diff(repo, song: str, song_versions: pd.DataFrame) -> None:
    st.subheader("Diff two versions")
    version_options = list(song_versions["version"])
    if len(version_options) < 2:
        st.caption("Need at least two analyzed versions to diff.")
        return

    col1, col2 = st.columns(2)
    with col1:
        version_a = st.selectbox("From", version_options, index=max(0, len(version_options) - 2), key="diff_a")
    with col2:
        version_b = st.selectbox("To", version_options, index=len(version_options) - 1, key="diff_b")

    if version_a == version_b:
        st.caption("Pick two different versions.")
        return

    id_a = int(song_versions[song_versions["version"] == version_a].iloc[0]["version_id"])
    id_b = int(song_versions[song_versions["version"] == version_b].iloc[0]["version_id"])
    feats_a = repo.get_features(entity="version", entity_id=id_a).set_index(["feature", "band"])["value"]
    feats_b = repo.get_features(entity="version", entity_id=id_b).set_index(["feature", "band"])["value"]

    common = sorted(set(feats_a.index) & set(feats_b.index))
    rows = []
    for feature, band in common:
        va, vb = feats_a[(feature, band)], feats_b[(feature, band)]
        delta = vb - va
        if abs(delta) < 1e-6:
            continue
        rows.append({"feature": feature, "band": band, version_a: va, version_b: vb, "delta": delta})

    if not rows:
        st.caption("No feature differences between these versions.")
        return

    diff_df = pd.DataFrame(rows).sort_values("delta", key=abs, ascending=False)
    st.dataframe(diff_df, use_container_width=True)
