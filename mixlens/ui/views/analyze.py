"""Analyze page: run peak checks or the full analysis pipeline on a mix
version, from the UI -- no CLI needed for the day-to-day `check`/`analyze` loop."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from mixlens.checks.peaks import CheckResult, any_fail
from mixlens.io.ingest import AUDIO_TYPES, save_sections, save_stems
from mixlens.io.sidecar import load_song_yaml
from mixlens.io.stems import STEM_NAMES
from mixlens.pipeline import analyze_version, run_checks_only


def _discover_songs(project_root: Path) -> dict[str, Path]:
    mixes_dir = project_root / "mixes"
    if not mixes_dir.exists():
        return {}
    return {d.name: d for d in sorted(mixes_dir.iterdir()) if d.is_dir() and (d / "song.yaml").exists()}


def _discover_versions(song_dir: Path) -> list[str]:
    versions = set()
    for p in song_dir.glob("*.wav"):
        parts = p.stem.split("__")
        if len(parts) == 3:
            versions.add(parts[1])
    return sorted(versions)


def render(repo, cfg, project_root: Path) -> None:
    st.header("Analyze")

    songs = _discover_songs(project_root)
    _render_upload(repo, project_root, songs, expanded=not songs)
    if not songs:
        return

    pending = st.session_state.get("analyze_pending")
    song_keys = sorted(songs.keys())
    song_name = st.selectbox(
        "Song", song_keys, index=song_keys.index(pending[0]) if pending and pending[0] in song_keys else 0
    )
    song_dir = songs[song_name]
    try:
        song_info = load_song_yaml(song_dir)
    except Exception as e:
        st.error(f"Couldn't read song.yaml: {e}")
        return
    st.caption(f"style: **{song_info.style}** · bpm: **{song_info.bpm}**")

    versions = _discover_versions(song_dir)
    if not versions:
        st.warning("No `{song}__{version}__{stem}.wav` files found in this folder.")
        return

    existing_versions_df = repo.get_versions_for_song(song_name)
    analyzed_versions = set(existing_versions_df["version"]) if not existing_versions_df.empty else set()

    version = st.selectbox(
        "Version",
        versions,
        index=versions.index(pending[1]) if pending and pending[0] == song_name and pending[1] in versions else 0,
        format_func=lambda v: f"{v}  (already analyzed)" if v in analyzed_versions else f"{v}  (not analyzed)",
    )

    col1, col2 = st.columns(2)
    with col1:
        st.caption("Peak safety only -- fast, no Demucs.")
        if st.button("Run peak checks", use_container_width=True):
            with st.spinner("Running peak safety checks..."):
                try:
                    results, _song = run_checks_only(song_dir, version, cfg)
                except Exception as e:
                    st.error(f"Check failed: {e}")
                else:
                    _render_check_results(results)

    with col2:
        st.caption("Checks + all features (splits with Demucs -- slower).")
        force = st.checkbox("Force re-analyze even if stems are unchanged", value=False)
        if st.button("Run full analysis", type="primary", use_container_width=True):
            with st.spinner("Splitting with Demucs and extracting features -- this can take a minute or two..."):
                try:
                    result = analyze_version(song_dir, version, cfg, repo, project_root / ".cache", force=force)
                except Exception as e:
                    st.error(f"Analysis failed: {e}")
                else:
                    if result.get("skipped"):
                        st.info(f"Skipped: {result['reason']} (stems unchanged since the last analysis; check 'Force' to redo it).")
                    else:
                        st.success(
                            f"Analyzed {result['song']} {result['version']}: "
                            f"{result['n_checks']} checks, {result['n_features']} feature rows. "
                            "See it on the Compare or History page."
                        )
                        st.rerun()


def _render_check_results(results: list[CheckResult]) -> None:
    df = pd.DataFrame(
        [{"check": r.check, "level": r.level, "value": r.value, "t_sec": r.t_sec, "bar": r.bar, "stem": r.stem} for r in results]
    )

    def _row_style(row):
        color = {"fail": "background-color: rgba(220,50,50,0.25)", "warn": "background-color: rgba(220,180,50,0.25)"}
        return [color.get(row["level"], "")] * len(row)

    st.dataframe(df.style.apply(_row_style, axis=1), use_container_width=True)

    if any_fail(results):
        st.error("Peak safety: at least one FAIL.")
    elif (df["level"] == "warn").any():
        st.warning("Peak safety: warnings present, no fails.")
    else:
        st.success("Peak safety: all checks pass.")


STEM_HELP = {
    "mix": "Full bounce, master chain ON",
    "vox_dry": "Vocal bus with inline FX, sends muted, master bypassed",
    "vox_wet": "Vocal reverb/delay returns only, master bypassed",
    "inst": "Everything except vocals and vocal returns, master bypassed",
}


def _render_upload(repo, project_root: Path, songs: dict[str, Path], expanded: bool) -> None:
    with st.expander("Upload a new mix version", expanded=expanded):
        st.caption(
            "Export four bounces from your DAW (same length, all starting at bar 1) "
            "and drop them in. Files are renamed and stored for you."
        )
        existing = ["(new song)"] + sorted(songs.keys())
        choice = st.selectbox("Song", existing, key="up_song_choice")

        defaults = {"style": "dream", "bpm": 120.0}
        if choice != "(new song)":
            info = load_song_yaml(songs[choice])
            defaults = {"style": info.style, "bpm": info.bpm}

        c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
        song = c1.text_input("Song name", value="" if choice == "(new song)" else choice,
                             disabled=choice != "(new song)", key="up_song")
        version = c2.text_input("Version", value="v1", key="up_version")
        styles = ["dream", "hyperpop", "electroclash"]
        style = c3.selectbox("Style", styles, index=styles.index(defaults["style"]) if defaults["style"] in styles else 0,
                             key="up_style")
        bpm = c4.number_input("BPM", min_value=40.0, max_value=260.0, value=float(defaults["bpm"]), key="up_bpm")

        uploads = {}
        cols = st.columns(2)
        for i, stem in enumerate(STEM_NAMES):
            with cols[i % 2]:
                uploads[stem] = st.file_uploader(
                    f"{stem}", type=AUDIO_TYPES, help=STEM_HELP[stem], key=f"up_{stem}"
                )

        st.markdown("**Sections** (optional, in seconds -- enables per-section vocal level)")
        sections_df = st.data_editor(
            pd.DataFrame({"section": ["verse1", "hook1"], "start": [0.0, 0.0], "end": [0.0, 0.0]}),
            num_rows="dynamic", use_container_width=True, key="up_sections",
        )

        ready = all(uploads.values())
        name = (choice if choice != "(new song)" else song).strip()
        if st.button("Save stems", type="primary", disabled=not ready or not name):
            try:
                song_dir = save_stems(
                    project_root / "mixes", name, version, style, bpm,
                    {stem: f.getvalue() for stem, f in uploads.items()},
                )
                secs = {
                    str(r["section"]): (r["start"], r["end"])
                    for _, r in sections_df.iterrows()
                    if r["section"] and r["end"] > r["start"]
                }
                if secs:
                    save_sections(song_dir, secs)
            except Exception as e:
                st.error(f"Couldn't save: {e}")
            else:
                st.session_state["analyze_pending"] = (name, version.strip())
                st.success(f"Saved {name} {version}. Pick it below and run the analysis.")
                st.rerun()
        elif not ready:
            st.caption("Waiting on: " + ", ".join(s for s, f in uploads.items() if not f))
