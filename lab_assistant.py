"""Unified local launcher for the All-in-One Lab Assistant.

The SDS-PAGE editor remains a self-contained Streamlit script (``gel_app.py``).
This shell only adds navigation, the dashboard, calculators, notebook, calendar
and shared settings; it does not modify the gel renderer or image pipeline.
"""

from __future__ import annotations

import runpy
from pathlib import Path

import streamlit as st

from lab_dashboard import (
    MODULES,
    calendar_page,
    help_controls,
    overview_page,
    projects_page,
    settings_controls,
)
from lab_locales import tr
from lab_pages import calculator_page, notebook_page
from lab_theme import inject_theme

# PWA Integration
from pwa_component import inject_pwa

ROOT = Path(__file__).parent
NAVIGATION = (
    ("home", ":material/home:"),
    ("notebook", ":material/menu_book:"),
    ("gel", ":material/colorize:"),
    ("calculators", ":material/calculate:"),
    ("calendar", ":material/calendar_month:"),
)

# PWA injizieren – MUSS vor erster st.* Ausgabe erfolgen
inject_pwa(
    name="Lab Assistant",
    short_name="LabAssistant",
    theme_color="#60a5fa",
    background_color="#f7f7f7",
)

st.session_state.setdefault("lab_lang", "de")
if st.session_state.lab_lang not in {"de", "en"}:
    st.session_state.lab_lang = "de"
st.session_state.setdefault("lab_theme", "light")
if st.session_state.lab_theme not in {"light", "dark"}:
    st.session_state.lab_theme = "light"
st.session_state.setdefault("lab_module", "home")
if st.session_state.lab_module not in MODULES:
    st.session_state.lab_module = "home"
st.session_state["lab_shell"] = True
lang = st.session_state.lab_lang
dark = st.session_state.lab_theme == "dark"
module = st.session_state.lab_module

inject_theme(dark)

# Sidebar
with st.sidebar:
    st.markdown(
        '<div class="la-brand">' + tr("app", lang)
        + '<span>' + tr("app_short_subtitle", lang) + '</span></div>',
        unsafe_allow_html=True,
    )
    for key, icon in NAVIGATION:
        active = st.session_state.lab_module == key
        if st.button(
            tr(key, lang), key=f"nav_{key}", icon=icon, width="stretch",
            type="primary" if active else "secondary",
        ):
            st.session_state.lab_module = key
            st.rerun()
    st.divider()
    with st.popover(tr("settings", lang), icon=":material/settings:", width="stretch"):
        settings_controls()
    with st.popover(tr("help", lang), icon=":material/help:", width="stretch"):
        help_controls()
    st.caption(tr("privacy_notice", lang))

# Routing
if module == "home":
    overview_page()
elif module == "notebook":
    notebook_page()
elif module == "gel":
    st.session_state["lab_shell"] = True
    st.session_state["ui_theme"] = st.session_state.lab_theme
    runpy.run_path(str(ROOT / "gel_app.py"), run_name="__main__")
elif module == "calculators":
    calculator_page()
elif module == "calendar":
    calendar_page()
elif module == "projects":
    projects_page()
