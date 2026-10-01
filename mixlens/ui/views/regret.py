"""Regret page: effect-size bars, signature list, labeling form."""
from __future__ import annotations

import streamlit as st

import widgets

import theme

from mixlens.compare.glossary import explain, feature_name
from mixlens.compare.regret import compare_groups

from plots import effect_size_bar_figure


def render(repo, cfg) -> None:
    theme.page_header("Regret", "Find which measurements predict the mixes you end up redoing.")
    with st.expander("How this works", expanded=False):
        st.markdown(
            "Weeks after finishing a mix, label it: **held_up** (still sounds good), **neutral**, or **regret** "
            "(you'd remix it). Once you have at least 5 of each, MixLens looks for measurements that systematically "
            "differ between the two groups.\n\n"
            "- **Effect size (Cliff's delta)** runs from -1 to +1: the chance a random regret mix scores higher than a random "
            "keeper, minus the chance it scores lower. 0 = no difference. Roughly: under 0.15 negligible, 0.15-0.33 small, "
            "0.33-0.47 medium, above 0.47 large.\n"
            "- **Red bars (+)** = higher in your regrets. **Blue bars (-)** = lower in your regrets.\n"
            "- With a small sample, treat this as a pattern to investigate, not proof. There are deliberately no p-values."
        )

    st.subheader("Label a version")
    versions_df = repo.get_all_versions()
    if not versions_df.empty:
        songs = sorted(versions_df["song_id"].unique())
        widgets.guard("reg_song", songs)
        song = st.selectbox("Song", songs, key="reg_song")
        song_versions = versions_df[versions_df["song_id"] == song]
        v_opts = sorted(song_versions["version"].unique())
        widgets.guard("reg_version", v_opts)
        version = st.selectbox("Version", v_opts, key="reg_version")
        rating = st.radio("Rating", ["held_up", "neutral", "regret"], horizontal=True, key="reg_rating")
        tag = st.text_input("Tag", key="reg_tag")
        note = st.text_area("Note", key="reg_note")
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

    def strength(d: float) -> str:
        d = abs(d)
        return "large" if d >= 0.474 else "medium" if d >= 0.33 else "small" if d >= 0.147 else "negligible"

    result = result.assign(
        measurement=[feature_name(f) + (f" [{b}]" if b else "") for f, b in zip(result["feature"], result["band"])],
        strength=[strength(d) for d in result["delta"]],
        meaning=[
            "Your regrets lean toward: " + explain(f, "high" if d > 0 else "low")
            for f, d in zip(result["feature"], result["delta"])
        ],
    )

    top = result[result["strength"].isin(["medium", "large"])].head(3)
    if top.empty:
        st.info("No medium or large differences yet; either your regrets aren't mix-related, or more labels are needed.")
    else:
        st.subheader("What stands out")
        for _i, r in top.iterrows():
            st.markdown(f"- **{r['measurement']}** ({r['strength']}, delta {r['delta']:+.2f}): {r['meaning']}")

    st.plotly_chart(effect_size_bar_figure(result), use_container_width=True)
    st.dataframe(
        result[["measurement", "strength", "delta", "held_up_median", "regret_median", "meaning"]],
        use_container_width=True, hide_index=True,
        column_config={"meaning": st.column_config.TextColumn("what it means", width="large")},
    )
