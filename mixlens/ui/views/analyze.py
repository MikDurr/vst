"""Analyze page: run peak checks or the full analysis pipeline on a mix
version, from the UI -- no CLI needed for the day-to-day `check`/`analyze` loop."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from mixlens.checks.peaks import CheckResult, any_fail
from mixlens.io.sidecar import load_song_yaml
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
    if not songs:
        st.info(
            "No songs found under `mixes/`. Export the four stems "
            "(`{song}__{version}__{mix,vox_dry,vox_wet,inst}.wav`) plus a "
            "`song.yaml` into `mixes/<song>/` first -- see README.md."
        )
        return

    song_name = st.selectbox("Song", sorted(songs.keys()))
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
