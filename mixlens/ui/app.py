"""Streamlit entry point. `mixlens ui` runs this."""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from mixlens.config import load_config
from mixlens.db.repo import Repo

import jobs
import theme
import widgets

PROJECT_ROOT = Path(__file__).resolve().parents[1]

st.set_page_config(page_title="MixLens", page_icon="🎚️", layout="wide", initial_sidebar_state="collapsed")


@st.cache_resource
def get_repo() -> Repo:
    return Repo(PROJECT_ROOT / "mixlens.db")


@st.cache_resource
def get_config():
    return load_config(PROJECT_ROOT / "config.yaml")


def main() -> None:
    theme.apply()
    widgets.keep_state()
    pages = ["Analyze", "Compare", "History", "References", "Regret"]
    # Other pages request navigation via nav_target; it has to be applied
    # before the radio is created, since a widget's state can't change after.
    target = st.session_state.pop("nav_target", None)
    if target in pages:
        st.session_state["page"] = target
    repo = get_repo()
    cfg = get_config()
    n_mixes = len(repo.get_all_versions())
    n_refs = int((~repo.list_refs()['path'].str.endswith('#accompaniment')).sum())  # derived rows don't count
    page = theme.topbar(pages, f"{n_mixes} mix{'es' if n_mixes != 1 else ''} · {n_refs} refs")
    jobs.render_banner()
    if st.session_state.get("_last_page") != page:
        st.session_state["_last_page"] = page
        theme.scroll_to_top()

    if page == "Analyze":
        from views import analyze

        analyze.render(repo, cfg, PROJECT_ROOT)
    elif page == "Compare":
        from views import compare

        compare.render(repo, cfg)
    elif page == "History":
        from views import history

        history.render(repo, cfg)
    elif page == "References":
        from views import references

        references.render(repo, cfg, PROJECT_ROOT)
    elif page == "Regret":
        from views import regret

        regret.render(repo, cfg)


if __name__ == "__main__":
    main()
