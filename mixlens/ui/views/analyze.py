"""Analyze page: run peak checks or the full analysis pipeline on a mix
version, from the UI -- no CLI needed for the day-to-day `check`/`analyze` loop."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from mixlens.checks.peaks import CheckResult, any_fail
from mixlens.io.ingest import AUDIO_TYPES, assign_stems, guess_song_version, save_sections, save_stems
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
    _render_upload(repo, cfg, project_root, songs, expanded=not songs)
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
                        _go_to_compare(song_name, version)


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


def _go_to_compare(song: str, version: str) -> None:
    """Jump to the Compare page with this version selected."""
    st.session_state["nav_target"] = "Compare"
    st.session_state["compare_target"] = (song, version)
    st.rerun()


def _render_upload(repo, cfg, project_root: Path, songs: dict[str, Path], expanded: bool) -> None:
    with st.expander("Upload a new mix version", expanded=expanded):
        st.caption(
            "Drop all four bounces at once (same length, all starting at bar 1): full mix with master on, "
            "vocal dry, vocal reverb/delay returns only, and instrumental. Names like `vox_dry`, `wet`, "
            "`inst`, `mix` are recognised; fix any wrong guess below."
        )
        with st.expander("What are the four stems?"):
            st.markdown(
                "Bounce all four from the start of bar 1, same length. Master chain is **bypassed on every stem except `mix`**.\n\n"
                "| Stem | Contains | How to bounce |\n|---|---|---|\n"
                "| `mix` | Everything, final master chain **on** (what listeners hear) | Normal final bounce |\n"
                "| `vox_dry` | The vocal after its normal channel processing (EQ, comp, de-ess, tuning, distortion) "
                "but **without** reverb/delay | Vocal bus, send returns muted |\n"
                "| `vox_wet` | **Only** the vocal reverb/delay returns, no dry vocal in it | Solo the aux returns, mute the vocal's direct signal |\n"
                "| `inst` | Everything except vocals and the vocal returns, keeping its own processing | Mute vocals and vocal auxes |\n\n"
                "Why split it: dry + wet lets MixLens judge your reverb separately (how wet it is, whether it ducks, "
                "whether it washes out consonants). Bypassing the master keeps the limiter from smearing those measurements."
            )
        files = st.file_uploader("Stems", type=AUDIO_TYPES, accept_multiple_files=True, key="up_files")

        by_name = {f.name: f for f in files or []}
        guesses = assign_stems(list(by_name))
        parsed = guess_song_version(list(by_name))
        if parsed and st.session_state.get("_up_parsed") != parsed:
            st.session_state["_up_parsed"] = parsed
            st.session_state["up_song_choice"] = parsed[0] if parsed[0] in songs else "(new song)"
            st.session_state["up_song"] = parsed[0]
            st.session_state["up_version"] = parsed[1]

        slots = ["(ignore)"] + list(STEM_NAMES)
        assignment: dict[str, str] = {}
        if by_name:
            st.markdown("**Which file is which**")
            cols = st.columns(min(len(by_name), 4))
            for i, name in enumerate(by_name):
                g = guesses[name]
                choice = cols[i % len(cols)].selectbox(
                    name, slots, index=slots.index(g) if g else 0, key=f"up_assign_{name}"
                )
                if choice != "(ignore)":
                    assignment[choice] = name

        chosen = [n for n in by_name if n in assignment.values()]
        dupes = len(chosen) != len(set(assignment.values())) or len(assignment) != len(chosen)
        missing = [s for s in STEM_NAMES if s not in assignment]
        if by_name:
            if dupes:
                st.error("Two files are assigned to the same slot.")
            elif missing:
                st.warning("Still need: " + ", ".join(missing))

        choice = st.selectbox("Song", ["(new song)"] + sorted(songs), key="up_song_choice")
        defaults = {"style": "dream", "bpm": 120.0}
        if choice != "(new song)":
            info = load_song_yaml(songs[choice])
            defaults = {"style": info.style, "bpm": info.bpm}

        c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
        song = c1.text_input("Song name", disabled=choice != "(new song)", key="up_song")
        st.session_state.setdefault("up_version", "v1")
        version = c2.text_input("Version", key="up_version")
        styles = ["dream", "hyperpop", "electroclash"]
        style = c3.selectbox(
            "Style", styles, index=styles.index(defaults["style"]) if defaults["style"] in styles else 0, key="up_style"
        )
        bpm = c4.number_input("BPM", min_value=40.0, max_value=260.0, value=float(defaults["bpm"]), key="up_bpm")

        st.markdown("**Sections** (optional, in seconds -- enables per-section vocal level)")
        sections_df = st.data_editor(
            pd.DataFrame({"section": ["verse1", "hook1"], "start": [0.0, 0.0], "end": [0.0, 0.0]}),
            num_rows="dynamic", use_container_width=True, key="up_sections",
        )

        name = (choice if choice != "(new song)" else song).strip()
        ready = by_name and not dupes and not missing and bool(name)
        col_a, col_b = st.columns(2)
        save_only = col_a.button("Save stems", disabled=not ready, use_container_width=True)
        one_click = col_b.button("Save & analyze", type="primary", disabled=not ready, use_container_width=True)

        if save_only or one_click:
            try:
                song_dir = save_stems(
                    project_root / "mixes", name, version, style, bpm,
                    {stem: by_name[fname].getvalue() for stem, fname in assignment.items()},
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
                return
            version = version.strip()
            if one_click:
                with st.spinner("Splitting with Demucs and extracting features -- a minute or two..."):
                    try:
                        result = analyze_version(song_dir, version, cfg, repo, project_root / ".cache", force=True)
                    except Exception as e:
                        st.error(f"Saved, but analysis failed: {e}")
                        return
                _go_to_compare(name, version)
            st.session_state["analyze_pending"] = (name, version)
            st.success(f"Saved {name} {version}. Pick it below and run the analysis.")
            st.rerun()
