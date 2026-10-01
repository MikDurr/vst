"""References page: the songs your mixes are measured against."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

import jobs
import theme
import widgets
from mixlens.compare.deviation import classify_level
from mixlens.compare.envelope import leave_one_out_audit
from mixlens.io.ingest import save_references
import re

from mixlens.io.sidecar import load_references_yaml, remove_reference, update_reference_meta
from mixlens.pipeline import ACCOMPANIMENT_TAG, analyze_reference, build_style_envelopes


def render(repo, cfg, project_root) -> None:
    theme.page_header("References", "The songs whose mix you want yours to sit near.")
    references_dir: Path = project_root / "references"

    theme.callout(
        "<b>References belong to a style, not to a song.</b> Pick a style, add the songs whose <i>mix</i> you love "
        "(8 to 20 is ideal), and every song of that style gets compared against them. "
        "Choose them for how they're mixed (vocal blend, reverb, sheen), not just because you like the song."
    )

    style = widgets.style_picker("Genre / sound", "ref_style", cfg, repo, project_root)
    entries = [e for e in load_references_yaml(references_dir) if e.style == style]

    _render_add(references_dir, style, expanded=not entries, project_root=project_root)

    if not entries:
        st.caption(f"No references for '{style}' yet.")
        return

    st.subheader(f"{len(entries)} reference{'s' if len(entries) != 1 else ''} in '{style}'")
    _render_editor(repo, references_dir, entries, style)
    if len(entries) < 8:
        st.caption(f"8 to 20 references is ideal. With only {len(entries)}, treat the comparison as a rough guide.")

    _render_analyze(repo, cfg, references_dir, style, entries)

    df = repo.get_features_for_style(style, entity="ref")
    if df.empty:
        return
    with st.expander("Check for odd one out"):
        st.caption("Scores each reference against all the others. One with more than 3 flags probably belongs to a different style, or is worth dropping.")
        audit = leave_one_out_audit(df, style, lambda v, env: classify_level(v, env, cfg))
        st.dataframe(audit.sort_values("n_flags", ascending=False), use_container_width=True, hide_index=True)
    with st.expander("See how your references are spread"):
        feats = sorted(df[df["band"] == ""]["feature"].unique())
        feat = st.selectbox("Measurement", feats, key="ref_dist_feature")
        st.plotly_chart(
            theme.style_figure(px.histogram(df[(df["feature"] == feat) & (df["band"] == "")], x="value", title=feat)),
            use_container_width=True,
        )


STEM_LIKE = re.compile(r"__(mix|vox_dry|vox_wet|inst)\.", re.I)


def _looks_like_your_own(name: str, project_root: Path) -> bool:
    """Stems and bounces of your own songs make poor references."""
    own = {p.name for p in (project_root / "mixes").glob("*/*.wav")}
    return bool(STEM_LIKE.search(name)) or name in own


def _render_add(references_dir: Path, style: str, expanded: bool, project_root: Path) -> None:
    with st.expander(f"Add references to '{style}'", expanded=expanded):
        st.caption("Full, untouched songs: WAV or FLAC, or 256 kbps+ AAC / 320 kbps MP3. Don't trim or normalise them.")
        found = widgets.file_source("ref_src", label="Drop reference songs here")
        names = list(found)
        own = [n for n in names if _looks_like_your_own(n, project_root)]
        if own:
            st.warning("These look like your own stems or mixes, not references, so they're left out unless you add them back: " + ", ".join(own))
        picked = st.multiselect("Which of these are references?", names, default=[n for n in names if n not in own]) if names else []
        sources = {n: found[n] for n in picked}
        if st.button(f"Add {len(sources) or ''} song{'s' if len(sources) != 1 else ''}", disabled=not sources, type="primary"):
            added = save_references(references_dir, style, [(n, load()) for n, load in sources.items()])
            st.session_state.pop("_ref_src_cache", None)
            st.toast(f"Added {len(added)} reference(s)." if added else "Those songs are already in the library.")
            st.rerun()


def _render_editor(repo, references_dir: Path, entries: list, style: str) -> None:
    st.caption("Double-click to add the artist, title and a note about why it's in the set. Tick 'remove' to take one out.")
    df = pd.DataFrame([{"remove": False, "file": e.path, "artist": e.artist, "title": e.title, "note": e.note} for e in entries])
    edited = st.data_editor(df, use_container_width=True, disabled=["file"], hide_index=True, key="ref_table_editor")
    meta_changed = not edited.drop(columns="remove").equals(df.drop(columns="remove"))
    to_remove = edited[edited["remove"]]["file"].tolist()
    c1, c2, _ = st.columns([1.2, 1.6, 4])
    if meta_changed and c1.button("Save changes"):
        for _i, row in edited.iterrows():
            update_reference_meta(references_dir, row["file"], row["artist"], row["title"], row["note"])
        st.toast("Saved.")
        st.rerun()
    if to_remove and c2.button(f"Remove {len(to_remove)} selected"):
        for path in to_remove:
            remove_reference(references_dir, path)
            repo.delete_ref(path)
        build_style_envelopes(repo, style)  # quick: no audio work, just re-summarises what's left
        st.toast(f"Removed {len(to_remove)}.")
        st.rerun()
    over = edited["artist"].replace("", pd.NA).dropna().value_counts()
    over = over[over > 3]
    if len(over):
        st.warning("More than 3 songs by: " + ", ".join(over.index) + ". The range will reflect one engineer's fingerprint.")


def _render_analyze(repo, cfg, references_dir: Path, style: str, entries: list) -> None:
    st.subheader("Measure them")
    known = set(repo.list_refs(style)["path"])
    known_acc = set(repo.list_refs(style + "::instrumental")["path"])
    stale = repo.refs_missing_feature(style, "stem_level")  # measured before instrument balance existed
    todo = [e for e in entries if e.path not in known or e.path + ACCOMPANIMENT_TAG not in known_acc
            or e.path in stale or e.path + ACCOMPANIMENT_TAG in stale]
    done = len(entries) - len(todo)
    busy = jobs.is_running("references")

    theme.callout(
        f"<b>{done} of {len(entries)} measured.</b> Measuring takes a minute or two per song. Each reference is split into drums, bass, "
        "synths/guitars/pads and vocals, then measured twice: as it is (used for songs with vocals) and with the vocals "
        "stripped out (used for instrumentals), so there's nothing to choose later. Run it again whenever you add songs, "
        "or when the app gains a new kind of analysis."
    )
    redo = st.checkbox("Re-measure all of them, even ones already done", key="ref_remeasure") if not todo else False
    targets = entries if redo else todo
    label = f"Measure {len(targets)} reference{'s' if len(targets) != 1 else ''}" if targets else "All references are measured"
    if st.button(label, type="primary", disabled=busy or not targets):
        cache = references_dir.parent / ".cache"

        def run() -> str:
            for entry in targets:
                analyze_reference(entry, references_dir, cfg, repo, cache)
            build_style_envelopes(repo, style)
            return f"{len(targets)} reference(s) measured. '{style}' comparisons are ready."

        jobs.submit("references", f"Measuring {len(targets)} '{style}' references", run,
                    done_label=f"'{style}' references are measured")
        st.rerun()
