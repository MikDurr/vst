"""Regret page: effect-size bars, signature list, labeling form."""
from __future__ import annotations

import streamlit as st

from mixlens.compare.regret import compare_groups

from plots import effect_size_bar_figure


def render(repo, cfg) -> None:
    st.header("Regret")

    st.subheader("Label a version")
    versions_df = repo.get_all_versions()
    if not versions_df.empty:
        songs = sorted(versions_df["song_id"].unique())
        song = st.selectbox("Song", songs, key="regret_song")
        song_versions = versions_df[versions_df["song_id"] == song]
        version = st.selectbox("Version", sorted(song_versions["version"].unique()), key="regret_version")
        rating = st.radio("Rating", ["held_up", "neutral", "regret"], horizontal=True)
        tag = st.text_input("Tag", "")
        note = st.text_area("Note", "")
        if st.button("Save label"):
            version_id = int(song_versions[song_versions["version"] == version].iloc[0]["version_id"])
            repo.set_label(version_id, rating, tag=tag, note=note)
            st.success(f"Labeled {song} {version} as {rating}.")
    else:
        st.info("No analyzed versions yet.")

    st.subheader("Effect-size ranking")
    labels_df = repo.get_labels()
    features_df = repo.get_features(entity="version")
    try:
        result = compare_groups(features_df, labels_df)
    except ValueError as e:
        st.warning(str(e))
        return

    if result.empty:
        st.info("No overlapping features between labeled groups.")
        return

    st.plotly_chart(effect_size_bar_figure(result), use_container_width=True)
    st.dataframe(result, use_container_width=True)
