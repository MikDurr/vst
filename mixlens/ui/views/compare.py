"""Compare page: what to do next first, then the numbers behind it."""
from __future__ import annotations

import pandas as pd
import streamlit as st

import theme
from mixlens.compare.glossary import ACTIONS, explain, feature_name, format_value, what_it_measures
from mixlens.compare.dynamics import PLR_CUTS, Z_CUTS, summarize_dynamics
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

    _render_safety(repo.get_checks(version_id))
    _render_dynamics(repo, version_id, range_key)

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
            {"measurement": feature_name(r.feature) + (f" ({r.band.replace('Hz', ' Hz')})" if r.band else ""),
             "how far off": {"flag": "clearly", "watch": "a bit"}[r.level],
             "you": format_value(r.feature, r.value),
             "your references": (f"{format_value(r.feature, r.ref_low)} to {format_value(r.feature, r.ref_high)}"
                                 if r.ref_low is not None else ""),
             "meaning": explain(r.feature, r.direction), "_z": abs(r.z)}
            for r in flagged
        ]).sort_values("_z", ascending=False).drop(columns="_z")
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


def _render_safety(checks: pd.DataFrame) -> None:
    """Always-visible peak safety line, so clipping and true peak never hide in a sub-page."""
    if checks.empty:
        return
    mix = checks[checks["stem"] == "mix"]
    def val(name):
        r = mix[mix["check_name"] == name]
        return None if r.empty else r.iloc[0]
    tp, clip, isp = val("true_peak"), val("clip_runs"), val("isp_overs")
    bad = [c for c in (tp, clip, isp) if c is not None and c["level"] == "fail"]
    warn = [c for c in (tp,) if c is not None and c["level"] == "warn"]
    state = "fail" if bad else "warn" if warn else "ok"
    parts = []
    if tp is not None:
        parts.append(f"true peak {tp['value']:.1f} dBTP")
    if clip is not None:
        parts.append("clipping found" if clip["level"] == "fail" else "no clipping")
    chip = {"ok": ("ok", "Peaks safe"), "warn": ("check", "Peaks close to the limit"), "fail": ("fix", "Peak problem")}[state]
    st.markdown(f'<p class="summary-line"><span class="chip {chip[0]}">{chip[1]}</span> &nbsp;{" · ".join(parts)}</p>', unsafe_allow_html=True)


def _render_dynamics(repo, version_id: int, range_key: str) -> None:
    """How compressed is it? One verdict, a gauge, then the measurements behind it."""
    feats = repo.get_features(entity="version", entity_id=version_id)
    values = {(r["feature"], r["band"]): float(r["value"]) for _i, r in feats.iterrows()}
    summary = summarize_dynamics(values, repo.get_envelopes(range_key))
    if summary is None:
        return
    st.subheader("Dynamics")
    st.caption("How compressed the mix is. Compression can't be read off the audio directly, so this looks at its "
               "effects: flattened short-term dynamics, peaks pinned to the average, lost punch and pumping.")
    if summary.basis == "references":
        theme.dynamics_card(summary, Z_CUTS, -3.0, 3.0)
    else:
        theme.dynamics_card(summary, PLR_CUTS, 3.0, 18.0)

    extra = [f"Vocal: {v}" for v in summary.vocal]
    if summary.pumping and summary.pumping.status == "pumping":
        extra.append("Pumping: the mix ducks after each kick more than your references do. " + ACTIONS[("pump_depth", "high")])
    for line in extra:
        st.markdown(f"- {line}")

    def table(rows):
        return pd.DataFrame([{
            "measurement": r.name, "you": format_value(r.feature, r.value),
            "your references": (f"{format_value(r.feature, r.ref_low)} to {format_value(r.feature, r.ref_high)}" if r.ref_low is not None else "-"),
            "result": r.status or "-",
        } for r in rows])

    if summary.rows or summary.bands:
        with st.expander("The measurements behind the verdict"):
            st.dataframe(table(summary.rows + summary.bands + ([summary.pumping] if summary.pumping else [])),
                         use_container_width=True, hide_index=True)
    if summary.sections:
        st.markdown("##### By section")
        if summary.section_note:
            st.markdown(summary.section_note)
        st.dataframe(pd.DataFrame([{
            "section": s["section"], "loudness": f"{s['loudness']:.1f} LUFS" if s["loudness"] is not None else "-",
            "micro-dynamics": f"{s['crest']:.1f} dB" if s["crest"] is not None else "-", "result": s["status"] or "-",
        } for s in summary.sections]), use_container_width=True, hide_index=True)
