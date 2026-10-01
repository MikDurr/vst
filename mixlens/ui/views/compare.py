"""Compare page: peak-safety banner, LTAS vs envelope, flag table with hints,
CSI timeline, space vs sheen scatter."""
from __future__ import annotations

import pandas as pd
import streamlit as st

import theme

from mixlens.compare.deviation import evaluate
from mixlens.compare.glossary import explain, feature_name, what_it_measures
from mixlens.pipeline import INSTRUMENTAL_SUFFIX
from mixlens.pipeline import build_hints

from plots import csi_timeline_figure, ltas_vs_envelope_figure, space_sheen_scatter


def render(repo, cfg) -> None:
    theme.page_header("Compare", "See how a mix sits against the references you chose.")
    with st.expander("How to read this page"):
        st.markdown(
            "This compares **one mix version** with the **reference set for its style**, "
            "i.e. songs whose mix you chose as the target.\n\n"
            "- **Peak safety** is pass/fail and independent of the references: clipping, true-peak overs, headroom.\n"
            "- **Flags and watches** list measurements outside the range your references cover. "
            "*ok* = inside the references' p10-p90 range; *watch* = moderately outside (z between 1.5 and 2.5, a hint only); "
            "*flag* = clearly outside (z above 2.5). z is how many 'typical spreads' you are from the reference median.\n"
            "- **Hints** are suggested fixes that trigger when specific measurements deviate together.\n"
            "- **Instrumental songs** have no vocal, so only the whole-mix measurements apply (loudness, dynamics, "
            "tonal balance, stereo width, top end, punch, pumping). You choose whether to compare against your references "
            "with their vocals removed, or their full mix.\n"
            "- A flag is not an error. If your references don't share the sound you want, the flag is telling you about your "
            "references. The numbers only say how your mix differs from them."
        )

    versions_df = repo.get_all_versions()
    if versions_df.empty:
        st.info("No analyzed versions yet. Use the Analyze page to run one.")
        return

    target = st.session_state.get("compare_target")
    songs = sorted(versions_df["song_id"].unique())
    song = st.selectbox("Song", songs, index=songs.index(target[0]) if target and target[0] in songs else 0)
    song_versions = versions_df[versions_df["song_id"] == song]
    version_opts = sorted(song_versions["version"].unique())
    version = st.selectbox(
        "Version", version_opts,
        index=version_opts.index(target[1]) if target and target[0] == song and target[1] in version_opts else 0,
    )
    version_id = int(song_versions[song_versions["version"] == version].iloc[0]["version_id"])

    song_info = repo.get_song(song) or {}
    style = song_info.get("style")
    instrumental = bool(song_info.get("instrumental"))

    checks_df = repo.get_checks(version_id)
    _render_safety_banner(checks_df)

    if not style:
        st.warning("Song has no known style; can't compare to an envelope.")
        return

    env_style = style
    if instrumental:
        st.info(
            "**Instrumental:** vocal measurements (vocal level, consonant clarity, reverb space, ducking) don't apply "
            "and aren't shown. Only whole-mix measurements are compared."
        )
        basis = st.radio(
            "Compare against",
            ["References with vocals removed", "References' full mix"],
            horizontal=True,
            help="Most references have vocals, and a vocal sits in the midrange of their spectrum and loudness. "
                 "'Vocals removed' measures each reference's Demucs accompaniment so you're compared like for like. "
                 "Pick 'full mix' only if your references are themselves instrumentals.",
        )
        if basis == "References with vocals removed":
            env_style = style + INSTRUMENTAL_SUFFIX
            st.caption(
                "Approximate: Demucs leaves a little vocal bleed in the accompaniment and slightly changes its "
                "character, so treat small deviations as noise."
            )

    envelopes = repo.get_envelopes(env_style)
    if not envelopes:
        if instrumental and env_style != style:
            st.warning(
                f"No vocals-removed envelope for style '{style}' yet. Use the References page to build envelopes "
                "(references analyzed before instrumental mode need rebuilding)."
            )
        else:
            st.warning(f"No envelopes built for style '{style}'. Use the References page to build them.")
        return

    features_df = repo.get_features(entity="version", entity_id=version_id)
    results = []
    for _idx, r in features_df.iterrows():
        env = envelopes.get((r["feature"], r["band"]))
        if env:
            results.append(evaluate(r["value"], env, cfg))

    st.subheader("Tonal balance vs references")
    st.caption(
        "Your mix's average spectrum (red line) against the band covering the middle 80% of your references "
        "(shaded). 0 dB is the average level between 250 Hz and 4 kHz, so this shows shape, not loudness. "
        "Where the line leaves the band, your mix is brighter/darker/bassier than nearly all references in that region."
    )
    env_df = pd.DataFrame([e.__dict__ for e in envelopes.values()])
    fig = ltas_vs_envelope_figure(features_df, env_df)
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Flags and watches")
    flagged = [r for r in results if r.level != "ok"]
    if flagged:
        flag_df = pd.DataFrame(
            [
                {
                    "measurement": feature_name(r.feature) + (f" [{r.band}]" if r.band else ""),
                    "level": r.level,
                    "your value": round(r.value, 2),
                    "z": round(r.z, 2),
                    "meaning": explain(r.feature, r.direction),
                    "feature": r.feature,
                }
                for r in flagged
            ]
        )
        st.dataframe(
            flag_df.sort_values("z", key=abs, ascending=False),
            use_container_width=True, hide_index=True,
            column_order=["measurement", "level", "your value", "z", "meaning"],
            column_config={"meaning": st.column_config.TextColumn("what it means", width="large")},
        )
        with st.expander("What each measurement is"):
            for feat in sorted({r.feature for r in flagged}):
                st.markdown(f"**{feature_name(feat)}** (`{feat}`): {what_it_measures(feat)}")
    else:
        st.success("Nothing outside p10-p90 or |z| > 1.5.")

    hints = build_hints(results, repo, version_id, cfg)
    if hints:
        st.subheader("Hints")
        st.caption("Suggested fixes, each with the measurements that triggered it.")
        rules = {r["id"]: r for r in cfg.get("hints", [])}
        by_feature = {r.feature: r for r in results}
        raw = {row["feature"]: row["value"] for _i, row in features_df.iterrows() if row["band"] == ""}
        for h in hints:
            st.markdown(f"**{h['message']}**")
            why = []
            for cond in rules.get(h["id"], {}).get("conditions", []):
                f = cond["feature"]
                if f in by_feature and cond["direction"] in ("low", "high"):
                    why.append(f"{feature_name(f)} is {cond['direction']} (z = {by_feature[f].z:+.1f})")
                elif f in raw:
                    why.append(f"{feature_name(f)} = {raw[f]:.2f}")
            if why:
                st.caption("Because: " + "; ".join(why))

    if instrumental:
        return

    st.subheader("Space vs sheen")
    st.caption(
        "The two things that define this sound. **Right = wetter vocal over a drier instrumental** (space contrast). "
        "**Up = brighter, airier top end** (air ratio). Grey dots are your references; the star is this mix. "
        "You want the star inside the cloud of references you like."
    )
    ref_features = repo.get_features_for_style(style, entity="ref")
    scatter_rows = []
    for ref_id, group in ref_features.groupby("entity_id"):
        sc = group[group["feature"] == "space_contrast"]["value"]
        ar = group[group["feature"] == "air_ratio"]["value"]
        if len(sc) and len(ar):
            scatter_rows.append({"entity": "ref", "space_contrast": sc.iloc[0], "air_ratio": ar.iloc[0], "label": f"ref {ref_id}"})
    my_sc = features_df[features_df["feature"] == "space_contrast"]["value"]
    my_ar = features_df[features_df["feature"] == "air_ratio"]["value"]
    if len(my_sc) and len(my_ar):
        scatter_rows.append({"entity": "yours", "space_contrast": my_sc.iloc[0], "air_ratio": my_ar.iloc[0], "label": f"{song} {version}"})
    if scatter_rows:
        st.plotly_chart(space_sheen_scatter(pd.DataFrame(scatter_rows)), use_container_width=True)


def _render_safety_banner(checks_df: pd.DataFrame) -> None:
    if checks_df.empty:
        st.info("No peak safety checks recorded.")
        return
    if (checks_df["level"] == "fail").any():
        fails = checks_df[checks_df["level"] == "fail"]
        st.error(f"Peak safety: {len(fails)} FAIL result(s). {', '.join(fails['check_name'].unique())}")
    elif (checks_df["level"] == "warn").any():
        st.warning("Peak safety: warnings present.")
    else:
        st.success("Peak safety: all checks pass.")
