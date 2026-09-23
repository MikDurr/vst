"""References page: per-style list, leave-one-out results, feature distributions."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from mixlens.compare.deviation import classify_level
from mixlens.compare.envelope import leave_one_out_audit
from mixlens.io.sidecar import load_references_yaml


def render(repo, cfg, project_root) -> None:
    st.header("References")

    entries = load_references_yaml(project_root / "references")
    if not entries:
        st.info("No references registered. Run `mixlens ref add references/<style>/*.flac --style <style>`.")
        return

    styles = sorted({e.style for e in entries})
    style = st.selectbox("Style", styles)
    style_entries = [e for e in entries if e.style == style]

    st.subheader(f"{len(style_entries)} references")
    st.dataframe(
        pd.DataFrame([{"path": e.path, "artist": e.artist, "title": e.title, "note": e.note} for e in style_entries]),
        use_container_width=True,
    )

    df = repo.get_features_for_style(style, entity="ref")
    if df.empty:
        st.warning("No analyzed features for this style yet. Run `mixlens ref build-envelopes`.")
        return

    st.subheader("Leave-one-out audit")
    audit_df = leave_one_out_audit(df, style, lambda v, env: classify_level(v, env, cfg))
    st.dataframe(audit_df.sort_values("n_flags", ascending=False), use_container_width=True)
    st.caption("References with more than 3 flags may belong to another style, or be worth dropping.")

    st.subheader("Feature distributions")
    scalar_features = sorted(df[df["band"] == ""]["feature"].unique())
    feature = st.selectbox("Feature", scalar_features)
    sub = df[(df["feature"] == feature) & (df["band"] == "")]
    st.plotly_chart(px.histogram(sub, x="value", title=feature), use_container_width=True)
