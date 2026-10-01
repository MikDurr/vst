"""Analyze page: add the bounces for a mix, then analyze. Three clear steps:
the files, which song they belong to, and go."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

import jobs
import theme
import widgets
from mixlens.checks.peaks import any_fail
from mixlens.io.ingest import assign_stems, derive_wet, guess_song_version, save_sections, save_stems
from mixlens.io.sidecar import load_song_yaml
from mixlens.io.stems import STEM_NAMES
from mixlens.pipeline import analyze_version, recommendations_for, reference_range_key, run_checks_only


ROLE_LABELS = {
    "(ignore)": "Not part of this song", "mix": "Full mix", "vox_dry": "Vocal, dry (no reverb/delay)",
    "vox_wet": "Vocal effects only (reverb/delay)", "inst": "Instrumental", "vox_full": "Vocal with effects",
}
CHECK_NAMES = {
    "clip_runs": "Clipped samples", "true_peak": "True peak (dBTP)",
    "isp_overs": "Peaks over 0 dBTP between samples", "stem_headroom": "Stem peak level (dBFS)",
}


def _discover_songs(project_root: Path) -> dict[str, Path]:
    mixes_dir = project_root / "mixes"
    if not mixes_dir.exists():
        return {}
    return {d.name: d for d in sorted(mixes_dir.iterdir()) if d.is_dir() and (d / "song.yaml").exists()}


def _versions(song_dir: Path) -> list[str]:
    return sorted({p.stem.split("__")[1] for p in song_dir.glob("*.wav") if len(p.stem.split("__")) == 3})


def _next_version(song_dir: Path | None) -> str:
    existing = _versions(song_dir) if song_dir else []
    nums = [int(v[1:]) for v in existing if v[:1] == "v" and v[1:].isdigit()]
    return f"v{max(nums) + 1}" if nums else "v1"


STEMS_HELP = """\
| Stem | Contains |
|---|---|
| `mix` | Everything, final master chain **on** (what listeners hear) |
| `vox_dry` | The vocal after its normal channel processing (EQ, comp, de-ess, tuning, distortion), **without** reverb/delay |
| `vox_wet` | **Only** the vocal reverb/delay returns, no dry vocal in it |
| `inst` | Everything except vocals and the vocal returns, keeping its own processing |

**Instrumental song?** Tick "This song is an instrumental" and you only need `mix` (`inst` is optional). The vocal
measurements are skipped and the song is compared against your references with their vocals removed.

All four: same length, same start point (bar 1). The master chain is **bypassed on every stem except `mix`**.

**Why split it:** dry + wet lets MixLens judge your reverb separately (how wet it is, whether it ducks, whether it
washes out consonants). Bypassing the master keeps the limiter from smearing those measurements.
"""

LOGIC_HELP = """\
Logic has no "export a stem" button for this: you mute things and do a normal bounce, four times. Menu names are for
Logic Pro X / 10.x; always **listen to each bounce** before uploading.

**Instrumental song:** just bounce `mix` (master chain on) and tick "This song is an instrumental". Nothing else needed.

**Set up once**
1. Set the cycle range from bar 1 to the end of the song. Use the **same range for all four bounces**, so the files
   are the same length and start together.
2. Sort your tracks into three groups: **vocal tracks** (lead, doubles, ad-libs, harmonies), **vocal FX returns**
   (the reverb/delay/chorus aux tracks your vocal sends feed), and **everything else**.
3. Bounce with **File → Bounce → Project or Section** (Cmd-B): PCM, WAV, **24-bit**, sample rate matching your
   project, **Normalize: Off**, **Include Audio Tail: On**.
4. Use **mute**, not solo. Logic can keep an aux audible when you solo the track feeding it, so muting is more predictable.

**The bounces**

| Stem | What to do before bouncing |
|---|---|
| `mix` | Mute nothing, master chain **on**. A normal final bounce. |
| `inst` | Mute all vocal tracks **and** all vocal FX returns. Bypass the plug-ins on **Stereo Out**. |
| `vox_dry` | Mute everything that isn't a vocal track, and mute the vocal FX returns. Bypass Stereo Out plug-ins. |
| `vox_full` | Mute everything that isn't a vocal track, **leave the vocal FX returns on**. Bypass Stereo Out plug-ins. |

**`vox_wet`: easiest route.** Upload `vox_full` and `vox_dry`, leave `vox_wet` empty, and MixLens computes
`vox_wet = vox_full - vox_dry`. This only cancels cleanly if the bounces are sample-aligned and the vocal processing
is identical in both (reverbs with random modulation leave a small residual). MixLens refuses misaligned files and
warns if the result looks wrong.

**`vox_wet`: bounce it directly.** Mute the non-vocal tracks and keep the vocal FX returns on. Right-click each vocal
send level and choose **Pre Fader**, then pull the vocal tracks' own faders to -∞ so the sends keep feeding the
reverb while the dry vocal is silent. Bypass Stereo Out plug-ins and bounce.

**Check before uploading**
- `vox_dry` has no reverb tails. `vox_wet` has no dry words. `inst` has no vocal.
- All four files are the same length.
- If a reverb or delay is shared between the vocal and other instruments, split it into a vocal-only return first, otherwise
  the instruments' reverb ends up in the wrong stem.
"""




def _start_analysis(repo, cfg, project_root: Path, song_dir: Path, song: str, version: str, force: bool) -> None:
    """Run the analysis in the background so switching pages can't kill it."""
    cache = project_root / ".cache"

    def run() -> str:
        res = analyze_version(song_dir, version, cfg, repo, cache, force=force)
        if res.get("skipped"):
            return "Nothing changed since the last analysis."
        info = repo.get_song(song) or {}
        recs, _results, _has = recommendations_for(
            repo, cfg, res["version_id"], reference_range_key(info.get("style", ""), info.get("instrumental", False))
        )
        n_fix = sum(r.severity == "fix" for r in recs)
        n_check = sum(r.severity == "check" for r in recs)
        return f"{n_fix} thing{'s' if n_fix != 1 else ''} to fix, {n_check} to take a look at."

    jobs.submit("analyze", f"Analyzing {song} {version}", run, song=song, version=version,
                done_label=f"{song} {version} is analyzed")


def render(repo, cfg, project_root: Path) -> None:
    theme.page_header("Analyze", "Add your bounces, check the peaks, and get a list of what to fix.")
    songs = _discover_songs(project_root)

    _render_add(repo, cfg, project_root, songs)
    _render_library(repo, cfg, project_root, songs)


def _apply_pending_state(songs: dict[str, Path]) -> None:
    """Widget values can only be set before the widget is created, so changes
    requested mid-run are queued and applied here, at the top of the next run."""
    for key, value in st.session_state.pop("_up_pending", {}).items():
        st.session_state[key] = value
    pick = st.session_state.get("up_song_pick")
    if (st.session_state.get("up_song_mode") == "Add to an existing song" and pick in songs
            and st.session_state.get("_up_last_pick") != pick):
        info = load_song_yaml(songs[pick])
        st.session_state.update({
            "_up_last_pick": pick, "up_style": info.style, "up_bpm": float(info.bpm),
            "up_instrumental": bool(info.instrumental), "up_version": _next_version(songs[pick]),
        })


def _render_add(repo, cfg, project_root: Path, songs: dict[str, Path]) -> None:
    _apply_pending_state(songs)
    st.subheader("Add a mix")
    theme.callout(
        "<b>Three steps:</b> drop in your bounces, tell us which song they belong to, then analyze. "
        "Each time you re-bounce a song, add it as a new version (v1, v2, v3…) so you can see what changed."
    )

    # ---- files ----
    st.markdown("##### The bounces")
    with st.container(key="help"):
        with st.expander("What are the four stems?"):
            st.markdown(STEMS_HELP)
        with st.expander("How to export them from Logic Pro"):
            st.markdown(LOGIC_HELP)
    for w in st.session_state.pop("derive_warnings", []):
        st.warning("Derived vox_wet: " + w + " The stems were saved, but not analyzed automatically.")

    instrumental = st.checkbox(
        "This song has no vocals (instrumental)", key="up_instrumental",
        help="You only need the full mix. Vocal measurements are skipped and it is compared against your references "
             "with their vocals removed.",
    )
    sources = widgets.file_source("up_src", label="Drop your bounces here")
    names = list(sources)
    guesses = assign_stems(names)
    parsed = guess_song_version(names)
    if parsed and st.session_state.get("_up_parsed") != (parsed, tuple(names)):
        st.session_state["_up_parsed"] = (parsed, tuple(names))
        in_library = parsed[0] in songs
        st.session_state["_up_pending"] = {
            "up_song_mode": "Add to an existing song" if in_library else "Start a new song",
            **({"up_song_pick": parsed[0], "_up_last_pick": None} if in_library else {"up_song_name": parsed[0]}),
            "up_version": parsed[1],
        }
        st.rerun()

    if instrumental:
        theme.callout("<b>Instrumental:</b> only the full mix is needed. Vocal measurements are skipped, and Compare uses "
                      "your references with their vocals removed (approximate, as a little vocal bleed remains).")
        guesses = {n: (g if g in ("mix", "inst") else None) for n, g in guesses.items()}
        if "mix" not in guesses.values():
            if len(guesses) == 1:
                guesses = {n: "mix" for n in guesses}
            else:
                for n, g in guesses.items():
                    if g is None:
                        guesses[n] = "mix"
                        break

    slots = ["(ignore)", "mix", "inst"] if instrumental else ["(ignore)"] + list(STEM_NAMES) + ["vox_full"]
    assignment: dict[str, str] = {}
    if names:
        st.caption("We matched your files to their roles by name. Change any that look wrong.")
        cols = st.columns(min(len(names), 4))
        for i, name in enumerate(names):
            g = guesses[name]
            akey = f"up_assign_{name}_{int(instrumental)}"
            widgets.guard(akey, slots)
            st.session_state.setdefault(akey, g if g in slots else "(ignore)")
            picked = cols[i % len(cols)].selectbox(name, slots, key=akey, format_func=lambda s: ROLE_LABELS.get(s, s))
            if picked != "(ignore)":
                assignment[picked] = name

    chosen = [n for n in names if n in assignment.values()]
    dupes = len(chosen) != len(set(assignment.values())) or len(assignment) != len(chosen)
    derive = not instrumental and "vox_wet" not in assignment and "vox_full" in assignment
    needed = ("mix",) if instrumental else STEM_NAMES
    missing = [s for s in needed if s not in assignment and not (s == "vox_wet" and derive)]
    if names:
        if derive:
            st.info("No vox_wet given: it will be derived as vox_full minus vox_dry. Both bounces must start at the same point.")
        if dupes:
            st.error("Two files are assigned to the same role.")
        elif missing:
            st.warning("Still needed: " + ", ".join(missing))

    # ---- which song ----
    st.markdown("##### Which song is this?")
    if parsed:
        st.caption(f"From your file names we picked the song '{parsed[0]}' and version '{parsed[1]}'. Change them below if that's wrong.")
    options = ["Add to an existing song", "Start a new song"] if songs else ["Start a new song"]
    if st.session_state.get("up_song_mode") not in options:
        st.session_state["up_song_mode"] = options[-1]
    mode = st.radio("Song", options, horizontal=True, key="up_song_mode", label_visibility="collapsed")
    existing = mode == "Add to an existing song"

    if existing:
        widgets.guard("up_song_pick", songs)
        pick = st.selectbox("Song", sorted(songs), key="up_song_pick")
        name = pick
        st.caption("Style and BPM below are taken from the song; change them if they've changed.")
    else:
        name = st.text_input("Song name", key="up_song_name", placeholder="neon-altar",
                             help="Letters, numbers and dashes only.").strip()

    st.session_state.setdefault("up_version", "v1")
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        style = widgets.style_picker(
            "Genre / sound", "up_style", cfg, repo, project_root,
            help="The reference library this song is compared against. References belong to a style, not a song: "
                 "every song with the same style shares the same references.",
        )
    st.session_state.setdefault("up_bpm", 120.0)
    bpm = c2.number_input("BPM", min_value=40.0, max_value=260.0, key="up_bpm")
    version = c3.text_input("Version", key="up_version", help="Re-bounced the song? Use a new version name.")

    sections_df = None
    if not instrumental:
        with st.expander("Song sections (optional)"):
            st.caption("Where each section starts and ends, in bars as shown in Logic's ruler (counting from bar 1, 4/4). "
                       "Adds a vocal level for each section, e.g. verse 9 to 24. Add a row per section.")
            known = load_song_yaml(songs[name]).section_bars if existing and name in songs else {}
            start = pd.DataFrame(
                [{"section": n, "first bar": a, "last bar": b} for n, (a, b) in known.items()]
                or {"section": pd.Series([], dtype=str), "first bar": pd.Series([], dtype=int), "last bar": pd.Series([], dtype=int)}
            )
            sections_df = st.data_editor(
                start, num_rows="dynamic", use_container_width=True, key=f"up_sections_editor_{name or 'new'}",
                column_config={"first bar": st.column_config.NumberColumn(min_value=1, step=1, format="%d"),
                               "last bar": st.column_config.NumberColumn(min_value=1, step=1, format="%d")},
            )

    # ---- go ----
    clash = bool(name and version.strip()) and (project_root / "mixes" / name / f"{name}__{version.strip()}__mix.wav").exists()
    replace_ok = True
    if clash:
        st.warning(f"{name} {version.strip()} already exists. Pick a new version name, or tick the box to replace it.")
        replace_ok = st.checkbox(f"Replace {name} {version.strip()} with these files", key="up_replace")
    ready = bool(names) and not dupes and not missing and bool(name) and bool(version.strip()) and replace_ok
    b1, b2 = st.columns(2)
    save_only = b1.button("Save only", disabled=not ready, use_container_width=True)
    go = b2.button("Save and analyze", type="primary", disabled=not ready, use_container_width=True)
    if not ready:
        why = ("Add all the files" if (not names or missing) else "Two files share a role" if dupes else
               "Name the song" if not name else "Tick the box above to replace the existing version" if not replace_ok else "Give it a version name")
        st.caption(f"{why} to enable these buttons.")
    if not (save_only or go):
        return

    try:
        stem_bytes = {stem: sources[fname]() for stem, fname in assignment.items() if stem != "vox_full"}
        derive_warnings: list[str] = []
        if derive:
            stem_bytes["vox_wet"], derive_warnings = derive_wet(sources[assignment["vox_full"]](), stem_bytes["vox_dry"])
        song_dir = save_stems(project_root / "mixes", name, version, style, bpm, stem_bytes, instrumental=instrumental)
        if derive_warnings:
            st.session_state["derive_warnings"] = derive_warnings
            go = False  # don't auto-analyze a derived stem that looks suspect
        secs = {} if sections_df is None else {
            str(r["section"]): (int(r["first bar"]), int(r["last bar"])) for _, r in sections_df.iterrows()
            if r["section"] and pd.notna(r["first bar"]) and pd.notna(r["last bar"]) and r["last bar"] >= r["first bar"]
        }
        if secs:
            save_sections(song_dir, secs)
    except Exception as e:
        st.error(f"Couldn't save: {e}")
        return

    version = version.strip()
    if go:
        _start_analysis(repo, cfg, project_root, song_dir, name, version, force=True)
        st.toast(f"Analysis of {name} {version} started. It keeps running if you switch pages.")
    else:
        st.toast(f"Saved {name} {version}.")
    st.session_state["_up_pending"] = {
        "up_song_mode": "Add to an existing song", "up_song_pick": name, "_up_last_pick": None,
        "up_src_folder": "", "up_replace": False,
    }
    st.session_state.pop("_up_src_cache", None)
    st.rerun()


def _render_library(repo, cfg, project_root: Path, songs: dict[str, Path]) -> None:
    st.subheader("Your mixes")
    if not songs:
        st.caption("Nothing here yet. Add your first mix above.")
        return
    analyzed = {(r["song_id"], r["version"]) for _i, r in repo.get_all_versions().iterrows()}
    for song, song_dir in songs.items():
        info = load_song_yaml(song_dir)
        tags = f"{info.style} · {info.bpm:g} BPM" + (" · instrumental" if info.instrumental else "")
        for version in reversed(_versions(song_dir)):
            c1, c2, c3, c4, c5 = st.columns([3, 1.4, 1.3, 1.3, .6], vertical_alignment="center")
            c1.markdown(f"**{song}** {version}  \n<span style='color:#E3D2F7;font-size:.9rem'>{tags}</span>", unsafe_allow_html=True)
            busy = jobs.is_running("analyze", song, version)
            done = (song, version) in analyzed
            c2.markdown(
                f'<span class="chip {"note" if busy else "ok" if done else "check"}">'
                f'{"Analyzing…" if busy else "Analyzed" if done else "Not analyzed"}</span>', unsafe_allow_html=True)
            if c3.button("Re-analyze" if done else "Analyze", key=f"lib_a_{song}_{version}", disabled=busy,
                         type="secondary" if done else "primary", use_container_width=True):
                _start_analysis(repo, cfg, project_root, song_dir, song, version, force=done)
                st.rerun()
            if c4.button("View results", key=f"lib_v_{song}_{version}", disabled=not done, use_container_width=True):
                st.session_state["nav_target"] = "Compare"
                st.session_state["cmp_song"], st.session_state["cmp_version"] = song, version
                st.rerun()
            with c5.popover("⋯", use_container_width=True):
                st.caption(f"Delete {song} {version} and its results? This removes the saved audio files.")
                if st.button("Delete this version", key=f"lib_d_{song}_{version}"):
                    _delete_version(repo, song_dir, song, version)
                    st.rerun()

    with st.expander("Quick peak check (no analysis)"):
        widgets.guard("up_peak_song", songs)
        song = st.selectbox("Song", sorted(songs), key="up_peak_song")
        widgets.guard("up_peak_version", _versions(songs[song]))
        version = st.selectbox("Version", _versions(songs[song]), key="up_peak_version")
        if st.button("Check peaks"):
            try:
                results, _s = run_checks_only(songs[song], version, cfg)
            except Exception as e:
                st.error(f"Check failed: {e}")
            else:
                _render_check_results(results)


def _render_check_results(results) -> None:
    df = pd.DataFrame([{"check": CHECK_NAMES.get(r.check, r.check), "result": r.level, "value": round(r.value, 2), "where": (f"bar {r.bar:.0f}" if r.bar is not None else r.stem)} for r in results])
    st.dataframe(df, use_container_width=True, hide_index=True)
    if any_fail(results):
        st.error("Peak safety: at least one FAIL.")
    elif (df["result"] == "warn").any():
        st.warning("Peak safety: warnings present, no fails.")
    else:
        st.success("Peak safety: all checks pass.")


def _delete_version(repo, song_dir: Path, song: str, version: str) -> None:
    for f in song_dir.glob(f"{song}__{version}__*.wav"):
        f.unlink(missing_ok=True)
    repo.delete_version(song, version)
    if not _versions(song_dir):  # last version gone: remove the song too
        (song_dir / "song.yaml").unlink(missing_ok=True)
        try:
            song_dir.rmdir()
        except OSError:
            pass
