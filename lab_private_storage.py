"""Browser-specific anonymous storage; never fall back to a shared database."""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from lab_locales import tr

ROOT = Path(__file__).resolve().parent
_identity = components.declare_component("lab_private_identity", path=str(ROOT / "components/private_identity"))


def visitor_folder(base: Path, token: str) -> Path:
    """Resolve a bearer credential to an opaque directory, rejecting paths/invalid IDs."""
    if not isinstance(token, str) or not re.fullmatch(r"[0-9a-f]{64}", token):
        raise ValueError("Invalid browser credential")
    return base / "visitors" / hashlib.sha256(token.encode("ascii")).hexdigest()


def is_local_storage() -> bool:
    return os.environ.get("LAB_ASSISTANT_STORAGE_MODE") == "local"


def data_folder() -> Path:
    base = Path(os.environ.get("LAB_ASSISTANT_DATA_DIR", ROOT / "lab_data"))
    # Explicit opt-in for a trusted, single-person local installation only.
    if is_local_storage():
        return base
    token = st.session_state.get("_lab_browser_credential")
    if token is None:
        token = _identity(key="lab_private_identity", default=None)
    if not isinstance(token, str) or not re.fullmatch(r"[0-9a-f]{64}", token):
        lang = st.session_state.get("lab_lang", "de")
        st.info(tr("private_storage_loading", lang))
        st.stop()
    st.session_state["_lab_browser_credential"] = token
    return visitor_folder(base, token)
