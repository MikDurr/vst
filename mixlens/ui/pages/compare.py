"""Compare page: peak-safety banner, LTAS vs envelope, flag table with hints,
CSI timeline, space vs sheen scatter."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from mixlens.compare.deviation import evaluate
from mixlens.pipeline import build_hints

from plots import csi_timeline_figure, ltas_vs_envelope_figure, space_sheen_scatter


def render(repo, cfg) -> None:
    st.header("Compare")

    versions_df = repo.get_all_versions()
    if versions_df.empty:
        st.info("No analyzed versions yet. Run `mixlens analyze <mix_dir> --version <v>` first.")
        return

    songs = sorted(versions_df["song_id"].unique())
    song = st.selectbox("Song", songs)
    song_versions = versions_df[versions_df["song_id"] == song]
    version = st.selectbox("Version", sorted(song_versions["version"].unique()))
    version_id = int(song_versions[song_versions["version"] == version].iloc[0]["version_id"])

    with repo.cursor() as cur:
        cur.execute("SELECT style FROM songs WHERE song_id=?", (song,))
        row = cur.fetchone()
    style = row[0] if row else None

    checks_df = repo.get_checks(version_id)
    _render_safety_banner(checks_df)

    if not style:
        st.warning("Song has no known style; can't compare to an envelope.")
        return

    envelopes = repo.get_envelopes(style)
    if not envelopes:
        st.warning(f"No envelopes built for style '{style}'. Run `mixlens ref build-envelopes`.")
        return

    features_df = repo.get_features(entity="version", entity_id=version_id)
    results = []
    for _idx, r in features_df.iterrows():
        env = envelopes.get((r["feature"], r["band"]))
        if env:
            results.append(evaluate(r["value"], env, cfg))

    st.subheader("LTAS vs style envelope")
    env_df = pd.DataFrame([e.__dict__ for e in envelopes.values()])
    fig = ltas_vs_envelope_figure(features_df, env_df)
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Flags and watches")
    flagged = [r for r in results if r.level != "ok"]
    if flagged:
        flag_df = pd.DataFrame(
            [{"feature": r.feature, "band": r.band, "value": r.value, "z": r.z, "level": r.level} for r in flagged]
        )
        st.dataframe(flag_df.sort_values("z", key=abs, ascending=False), use_container_width=True)
    else:
        st.success("Nothing outside p10-p90 or |z| > 1.5.")

    hints = build_hints(results, repo, version_id, cfg)
    if hints:
        st.subheader("Hints")
        for h in hints:
            st.markdown(f"- {h['message']}")

    st.subheader("Space vs sheen")
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
