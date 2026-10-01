"""Compare page: what to do next first, then the numbers behind it."""
from __future__ import annotations

import pandas as pd
import streamlit as st

import theme
from mixlens.compare.glossary import explain, feature_name, what_it_measures
from mixlens.pipeline import recommendations_for, reference_range_key
from plots import ltas_vs_envelope_figure, space_sheen_scatter

VOCALS, INSTRUMENTALS = "Songs with vocals", "Instrumentals"


def render(repo, cfg) -> None:
    theme.page_header("Compare", "See how a mix sits against your references, and what to do about it.")

    versions_df = repo.get_all_versions()
    if versions_df.empty:
        theme.callout("<b>Nothing to compare yet.</b> Analyze a mix on the Analyze page and the results land here.")
        return

    songs = sorted(versions_df["song_id"].unique())
    if st.session_state.get("cmp_song") not in songs:
        st.session_state["cmp_song"] = songs[0]
    c1, c2 = st.columns(2)
    song = c1.selectbox("Song", songs, key="cmp_song")
    song_versions = versions_df[versions_df["song_id"] == song]
    version_opts = sorted(song_versions["version"].unique(), key=lambda v: int(song_versions[song_versions["version"] == v].iloc[0]["version_id"]))
    if st.session_state.get("cmp_version") not in version_opts:
        st.session_state["cmp_version"] = version_opts[-1]
    version = c2.selectbox("Version", version_opts, key="cmp_version")
    version_id = int(song_versions[song_versions["version"] == version].iloc[0]["version_id"])

    info = repo.get_song(song) or {}
    style, instrumental = info.get("style"), bool(info.get("instrumental"))
    if not style:
        st.warning("This song has no style set, so it can't be compared to references.")
        return

    refs_have_vocals = True
    if instrumental:
        kind = st.radio(
            "Your references are…", [VOCALS, INSTRUMENTALS], horizontal=True, key="cmp_refs_kind",
            help="Most references have vocals sitting in their midrange. If yours do, we compare your instrumental "
                 "against them with the vocals removed so it's like for like. If your references are instrumentals, pick the second.",
        )
        refs_have_vocals = kind == VOCALS
    range_key = reference_range_key(style, instrumental, refs_have_vocals)
    recs, results, has_range = recommendations_for(repo, cfg, version_id, range_key)

    # ---- what to do next ----
    st.subheader("What to do next")
    fixes = [r for r in recs if r.severity == "fix"]
    checks = [r for r in recs if r.severity == "check"]
    if fixes or checks:
        st.markdown(
            f'<p class="summary-line">{len(fixes)} to fix first, {len(checks)} to take a look at.</p>', unsafe_allow_html=True
        )
    elif has_range:
        theme.callout("<b>Nothing to fix.</b> Every measurement sits inside the range your references cover, and the safety checks pass.")
    for rec in recs:
        theme.rec_card(rec)
    if instrumental:
        st.caption(
            "Instrumental: vocal measurements don't apply. " + (
                "Compared against your references with their vocals removed (approximate: a little vocal bleed remains)."
                if refs_have_vocals else "Compared against your references' full mix."
            )
        )
    if not has_range:
        return

    # ---- the numbers ----
    st.subheader("The numbers behind it")
    features_df = repo.get_features(entity="version", entity_id=version_id)
    envelopes = repo.get_envelopes(range_key)

    with st.expander("How to read these", expanded=False):
        st.markdown(
            "- *ok* means inside the range your references cover (their middle 80%). *watch* is moderately outside, "
            "a hint only. *flag* is clearly outside.\n"
            "- **z** is how many typical spreads you are from the reference median.\n"
            "- A flag isn't an error. If your references don't share the sound you want, the flag is telling you about the references."
        )

    st.markdown("##### Tonal balance")
    st.caption(
        "Your mix's average spectrum (lime) against the band covering the middle 80% of your references (shaded). "
        "0 dB is the average level between 250 Hz and 4 kHz, so this shows shape, not loudness."
    )
    env_df = pd.DataFrame([e.__dict__ for e in envelopes.values()])
    st.plotly_chart(ltas_vs_envelope_figure(features_df, env_df), use_container_width=True)

    flagged = [r for r in results if r.level != "ok"]
    st.markdown("##### Everything outside your references' range")
    if flagged:
        flag_df = pd.DataFrame([
            {"measurement": feature_name(r.feature) + (f" [{r.band}]" if r.band else ""), "level": r.level,
             "your value": round(r.value, 2), "z": round(r.z, 2), "meaning": explain(r.feature, r.direction)}
            for r in flagged
        ]).sort_values("z", key=abs, ascending=False)
        st.dataframe(flag_df, use_container_width=True, hide_index=True,
                     column_config={"meaning": st.column_config.TextColumn("what it means", width="large")})
        with st.expander("What each measurement is"):
            for feat in sorted({r.feature for r in flagged}):
                st.markdown(f"**{feature_name(feat)}** (`{feat}`): {what_it_measures(feat)}")
    else:
        st.success("Nothing outside the range.")

    if instrumental:
        return
    ref_features = repo.get_features_for_style(style, entity="ref")
    rows = []
    for ref_id, group in ref_features.groupby("entity_id"):
        sc, ar = group[group["feature"] == "space_contrast"]["value"], group[group["feature"] == "air_ratio"]["value"]
        if len(sc) and len(ar):
            rows.append({"entity": "ref", "space_contrast": sc.iloc[0], "air_ratio": ar.iloc[0], "label": f"ref {ref_id}"})
    mine = features_df.set_index("feature")["value"] if not features_df.empty else {}
    if "space_contrast" in mine and "air_ratio" in mine:
        rows.append({"entity": "yours", "space_contrast": mine["space_contrast"], "air_ratio": mine["air_ratio"], "label": f"{song} {version}"})
    if rows:
        st.markdown("##### Space and sheen")
        st.caption("Right = wetter vocal over a drier instrumental. Up = brighter, airier top end. "
                   "Violet dots are your references; the star is this mix. Aim to land inside the cloud you like.")
        st.plotly_chart(space_sheen_scatter(pd.DataFrame(rows)), use_container_width=True)
