"""Shared Streamlit helpers: state that survives page switches, the style
picker, and file sources (upload or a folder on this Mac)."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Callable

import streamlit as st
import yaml

from mixlens.io.ingest import AUDIO_TYPES
from mixlens.io.sidecar import load_references_yaml

PERSIST_PREFIXES = ("up_", "ref_", "cmp_", "hist_", "reg_")
NEW_STYLE = "+ New style…"


def keep_state() -> None:
    """Streamlit forgets a widget's value the moment a run doesn't render it,
    which wipes a form when you visit another page. Re-assigning the value on
    every run keeps it. File uploaders can't be assigned, so they're skipped
    (see `file_source`, which caches their bytes instead)."""
    for key in list(st.session_state.keys()):
        if isinstance(key, str) and key.startswith(PERSIST_PREFIXES) and not any(
            skip in key for skip in ("_files", "_editor")
        ):
            st.session_state[key] = st.session_state[key]


def guard(key: str, options) -> None:
    """Drop a remembered selection that is no longer one of the options, so a
    kept value can't make a selectbox raise after the data changed."""
    if key in st.session_state and st.session_state[key] not in list(options):
        del st.session_state[key]


# ---- styles ----------------------------------------------------------------


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def style_lists(cfg, repo, project_root: Path) -> tuple[list[str], list[str], list[str]]:
    """(your styles, general genres, any others already in use)."""
    yours = list(cfg.get("styles.yours", []))
    genres = list(cfg.get("styles.genres", []))
    used = {e.style for e in load_references_yaml(project_root / "references")}
    used |= set(repo.list_styles())
    for yml in (project_root / "mixes").glob("*/song.yaml"):
        try:
            used.add(str((yaml.safe_load(yml.read_text()) or {}).get("style", "")).strip())
        except (OSError, yaml.YAMLError):
            pass
    used.discard("")
    extra = sorted(used - set(yours) - set(genres))
    return yours, genres, extra


def style_picker(label: str, key: str, cfg, repo, project_root: Path, help: str | None = None) -> str:
    yours, genres, extra = style_lists(cfg, repo, project_root)
    options = yours + genres + extra + [NEW_STYLE]

    def fmt(s: str) -> str:
        return f"{s}  ·  your style" if s in yours else s

    guard(key, options)
    choice = st.selectbox(label, options, key=key, format_func=fmt, help=help)
    if choice == NEW_STYLE:
        typed = st.text_input("Name the new style", key=f"{key}_new", placeholder="e.g. jersey-club")
        return slugify(typed) or yours[0]
    return choice


# ---- folders & files ---------------------------------------------------------


def choose_folder() -> str | None:
    """Native macOS folder dialog (this app runs on your Mac, so it can open one)."""
    try:
        out = subprocess.run(
            ["osascript", "-e", 'POSIX path of (choose folder with prompt "Pick the folder with your audio files")'],
            capture_output=True, text=True, timeout=600,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None if out.returncode == 0 else None


def audio_files_in(folder: str) -> dict[str, Path]:
    p = Path(folder).expanduser()
    if not p.is_dir():
        return {}
    exts = {f".{e}" for e in AUDIO_TYPES}
    return {f.name: f for f in sorted(p.iterdir()) if f.suffix.lower() in exts and not f.name.startswith(".")}


def _pick_folder_into(key: str) -> None:
    path = choose_folder()
    if path:
        st.session_state[key] = path


def _clear_cache(cache_key: str) -> None:
    st.session_state.pop(cache_key, None)


def file_source(key: str, accept_multiple: bool = True, label: str = "Files") -> dict[str, Callable[[], bytes]]:
    """Files from an upload or from a folder on this Mac, as {name: loader}.

    Uploaded bytes are cached in the session so they survive visiting another
    page (an uploader widget itself resets when it isn't rendered)."""
    mode = st.radio(
        "Where are the files?", ["Upload them here", "Pick a folder on this Mac"],
        horizontal=True, key=f"{key}_mode",
        help="Picking a folder is fastest for big bounces: nothing is uploaded through the browser.",
    )
    if mode.startswith("Pick"):
        c1, c2 = st.columns([1, 3], vertical_alignment="bottom")
        c1.button("Choose folder…", key=f"btn_{key}_choose", on_click=_pick_folder_into, args=(f"{key}_folder",))
        folder = c2.text_input("Folder path", key=f"{key}_folder", placeholder="/Users/you/Music/bounces/neon-altar")
        found = audio_files_in(folder) if folder else {}
        if folder and not found:
            st.warning("No audio files in that folder.")
        elif found:
            st.caption(f"Found {len(found)} audio file(s).")
        return {name: (lambda p=path: p.read_bytes()) for name, path in found.items()}

    cache_key = f"_{key}_cache"
    files = st.file_uploader(
        label, type=AUDIO_TYPES, accept_multiple_files=accept_multiple, key=f"{key}_files",
    )
    st.caption("Dragging from Finder not working in this window? Use \"Pick a folder on this Mac\" above, or open this app in Chrome or Safari.")
    uploaded = files if isinstance(files, list) else ([files] if files else [])
    if uploaded:
        st.session_state[cache_key] = {f.name: f.getvalue() for f in uploaded}
    cache = st.session_state.get(cache_key, {})
    if cache and not uploaded:
        c1, c2 = st.columns([4, 1], vertical_alignment="center")
        c1.info("Kept from earlier: " + ", ".join(cache))
        c2.button("Clear", key=f"btn_{key}_clear", on_click=_clear_cache, args=(cache_key,))
    return {name: (lambda b=data: b) for name, data in cache.items()}
