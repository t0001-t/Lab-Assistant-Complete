"""Startet die unveränderte Dokument-Vorlage mit den Laufzeitvoraussetzungen."""
from __future__ import annotations

import base64
import runpy
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent

st.set_page_config(
    page_title="Lab Assistant",
    page_icon="data:image/png;base64,"
    + base64.b64encode((ROOT / "assets" / "browser_icon.png").read_bytes()).decode("ascii"),
    layout="wide",
    initial_sidebar_state="auto",
)
module = st.query_params.get("module", "home")
allowed = {"home", "notebook", "gel", "calculators", "calendar", "projects"}
st.session_state.setdefault("lab_module", module if module in allowed else "home")
runpy.run_path(str(ROOT / "lab_assistant.py"), run_name="__main__")
