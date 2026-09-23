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

PROJECT_ROOT = Path(__file__).resolve().parents[1]

st.set_page_config(page_title="MixLens", layout="wide")


@st.cache_resource
def get_repo() -> Repo:
    return Repo(PROJECT_ROOT / "mixlens.db")


@st.cache_resource
def get_config():
    return load_config(PROJECT_ROOT / "config.yaml")


def main() -> None:
    st.sidebar.title("MixLens")
    page = st.sidebar.radio("Page", ["Analyze", "Compare", "History", "References", "Regret"])

    repo = get_repo()
    cfg = get_config()

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
