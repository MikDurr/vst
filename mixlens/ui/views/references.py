"""References page: register reference tracks, build envelopes, per-style
list, leave-one-out results, feature distributions -- no CLI needed."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from mixlens.compare.deviation import classify_level
from mixlens.compare.envelope import build_envelopes, leave_one_out_audit
from mixlens.io.sidecar import load_references_yaml, register_references
from mixlens.pipeline import analyze_reference

KNOWN_STYLES = ["dream", "hyperpop", "electroclash"]


def render(repo, cfg, project_root) -> None:
    st.header("References")

    references_dir = project_root / "references"
    entries = load_references_yaml(references_dir)
    known_styles = sorted(set(KNOWN_STYLES) | {e.style for e in entries})

    _render_add_references(references_dir, known_styles, entries)

    if not entries:
        st.info("No references registered yet. Use \"Add references\" above.")
        return

    styles = sorted({e.style for e in entries})
    style = st.selectbox("Style", styles)
    style_entries = [e for e in entries if e.style == style]

    st.subheader(f"{len(style_entries)} references")
    st.dataframe(
        pd.DataFrame([{"path": e.path, "artist": e.artist, "title": e.title, "note": e.note} for e in style_entries]),
        use_container_width=True,
    )
    if len(style_entries) < 8:
        st.caption(
            f"Only {len(style_entries)} references for '{style}' -- the spec recommends 12-20; "
            "fewer than 8 makes the percentiles meaningless."
        )

    _render_build_envelopes(repo, cfg, references_dir, style, style_entries)

    df = repo.get_features_for_style(style, entity="ref")
    if df.empty:
        st.warning("No analyzed features for this style yet. Use \"Build envelopes\" above.")
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


def _render_add_references(references_dir: Path, known_styles: list[str], entries: list) -> None:
    with st.expander("Add references", expanded=not entries):
        st.caption(
            "Point this at a folder of full, untouched reference songs under "
            "`references/<style>/` (WAV/FLAC, or 256kbps+ AAC / 320kbps MP3). "
            "This only registers the files in references.yaml -- it doesn't "
            "analyze them yet."
        )
        col1, col2 = st.columns([1, 2])
        with col1:
            style = st.selectbox("Style", known_styles, key="add_ref_style")
        with col2:
            default_pattern = str(Path("references") / style / "*.flac")
            pattern = st.text_input("File glob (relative to the project root)", value=default_pattern, key="add_ref_pattern")

        if st.button("Register matching files"):
            added = register_references([pattern], style, references_dir)
            if added:
                st.success(f"Registered {len(added)} new reference(s): " + ", ".join(e.path for e in added))
                st.rerun()
            else:
                st.warning("No new files matched -- either none were found, or they're already registered.")


def _render_build_envelopes(repo, cfg, references_dir: Path, style: str, style_entries: list) -> None:
    with st.expander("Build envelopes", expanded=False):
        st.caption(
            f"Analyzes every '{style}' reference not yet in the database (splits "
            "with Demucs), then rebuilds the style envelope used by the Compare page."
        )
        if st.button(f"Build envelopes for '{style}'", type="primary"):
            progress = st.progress(0.0, text="Starting...")
            errors = []
            for i, entry in enumerate(style_entries):
                progress.progress(i / max(len(style_entries), 1), text=f"Analyzing {entry.path}...")
                try:
                    analyze_reference(entry, references_dir, cfg, repo, references_dir.parent / ".cache")
                except Exception as e:
                    errors.append(f"{entry.path}: {e}")
            progress.progress(1.0, text="Building envelope...")

            df = repo.get_features_for_style(style, entity="ref")
            if df.empty:
                st.error("No features were extracted -- nothing to build an envelope from.")
            else:
                envelopes = build_envelopes(df)
                repo.replace_envelopes(style, envelopes)
                st.success(f"Built {len(envelopes)} envelope entries for '{style}'.")

            for msg in errors:
                st.error(f"Failed: {msg}")

            if not errors:
                st.rerun()
