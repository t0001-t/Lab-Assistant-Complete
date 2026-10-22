"""Haupteinstieg für den vollständigen Lab Assistant.

Start: streamlit run app.py
"""
from __future__ import annotations

import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().parent / "pwa_entrypoint.py"), run_name="__main__")
