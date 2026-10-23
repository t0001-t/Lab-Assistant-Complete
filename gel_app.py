"""GelDoc Studio – wissenschaftliche SDS-PAGE-Abbildungsdokumentation.

Start:  streamlit run gel_app.py

Die App ist komplett zweisprachig (Deutsch/Englisch), verwaltet mehrere
Gel-Panels und speichert den kompletten Projektstand als JSON-Datei.
Das Originalgel wird im Export nie verändert.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from PIL import Image

import canvas_renderer as cr
import image_processing as ip
from demo_project import translate_demo
from editor_component import corners_layout, gel_editor
from label_editor import encode_runs, label_editor
from locales import LANG_CODES, LANGUAGES, t
from models import (
    ConditionRow,
    GelPanel,
    GroupLabel,
    MarkerBand,
    Project,
    TargetArrow,
    clamp,
    default_project,
)
from tutorial_component import accept_demo_event, tutorial_controls
from workflow import (
    apply_editor_event,
    distribute_lanes,
    index_of_identity,
    insert_lane,
    remove_lane,
    renumber_lanes,
    reset_markers,
    set_lane_count,
    set_marker_count,
    visible_arrows,
    visible_markers,
)

ROOT = Path(__file__).parent
SAMPLE_PATH = ROOT / "assets" / "sample_gel.jpg"
PROJECTS_DIR = ROOT / "projects"
UPLOAD_TYPES = ["png", "jpg", "jpeg", "tif", "tiff"]
PROJECTS_DIR.mkdir(exist_ok=True)

if not st.session_state.get("lab_shell"):
    st.set_page_config(
        page_title="GelDoc Studio · SDS-PAGE",
        page_icon="data:image/png;base64,"
        + base64.b64encode((ROOT / "assets" / "browser_icon.png").read_bytes()).decode("ascii"),
        layout="wide",
        initial_sidebar_state="expanded",
    )

_LIGHT_CSS = """
  .block-container { padding-top: 1.4rem; padding-bottom: 3rem; max-width: 1500px; }
  [data-testid="stSidebar"] { background: #f8f8f8; }
  h1 { letter-spacing: -0.025em; margin-bottom: 0.1rem; }
  .gd-sub { color: #646464; font-size: 0.95rem; margin-bottom: 1.1rem; }
  .gd-chip {
    display: inline-block; padding: 2px 9px; border-radius: 999px;
    background: #f0f0f0; color: #484848; font-size: 0.78rem;
    font-weight: 600; margin-right: 6px;
  }
  .gd-chip.green { background: #f2f2f2; color: #525252; }
  .gd-chip.amber { background: #eaf3ff; color: #285b91; }
  .gd-note {
    background: #f9f9f9; border: 1px solid #e8e8e8; border-radius: 10px;
    padding: 0.75rem 0.9rem; font-size: 0.86rem; color: #494949;
  }
  .stTabs [data-baseweb="tab"], .stTabs [role="tab"] { font-weight: 600; }

  /* Arbeitsfläche: Bild bleibt beim Scrollen sichtbar, Bedienung scrollt. */
  [class*="st-key-gd-sticky"] {
    position: sticky;
    top: 4.2rem;
    align-self: flex-start;
  }
  /* Bildspalte mit mehreren Blöcken: bleibt sichtbar und scrollt selbst. */
  [class*="st-key-gd-fixed"] {
    position: sticky;
    top: 4.2rem;
    align-self: flex-start;
    max-height: calc(100vh - 11.5rem);
    overflow-y: auto;
    overflow-x: hidden;
    padding-right: 0.5rem;
    scrollbar-gutter: stable;
  }
  [class*="st-key-gd-scroll"] {
    max-height: calc(100vh - 11.5rem);
    overflow-y: auto;
    overflow-x: hidden;
    padding-right: 0.5rem;
    scrollbar-gutter: stable;
  }
  [class*="st-key-gd-scroll"]::-webkit-scrollbar { width: 9px; }
  [class*="st-key-gd-scroll"]::-webkit-scrollbar-thumb {
    background: #d1d1d1; border-radius: 999px;
  }
  [class*="st-key-gd-scroll"]::-webkit-scrollbar-track { background: transparent; }
"""

# Dunkelmodus der Oberfläche. Die Export-Abbildung hat davon unabhängig ihr
# eigenes Farbschema ("Farbschema" in der Seitenleiste).
_DARK_CSS = """
  .stApp, [data-testid="stAppViewContainer"] { background-color: #131313; color: #eaeaea; }
  [data-testid="stHeader"] { background-color: rgba(19, 19, 19, 0.82); }
  [data-testid="stSidebar"] { background: #1b1b1b; border-right: 1px solid #2b2b2b; }

  h1, h2, h3, h4, h5, h6 { color: #f5f5f5; }
  [data-testid="stMarkdownContainer"] p,
  [data-testid="stMarkdownContainer"] li,
  [data-testid="stWidgetLabel"] p,
  [data-testid="stWidgetLabel"] label { color: #e2e2e2; }
  [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p { color: #a0a0a0; }
  a { color: #93c5fd; }
  code {
    background: #282828 !important; color: #eaeaea; border-radius: 4px;
    padding: 0 0.25rem; font-size: 0.86em;
  }
  hr, [data-testid="stDivider"] { border-color: #2f2f2f; background-color: #2f2f2f; }

  .gd-sub { color: #a0a0a0; }
  .gd-note { background: #1d1d1d; border-color: #313131; color: #c3c3c3; }
  [data-testid="stPopoverBody"] {
    background-color: #1b1b1b !important; color: #eaeaea !important;
    border: 1px solid #363636 !important;
  }
  [data-testid="stPopoverBody"] p, [data-testid="stPopoverBody"] h4,
  [data-testid="stPopoverBody"] label { color: #eaeaea !important; }
  .gd-chip { background: #262626; color: #c5c5c5; }
  .gd-chip.green { background: #282828; color: #cbcbcb; }
  .gd-chip.amber { background: #203047; color: #a8cfff; }

  /* Eingaben und Auswahllisten */
  body { color: #eaeaea; }
  [data-testid="stTextInputRootElement"],
  [data-testid="stNumberInputContainer"],
  [data-testid="stSelectbox"] [role="group"],
  [data-testid="stMultiSelect"] [role="group"],
  [data-testid="stTextArea"] [role="group"] {
    background-color: #212121 !important;
    border-color: #363636 !important;
  }
  [data-testid="stTextInputRootElement"] *,
  [data-testid="stNumberInputContainer"] *,
  [data-testid="stSelectbox"] [role="group"] *,
  [data-testid="stMultiSelect"] [role="group"] * { color: #eaeaea; }

  [data-baseweb="input"], [data-baseweb="base-input"],
  [data-baseweb="textarea"], [data-baseweb="select"] > div {
    background-color: #212121 !important;
    border-color: #363636 !important;
  }
  input, textarea { color: #eaeaea !important; -webkit-text-fill-color: #eaeaea; }
  [data-testid="stTextInputField"], [data-testid="stNumberInputField"],
  [data-testid="stTextAreaField"], input[type="text"], input[type="number"], textarea {
    background-color: transparent !important;
  }
  [data-testid="stCheckbox"]:not([data-selected="true"]) label > div:first-of-type,
  [data-testid="stCheckbox"] label:not([data-selected="true"]) > div:first-of-type {
    background-color: #212121 !important; border-color: #454545 !important;
  }
  [data-testid="stRadioOption"]:not([data-selected="true"]) > div > div:first-of-type {
    background-color: #212121 !important; border-color: #454545 !important;
  }
  input[type="range"] { background-color: transparent !important; }
  input::placeholder, textarea::placeholder {
    color: #777777 !important; -webkit-text-fill-color: #777777;
  }
  [data-baseweb="select"] div { color: #eaeaea; }
  [data-baseweb="popover"] [role="listbox"], [data-baseweb="popover"] ul {
    background-color: #212121 !important;
    border: 1px solid #363636;
  }
  [role="option"] { background-color: #212121 !important; color: #eaeaea !important; }
  [role="option"]:hover, [role="option"][aria-selected="true"] {
    background-color: #2f2f2f !important;
  }

  [data-testid="stFileUploaderDropzone"] {
    background-color: #1b1b1b; border-color: #363636;
  }
  [data-testid="stFileUploaderDropzone"] span { color: #c3c3c3; }

  [data-testid="stSelectboxVirtualDropdown"],
  [data-testid="stMultiSelectVirtualDropdown"] {
    background-color: #212121 !important;
    border: 1px solid #363636;
    border-radius: 8px;
  }

  /* Schaltflächen */
  [data-testid="stBaseButton-secondary"], [data-testid="stDownloadButton"] button,
  [data-testid="stBaseButton-secondaryFormSubmit"],
  [data-testid="stBaseButton-headerNoPadding"] {
    background-color: #212121; color: #eaeaea; border-color: #363636;
  }
  [data-testid="stBaseButton-secondary"]:hover,
  [data-testid="stDownloadButton"] button:hover {
    background-color: #2f2f2f; border-color: #454545; color: #ffffff;
  }
  [data-testid="stBaseButton-secondary"]:disabled {
    background-color: #191919; color: #6a6a6a; border-color: #2b2b2b;
  }

  /* Tabs */
  [data-baseweb="tab-list"] { background-color: transparent; }
  [data-testid="stTabs"] [role="tab"] { color: #a0a0a0; }
  [data-testid="stTabs"] [role="tab"][aria-selected="true"] { color: #93c5fd; }
  button[data-baseweb="tab"] { color: #a0a0a0; }
  button[data-baseweb="tab"][aria-selected="true"] { color: #93c5fd; }
  [data-baseweb="tab-highlight"] { background-color: #60a5fa !important; }
  [data-baseweb="tab-border"] { background-color: #2f2f2f !important; }

  /* Expander, Toasts, Slider */
  [data-testid="stExpander"] details { background-color: #1b1b1b; border-color: #2f2f2f; }
  [data-testid="stExpander"] summary { color: #eaeaea; }
  [data-testid="stToast"] {
    background-color: #212121; border: 1px solid #363636;
  }
  [data-testid="stToast"], [data-testid="stToast"] * { color: #eaeaea; }
  [data-baseweb="slider"] [role="slider"] { background-color: #60a5fa; }

  /* Tabellen (glide-data-grid verwendet CSS-Variablen) */
  .stDataFrame { background-color: #1b1b1b; }
  .stDataFrameGlideDataEditor {
    --gdg-text-dark: #eaeaea !important;
    --gdg-text-medium: rgba(234, 234, 234, 0.8) !important;
    --gdg-text-light: rgba(234, 234, 234, 0.45) !important;
    --gdg-text-bubble: rgba(234, 234, 234, 0.6) !important;
    --gdg-bg-icon-header: rgba(234, 234, 234, 0.6) !important;
    --gdg-text-header: rgba(234, 234, 234, 0.75) !important;
    --gdg-text-group-header: rgba(234, 234, 234, 0.75) !important;
    --gdg-bg-group-header: #1b1b1b !important;
    --gdg-bg-group-header-hovered: #272727 !important;
    --gdg-bg-cell: #1b1b1b !important;
    --gdg-bg-cell-medium: #1b1b1b !important;
    --gdg-bg-header: #212121 !important;
    --gdg-bg-header-has-focus: #2f2f2f !important;
    --gdg-bg-header-hovered: #2b2b2b !important;
    --gdg-bg-bubble: #212121 !important;
    --gdg-bg-bubble-selected: #2f2f2f !important;
    --gdg-bg-search-result: rgba(176, 176, 176, 0.18) !important;
    --gdg-border-color: rgba(255, 255, 255, 0.08) !important;
    --gdg-horizontal-border-color: rgba(255, 255, 255, 0.06) !important;
    --gdg-drilldown-border: rgba(255, 255, 255, 0.18) !important;
    --gdg-link-color: #b0b0b0 !important;
  }
"""


_MODERN_CSS = """
  .stApp { background: #f7f7f7; }
  [data-testid="stHeader"] { background: rgba(247, 247, 247,.94); }
  .block-container { max-width: 1600px; padding-top: 2rem; }
  h1 { font-size: clamp(1.7rem, 3vw, 2.35rem); font-weight: 750; letter-spacing: -.045em; }
  h2, h3 { letter-spacing: -.025em; }
  [data-testid="stSidebar"] { border-right: 1px solid #e4e4e4; }
  .stTabs [data-baseweb="tab-list"], .stTabs [role="tablist"] {
    gap: .4rem; padding: .4rem; background: #eeeeee;
    border-radius: 14px; flex-wrap: wrap;
  }
  .stTabs [data-baseweb="tab"], .stTabs [role="tab"] {
    border-radius: 10px; padding: .65rem 1rem; height: auto;
  }
  .stTabs [aria-selected="true"] { background: white; color: #285b91; box-shadow: none; }
  .stTabs [data-baseweb="tab-highlight"],
  .stTabs [data-baseweb="tab-border"] { display: none; }
  [data-testid="stButton"] button, [data-testid="stDownloadButton"] button {
    border-radius: 9px; min-height: 2.6rem;
  }
  [data-testid="stExpander"] { background: white; border-radius: 12px; }
  [data-testid="stPopoverBody"] {
    min-width: min(23rem, 92vw); max-height: 82vh; overflow-y: auto;
  }
  .gd-note { border-left: 3px solid #6e6e6e; }
  .gd-chip { padding: 5px 11px; margin-bottom: 5px; }
  [data-testid="stAlertContainer"]:has([data-testid="stAlertContentInfo"]) {
    background-color: #ededed; color: #414141;
  }
  [data-testid="stAlertContentInfo"] { color: inherit; }

  @media (max-width: 900px) {
    [class*="st-key-gd-fixed"], [class*="st-key-gd-sticky"],
    [class*="st-key-gd-scroll"] { position: static; max-height: none; overflow: visible; }
    .block-container { padding: 1rem; }
  }
"""
_MODERN_DARK_CSS = """
  [data-testid="stAlertContainer"]:has([data-testid="stAlertContentInfo"]) {
    background-color: #292929; color: #dedede;
  }

  .stTabs [data-baseweb="tab-list"], .stTabs [role="tablist"] { background: #232323; }
  .stTabs [aria-selected="true"] { background: #363636; color: #d8d8d8; }
  [data-testid="stExpander"] { background: #1b1b1b; }
"""


_ACCENT_CSS = """
  .stTabs [role="tablist"] { background: transparent; border-radius: 0; padding: 0; }
  .stTabs [role="tab"] { background: transparent; border-radius: 0; box-shadow: none; border-bottom: 3px solid transparent; }
  .stTabs [role="tab"][aria-selected="true"] { background: transparent; border-bottom-color: #60a5fa; }

  .stTabs [role="tab"][aria-selected="true"] {
    color: #285b91; box-shadow: none;
  }
"""
_ACCENT_DARK_CSS = """
  .stTabs [role="tab"][aria-selected="true"] { color: #93c5fd; }
"""


def app_css(dark: bool) -> str:
    """Basis-Styles plus optionaler Dunkelmodus für die Oberfläche."""
    from lab_theme import shared_ui_css

    return f"<style>{_LIGHT_CSS}{_MODERN_CSS}{(_DARK_CSS + _MODERN_DARK_CSS) if dark else ''}{_ACCENT_CSS}{_ACCENT_DARK_CSS if dark else ''}</style>" + shared_ui_css(dark)

# ----------------------------------------------------------------------
# Session-State
# ----------------------------------------------------------------------
ss = st.session_state
ss.setdefault("project", None)
ss.setdefault("active", 0)
ss.setdefault("selected_lane", 0)
ss.setdefault("selected_marker", 0)
ss.setdefault("selected_arrow", 0)
ss.setdefault("editor_nonces", {})
ss.setdefault("flash", None)
ss.setdefault("upload_hash", "")
ss.setdefault("ui_version", 0)
ss.setdefault("crop_version", 0)
ss.setdefault("editor_side", "right")
ss.setdefault("proc_cache", {})
ss.setdefault("display_cache", {})
ss.setdefault("preview_cache", {})
ss.setdefault("export_cache", {})
ss.setdefault("ui_theme", "light")

st.markdown(app_css(ss.ui_theme == "dark"), unsafe_allow_html=True)


def sha1(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def _fresh_project() -> Project:
    """Neues Projekt ohne Bild – Upload oder Referenzgel starten die Arbeit."""
    return default_project()


if ss.project is None:
    ss.project = _fresh_project()
    if ss.get("lab_lang") in LANG_CODES:
        ss.project.lang = ss.lab_lang
        ss["gel_language"] = LANGUAGES[ss.lab_lang]
elif ss.get("lab_lang") in LANG_CODES and ss.project.lang != ss.lab_lang:
    translate_demo(ss.project, ss.get("demo_tracking"), ss.lab_lang)
    ss.project.lang = ss.lab_lang
    ss["gel_language"] = LANGUAGES[ss.lab_lang]

if ss.get("lab_shell"):
    # In der Shell steuert die globale Einstellung auch das Abbildungs-Farbschema.
    ss.project.theme = ss.ui_theme
    ss.project.export.theme = ss.ui_theme


def L(key: str, **kwargs: object) -> str:
    return t(key, ss.project.lang, **kwargs)


def panel() -> GelPanel:
    ss.active = int(clamp(ss.active, 0, len(ss.project.panels) - 1))
    return ss.project.panels[ss.active]


def flash(key: str, **kwargs: object) -> None:
    ss.flash = (key, kwargs)


def show_flash() -> None:
    # Toast statt st.success: eine Meldung darf das Layout über den Tabs nicht
    # verschieben, sonst springt die Seite beim Auslösen einer Aktion nach oben.
    if ss.flash:
        key, kwargs = ss.flash
        st.toast(L(key, **kwargs), icon=":material/check_circle:")
        ss.flash = None


def get_processed(target: GelPanel) -> Image.Image:
    """Verarbeitetes Gel mit einfachem Cache über Session-Reruns."""
    cache = ss.proc_cache
    signature = (
        target.id,
        target.transform.model_dump_json(),
        target.adjustments.model_dump_json(),
        id(target.source_image),
    )
    if signature not in cache:
        if len(cache) > 16:
            cache.clear()
        cache[signature] = target.processed_image()
    return cache[signature]


def display_png(image: Image.Image) -> bytes:
    """PNG-Bytes für ``st.image``, gecacht.

    ``st.image`` kodiert PIL-Bilder bei jedem Rerun neu; das sind bei großen
    Abbildungen schnell einige hundert Millisekunden.
    """
    rgb = image.convert("RGB")
    key = hashlib.sha1(f"{rgb.size}".encode("ascii") + rgb.tobytes()).hexdigest()
    cached = ss.display_cache.get(key)
    if cached is not None:
        return cached
    buffer = io.BytesIO()
    rgb.save(buffer, format="PNG", compress_level=6)
    data = buffer.getvalue()
    if len(ss.display_cache) >= 12:
        ss.display_cache.clear()
    ss.display_cache[key] = data
    return data


def clear_render_caches() -> None:
    """Nach Bild- oder Projektwechsel alle abgeleiteten Bilder verwerfen."""
    ss.proc_cache.clear()
    ss.preview_cache.clear()
    ss.display_cache.clear()
    ss.export_cache.clear()


def panel_gel(target: GelPanel) -> Image.Image | None:
    if target.source_image is None:
        return None
    return get_processed(target)


def render_options() -> cr.RenderOptions:
    ss.project.export.theme = ss.project.theme
    return cr.RenderOptions.from_settings(ss.project.export).validated()


def choice(label: str, values: list, labels: list[str], index: int, **kwargs):
    """Selectbox/Radio ohne ``format_func`` (AppTest-kompatibel)."""
    horizontal = kwargs.pop("horizontal", False)
    if horizontal:
        selected = st.radio(label, options=labels, index=index, horizontal=True, **kwargs)
    else:
        selected = st.selectbox(label, options=labels, index=index, **kwargs)
    return values[labels.index(selected)]


_LN_VALUES = ("bottom", "top", "none")


def lane_numbers_select(key: str) -> None:
    """Spurnummern-Position; mehrere Stellen bleiben über das Modell synchron."""
    labels = [L("ln_bottom"), L("ln_top"), L("none")]
    current = ss.project.export.lane_numbers_position
    if current not in _LN_VALUES:
        current = "bottom"
    # Modell ist die Wahrheit: vor dem Erzeugen des Widgets den State angleichen.
    ss[key] = labels[_LN_VALUES.index(current)]

    def _apply(source_key: str) -> None:
        ss.project.export.lane_numbers_position = _LN_VALUES[labels.index(ss[source_key])]

    st.selectbox(
        L("lane_numbers_position"),
        options=labels,
        key=key,
        on_change=_apply,
        args=(key,),
        help=L("lane_numbers_help"),
    )


def typography_controls() -> None:
    """Schrift, Labels und Spurnummern im Bedienfeld von Spuren & Labels."""
    before = (
        ss.project.export.font_family,
        float(ss.project.export.font_scale),
        int(ss.project.export.label_rotation),
        bool(ss.project.export.show_lane_labels_bottom),
    )
    families = cr.available_font_families()
    left, right = st.columns(2, vertical_alignment="top")
    with left:
        family = choice(
            L("font_family"),
            families,
            families,
            families.index(ss.project.export.font_family) if ss.project.export.font_family in families else 0,
        )
        scale = float(st.slider(L("font_scale"), 0.7, 1.6, float(ss.project.export.font_scale), 0.05))
    with right:
        rotations = [0, 45, 90]
        rotation = choice(
            L("label_rotation"),
            rotations,
            ["0°", "45°", "90°"],
            rotations.index(ss.project.export.label_rotation),
        )
        bottom = st.checkbox(
            L("lane_labels_bottom"), value=ss.project.export.show_lane_labels_bottom
        )
        lane_numbers_select("ln_tab2")
    if (family, scale, rotation, bottom) != before:
        ss.project.export.font_family = family
        ss.project.export.font_scale = scale
        ss.project.export.label_rotation = rotation
        ss.project.export.show_lane_labels_bottom = bottom
        st.rerun()


def _text(value: object) -> str:
    """Editor-Zellwert robust in einen getrimmten Text wandeln (NaN → "")."""
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _num(value: object, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _flag(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "ja", "yes", "wahr")
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return bool(value)


# ----------------------------------------------------------------------
# Gel-specific options (standalone sidebar or shell editor panel)
# ----------------------------------------------------------------------
def editor_options() -> None:
    """Render gel and figure controls outside the global navigation."""
    st.markdown("#### GelDoc Studio")
    st.caption(L("app_title"))

    if not ss.get("lab_shell"):
        st.divider()
        lang = choice(
            L("sb_language"),
            list(LANG_CODES),
            [LANGUAGES[code] for code in LANG_CODES],
            LANG_CODES.index(ss.project.lang),
            horizontal=True,
            key="gel_language",
        )
        if lang != ss.project.lang:
            translate_demo(ss.project, ss.get("demo_tracking"), lang)
            ss.project.lang = lang
            st.rerun()

    if not ss.get("lab_shell"):
        theme = choice(
            L("sb_theme"),
            ["light", "dark"],
            [L("theme_light"), L("theme_dark")],
            ["light", "dark"].index(ss.project.theme),
        )
        if theme != ss.project.theme:
            ss.project.theme = theme
            ss.project.export.theme = theme
            st.rerun()

    if not ss.get("lab_shell"):
        # In der Shell steuert die globale Einstellung das System-Theme.
        ui_dark = st.toggle(L("sb_ui_dark"), value=ss.ui_theme == "dark", help=L("sb_ui_dark_help"))
        new_ui_theme = "dark" if ui_dark else "light"
        if new_ui_theme != ss.ui_theme:
            # Die Styles werden am Skriptanfang gesetzt – daher ein kurzer Rerun.
            ss.ui_theme = new_ui_theme
            st.rerun()

    if not ss.get("lab_shell"):
        st.divider()
    st.markdown(f"#### {L('sb_project')}")
    project_name = st.text_input(L("project_name"), value=ss.project.name)
    if project_name != ss.project.name:
        ss.project.name = project_name

    def _slug(text: str) -> str:
        keep = [c if (c.isalnum() or c in "-_") else "_" for c in text.strip()]
        return ("".join(keep) or "projekt")[:60]

    if st.button(L("project_save"), width="stretch"):
        path = PROJECTS_DIR / f"{_slug(ss.project.name)}.json"
        ss.project.save(path)
        flash("project_saved", name=path.name)
        st.rerun()

    saved = sorted(path.stem for path in PROJECTS_DIR.glob("*.json"))
    if saved:
        chosen = st.selectbox(L("project_load"), options=saved, index=0)
        cols = st.columns(2)
        if cols[0].button(L("btn_load"), width="stretch", help=L("project_load")):
            ss.project = Project.load(PROJECTS_DIR / f"{chosen}.json")
            ss.active = 0
            clear_render_caches()
            flash("project_loaded", name=f"{chosen}.json")
            st.rerun()
        if cols[1].button(L("delete"), width="stretch", help=L("project_delete")):
            (PROJECTS_DIR / f"{chosen}.json").unlink(missing_ok=True)
            flash("project_deleted", name=chosen)
            st.rerun()
    else:
        st.caption(L("project_none"))

    st.download_button(
        L("project_download"),
        data=ss.project.to_json_bytes(embed_images=ss.project.export.embed_images),
        file_name=f"{_slug(ss.project.name)}.json",
        mime="application/json",
        width="stretch",
    )
    uploaded_project = st.file_uploader(L("project_upload"), type=["json"], key="project_upload")
    if uploaded_project is not None:
        digest = sha1(uploaded_project.getvalue())
        if digest != ss.get("project_upload_hash"):
            try:
                ss.project = Project.from_json_bytes(uploaded_project.getvalue())
                ss.active = 0
                clear_render_caches()
                ss.project_upload_hash = digest
                flash("project_imported")
                st.rerun()
            except (ValueError, json.JSONDecodeError) as exc:
                st.error(L("project_error", error=str(exc)))
    st.caption(L("project_persistence_hint"))

    st.divider()
    st.markdown(f"#### {L('sb_export')}")
    dpi_values = [300, 600, 150]
    ss.project.export.dpi = choice(
        L("export_dpi"),
        dpi_values,
        [L("dpi_publication"), L("dpi_print"), L("dpi_preview")],
        dpi_values.index(ss.project.export.dpi) if ss.project.export.dpi in dpi_values else 0,
    )
    quality_values = [2, 3, 1]
    ss.project.export.supersample = choice(
        L("quality"),
        quality_values,
        [L("quality_2"), L("quality_3"), L("quality_1")],
        quality_values.index(ss.project.export.supersample) if ss.project.export.supersample in quality_values else 0,
        help=L("quality_help"),
    )

    st.divider()
    st.markdown(f"#### {L('sb_harmonization')}")
    harm_values = ["none", "height", "affine"]
    ss.project.export.harmonization = choice(
        L("sb_harmonization"),
        harm_values,
        [L("harm_none"), L("harm_height"), L("harm_affine")],
        harm_values.index(ss.project.export.harmonization),
        help=L("harm_tip"),
    )
    if ss.project.export.harmonization in ("height", "affine"):
        ss.project.export.target_height = int(
            st.number_input(L("harm_target_height"), 120, 6000, int(ss.project.export.target_height), 10)
        )
    if ss.project.export.harmonization == "affine":
        c1, c2 = st.columns(2)
        ss.project.export.ref_marker_top = float(
            c1.number_input(L("harm_ref_top"), 1.0, 1000.0, float(ss.project.export.ref_marker_top), 1.0)
        )
        ss.project.export.ref_marker_bottom = float(
            c2.number_input(L("harm_ref_bottom"), 1.0, 1000.0, float(ss.project.export.ref_marker_bottom), 1.0)
        )

    st.divider()
    st.markdown(f'<div class="gd-note">{L("sb_note")}</div>', unsafe_allow_html=True)


if not ss.get("lab_shell"):
    with st.sidebar:
        editor_options()

# ----------------------------------------------------------------------
# Kopfbereich & Panel-Verwaltung
# ----------------------------------------------------------------------
if ss.get("lab_shell"):
    title_col, tools_col = st.columns([4.1, 1.1], vertical_alignment="top")
    with title_col:
        st.title(L("app_title"))
        st.markdown(f'<div class="gd-sub">{L("app_subtitle")}</div>', unsafe_allow_html=True)
    with tools_col, st.popover(L("editor_options"), icon=":material/tune:", width="stretch"):
        editor_options()
else:
    st.title(L("app_title"))
    st.markdown(f'<div class="gd-sub">{L("app_subtitle")}</div>', unsafe_allow_html=True)

options = render_options()
preview_opts = options.model_copy(update={"supersample": 1})


def preview_figure(target: GelPanel, gel: Image.Image, mode: str) -> tuple[Image.Image, cr.Layout]:
    """Editor-Vorschau je Panel und Modus, gecacht über eine Signatur.

    Ohne Cache würde bei jedem Rerun jede der drei Editor-Vorschauen neu
    gerendert und kodiert, obwohl sich meist nur eine davon geändert hat.
    """
    key = target.id  # Alle Bearbeitungsmodi verwenden dieselbe unmarkierte Abbildung.
    sig = (target.model_dump_json(), preview_opts.model_dump_json(), gel.size, id(target.source_image))
    entry = ss.preview_cache.get(key)
    if entry is not None and entry[0] == sig:
        return entry[1], entry[2]
    figure = cr.render_figure(target, gel, preview_opts)
    layout = cr.compute_layout(target, gel.size, preview_opts)
    if len(ss.preview_cache) >= 12:
        ss.preview_cache.clear()
    ss.preview_cache[key] = (sig, figure, layout)
    return figure, layout


def onboarding_controls(compact=False):
    event = tutorial_controls(
        ss.project, dark=ss.ui_theme == "dark", compact=compact,
        demo_token=ss.get("demo_token"), start_tour=ss.get("demo_start_tour", False),
    )
    try:
        loaded = accept_demo_event(ss, event, clear_render_caches)
    except (OSError, ValueError):
        st.error(L("onboard_demo_error"))
    else:
        if loaded:
            st.rerun()


onboarding_controls()
if ss.get("demo_tracking") and ss.demo_tracking.get("project") is ss.project:
    st.caption(L("onboard_demo_note"))

panel_labels = [f"{p.letter} · {p.name or p.source_name or '—'}" for p in ss.project.panels]
head_left, head_mid, head_right = st.columns([2.6, 2.2, 1.6])
with head_left:
    selected_panel = st.selectbox(L("panel_select"), options=panel_labels, index=ss.active)
    ss.active = panel_labels.index(selected_panel)
with head_mid:
    c1, c2 = st.columns(2)
    letter = c1.text_input(L("panel_letter"), value=panel().letter, max_chars=4)
    name = c2.text_input(L("panel_name"), value=panel().name)
    if letter != panel().letter:
        panel().letter = letter
    if name != panel().name:
        panel().name = name
with head_right:
    b1, b2, b3 = st.columns(3)
    if b1.button("＋", width="stretch", help=L("panel_add")):
        ss.project.add_panel()
        ss.active = len(ss.project.panels) - 1
        st.rerun()
    if b2.button("⧉", width="stretch", help=L("panel_duplicate")):
        ss.project.duplicate_panel(ss.active)
        ss.active = len(ss.project.panels) - 1
        st.rerun()
    if b3.button(L("delete"), width="stretch", help=L("panel_delete"), disabled=len(ss.project.panels) <= 1) and ss.project.remove_panel(ss.active):
        ss.active = max(0, ss.active - 1)
        flash("project_deleted", name=panel_labels[ss.active])
        st.rerun()

active = panel()
gel = panel_gel(active)
if gel is not None:
    chips = [
        f'<span class="gd-chip">{active.letter} · {gel.width}×{gel.height} px</span>',
        f'<span class="gd-chip green">{len(active.lanes)} {L("lane")}</span>',
        f'<span class="gd-chip amber">{len(visible_markers(active))} {L("marker")}</span>',
        f'<span class="gd-chip">{len(visible_arrows(active))} {L("targets")}</span>',
        f'<span class="gd-chip">{ss.project.export.dpi} DPI</span>',
    ]
    st.markdown("".join(chips), unsafe_allow_html=True)
    st.write("")

show_flash()

tabs = st.tabs(
    [L("tab_import"), L("tab_lanes"), L("tab_markers"), L("tab_targets"), L("tab_export")],
    on_change="rerun",
)
tab_import, tab_lanes, tab_markers, tab_targets, tab_export = tabs


# ----------------------------------------------------------------------
# Editor-Ereignisse
# ----------------------------------------------------------------------
EVENTS = {
    "lanes": {"lanes", "add_lane", "delete_lane", "select_lane"},
    "markers": {"markers", "add_marker", "delete_marker", "select_marker"},
    "targets": {"arrows", "add_arrow", "delete_arrow", "select_arrow"},
    "corners": {"corners"},
}


def handle_editor_result(result: dict | None, mode: str) -> None:
    if not result or not isinstance(result, dict):
        return
    nonce = result.get("nonce")
    if nonce is not None and ss.editor_nonces.get(mode) == nonce:
        return
    if nonce is not None:
        ss.editor_nonces[mode] = nonce
    if str(result.get("event", "")) not in EVENTS[mode]:
        return
    outcome = apply_editor_event(active, result)
    if outcome.selected_lane is not None:
        ss.selected_lane = int(outcome.selected_lane)
    if outcome.selected_marker is not None:
        ss.selected_marker = int(outcome.selected_marker)
    if outcome.selected_arrow is not None:
        ss.selected_arrow = int(outcome.selected_arrow)
    if outcome.ui_bump:
        ss.ui_version += 1
    if outcome.rerun:
        if outcome.message_key:
            flash(outcome.message_key, **outcome.message_args)
        st.rerun()


def editor_labels() -> dict[str, str]:
    return {
        "lanes_badge": L("lane"),
        "lanes_hint": L("lanes_editor_hint").replace("**", ""),
        "markers_badge": L("band"),
        "markers_hint": L("markers_editor_hint").replace("**", ""),
        "arrows_badge": L("targets_title"),
        "arrows_hint": L("targets_editor_hint").replace("**", ""),
        "corners_badge": L("persp_title"),
        "corners_hint": L("persp_hint"),
    }


# ----------------------------------------------------------------------
# Tab 1 – Import & Geometrie
# ----------------------------------------------------------------------
def work_area(key: str):
    """Zweispaltige Arbeitsfläche: links das Bild, rechts die Bedienung."""
    return st.columns([1.12, 1.0], gap="large")


with tab_import:
    st.subheader(L("import_title"))

    upload_col, sample_col = st.columns([2.2, 1])
    with upload_col:
        uploaded = st.file_uploader(L("import_upload"), type=UPLOAD_TYPES, help=L("import_upload_help"))
        if uploaded is not None:
            data = uploaded.getvalue()
            digest = sha1(data)
            if digest != ss.upload_hash:
                try:
                    image = ip.load_image(data)
                    active.source_image = image
                    active.source_name = uploaded.name
                    detection = ip.detect_lanes(image, len(active.lanes))
                    for lane, x_rel in zip(active.lanes, detection.positions_rel, strict=False):
                        lane.x_pos_rel = x_rel
                    active.transform.reset()
                    active.adjustments.reset()
                    ss.upload_hash = digest
                    clear_render_caches()
                    ss.crop_version += 1
                    flash("import_loaded", name=uploaded.name)
                    st.rerun()
                except Exception as exc:  # noqa: BLE001 – Nutzerfeedback
                    st.error(L("import_failed", error=str(exc)))
    with sample_col:
        onboarding_controls(compact=True)
        st.caption(L("import_sample_hint"))

    st.divider()
    import_image_col, import_ctl_col = st.columns([1.45, 1.0], gap="large")

    with import_image_col, st.container(key="gd-fixed-import"):
        if active.source_image is not None:
            st.caption(L("preview_original"))
            st.image(display_png(ip.resize_for_display(active.source_image, 900, 700)), width="stretch")
            st.caption(L("preview_processed"))
            st.image(display_png(ip.resize_for_display(panel_gel(active), 900, 700)), width="stretch")

            # Perspektiv-Entzerrung gehört direkt an das verarbeitete Bild.
            st.markdown(f"##### {L('persp_title')}")
            st.caption(L("persp_hint"))
            source_preview = ip.resize_for_display(active.source_image, 900, 620)
            result = gel_editor(
                figure=source_preview,
                panel=active,
                layout=corners_layout(source_preview.size),
                mode="corners",
                selected=0,
                labels=editor_labels(),
                key=f"corner_editor_{active.id}",
            )
            handle_editor_result(result, "corners")
            if st.button(L("persp_reset")):
                active.transform.perspective = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
                st.rerun()
            st.caption(L("preview_live_hint"))
        else:
            st.info(L("import_none"))

    with import_ctl_col, st.container(key="gd-scroll-import"):
        st.markdown(f"##### {L('crop_title')}")
        c_auto, c_full = st.columns(2)
        if c_auto.button(L("crop_auto"), width="stretch", disabled=active.source_image is None):
            base = active.transform.model_copy(deep=True)
            base.crop = [0.0, 0.0, 1.0, 1.0]
            transformed = ip.apply_transform(active.source_image, base)
            box = ip.auto_crop_box(transformed)
            width, height = transformed.size
            active.transform.crop = [box[0] / width, box[1] / height, box[2] / width, box[3] / height]
            ss.crop_version += 1
            st.rerun()
        if c_full.button(L("crop_full"), width="stretch"):
            active.transform.crop = [0.0, 0.0, 1.0, 1.0]
            ss.crop_version += 1
            st.rerun()
        st.caption(L("crop_hint"))

        crop = active.transform.crop
        sx = st.slider(
            L("crop_title") + " X (%)",
            0, 100,
            (round(crop[0] * 100), round(crop[2] * 100)),
            key=f"crop_x_{active.id}_{ss.crop_version}",
        )
        sy = st.slider(
            L("crop_title") + " Y (%)",
            0, 100,
            (round(crop[1] * 100), round(crop[3] * 100)),
            key=f"crop_y_{active.id}_{ss.crop_version}",
        )
        new_crop = [sx[0] / 100, sy[0] / 100, sx[1] / 100, sy[1] / 100]
        if [round(v, 4) for v in new_crop] != [round(v, 4) for v in crop]:
            active.transform.crop = new_crop
            st.rerun()

        st.divider()
        st.markdown(f"##### {L('transform_title')}")
        t1, t2 = st.columns(2)
        t3, t4 = st.columns(2)
        if t1.button(L("rotate_cw"), width="stretch"):
            active.transform.rotation = (active.transform.rotation + 90) % 360
            st.rerun()
        if t2.button(L("rotate_ccw"), width="stretch"):
            active.transform.rotation = (active.transform.rotation - 90) % 360
            st.rerun()
        if t3.button(L("flip_h"), width="stretch"):
            active.transform.flip_h = not active.transform.flip_h
            st.rerun()
        if t4.button(L("flip_v"), width="stretch"):
            active.transform.flip_v = not active.transform.flip_v
            st.rerun()
        if st.button(L("transform_reset"), width="stretch"):
            active.transform.reset()
            st.rerun()
        fine = st.slider(
            L("fine_rotation"), -45.0, 45.0, float(active.transform.fine_rotation), 0.1,
            key=f"fine_{active.id}",
        )
        if abs(fine - active.transform.fine_rotation) > 1e-9:
            active.transform.fine_rotation = fine
            st.rerun()

        st.divider()
        st.markdown(f"##### {L('adjust_title')}")
        brightness = st.slider(L("brightness"), -100, 100, int(active.adjustments.brightness))
        contrast = st.slider(L("contrast"), 0.1, 3.0, float(active.adjustments.contrast), 0.05)
        gamma = st.slider(L("gamma"), 0.1, 3.0, float(active.adjustments.gamma), 0.05)
        invert = st.checkbox(L("invert"), value=active.adjustments.invert)
        clahe = st.checkbox(L("clahe"), value=active.adjustments.clahe)
        if (
            brightness != active.adjustments.brightness
            or abs(contrast - active.adjustments.contrast) > 1e-9
            or abs(gamma - active.adjustments.gamma) > 1e-9
            or invert != active.adjustments.invert
            or clahe != active.adjustments.clahe
        ):
            active.adjustments.brightness = float(brightness)
            active.adjustments.contrast = float(contrast)
            active.adjustments.gamma = float(gamma)
            active.adjustments.invert = bool(invert)
            active.adjustments.clahe = bool(clahe)
            st.rerun()
        if st.button(L("adjust_reset")):
            active.adjustments.reset()
            st.rerun()


# ----------------------------------------------------------------------
# Tab 2 – Spuren & Labels
# ----------------------------------------------------------------------
with tab_lanes:
    lanes_tab, typo_tab = st.tabs(
        [L("lanes_controls"), L("sb_typography")],
        default=L("lanes_controls"),
        key="lanes_subtabs",
    )
    with typo_tab:
        typography_controls()
        st.divider()
        if gel is not None:
            figure, _ = preview_figure(active, gel, "lanes")
            st.image(display_png(figure), caption=L("adjust_preview"), width="stretch")
        else:
            st.caption(L("import_none"))

    with lanes_tab:
        st.subheader(L("lanes_title"))
        st.caption(L("lanes_hint"))

        side_values = ["right", "left"]
        ss.editor_side = choice(
            L("editor_side"),
            side_values,
            [L("side_right"), L("side_left")],
            side_values.index(ss.editor_side),
            horizontal=True,
        )

        act = st.columns(4)
        if act[0].button(L("lanes_detect"), width="stretch", disabled=gel is None):
            detection = ip.detect_lanes(gel, len(active.lanes))
            if len(detection.positions_rel) == len(active.lanes):
                for lane, x_rel in zip(active.lanes, detection.positions_rel, strict=False):
                    lane.x_pos_rel = x_rel
                flash("lanes_detected", peaks=detection.detected_peak_count)
                st.rerun()
        if act[1].button(L("lanes_distribute"), width="stretch"):
            distribute_lanes(active)
            st.rerun()
        if act[2].button(L("lanes_renumber"), width="stretch"):
            renumber_lanes(active)
            st.rerun()
        if act[3].button(L("lanes_add"), width="stretch", help=L("lanes_add_help")):
            xs = sorted(lane.x_pos_rel for lane in active.lanes)
            gaps = [(xs[i + 1] - xs[i], (xs[i] + xs[i + 1]) / 2) for i in range(len(xs) - 1)]
            gaps = [(xs[0], xs[0] / 2)] + gaps + [(1.0 - xs[-1], (xs[-1] + 1.0) / 2)]
            _, x_new = max(gaps, key=lambda item: item[0])
            ss.selected_lane = insert_lane(active, float(clamp(x_new, 0.0, 1.0)))
            flash("msg_lane_inserted", index=ss.selected_lane + 1)
            st.rerun()

        count_cols = st.columns([1.0, 0.75, 1.75], vertical_alignment="bottom")
        lane_count = count_cols[0].number_input(
            L("lanes_count"),
            min_value=1,
            max_value=30,
            value=len(active.lanes),
            step=1,
            key=f"lane_count_{active.id}_{len(active.lanes)}",
            help=L("lanes_count_help"),
        )
        if count_cols[1].button(L("count_apply"), width="stretch", key=f"lane_count_apply_{active.id}"):
            set_lane_count(active, int(lane_count))
            ss.selected_lane = 0
            ss.ui_version += 1
            flash("lanes_count_set", count=int(lane_count))
            st.rerun()

        if ss.editor_side == "left":
            controls_col, image_col = st.columns([1.0, 1.12], gap="large")
        else:
            image_col, controls_col = st.columns([1.12, 1.0], gap="large")

        with image_col, st.container(key="gd-sticky-lanes"):
            if gel is not None:
                figure, layout = preview_figure(active, gel, "lanes")
                result = gel_editor(
                    figure=figure,
                    panel=active,
                    layout=layout,
                    mode="lanes",
                    selected=ss.selected_lane,
                    labels=editor_labels(),
                    key=f"lane_editor_{active.id}",
                    show_lane_numbers=ss.project.export.lane_numbers_position != "none",
                )
                handle_editor_result(result, "lanes")
            st.caption(L("lanes_editor_hint"))

        with controls_col, st.container(key="gd-scroll-lanes"):
            ss.selected_lane = int(clamp(ss.selected_lane, 0, len(active.lanes) - 1))
            lane_labels = [f"{L('lane')} {i + 1} · {''.join(text for text, _ in cr.parse_rich(active.lanes[i].label_top))}" for i in range(len(active.lanes))]
            ss.selected_lane = lane_labels.index(
                st.selectbox(L("lanes_selected"), options=lane_labels, index=ss.selected_lane)
            )
            if st.button(L("lanes_delete"), width="stretch", disabled=len(active.lanes) <= 1) and remove_lane(active, ss.selected_lane):
                ss.selected_lane = max(0, min(ss.selected_lane, len(active.lanes) - 1))
                flash("msg_lane_deleted")
                st.rerun()

            st.caption(L("lanes_markup_hint"))
            label_result = label_editor(
                active.lanes, key=f"labels_{active.id}_{ss.ui_version}_{len(active.lanes)}",
                lang=ss.project.lang, dark=ss.ui_theme == "dark",
            )
            if isinstance(label_result, dict) and label_result.get("nonce") != ss.get("label_edit_nonce"):
                try:
                    rows = label_result.get("rows")
                    if not isinstance(rows, list) or len(rows) != len(active.lanes):
                        raise ValueError("Invalid rows")
                    values = []
                    for row in rows:
                        x = float(row["x"])
                        if not 0 <= x <= 100:
                            raise ValueError("Invalid position")
                        values.append((encode_runs(row["top"]), encode_runs(row["bottom"]), x / 100))
                except (ValueError, TypeError, KeyError):
                    st.error("Ungültige Beschriftung oder Position" if ss.project.lang == "de" else "Invalid label or position")
                else:
                    ss.label_edit_nonce = label_result.get("nonce")
                    for lane, (top, bottom, x) in zip(active.lanes, values):
                        lane.label_top, lane.label_bottom, lane.x_pos_rel = top, bottom, x
                    ss.ui_version += 1
                    st.rerun()

            st.divider()
            marker_lane_labels = [f"{L('lane')} {i + 1} · {''.join(text for text, _ in cr.parse_rich(active.lanes[i].label_top))}" for i in range(len(active.lanes))]
            defaults = [marker_lane_labels[i] for i in active.marker_lane_indexes if 0 <= i < len(marker_lane_labels)]
            chosen = st.multiselect(
                L("lanes_marker_lanes"), options=marker_lane_labels, default=defaults, help=L("lanes_marker_lanes_help")
            )
            new_indexes = [marker_lane_labels.index(item) for item in chosen]
            if new_indexes != list(active.marker_lane_indexes):
                active.marker_lane_indexes = new_indexes

            st.divider()
            st.subheader(L("group_title"))
            group_df = pd.DataFrame(
                {
                    L("group_text"): pd.Series([g.text for g in active.groups], dtype="object"),
                    L("group_from"): pd.Series([g.start_index + 1 for g in active.groups], dtype="float"),
                    L("group_to"): pd.Series([g.end_index + 1 for g in active.groups], dtype="float"),
                    L("group_underline"): pd.Series([g.underline for g in active.groups], dtype=bool),
                }
            )
            edited_groups = st.data_editor(
                group_df,
                hide_index=True,
                width="stretch",
                num_rows="dynamic",
                column_config={
                    L("group_from"): st.column_config.NumberColumn(min_value=1, max_value=max(1, len(active.lanes)), step=1),
                    L("group_to"): st.column_config.NumberColumn(min_value=1, max_value=max(1, len(active.lanes)), step=1),
                },
                key=f"group_table_{active.id}_{len(active.groups)}",
            )
            rebuilt_groups: list[GroupLabel] = []
            for _, row in edited_groups.iterrows():
                text = _text(row[L("group_text")])
                if not text:
                    continue
                rebuilt_groups.append(
                    GroupLabel(
                        text=text,
                        start_index=int(clamp(int(_num(row[L("group_from")], 1)) - 1, 0, len(active.lanes) - 1)),
                        end_index=int(clamp(int(_num(row[L("group_to")], 1)) - 1, 0, len(active.lanes) - 1)),
                        underline=_flag(row[L("group_underline")]),
                    )
                )
            if [g.model_dump() for g in rebuilt_groups] != [g.model_dump() for g in active.groups]:
                active.groups = rebuilt_groups
                st.rerun()
            if not active.groups:
                st.caption(L("group_none"))

            st.divider()
            st.subheader(L("cond_title"))
            st.caption(L("cond_hint"))
            cond_data: dict[str, list] = {"Bedingung": [c.name for c in active.conditions]}
            for index in range(len(active.lanes)):
                cond_data[f"S{index + 1}"] = [c.value_for(index) for c in active.conditions]
            cond_df = pd.DataFrame(cond_data)
            edited_conditions = st.data_editor(
                cond_df,
                hide_index=True,
                width="stretch",
                num_rows="dynamic",
                key=f"cond_table_{active.id}_{len(active.conditions)}_{len(active.lanes)}",
            )
            rebuilt_conditions = [
                ConditionRow(
                    name=_text(row["Bedingung"]),
                    values=[_text(row[f"S{index + 1}"]) for index in range(len(active.lanes))],
                )
                for _, row in edited_conditions.iterrows()
                if _text(row["Bedingung"]) or any(_text(row[f"S{i + 1}"]) for i in range(len(active.lanes)))
            ]
            if [c.model_dump() for c in rebuilt_conditions] != [c.model_dump() for c in active.conditions]:
                active.conditions = rebuilt_conditions
                st.rerun()
            if not active.conditions:
                st.caption(L("cond_none"))


# ----------------------------------------------------------------------
# Tab 3 – Marker & Leiter
# ----------------------------------------------------------------------
with tab_markers:
    st.subheader(L("markers_title"))
    markers_image_col, markers_ctl_col = work_area("markers")

    with markers_image_col, st.container(key="gd-sticky-markers"):
        if gel is not None:
            figure, layout = preview_figure(active, gel, "markers")
            result = gel_editor(
                figure=figure,
                panel=active,
                layout=layout,
                mode="markers",
                selected=ss.selected_marker,
                labels=editor_labels(),
                key=f"marker_editor_{active.id}",
            )
            handle_editor_result(result, "markers")
        st.caption(L("markers_editor_hint"))

    with markers_ctl_col, st.container(key="gd-scroll-markers"):
        unit_value = st.text_input(
            L("unit"),
            value=active.unit,
            max_chars=12,
            help=L("unit_help"),
            key=f"unit_{active.id}",
        )
        unit_value = unit_value.strip() or "kDa"
        if unit_value != active.unit:
            active.unit = unit_value
            for marker in active.markers:
                marker.unit = unit_value
            ss.ui_version += 1
            st.rerun()

        side_values = ["left", "right", "both"]
        chosen_side = choice(
            L("markers_ladder_side"),
            side_values,
            [L("ladder_left"), L("ladder_right"), L("ladder_both")],
            side_values.index(active.ladder_sides),
            horizontal=True,
        )
        if chosen_side != active.ladder_sides:
            active.ladder_sides = chosen_side
            st.rerun()

        det = st.columns(3)
        if det[0].button(L("markers_detect_left"), width="stretch", disabled=gel is None):
            detection = ip.detect_marker_bands(gel, "left", count=len(visible_markers(active)))
            if len(detection.positions_rel) >= 3:
                for marker, y_rel in zip(visible_markers(active), detection.positions_rel, strict=False):
                    marker.y_pos_rel = y_rel
                ss.ui_version += 1
                flash("markers_detected_left", count=len(detection.positions_rel))
                st.rerun()
            else:
                st.warning(L("markers_too_few"))
        if det[1].button(L("markers_detect_right"), width="stretch", disabled=gel is None):
            detection = ip.detect_marker_bands(gel, "right", count=len(visible_markers(active)))
            if len(detection.positions_rel) >= 3:
                for marker, y_rel in zip(visible_markers(active), detection.positions_rel, strict=False):
                    marker.y_pos_rel = y_rel
                ss.ui_version += 1
                flash("markers_detected_right", count=len(detection.positions_rel))
                st.rerun()
            else:
                st.warning(L("markers_too_few"))
        if det[2].button(L("markers_reset"), width="stretch"):
            reset_markers(active)
            ss.ui_version += 1
            st.rerun()

        marker_count_cols = st.columns([1.0, 0.75, 1.75], vertical_alignment="bottom")
        marker_count = marker_count_cols[0].number_input(
            L("markers_count"),
            min_value=1,
            max_value=30,
            value=max(1, len(visible_markers(active))),
            step=1,
            key=f"marker_count_{active.id}_{len(active.markers)}",
            help=L("markers_count_help"),
        )
        if marker_count_cols[1].button(L("count_apply"), width="stretch", key=f"marker_count_apply_{active.id}"):
            set_marker_count(active, int(marker_count))
            ss.selected_marker = 0
            ss.ui_version += 1
            flash("markers_count_set", count=int(marker_count))
            st.rerun()

        markers = visible_markers(active)
        ss.selected_marker = int(clamp(ss.selected_marker, 0, max(0, len(markers) - 1)))
        if markers:
            marker_labels = [f"{m.display_value} {active.unit} · {m.y_pos_rel * 100:.1f} %" for m in markers]
            ss.selected_marker = marker_labels.index(
                st.selectbox(L("markers_selected"), options=marker_labels, index=ss.selected_marker)
            )
            selected_marker = markers[ss.selected_marker]
            version = ss.ui_version
            y_pct = st.slider(
                L("markers_y"), 0.0, 100.0, float(round(selected_marker.y_pos_rel * 100, 1)), 0.1,
                key=f"marker_y_{active.id}_{ss.selected_marker}_{version}",
            )
            value = st.number_input(
                L("markers_value", unit=active.unit), 0.0, 10000.0, float(selected_marker.mw), 1.0,
                key=f"marker_value_{active.id}_{ss.selected_marker}_{version}",
            )
            visible = st.checkbox(
                L("visible"), value=selected_marker.visible,
                key=f"marker_visible_{active.id}_{ss.selected_marker}_{version}",
            )
            if (
                abs(y_pct / 100 - selected_marker.y_pos_rel) > 1e-6
                or abs(value - selected_marker.mw) > 1e-9
                or visible != selected_marker.visible
            ):
                selected_marker.y_pos_rel = y_pct / 100.0
                selected_marker.mw = float(value)
                selected_marker.visible = bool(visible)
                ss.ui_version += 1
                st.rerun()
        else:
            st.info(L("markers_none"))

        b1, b2 = st.columns(2)
        if b1.button(L("markers_add"), width="stretch"):
            if markers:
                y_new = float(clamp(markers[-1].y_pos_rel + 0.05, 0.01, 0.99))
            else:
                y_new = 0.5
            value = active.marker_mw_at(y_new) or 50.0
            new_marker = MarkerBand(mw=value, y_pos_rel=y_new, unit=active.unit)
            active.markers.append(new_marker)
            active.markers.sort(key=lambda item: item.y_pos_rel)
            ss.selected_marker = index_of_identity(visible_markers(active), new_marker)
            ss.ui_version += 1
            flash("msg_marker_added", value=new_marker.display_value)
            st.rerun()
        if b2.button(L("markers_delete"), width="stretch", disabled=not markers):
            active.markers.remove(markers[ss.selected_marker])
            ss.selected_marker = max(0, ss.selected_marker - 1)
            ss.ui_version += 1
            flash("msg_marker_removed")
            st.rerun()

        value_col = L("markers_value", unit=active.unit)
        marker_df = pd.DataFrame(
            {
                L("markers_table_no"): list(range(1, len(active.markers) + 1)),
                value_col: [m.mw for m in active.markers],
                L("markers_table_y"): [round(m.y_pos_rel * 100, 2) for m in active.markers],
                L("markers_table_visible"): pd.Series([m.visible for m in active.markers], dtype=bool),
            }
        )
        edited_markers = st.data_editor(
            marker_df,
            hide_index=True,
            width="stretch",
            disabled=[L("markers_table_no")],
            num_rows="fixed",
            column_config={
                value_col: st.column_config.NumberColumn(min_value=0.0, max_value=10000.0, step=1.0, format="%.2f"),
                L("markers_table_y"): st.column_config.NumberColumn(min_value=0.0, max_value=100.0, step=0.1, format="%.2f"),
                L("markers_table_visible"): st.column_config.CheckboxColumn(),
            },
            key=f"marker_table_{active.id}_{len(active.markers)}",
        )
        marker_changed = False
        for index, marker in enumerate(active.markers):
            value = _num(edited_markers.iloc[index][value_col], marker.mw)
            y_pct = _num(edited_markers.iloc[index][L("markers_table_y")], marker.y_pos_rel * 100)
            visible = _flag(edited_markers.iloc[index][L("markers_table_visible")])
            if abs(value - marker.mw) > 1e-9 or abs(y_pct / 100 - marker.y_pos_rel) > 1e-9 or visible != marker.visible:
                marker_changed = True
            marker.mw = value
            marker.y_pos_rel = float(clamp(y_pct / 100.0, 0.0, 1.0))
            marker.visible = visible
        if marker_changed:
            active.markers.sort(key=lambda item: item.y_pos_rel)
            ss.ui_version += 1
            st.rerun()


# ----------------------------------------------------------------------
# Tab 4 – Zielbanden
# ----------------------------------------------------------------------
with tab_targets:
    st.subheader(L("targets_title"))
    st.caption(L("targets_hint"))
    targets_image_col, targets_ctl_col = work_area("targets")

    with targets_image_col, st.container(key="gd-sticky-targets"):
        if gel is not None:
            figure, layout = preview_figure(active, gel, "targets")
            result = gel_editor(
                figure=figure,
                panel=active,
                layout=layout,
                mode="targets",
                selected=ss.selected_arrow,
                labels=editor_labels(),
                key=f"target_editor_{active.id}",
            )
            handle_editor_result(result, "targets")
        st.caption(L("targets_editor_hint"))

    with targets_ctl_col, st.container(key="gd-scroll-targets"):
        requested_sides = {"left", "right"} if active.ladder_sides == "both" else {active.ladder_sides}
        arrow_sides = {a.side for a in visible_arrows(active)}
        if requested_sides & arrow_sides:
            st.warning(L("targets_scale_conflict"))

        if st.button(L("targets_add"), width="stretch"):
            new_arrow = TargetArrow(label="", y_pos_rel=0.5, side="right")
            active.arrows.append(new_arrow)
            ss.selected_arrow = index_of_identity(visible_arrows(active), new_arrow)
            flash("msg_arrow_added")
            st.rerun()

        arrows = visible_arrows(active)
        ss.selected_arrow = int(clamp(ss.selected_arrow, 0, max(0, len(arrows) - 1)))
        if arrows:
            arrow_labels = [f"{i + 1} · {a.label or '—'} · {a.y_pos_rel * 100:.1f} % · {L('side_left') if a.side == 'left' else L('side_right')}" for i, a in enumerate(arrows)]
            ss.selected_arrow = arrow_labels.index(
                st.selectbox(L("targets_selected"), options=arrow_labels, index=ss.selected_arrow)
            )
            selected_arrow = arrows[ss.selected_arrow]
            label = st.text_input(L("targets_label"), value=selected_arrow.label)
            y_pct = st.slider(L("targets_y"), 0.0, 100.0, float(round(selected_arrow.y_pos_rel * 100, 1)), 0.1,
                              key=f"arrow_y_{active.id}_{ss.selected_arrow}_{ss.ui_version}")
            c1, c2 = st.columns(2)
            side = c1.radio(L("targets_side"), options=[L("side_right"), L("side_left")],
                            index=0 if selected_arrow.side == "right" else 1)
            visible = c2.checkbox(L("visible"), value=selected_arrow.visible,
                                  key=f"arrow_visible_{active.id}_{ss.selected_arrow}")
            new_side = "right" if side == L("side_right") else "left"
            if (
                label != selected_arrow.label
                or abs(y_pct / 100 - selected_arrow.y_pos_rel) > 1e-6
                or new_side != selected_arrow.side
                or visible != selected_arrow.visible
            ):
                selected_arrow.label = label
                selected_arrow.y_pos_rel = y_pct / 100.0
                selected_arrow.side = new_side
                selected_arrow.visible = bool(visible)
                st.rerun()
            if st.button(L("targets_delete"), width="stretch"):
                active.arrows.remove(selected_arrow)
                ss.selected_arrow = max(0, ss.selected_arrow - 1)
                flash("msg_arrow_removed")
                st.rerun()
        else:
            st.info(L("targets_none"))

        arrow_df = pd.DataFrame(
            {
                L("targets_table_no"): list(range(1, len(active.arrows) + 1)),
                L("targets_table_label"): pd.Series([a.label for a in active.arrows], dtype="object"),
                L("targets_table_y"): [round(a.y_pos_rel * 100, 2) for a in active.arrows],
                L("targets_table_side"): pd.Series(
                    [L("side_left") if a.side == "left" else L("side_right") for a in active.arrows],
                    dtype="object",
                ),
                L("visible"): pd.Series([a.visible for a in active.arrows], dtype=bool),
            }
        )
        edited_arrows = st.data_editor(
            arrow_df,
            hide_index=True,
            width="stretch",
            disabled=[L("targets_table_no")],
            num_rows="fixed",
            column_config={
                L("targets_table_y"): st.column_config.NumberColumn(min_value=0.0, max_value=100.0, step=0.1, format="%.2f"),
                L("visible"): st.column_config.CheckboxColumn(),
            },
            key=f"arrow_table_{active.id}_{len(active.arrows)}",
        )
        arrow_changed = False
        for index, arrow in enumerate(active.arrows):
            label = _text(edited_arrows.iloc[index][L("targets_table_label")])
            y_pct = _num(edited_arrows.iloc[index][L("targets_table_y")], arrow.y_pos_rel * 100)
            side_text = _text(edited_arrows.iloc[index][L("targets_table_side")])
            visible = _flag(edited_arrows.iloc[index][L("visible")])
            new_side = "left" if side_text == L("side_left") else "right"
            if label != arrow.label or abs(y_pct / 100 - arrow.y_pos_rel) > 1e-9 or new_side != arrow.side or visible != arrow.visible:
                arrow_changed = True
            arrow.label = label
            arrow.y_pos_rel = float(clamp(y_pct / 100.0, 0.0, 1.0))
            arrow.side = new_side
            arrow.visible = visible
        if arrow_changed:
            st.rerun()


# ----------------------------------------------------------------------
# Tab 5 – Multi-Gel & Export
# ----------------------------------------------------------------------
def build_export_panels() -> tuple[list[GelPanel], list[Image.Image]]:
    """Bereitet alle Panels inkl. Harmonisierung für den Export auf."""
    panels: list[GelPanel] = []
    gels: list[Image.Image] = []
    fill = options.colors["background"]
    for p in ss.project.panels:
        if p.source_image is None:
            continue
        if ss.project.export.harmonization == "none":
            gels.append(get_processed(p))
            panels.append(p)
        else:
            harmonized_gel, mapper = ip.harmonize_panel(p, ss.project, fill=fill)
            gels.append(harmonized_gel)
            panels.append(ip.remap_panel(p, mapper))
    return panels, gels


def project_signature() -> str:
    """Signatur des gesamten Projektstands (ohne Bilddaten, die sind excluded)."""
    sources = "|".join(str(id(p.source_image)) for p in ss.project.panels)
    return hashlib.sha1(
        (ss.project.model_dump_json() + options.model_dump_json() + sources).encode("utf-8")
    ).hexdigest()


def render_all() -> tuple[list[GelPanel], list[Image.Image], list[Image.Image]]:
    sig = project_signature()
    cached = ss.export_cache.get("figures")
    if cached is not None and cached[0] == sig:
        return cached[1]
    panels, gels = build_export_panels()
    if not panels:
        result: tuple[list[GelPanel], list[Image.Image], list[Image.Image]] = ([], [], [])
    else:
        overrides = cr.common_layout_overrides(panels, gels, options)
        figures = [
            cr.render_figure(p, g, options, layout=cr.compute_layout(p, g.size, options, **overrides))
            for p, g in zip(panels, gels, strict=True)
        ]
        result = (panels, gels, figures)
    ss.export_cache["figures"] = (sig, result)
    return result


def export_archive(base_name: str, export_panels, figures, combined, gel_sizes) -> bytes:
    """ZIP mit allen Panels; wird nur bei Änderungen neu gepackt."""
    sig = project_signature() + "|" + base_name
    cached = ss.export_cache.get("archive")
    if cached is not None and cached[0] == sig:
        return cached[1]
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for panel_item, fig in zip(export_panels, figures, strict=True):
            bundle.writestr(f"{base_name}_{panel_item.letter}.png", cr.png_bytes(fig, ss.project.export.dpi))
        bundle.writestr(f"{base_name}_kombiniert.png", cr.png_bytes(combined, ss.project.export.dpi))
        bundle.writestr(f"{base_name}_kombiniert.pdf", cr.pdf_bytes(combined, ss.project.export.dpi))
        bundle.writestr(f"{base_name}_metadaten.csv", cr.metadata_csv(ss.project, gel_sizes))
        bundle.writestr(f"{base_name}_metadaten.json", cr.metadata_json(ss.project, gel_sizes))
        bundle.writestr("projekt.json", ss.project.to_json(embed_images=ss.project.export.embed_images))
    data = archive.getvalue()
    ss.export_cache["archive"] = (sig, data)
    return data


def working_view_png(target: GelPanel, gel: Image.Image) -> bytes:
    """Arbeitsansicht als PNG, gecacht über Projektstand und Auswahl."""
    key = f"working:{target.id}:{ss.selected_lane}:{ss.selected_marker}:{ss.selected_arrow}"
    sig = project_signature()
    cached = ss.export_cache.get(key)
    if cached is not None and cached[0] == sig:
        return cached[1]
    working = cr.render_working_view(
        target,
        gel,
        options,
        selected_lane=ss.selected_lane,
        selected_marker=ss.selected_marker,
        selected_arrow=ss.selected_arrow,
    )
    data = cr.png_bytes(working, ss.project.export.dpi)
    ss.export_cache[key] = (sig, data)
    return data


def export_bytes(kind: str, figure: Image.Image) -> bytes:
    """PNG/TIFF/PDF erst auf Änderung neu erzeugen, nicht bei jedem Rerun."""
    dpi = ss.project.export.dpi
    key = f"bytes:{kind}:{dpi}:{hashlib.sha1(figure.tobytes()).hexdigest()}"
    cached = ss.export_cache.get(key)
    if cached is not None:
        return cached
    encoder = {"png": cr.png_bytes, "tiff": cr.tiff_bytes, "pdf": cr.pdf_bytes}[kind]
    data = encoder(figure, dpi)
    stale = [entry for entry in ss.export_cache if entry.startswith("bytes:")]
    if len(stale) >= 9:
        for entry in stale:
            ss.export_cache.pop(entry, None)
    ss.export_cache[key] = data
    return data


if tab_export.open:
    with tab_export:
        st.subheader(L("export_title"))

        export_panels, export_gels, figures = render_all()
        if not figures:
            st.info(L("export_no_source"))
        else:
            logs = {p.id: (p.letter, p.name) for p in ss.project.panels}
            gel_sizes = {panel_item.id: g.size for panel_item, g in zip(export_panels, export_gels, strict=True)}
            combined = cr.compose_panels(figures, gutter=ss.project.export.gutter_px, background=options.colors["background"])
            stamp = datetime.now().strftime("%Y%m%d_%H%M")
            base_name = f"sds_page_{stamp}"

            scope_values = ["single", "combined"]
            scope = choice(
                L("export_preview"),
                scope_values,
                [L("export_single"), L("export_combined")],
                0,
                horizontal=True,
                key="export_scope",
            )
            if scope == "combined":
                figure = combined
                crop_name = "kombiniert"
            else:
                active_index = next((i for i, p in enumerate(export_panels) if p.id == active.id), 0)
                figure = figures[active_index]
                crop_name = active.letter

            export_image_col, export_ctl_col = work_area("export")

            with export_image_col, st.container(key="gd-sticky-export"):
                st.image(
                    display_png(figure),
                    caption=f"{figure.width} × {figure.height} px · {ss.project.export.dpi} DPI",
                    width="stretch",
                )

            with export_ctl_col, st.container(key="gd-scroll-export"):
                st.markdown(f"##### {L('export_title')}")
                png = export_bytes("png", figure)
                tiff = export_bytes("tiff", figure)
                pdf = export_bytes("pdf", figure)
                st.download_button(L("export_png"), data=png, file_name=f"{base_name}_{crop_name}.png", mime="image/png", type="primary", width="stretch")
                st.download_button(L("export_tiff"), data=tiff, file_name=f"{base_name}_{crop_name}.tiff", mime="image/tiff", width="stretch")
                st.download_button(L("export_pdf"), data=pdf, file_name=f"{base_name}_{crop_name}.pdf", mime="application/pdf", width="stretch")
                csv_data = cr.metadata_csv(ss.project, gel_sizes).encode("utf-8")
                json_data = cr.metadata_json(ss.project, gel_sizes).encode("utf-8")
                st.download_button(
                    L("export_csv"),
                    data=csv_data,
                    file_name=f"{base_name}_metadaten.csv",
                    mime="text/csv",
                    width="stretch",
                )
                st.download_button(
                    L("export_json"),
                    data=json_data,
                    file_name=f"{base_name}_metadaten.json",
                    mime="application/json",
                    width="stretch",
                )

                archive = export_archive(base_name, export_panels, figures, combined, gel_sizes)
                st.download_button(L("export_zip"), data=archive, file_name=f"{base_name}.zip", mime="application/zip", width="stretch")

                st.divider()
                if gel is not None:
                    st.download_button(
                        L("export_working_view"),
                        data=working_view_png(active, gel),
                        file_name=f"{base_name}_arbeitsansicht.png",
                        mime="image/png",
                        width="stretch",
                        help=L("export_working_help"),
                    )
                layout = cr.compute_layout(active, gel.size, options) if gel is not None else None
                if layout is not None:
                    st.caption(
                        L("export_canvas_info", cw=layout.canvas_w, ch=layout.canvas_h, hh=layout.header_h, lm=layout.left_margin, rm=layout.right_margin)
                    )

            st.divider()
            s1, s2 = st.columns(2)
            with s1:
                st.markdown(f"##### {L('export_lanes_title')}")
                st.dataframe(
                    pd.DataFrame(
                        {
                            L("meta_panel"): [p.letter for p in export_panels for _ in p.lanes],
                            L("lanes_table_index"): [i + 1 for p in export_panels for i in range(len(p.lanes))],
                            L("meta_sample"): [lane.label_top for p in export_panels for lane in p.lanes],
                            L("meta_role"): [L("role_marker") if p.is_marker_lane(i) else L("role_sample") for p in export_panels for i in range(len(p.lanes))],
                        }
                    ),
                    hide_index=True,
                    width="stretch",
                )
            with s2:
                st.markdown(f"##### {L('export_targets_title')}")
                st.dataframe(
                    pd.DataFrame(
                        {
                            L("meta_panel"): [p.letter for p in export_panels for _ in p.arrows],
                            L("targets_table_label"): [a.label for p in export_panels for a in p.arrows],
                            L("targets_table_y"): [f"{a.y_pos_rel * 100:.1f}" for p in export_panels for a in p.arrows],
                            L("targets_table_side"): [L("side_left") if a.side == "left" else L("side_right") for p in export_panels for a in p.arrows],
                        }
                    ),
                    hide_index=True,
                    width="stretch",
                )

            st.success(L("export_success"))

st.divider()
st.caption("GelDoc Studio · " + L("app_title"))
