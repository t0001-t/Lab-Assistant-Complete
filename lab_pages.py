"""Streamlit pages for the Lab Assistant.

The module deliberately does not import the GelDoc renderer or image pipeline.
The gel editor is launched from ``lab_assistant.py`` as a separate page, so the
existing SDS-PAGE implementation stays isolated.
"""

from __future__ import annotations

import hashlib
import html
import io
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st
from PIL import Image

import lab_calculators as calc
from demo_project import has_project_work
from lab_eln import (
    AUDIO_EXTENSIONS,
    IMAGE_EXTENSIONS,
    PRACTICUM_COLORS,
    ELNStore,
    normalize_color,
)
from lab_exports import docx_bytes, pdf_bytes
from lab_gel_bridge import build_project, parse_notes
from lab_locales import tr
from lab_private_storage import data_folder
from lab_synthesis import (
    ocr_image,
    protocol_stats,
    synthesize,
    transcribe_audio,
)
from lab_theme import colored_cards_css

ROOT = Path(__file__).parent


def language() -> str:
    return st.session_state.get("lab_lang", "de")


def T(key: str, **kwargs: object) -> str:
    text = tr(key, language())
    return text.format(**kwargs) if kwargs else text


def _fmt(value: float | None, unit: str = "") -> str:
    if value is None:
        return "–"
    if value != 0 and (abs(value) >= 1e6 or abs(value) < 1e-3):
        text = f"{value:.4e}"
    else:
        text = f"{value:.4g}"
    return f"{text} {unit}".strip()


def _kind_label(kind: str) -> str:
    return {
        "text": T("kind_text"),
        "ocr": T("kind_ocr"),
        "transcript": T("kind_transcript"),
        "edited": T("kind_edited"),
    }.get(kind, kind)


def _style_label(style: str) -> str:
    return {
        "bullet": T("bullet"), "prose": T("prose"), "hybrid": T("hybrid"),
    }.get(style, style)


def _provider_label(provider: str) -> str:
    return {
        "source": T("source_only"), "ollama": T("ollama"),
        "openai": T("openai"), "edited": T("kind_edited"),
    }.get(provider, provider)


def _preview(data: bytes, name: str) -> None:
    suffix = Path(name).suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        try:
            image = Image.open(io.BytesIO(data))
            image.load()
            st.image(image, caption=name)
        except Exception:  # noqa: BLE001 - optional image/audio backend errors are user-facing
            st.caption(T("no_preview"))
    elif suffix in AUDIO_EXTENSIONS:
        try:
            st.audio(data)
        except Exception:  # noqa: BLE001 - optional audio backend errors are user-facing
            st.caption(T("no_preview"))
    else:
        st.caption(T("no_preview"))


# --------------------------------------------------------------------- calculators
def calculator_page() -> None:
    st.title(T("calculators"))
    count_tab, mol_tab, dilution_tab, mix_tab, units_tab, qpcr_tab = st.tabs(
        [
            T("count"),
            T("molarity"),
            T("dilution"),
            T("mastermix"),
            T("units"),
            T("qpcr"),
        ]
    )

    with count_tab:
        st.caption(T("formula_count"))
        n = int(st.number_input(T("squares"), min_value=1, max_value=100,
                                value=4, step=1, key="nb_squares"))
        include_dead = st.checkbox(T("dead_optional"), key="nb_dead")
        st.caption(T("include_dead_hint"))
        with st.form("count_form"):
            columns = st.columns(min(n, 5))
            live = [
                columns[index % len(columns)].number_input(
                    f"{T('live')} {index + 1}", min_value=0, value=0, step=1,
                    key=f"live_{index}",
                )
                for index in range(n)
            ]
            dead = [
                columns[index % len(columns)].number_input(
                    f"{T('dead')} {index + 1}", min_value=0, value=0, step=1,
                    key=f"dead_{index}",
                )
                for index in range(n)
            ] if include_dead else None
            a, b = st.columns(2)
            factor = a.number_input(T("dilution_factor"), min_value=1e-6, value=1.0, format="%.6g")
            suspension = b.number_input(T("suspension"), min_value=1e-6, value=1.0, format="%.6g")
            a, b = st.columns(2)
            target = a.number_input(T("target_cells"), min_value=0.0, value=0.0, format="%.6g")
            target_conc = b.number_input(T("target_conc"), min_value=0.0, value=0.0, format="%.6g")
            st.caption(T("target_cells_hint"))
            submitted = st.form_submit_button(T("calculate"))
        if submitted:
            try:
                result = calc.neubauer(
                    live, dead, factor, suspension,
                    target or None, target_conc or None,
                )
                a, b, c = st.columns(3)
                a.metric(T("live_conc"), _fmt(result.live_per_ml, "/mL"))
                b.metric(T("total_conc"), _fmt(result.total_per_ml, "/mL"))
                c.metric(T("viability"), T("unavailable") if result.viability_percent is None
                         else f"{result.viability_percent:.2f} %")
                a, b, c = st.columns(3)
                a.metric(T("total_live"), _fmt(result.total_live_cells))
                b.metric(T("total_cells"), _fmt(result.total_cells_in_suspension))
                c.metric(T("dead_total"), _fmt(result.total_dead_cells))
                if result.stock_volume_ml is not None:
                    a, b = st.columns(2)
                    a.metric(T("stock_needed"), _fmt(result.stock_volume_ml, "mL"))
                    if result.medium_volume_ml is not None:
                        b.metric(T("medium_needed"), _fmt(result.medium_volume_ml, "mL"))
                    else:
                        b.caption(T("no_medium"))
                st.caption(T("seeding_hint"))
            except ValueError:
                st.error(T("invalid"))

    with mol_tab:
        st.caption(T("formula_m"))
        st.caption(T("solve_hint"))
        solve = st.selectbox(
            T("solve"), ["m", "c", "V", "M"],
            format_func=lambda value: {
                "m": T("mass"), "c": T("concentration"),
                "V": T("volume"), "M": T("molar_mass"),
            }[value],
        )
        with st.form("molarity_form"):
            fields = {
                "m": (T("mass"), calc.MASS_UNITS, "g", 1.0),
                "c": (T("concentration"), calc.CONCENTRATION_UNITS, "mol/L", 0.1),
                "V": (T("volume"), calc.VOLUME_UNITS, "mL", 10.0),
                "M": (T("molar_mass"), calc.MOLAR_MASS_UNITS, "g/mol", 100.0),
            }
            entered: dict[str, float] = {}
            factors: dict[str, float] = {}
            labels: dict[str, str] = {}
            for key, (label, units, default_unit, default_value) in fields.items():
                left, right = st.columns([2, 1])
                entered[key] = left.number_input(
                    label, min_value=0.0, value=default_value,
                    disabled=key == solve, key=f"mol_{key}", format="%.6g",
                )
                labels[key] = right.selectbox(
                    f"{label}: {T('unit')}", list(units),
                    index=list(units).index(default_unit), key=f"mol_unit_{key}",
                )
                factors[key] = units[labels[key]]
            submitted = st.form_submit_button(T("calculate"))
        if submitted:
            try:
                canonical = {
                    key: entered[key] * factors[key] for key in fields if key != solve
                }
                answer = calc.molarity(
                    solve=solve, mass_g=canonical.get("m"),
                    concentration_mol_l=canonical.get("c"),
                    volume_l=canonical.get("V"),
                    molar_mass_g_mol=canonical.get("M"),
                )
                st.metric(T("result"), _fmt(answer / factors[solve], labels[solve]))
                st.caption(
                    f"{T('canonical')}: m={_fmt(canonical.get('m'), 'g')} · "
                    f"c={_fmt(canonical.get('c'), 'mol/L')} · "
                    f"V={_fmt(canonical.get('V'), 'L')} · "
                    f"M={_fmt(canonical.get('M'), 'g/mol')}"
                )
                st.caption(T("unit_hint"))
            except ValueError:
                st.error(T("invalid"))

    with dilution_tab:
        st.caption(T("formula_d"))
        st.caption(T("dilution_hint"))
        solve = st.selectbox(
            T("solve"), ["c1", "v1", "c2", "v2"], key="dil_solve",
            format_func=lambda value: {"c1": "C₁", "v1": "V₁", "c2": "C₂", "v2": "V₂"}[value],
        )
        with st.form("dilution_form"):
            entered: dict[str, float] = {}
            factors: dict[str, float] = {}
            labels: dict[str, str] = {}
            for key in ("c1", "v1", "c2", "v2"):
                units = calc.CONCENTRATION_UNITS if key.startswith("c") else calc.VOLUME_UNITS
                default_unit = "mmol/L" if key.startswith("c") else "mL"
                left, right = st.columns([2, 1])
                entered[key] = left.number_input(
                    key.upper(), min_value=0.0, value=1.0, disabled=key == solve,
                    key=f"dil_{key}", format="%.6g",
                )
                labels[key] = right.selectbox(
                    f"{key.upper()}: {T('unit')}", list(units),
                    index=list(units).index(default_unit), key=f"dil_unit_{key}",
                )
                factors[key] = units[labels[key]]
            submitted = st.form_submit_button(T("calculate"))
        if submitted:
            try:
                values = {
                    key: entered[key] * factors[key] for key in entered if key != solve
                }
                answer = calc.dilution(solve=solve, **values)
                st.metric(T("result"), _fmt(answer / factors[solve], labels[solve]))
                if "v1" in values and "v2" in values:
                    added = values["v2"] - values["v1"]
                elif solve == "v2":
                    added = answer - values["v1"]
                elif solve == "v1":
                    added = values["v2"] - answer
                else:
                    added = None
                if added is not None and added >= 0:
                    st.metric(T("dilution_added"), _fmt(added / calc.VOLUME_UNITS["mL"], "mL"))
            except ValueError:
                st.error(T("invalid"))

    with mix_tab:
        initial = pd.DataFrame([
            {T("reagent"): T("buffer"), T("per_reaction"): 2.5},
            {T("reagent"): T("enzyme"), T("per_reaction"): 0.5},
            {T("reagent"): T("water"), T("per_reaction"): 7.0},
        ])
        st.caption(T("mix_hint"))
        frame = st.data_editor(
            initial, num_rows="dynamic", hide_index=True, key=f"mix_table_{language()}",
            column_config={
                T("reagent"): st.column_config.TextColumn(T("reagent")),
                T("per_reaction"): st.column_config.NumberColumn(
                    T("per_reaction"), min_value=0.0, format="%.4f"
                ),
            },
        )
        a, b = st.columns(2)
        reactions = a.number_input(T("reactions"), min_value=1, value=10, step=1)
        excess = b.number_input(T("excess"), min_value=0.0, max_value=500.0, value=10.0)
        if st.button(T("calculate"), key="mix_calculate"):
            try:
                rows = [
                    (str(row.iloc[0]), float(row.iloc[1]))
                    for _, row in frame.dropna(how="all").iterrows()
                    if str(row.iloc[0]).strip()
                ]
                result = calc.mastermix(rows, int(reactions), excess)
                st.session_state.mix_result = result
                st.session_state.mix_lang = language()
                st.session_state.mix_reactions = int(reactions)
                st.session_state.mix_excess = float(excess)
            except (ValueError, TypeError):
                st.error(T("invalid"))
        result = st.session_state.get("mix_result")
        if result and st.session_state.get("mix_lang") == language():
            table = pd.DataFrame(result).rename(columns={
                "reagent": T("reagent"),
                "per_reaction_ul": T("per_reaction"),
                "total_ul": T("total"),
            })
            st.dataframe(table, hide_index=True, width="stretch")
            total = sum(row["total_ul"] for row in result)
            per_reaction = sum(row["per_reaction_ul"] for row in result)
            a, b, c = st.columns(3)
            a.metric(T("mix_total"), _fmt(total, "µL"))
            b.metric(T("mix_per_reaction"), _fmt(per_reaction, "µL"))
            c.metric(T("excess"), f"{st.session_state.get('mix_excess', 0):g} %")
            st.download_button(
                T("mix_download"),
                table.to_csv(index=False).encode("utf-8-sig"),
                file_name="mastermix.csv", mime="text/csv",
                key="mix_download_button",
            )

    with units_tab:
        st.caption(T("units_hint"))
        group_labels = {
            "mass": T("mass"),
            "volume": T("volume"),
            "concentration": T("concentration"),
            "molar_mass": T("molar_mass"),
            "time": T("duration"),
            "temperature": T("temperature"),
        }
        group = st.selectbox(
            T("unit_group"), calc.UNIT_GROUP_KEYS,
            format_func=lambda value: group_labels[value], key="unit_group",
        )
        units = list(calc.units_for(group))
        left, right = st.columns(2)
        value = left.number_input(
            T("value"), value=1.0, format="%.6g", key=f"unit_value_{group}"
        )
        from_unit = left.selectbox(
            T("from_unit"), units, key=f"unit_from_{group}"
        )
        to_unit = right.selectbox(
            T("to_unit"), units, index=max(0, len(units) - 1),
            key=f"unit_to_{group}",
        )
        if st.button(T("convert"), key="unit_convert", type="primary"):
            try:
                answer = calc.convert_unit(value, group, from_unit, to_unit)
                st.metric(T("result"), _fmt(answer, to_unit))
            except ValueError:
                st.error(T("invalid"))

    with qpcr_tab:
        st.caption(T("qpcr_hint"))
        with st.form("qpcr_form"):
            left, right = st.columns(2)
            target_sample = left.number_input(
                T("qpcr_target_sample"), min_value=0.0, value=25.0,
                format="%.6g", key="qpcr_target_sample",
            )
            reference_sample = left.number_input(
                T("qpcr_ref_sample"), min_value=0.0, value=20.0,
                format="%.6g", key="qpcr_ref_sample",
            )
            target_control = right.number_input(
                T("qpcr_target_control"), min_value=0.0, value=26.0,
                format="%.6g", key="qpcr_target_control",
            )
            reference_control = right.number_input(
                T("qpcr_ref_control"), min_value=0.0, value=20.0,
                format="%.6g", key="qpcr_ref_control",
            )
            efficiency = st.number_input(
                T("qpcr_efficiency"), min_value=0.1, max_value=200.0,
                value=100.0, format="%.6g", key="qpcr_efficiency",
            )
            submitted = st.form_submit_button(T("calculate"))
        if submitted:
            try:
                result = calc.qpcr(
                    target_sample, reference_sample,
                    target_control, reference_control, efficiency,
                )
                a, b = st.columns(2)
                a.metric(T("qpcr_delta_sample"), _fmt(result.delta_ct_sample))
                b.metric(T("qpcr_delta_control"), _fmt(result.delta_ct_control))
                a, b = st.columns(2)
                a.metric(T("qpcr_delta_delta"), _fmt(result.delta_delta_ct))
                b.metric(T("qpcr_fold"), f"{result.fold_change:.4g}×")
                st.caption(T("qpcr_fold_hint", efficiency=f"{result.efficiency_percent:g}"))
            except ValueError:
                st.error(T("invalid"))


# ------------------------------------------------------------------------ notebook
def _store() -> ELNStore:
    return ELNStore(data_folder())


def _dark() -> bool:
    return st.session_state.get("lab_theme") == "dark"


def _chunks(items: list[dict], size: int) -> list[list[dict]]:
    return [items[index:index + size] for index in range(0, len(items), size)]


def _practicum_color(practicum: dict, index: int = 0) -> str:
    return normalize_color(
        practicum.get("color"), PRACTICUM_COLORS[index % len(PRACTICUM_COLORS)]
    )


def _selected_practicum(practica: list[dict]) -> dict:
    mapping = {item["id"]: item for item in practica}
    selected = st.session_state.get("eln_practicum_id")
    if selected not in mapping:
        selected = practica[0]["id"]
        st.session_state.eln_practicum_id = selected
    return mapping[selected]


def _selected_day(days: list[dict]) -> dict:
    ordered = sorted(days, key=lambda item: (item["date"], item["created_at"]))
    mapping = {item["id"]: item for item in ordered}
    selected = st.session_state.get("eln_day_id")
    if selected not in mapping:
        selected = ordered[0]["id"]
        st.session_state.eln_day_id = selected
    return mapping[selected]


def _new_practicum_form(store: ELNStore, key: str) -> None:
    with st.form(key):
        name = st.text_input(T("practicum"))
        field = st.text_input(T("field"))
        color = st.color_picker(T("folder_color"), PRACTICUM_COLORS[0])
        if st.form_submit_button(T("create"), type="primary", width="stretch"):
            try:
                identifier = store.add_practicum(name, field, color)
                st.session_state.eln_practicum_id = identifier
                st.session_state.pop("eln_day_id", None)
                st.rerun()
            except ValueError:
                st.error(T("invalid"))


def _new_day_form(store: ELNStore, practicum: dict, key: str) -> None:
    with st.form(key):
        title = st.text_input(T("title"))
        day_date = st.date_input(T("date"), value=date.today())
        supervisor = st.text_input(T("supervisor"))
        author = st.text_input(T("author"))
        if st.form_submit_button(T("create"), type="primary", width="stretch"):
            try:
                identifier = store.add_day(
                    practicum["id"], day_date.isoformat(), title, supervisor, author
                )
                st.session_state.eln_day_id = identifier
                st.rerun()
            except ValueError:
                st.error(T("invalid"))


def _practicum_bar(store: ELNStore, practica: list[dict], selected: dict) -> None:
    heading, new_button = st.columns([4, 1.1], vertical_alignment="center")
    heading.markdown(
        f'<div class="la-section"><h3>{T("dashboard_practica")}</h3>'
        f'<span>{T("dashboard_practica_hint")}</span></div>',
        unsafe_allow_html=True,
    )
    with new_button, st.popover(
        T("new_practicum"), icon=":material/create_new_folder:", width="stretch"
    ):
        _new_practicum_form(store, "notebook_new_practicum")
    colors = [
        (f"practicum_switch_{item['id']}", _practicum_color(item, index))
        for index, item in enumerate(practica)
    ]
    st.markdown(
        colored_cards_css(colors, _dark(), height="3.1rem", folder_tab=False),
        unsafe_allow_html=True,
    )
    for row in _chunks(practica, 4):
        columns = st.columns(4)
        for column, practicum in zip(columns, row):
            with column:
                if st.button(
                    practicum["name"], key=f"practicum_switch_{practicum['id']}",
                    icon=":material/folder_shared:", width="stretch",
                    type="primary" if practicum["id"] == selected["id"] else "secondary",
                ):
                    st.session_state.eln_practicum_id = practicum["id"]
                    st.session_state.pop("eln_day_id", None)
                    st.rerun()


def _day_cards(store: ELNStore, practicum: dict, days: list[dict], selected: dict) -> None:
    ordered = sorted(days, key=lambda item: (item["date"], item["created_at"]))
    color = normalize_color(practicum.get("color"), PRACTICUM_COLORS[0])
    st.markdown(
        f'<div class="la-section"><h3>{T("experiment_days")}</h3>'
        f'<span>{T("experiment_days_hint")}</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        colored_cards_css(
            [(f"day_open_{item['id']}", color) for item in ordered],
            _dark(), height="4.5rem",
        ),
        unsafe_allow_html=True,
    )
    for row in _chunks(ordered, 4):
        columns = st.columns(4)
        for column, day in zip(columns, row):
            code = f"V{ordered.index(day) + 1}"
            summary = store.day_summary(day["id"])
            with column:
                if st.button(
                    f"{code} · {day['title']}", key=f"day_open_{day['id']}",
                    icon=":material/folder:", width="stretch",
                    type="primary" if day["id"] == selected["id"] else "secondary",
                ):
                    st.session_state.eln_day_id = day["id"]
                    st.rerun()
                st.markdown(
                    f'<div class="la-meta">{day["date"]} · '
                    f'{summary["entries"]} {T("summary_entries")} · '
                    f'{summary["attachments"]} {T("summary_attachments")}</div>',
                    unsafe_allow_html=True,
                )


def _open_result(result: dict) -> None:
    st.session_state.eln_practicum_id = result["practicum_id"]
    st.session_state.eln_day_id = result["day_id"]
    st.rerun()


def _search_block(store: ELNStore) -> None:
    with st.expander(T("search")):
        st.caption(T("search_hint"))
        query = st.text_input(T("search"), placeholder=T("search_placeholder"), key="eln_search_query")
        if not query.strip():
            return
        results = store.search_entries(query)
        if not results:
            st.info(T("no_results"))
            return
        st.caption(f"{len(results)} {T('results_count')}")
        for result in results:
            with st.expander(
                f"{result['day_date']} · {result['practicum_name']} · {result['title']}"
            ):
                st.markdown(result["content"][:1200])
                if st.button(T("open"), key=f"open_search_{result['id']}"):
                    _open_result(result)


def _edit_practicum(store: ELNStore, practicum: dict) -> None:
    with st.expander(T("edit_practicum")):
        with st.form(f"edit_practicum_{practicum['id']}"):
            name = st.text_input(T("practicum"), value=practicum["name"])
            field = st.text_input(T("field"), value=practicum["field"])
            if st.form_submit_button(T("save")):
                try:
                    store.update_practicum(practicum["id"], name, field)
                    st.rerun()
                except ValueError:
                    st.error(T("invalid"))
        confirm = st.checkbox(T("confirm_delete_practicum"), key=f"del_practicum_confirm_{practicum['id']}")
        if st.button(T("delete_practicum"), key=f"del_practicum_{practicum['id']}", disabled=not confirm):
            store.delete_practicum(practicum["id"])
            for key in ("eln_practicum_id", "eln_day_id"):
                st.session_state.pop(key, None)
            st.rerun()


def _edit_day(store: ELNStore, day: dict) -> None:
    with st.expander(T("edit_day")):
        try:
            default_date = date.fromisoformat(day["date"])
        except ValueError:
            default_date = date.today()
        with st.form(f"edit_day_{day['id']}"):
            title = st.text_input(T("title"), value=day["title"])
            day_date = st.date_input(T("date"), value=default_date)
            supervisor = st.text_input(T("supervisor"), value=day["supervisor"])
            author = st.text_input(T("author"), value=day["author"])
            if st.form_submit_button(T("save")):
                try:
                    store.update_day(
                        day["id"], date=day_date.isoformat(), title=title,
                        supervisor=supervisor, author=author,
                    )
                    st.rerun()
                except ValueError:
                    st.error(T("invalid"))
        confirm = st.checkbox(T("confirm_delete_day"), key=f"del_day_confirm_{day['id']}")
        if st.button(T("delete_day"), key=f"del_day_{day['id']}", disabled=not confirm):
            store.delete_day(day["id"])
            st.session_state.pop("eln_day_id", None)
            st.rerun()


def _entry_card(store: ELNStore, entry: dict) -> None:
    label = f"{entry['title']} · {_kind_label(entry['kind'])} · {entry['created_at']}"
    with st.expander(label):
        st.markdown(entry["content"])
        for media in store.list_media(entry["id"]):
            try:
                item, data = store.read_media(media["id"])
            except (KeyError, OSError, ValueError):
                st.error(T("media_broken"))
                continue
            with st.container(border=True):
                st.caption(f"{item['filename']} · {item['bytes'] / 1024:.1f} KB")
                _preview(data, item["filename"])
                st.download_button(
                    f"{T('download')}: {item['filename']}", data,
                    file_name=item["filename"], mime=item["mime"],
                    key=f"media_download_{item['id']}",
                )
        confirm = st.checkbox(T("confirm_delete_entry"), key=f"del_entry_confirm_{entry['id']}")
        if st.button(T("delete_entry"), key=f"del_entry_{entry['id']}", disabled=not confirm):
            store.delete_entry(entry["id"])
            st.success(T("entry_deleted"))
            st.rerun()


def _notes_tab(store: ELNStore, day_id: str) -> None:
    draft = store.get_draft(day_id)
    revision = st.session_state.get(f"eln_revision_{day_id}", 0)
    title_key = f"eln_title_{day_id}_{revision}"
    content_key = f"eln_content_{day_id}_{revision}"

    def autosave() -> None:
        store.save_draft(
            day_id,
            st.session_state.get(title_key, ""),
            st.session_state.get(content_key, ""),
        )

    st.caption(T("autosave"))
    st.caption(T("draft_hint"))
    if draft.get("updated_at"):
        st.caption(f"{T('draft_updated')}: {draft['updated_at']}")
    note_title = st.text_input(
        T("note_title"), value=draft["title"], key=title_key, on_change=autosave,
    )
    content = st.text_area(
        T("notes"), value=draft["content"], height=260, key=content_key, on_change=autosave,
    )
    a, b, c = st.columns(3)
    if a.button(T("save_note"), key=f"save_note_{day_id}"):
        try:
            current_title = st.session_state.get(title_key, note_title)
            current_content = st.session_state.get(content_key, content)
            store.add_entry(day_id, current_title, "text", current_content)
            store.clear_draft(day_id)
            st.session_state[f"eln_revision_{day_id}"] = revision + 1
            st.rerun()
        except ValueError:
            st.error(T("invalid"))
    if b.button(T("save_draft"), key=f"save_draft_{day_id}"):
        autosave()
        st.success(T("draft_saved"))
    if c.button(T("discard_draft"), key=f"discard_draft_{day_id}"):
        store.clear_draft(day_id)
        st.session_state[f"eln_revision_{day_id}"] = revision + 1
        st.rerun()
    st.divider()
    st.subheader(T("entries"))
    entries = store.list_entries(day_id)
    if not entries:
        st.info(T("none"))
    for entry in entries:
        _entry_card(store, entry)


def _extraction_ui(store: ELNStore, day_id: str, name: str, data: bytes) -> None:
    marker = hashlib.sha256(data).hexdigest()
    extraction = st.session_state.get(f"el_extract_{day_id}")
    if not extraction or extraction.get("marker") != marker:
        return
    st.info(T("extraction_ready"))
    key = f"extract_text_{day_id}_{marker}"
    text = st.text_area(T("extracted"), value=extraction["text"], height=200, key=key)
    if st.button(T("save_extraction"), key=f"save_extract_{day_id}_{marker}"):
        try:
            entry_id = store.add_entry(day_id, name, extraction["kind"], text)
            store.add_media(entry_id, name, data)
            st.session_state.pop(f"el_extract_{day_id}", None)
            st.success(T("saved"))
            st.rerun()
        except ValueError:
            st.error(T("invalid"))


def _media_tab(store: ELNStore, day_id: str, lang: str) -> None:
    """Universal import: any file, several files at once, plus audio memos."""
    st.caption(T("notebook_import_hint"))
    revision = st.session_state.get(f"media_revision_{day_id}", 0)
    uploaded = st.file_uploader(
        T("media"), accept_multiple_files=True,
        key=f"media_upload_{day_id}_{revision}",
    )
    recorded = st.audio_input(T("record"), key=f"audio_record_{day_id}_{revision}")
    st.caption(T("record_hint"))
    if uploaded is None:
        files = []
    elif isinstance(uploaded, list):
        files = list(uploaded)
    else:
        files = [uploaded]
    if recorded is not None:
        files.append(recorded)
    if not files:
        return
    items: list[tuple[str, bytes]] = []
    for file in files:
        data = file.getvalue()
        name = getattr(file, "name", "memo.wav")
        if file is recorded and not Path(name).suffix:
            name += ".wav"
        items.append((name, data))
    description = st.text_input(
        T("attachment_note"), key=f"attach_description_{day_id}"
    )
    for name, data in items[:3]:
        st.write(f"{Path(name).name} · {len(data) / 1024:.1f} KB")
        _preview(data, name)
    if len(items) > 3:
        st.caption(f"+{len(items) - 3}")
    if st.button(
        T("notebook_import_button"), key=f"import_files_{day_id}",
        icon=":material/upload_file:", type="primary", width="stretch",
    ):
        try:
            for name, data in items:
                title = description.strip() or Path(name).name
                entry_id = store.add_entry(day_id, title, "text", title)
                store.add_media(entry_id, name, data)
            st.session_state[f"media_revision_{day_id}"] = revision + 1
            st.success(T("notebook_files_added", count=len(items)))
            st.rerun()
        except ValueError:
            st.error(T("invalid"))
    if len(items) != 1:
        return
    name, data = items[0]
    suffix = Path(name).suffix.lower()
    if suffix in IMAGE_EXTENSIONS and st.button(T("run_ocr"), key=f"run_ocr_{day_id}"):
        try:
            st.session_state[f"el_extract_{day_id}"] = {
                "marker": hashlib.sha256(data).hexdigest(),
                "kind": "ocr",
                "text": ocr_image(data, lang),
            }
        except (ValueError, RuntimeError):
            st.error(T("optional"))
    if suffix in AUDIO_EXTENSIONS:
        backend = st.radio(
            T("backend"), ["local", "openai"],
            format_func=lambda value: T("local") if value == "local" else T("api"),
            horizontal=True, key=f"audio_backend_{day_id}",
        )
        st.caption(T("model_hint"))
        model = st.text_input(T("model"), value="small", disabled=backend != "local",
                              key=f"audio_model_{day_id}")
        api_key = st.text_input(T("api_key"), type="password", disabled=backend != "openai",
                                key=f"audio_key_{day_id}")
        consent = st.checkbox(T("api_consent"), disabled=backend != "openai",
                              key=f"audio_consent_{day_id}")
        st.caption(T("api_note"))
        if st.button(T("run_transcription"), key=f"run_transcription_{day_id}"):
            if backend == "openai" and not consent:
                st.error(T("api_consent"))
            else:
                try:
                    st.session_state[f"el_extract_{day_id}"] = {
                        "marker": hashlib.sha256(data).hexdigest(),
                        "kind": "transcript",
                        "text": transcribe_audio(data, name, backend,
                                                 api_key=api_key, model=model),
                    }
                except (ValueError, RuntimeError):
                    st.error(T("optional"))
    _extraction_ui(store, day_id, name, data)


def _protocol_tab(store: ELNStore, day: dict, lang: str) -> None:
    day_id = day["id"]
    entries = store.source_entries(day_id)
    st.caption(T("review"))
    st.caption(T("synthesis_ready_hint"))
    if not entries:
        st.info(T("synthesis_empty"))
        return
    attachment_count = sum(len(entry.get("attachments", [])) for entry in entries)
    a, b, c = st.columns(3)
    a.metric(T("synthesis_sources"), len(entries))
    b.metric(T("summary_attachments"), attachment_count)
    c.metric(T("summary_protocols"), len(store.list_protocols(day_id)))

    style = st.radio(
        T("format"), ["prose", "bullet"], index=0,
        format_func=lambda value: {
            "bullet": T("style_bullet"), "prose": T("style_prose"),
        }[value],
        horizontal=True, key=f"protocol_style_{day_id}",
    )
    with st.expander(T("synthesis_options"), icon=":material/tune:"):
        provider = st.selectbox(
            T("provider"), ["source", "ollama", "openai"],
            format_func=lambda value: {
                "source": T("source_only"), "ollama": T("ollama"), "openai": T("openai"),
            }[value],
            key=f"protocol_provider_{day_id}",
        )
        st.caption(T("provider_hint"))
        model = st.text_input(
            T("model"),
            value="llama3.1" if provider == "ollama" else "gpt-4o-mini",
            disabled=provider == "source", key=f"protocol_model_{day_id}",
        )
        api_key = st.text_input(T("api_key"), type="password", disabled=provider != "openai",
                                key=f"protocol_api_key_{day_id}")
        consent = st.checkbox(T("api_consent"), disabled=provider != "openai",
                              key=f"protocol_consent_{day_id}")
        if provider == "openai":
            st.caption(T("api_note"))
    if st.button(T("generate"), key=f"generate_{day_id}",
                 icon=":material/summarize:", type="primary", width="stretch"):
        if provider == "openai" and not consent:
            st.error(T("api_consent"))
        else:
            try:
                protocol, gaps = synthesize(
                    day, entries, style, lang, provider, model=model, api_key=api_key,
                )
                store.save_protocol(day_id, style, provider, protocol,
                                    [entry["id"] for entry in entries])
                st.session_state.lab_protocol_text = protocol
                st.session_state.lab_protocol_day = day_id
                st.session_state.lab_protocol_style = style
                st.session_state.lab_protocol_revision = st.session_state.get("lab_protocol_revision", 0) + 1
                if gaps:
                    st.warning(T("audit_missing") + " " + ", ".join(gaps[:20]))
                else:
                    st.success(T("protocol_saved"))
            except Exception:  # noqa: BLE001 - provider/network errors become a localized UI message
                st.error(T("optional") if provider != "source" else T("invalid"))

    protocols = store.list_protocols(day_id)
    if protocols:
        selected = st.selectbox(
            T("previous"), protocols,
            format_func=lambda item: (
                f"{item['created_at']} · {_style_label(item['style'])} · "
                f"{_provider_label(item['provider'])}"
            ),
            key=f"previous_protocol_{day_id}",
        )
        a, b = st.columns(2)
        if a.button(T("load_protocol"), key=f"load_protocol_{day_id}"):
            st.session_state.lab_protocol_text = selected["content"]
            st.session_state.lab_protocol_day = day_id
            st.session_state.lab_protocol_style = selected["style"]
            st.session_state.lab_protocol_revision = st.session_state.get("lab_protocol_revision", 0) + 1
            st.rerun()
        confirm = b.checkbox(T("confirm_delete"), key=f"del_protocol_confirm_{day_id}")
        if b.button(T("delete_protocol"), key=f"delete_protocol_{day_id}", disabled=not confirm):
            store.delete_protocol(selected["id"])
            st.success(T("protocol_deleted"))
            st.rerun()

    if st.session_state.get("lab_protocol_day") != day_id:
        st.info(T("no_protocol"))
        return
    protocol = st.session_state.get("lab_protocol_text", "")
    revision = st.session_state.get("lab_protocol_revision", 0)
    key = f"protocol_{day_id}_{revision}"
    edited = st.text_area(T("edit_protocol"), value=protocol, height=460, key=key)
    stats = protocol_stats(edited, entries)
    a, b, c = st.columns(3)
    a.metric(T("synthesis_sections"), stats["sections"])
    b.metric(T("synthesis_sources"), f"{stats['sources']}/{len(entries)}")
    c.metric(T("synthesis_numbers"), stats["numbers"])
    st.download_button(
        T("markdown"), edited.encode("utf-8"),
        file_name="protocol.md", mime="text/markdown",
        key=f"download_md_{day_id}",
    )
    st.download_button(
        T("pdf"), pdf_bytes(edited), file_name="protocol.pdf",
        mime="application/pdf", key=f"download_pdf_{day_id}",
    )
    st.download_button(
        T("docx"), docx_bytes(edited), file_name="protocol.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        key=f"download_docx_{day_id}",
    )
    if st.button(T("save_revision"), key=f"save_revision_{day_id}"):
        store.save_protocol(day_id, st.session_state.get("lab_protocol_style", "hybrid"),
                            "edited", edited, [entry["id"] for entry in entries])
        st.session_state.lab_protocol_text = edited
        st.success(T("protocol_saved"))
        st.rerun()


def _day_text(store: ELNStore, day_id: str) -> str:
    draft = store.get_draft(day_id)
    parts = [draft["content"]] if draft.get("content", "").strip() else []
    for entry in store.source_entries(day_id):
        if entry.get("content", "").strip():
            parts.append(entry["content"])
    return "\n\n".join(parts)


def _day_gel_images(store: ELNStore, day_id: str) -> list[dict]:
    images = []
    for entry in store.source_entries(day_id):
        for media in entry.get("attachments", []):
            if Path(media["filename"]).suffix.lower() in IMAGE_EXTENSIONS:
                images.append(media)
    return images


def _run_gel_bridge(store: ELNStore, day: dict, lang: str) -> None:
    text = _day_text(store, day["id"])
    if not text.strip():
        st.warning(T("gel_bridge_no_notes"))
        return
    images = _day_gel_images(store, day["id"])
    if not images:
        st.warning(T("gel_bridge_no_image"))
        return
    media = images[-1]
    try:
        item, data = store.read_media(media["id"])
        with Image.open(io.BytesIO(data)) as raw:
            image = raw.convert("RGB")
        annotation = parse_notes(text)
        project, report = build_project(
            annotation, image, lang=lang, name=day["title"],
            source_name=item["filename"],
        )
    except (KeyError, OSError, ValueError):
        st.error(T("invalid"))
        return
    theme = "dark" if st.session_state.get("lab_theme") == "dark" else "light"
    project.theme = theme
    project.export.theme = theme
    st.session_state.project = project
    st.session_state.pop("demo_tracking", None)
    st.session_state.active = 0
    st.session_state.selected_lane = 0
    st.session_state.selected_marker = 0
    st.session_state.selected_arrow = 0
    st.session_state.ui_version = st.session_state.get("ui_version", 0) + 1
    st.session_state.crop_version = st.session_state.get("crop_version", 0) + 1
    st.session_state.editor_nonces = {}
    st.session_state.upload_hash = ""
    for cache in ("proc_cache", "display_cache", "preview_cache", "export_cache"):
        st.session_state.get(cache, {}).clear()
    st.session_state.lab_bridge_flash = T(
        "gel_bridge_flash", lanes=report["lane_count"], targets=report["targets"]
    )
    st.session_state.lab_module = "gel"
    st.rerun()


def _notebook_actions(store: ELNStore, day: dict, lang: str) -> None:
    add_column, bridge_column = st.columns(2)
    import_key = f"notebook_import_open_{day['id']}"
    if add_column.button(
        T("notebook_add_docs"), key=f"notebook_add_docs_{day['id']}",
        icon=":material/upload_file:", type="primary", width="stretch",
        help=T("notebook_add_docs_hint"),
    ):
        st.session_state[import_key] = not st.session_state.get(import_key, False)
        st.rerun()
    text = _day_text(store, day["id"])
    images = _day_gel_images(store, day["id"])
    existing = st.session_state.get("project")
    needs_confirm = existing is not None and has_project_work(existing)
    confirmed = True
    if needs_confirm:
        confirmed = st.checkbox(
            T("gel_bridge_confirm"), key=f"gel_bridge_confirm_{day['id']}"
        )
    if bridge_column.button(
        T("notebook_gel_annotate"), key=f"notebook_gel_bridge_{day['id']}",
        icon=":material/colorize:", type="primary", width="stretch",
        help=T("notebook_gel_hint"), disabled=not confirmed,
    ):
        _run_gel_bridge(store, day, lang)
    if text.strip():
        annotation = parse_notes(text)
        if images:
            st.caption(T(
                "gel_bridge_preview",
                lanes=annotation.lane_count or 10,
                conditions=sum(1 for spec in annotation.lanes if spec.condition),
                targets=len(annotation.targets),
            ))
        else:
            st.caption(T("gel_bridge_no_image"))
    else:
        st.caption(T("gel_bridge_no_notes"))

    if st.session_state.get(import_key):
        with st.container(border=True):
            head, close = st.columns([5, 1], vertical_alignment="center")
            head.markdown(f"**{T('notebook_import')}**")
            head.caption(T("notebook_import_hint"))
            if close.button(
                T("cancel"), key=f"notebook_import_close_{day['id']}",
                width="stretch",
            ):
                st.session_state[import_key] = False
                st.rerun()
            _media_tab(store, day["id"], lang)


def notebook_page() -> None:
    lang = language()
    store = _store()
    st.title(T("notebook"))
    st.caption(T("privacy"))
    _search_block(store)

    practica = store.list_practica()
    if not practica:
        st.info(T("no_practicum"))
        with st.expander(T("new_practicum"), expanded=True):
            _new_practicum_form(store, "notebook_first_practicum")
        return
    practicum = _selected_practicum(practica)
    _practicum_bar(store, practica, practicum)

    header, new_day, edit_practicum = st.columns([5, 1, 1], vertical_alignment="center")
    color = normalize_color(practicum.get("color"), PRACTICUM_COLORS[0])
    header.markdown(
        f'<div class="la-section"><h3><span class="la-dot" '
        f'style="background:{color}"></span>{html.escape(practicum["name"])}</h3>'
        f'<span>{html.escape(practicum["field"] or T("field"))}</span></div>',
        unsafe_allow_html=True,
    )
    with new_day, st.popover(
        T("new_day"), icon=":material/add_box:", width="stretch"
    ):
        _new_day_form(store, practicum, "notebook_new_day")
    with edit_practicum, st.popover(
        T("edit_practicum"), icon=":material/edit:", width="stretch"
    ):
        _edit_practicum(store, practicum)

    days = store.list_days(practicum["id"])
    if not days:
        st.info(T("no_day"))
        with st.expander(T("new_day"), expanded=True):
            _new_day_form(store, practicum, "notebook_first_day")
        return
    day = _selected_day(days)
    _day_cards(store, practicum, days, day)

    st.divider()
    title_column, edit_day = st.columns([5, 1], vertical_alignment="center")
    title_column.subheader(day["title"])
    title_column.caption(
        f"{day['date']} · {T('supervisor')}: {day['supervisor'] or '–'} · "
        f"{T('author')}: {day['author'] or '–'}"
    )
    with edit_day, st.popover(
        T("edit_day"), icon=":material/edit_calendar:", width="stretch"
    ):
        _edit_day(store, day)

    summary = store.day_summary(day["id"])
    a, b, c = st.columns(3)
    a.metric(T("summary_entries"), summary["entries"])
    b.metric(T("summary_attachments"), summary["attachments"])
    c.metric(T("summary_protocols"), summary["protocols"])

    _notebook_actions(store, day, lang)

    notes_tab, synthesis_tab = st.tabs(
        [T("notebook_notes_sources"), T("notebook_summary")]
    )
    with notes_tab:
        _notes_tab(store, day["id"])
    with synthesis_tab:
        _protocol_tab(store, day, lang)

    with st.expander(T("media_integrity")):
        if st.button(T("verify_media"), key="verify_media_button"):
            broken = store.verify_media()
            if broken:
                st.error(T("media_broken") + ": " + ", ".join(broken))
            else:
                st.success(T("media_ok"))
