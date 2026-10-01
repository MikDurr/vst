"""References page: register reference tracks, build envelopes, per-style
list, leave-one-out results, feature distributions -- no CLI needed."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from mixlens.compare.deviation import classify_level
from mixlens.compare.envelope import leave_one_out_audit
from mixlens.io.ingest import AUDIO_TYPES, save_references
from mixlens.io.sidecar import load_references_yaml, update_reference_meta
from mixlens.pipeline import INSTRUMENTAL_SUFFIX, analyze_reference, build_style_envelopes

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
    _render_metadata_editor(references_dir, style_entries)
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
    with st.expander("Upload references", expanded=not entries):
        st.caption(
            "Full, untouched songs (WAV/FLAC, or 256kbps+ AAC / 320kbps MP3). "
            "Choose ones whose *mix* you want yours to sit near: 12-20 per style, "
            "max 3 per artist. Files are stored as-is under `references/<style>/`."
        )
        style = st.selectbox("Style", known_styles, key="add_ref_style")
        files = st.file_uploader(
            "Reference songs", type=AUDIO_TYPES, accept_multiple_files=True, key=f"add_ref_files_{style}"
        )
        if st.button("Add to library", disabled=not files):
            added = save_references(references_dir, style, [(f.name, f.getvalue()) for f in files])
            if added:
                st.success(f"Added {len(added)} reference(s). Fill in artist/title below, then build envelopes.")
                st.rerun()
            else:
                st.warning("Those files are already in the library.")


def _render_metadata_editor(references_dir: Path, style_entries: list) -> None:
    st.caption("Double-click a cell to edit artist / title / note. Notes help you remember why a track is in the set.")
    df = pd.DataFrame([{"path": e.path, "artist": e.artist, "title": e.title, "note": e.note} for e in style_entries])
    edited = st.data_editor(df, use_container_width=True, disabled=["path"], hide_index=True, key="ref_editor")
    if not edited.equals(df) and st.button("Save edits"):
        for _, row in edited.iterrows():
            update_reference_meta(references_dir, row["path"], row["artist"], row["title"], row["note"])
        st.success("Saved.")
        st.rerun()

    artists = edited["artist"].replace("", pd.NA).dropna().value_counts()
    over = artists[artists > 3]
    if len(over):
        st.warning("More than 3 tracks by: " + ", ".join(over.index) + " -- the envelope will reflect one engineer's fingerprint.")


def _render_build_envelopes(repo, cfg, references_dir: Path, style: str, style_entries: list) -> None:
    with st.expander("Build envelopes", expanded=False):
        st.caption(
            f"Analyzes every '{style}' reference not yet in the database (splits "
            "with Demucs), then rebuilds the style envelope used by the Compare page. It also measures each "
            "reference with its vocals removed (the Demucs accompaniment), which is what an *instrumental* song "
            "is compared against."
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

            built = build_style_envelopes(repo, style)
            if not built:
                st.error("No features were extracted -- nothing to build an envelope from.")
            for key, n in built.items():
                label = "vocals removed (for instrumentals)" if key.endswith(INSTRUMENTAL_SUFFIX) else "full mix"
                st.success(f"Built {n} envelope entries for '{style}' [{label}].")

            for msg in errors:
                st.error(f"Failed: {msg}")

            if not errors:
                st.rerun()
