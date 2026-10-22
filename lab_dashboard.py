"""Dashboard, projects overview, calendar and shared dialogs.

The dashboard is the entry point of the unified shell. It only reads the gel
project state for the demo button and never imports the gel renderer, so the
SDS-PAGE pipeline stays isolated in ``gel_app.py``.
"""

from __future__ import annotations

import html
import os
from datetime import date, timedelta
from pathlib import Path

import streamlit as st

from demo_project import build_demo, has_project_work
from lab_calendar import (
    EVENT_KINDS,
    IMPORTANCE_LEVELS,
    CalendarStore,
    month_matrix,
    shift_month,
)
from lab_eln import PRACTICUM_COLORS, ELNStore, normalize_color
from lab_locales import tr
from lab_theme import colored_cards_css

ROOT = Path(__file__).parent
WEEKDAYS = {
    "de": ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"],
    "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
}
MONTHS = {
    "de": ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
           "August", "September", "Oktober", "November", "Dezember"],
    "en": ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"],
}
MODULES = ("home", "projects", "gel", "calculators", "notebook", "calendar")


def language() -> str:
    return st.session_state.get("lab_lang", "de")


def T(key: str, **kwargs: object) -> str:
    text = tr(key, language())
    return text.format(**kwargs) if kwargs else text


def data_folder() -> Path:
    return Path(os.environ.get("LAB_ASSISTANT_DATA_DIR", ROOT / "lab_data"))


def eln_store() -> ELNStore:
    return ELNStore(data_folder())


def calendar_store() -> CalendarStore:
    return CalendarStore(data_folder())


def _navigate(module: str) -> None:
    st.session_state.lab_module = module if module in MODULES else "home"
    st.rerun()


def _dark() -> bool:
    return st.session_state.get("lab_theme") == "dark"


def _practicum_color(practicum: dict, index: int = 0) -> str:
    return normalize_color(
        practicum.get("color"), PRACTICUM_COLORS[index % len(PRACTICUM_COLORS)]
    )


def _open_practicum(practicum_id: str) -> None:
    st.session_state.eln_practicum_id = practicum_id
    st.session_state.pop("eln_day_id", None)
    _navigate("notebook")


def _chunks(items: list[dict], size: int) -> list[list[dict]]:
    return [items[index:index + size] for index in range(0, len(items), size)]


def _month_state() -> tuple[int, int]:
    raw = st.session_state.get("lab_cal_month", "")
    try:
        year, month = (int(part) for part in str(raw).split("-", 1))
        if 1 <= month <= 12 and 1900 <= year <= 2200:
            return year, month
    except (TypeError, ValueError):
        pass
    today = date.today()
    return today.year, today.month


def _set_month(year: int, month: int) -> None:
    year, month = shift_month(year, month, 0)
    st.session_state.lab_cal_month = f"{year:04d}-{month:02d}"


def _month_label(year: int, month: int, lang: str) -> str:
    return f"{MONTHS['de' if lang == 'de' else 'en'][month - 1]} {year}"


def _format_date(value: str | date, lang: str) -> str:
    """Show stored ISO dates in the language-specific display format."""
    if isinstance(value, str):
        try:
            value = date.fromisoformat(value)
        except ValueError:
            return value
    return value.strftime("%d.%m.%Y" if lang == "de" else "%m/%d/%Y")


def _date_input_format(lang: str) -> str:
    return "DD.MM.YYYY" if lang == "de" else "MM/DD/YYYY"


def _kind_label(kind: str) -> str:
    return {
        "practicum": T("kind_practicum"),
        "deadline": T("kind_deadline"),
        "incubation": T("kind_incubation"),
        "submission": T("kind_submission"),
        "todo": T("kind_todo"),
        "other": T("kind_other"),
    }.get(kind, kind)


def _kind_options() -> list[str]:
    return list(EVENT_KINDS)


def _importance_label(importance: str) -> str:
    return {
        "low": T("importance_low"),
        "normal": T("importance_normal"),
        "high": T("importance_high"),
    }.get(importance, importance)


def _importance_options() -> list[str]:
    return list(IMPORTANCE_LEVELS)


def _calendar_html(year: int, month: int, events: list[dict], lang: str, compact: bool) -> str:
    weeks = month_matrix(year, month, events)
    head = "".join(f"<th>{name}</th>" for name in WEEKDAYS["de" if lang == "de" else "en"])
    today = date.today()
    rows = []
    limit = 2 if compact else 3
    for week in weeks:
        cells = []
        for cell in week:
            classes = []
            if not cell["in_month"]:
                classes.append("la-out")
            if cell["date"] == today:
                classes.append("la-today")
            day_events = cell["events"]
            chips = []
            for event in day_events[:limit]:
                kind = event.get("kind", "other")
                importance = event.get("importance", "normal")
                marker = f" la-ev kind-{kind} importance-{importance}"
                clock = f"{event['time']} · " if event["time"] else ""
                tooltip = (
                    f"{_kind_label(kind)} · {_importance_label(importance)} · "
                    f"{event['title']}"
                )
                chips.append(
                    f'<span class="{marker.strip()}" title="{html.escape(tooltip)}">'
                    f'{html.escape(clock + event["title"])}</span>'
                )
            if len(day_events) > limit:
                chips.append(f'<span class="la-ev">+{len(day_events) - limit}</span>')
            classes_attr = f' class="{" ".join(classes)}"' if classes else ""
            cells.append(
                f'<td{classes_attr}><div class="la-day">{cell["date"].day}</div>'
                f'{"".join(chips)}</td>'
            )
        rows.append("<tr>" + "".join(cells) + "</tr>")
    classes = "la-cal la-cal-compact" if compact else "la-cal"
    return (
        f'<table class="{classes}"><thead><tr>{head}</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>'
    )


def _calendar_controls(store: CalendarStore, lang: str, compact: bool) -> None:
    year, month = _month_state()
    if not compact:
        month_column, year_column, today_column = st.columns([3, 2, 1], vertical_alignment="bottom")
        selected_month = month_column.selectbox(
            T("calendar_month"), list(range(1, 13)), index=month - 1,
            format_func=lambda value: MONTHS["de" if lang == "de" else "en"][value - 1],
            key=f"calendar_month_jump_{year}_{month}",
        )
        selected_year = year_column.number_input(
            T("calendar_year"), min_value=1900, max_value=2200, value=year, step=1,
            key=f"calendar_year_jump_{year}_{month}",
            help=T("calendar_year_hint"),
        )
        if today_column.button(T("today"), key="calendar_jump_today", width="stretch"):
            _set_month(date.today().year, date.today().month)
            st.rerun()
        if (selected_year, selected_month) != (year, month):
            _set_month(int(selected_year), selected_month)
            st.rerun()
    left, middle, right = st.columns([1, 5, 1], gap="small", vertical_alignment="center")
    if left.button("‹", key="cal_prev", help=T("prev_month"), width="stretch",
                   disabled=year == 1900 and month == 1):
        _set_month(*shift_month(year, month, -1))
        st.rerun()
    middle.markdown(
        f"**{_month_label(year, month, lang)}**"
        + (f" · <span class='la-muted'>{T('today')}: {_format_date(date.today(), lang)}</span>"
           if not compact else ""),
        unsafe_allow_html=True,
    )
    if right.button("›", key="cal_next", help=T("next_month"), width="stretch",
                    disabled=year == 2200 and month == 12):
        _set_month(*shift_month(year, month, 1))
        st.rerun()
    start = date(year, month, 1).isoformat()
    next_year, next_month = shift_month(year, month, 1)
    end = (date(next_year, next_month, 1) - timedelta(days=1)).isoformat()
    events = store.list_events(start, end)
    st.markdown(_calendar_html(year, month, events, lang, compact), unsafe_allow_html=True)
    if not events:
        st.caption(T("no_events"))
    if not compact:
        legend = "".join(
            f'<span class="la-importance importance-{level}">{html.escape(_importance_label(level))}</span>'
            for level in _importance_options()
        )
        st.markdown(f'<div class="la-importance-legend">{legend}</div>', unsafe_allow_html=True)
        st.caption(T("calendar_color_hint"))


def _upcoming_list(store: CalendarStore, limit: int, *, show_delete: bool,
                   lang: str) -> None:
    events = store.upcoming(limit)
    if not events:
        st.caption(T("upcoming_empty"))
        return
    for event in events:
        label = (
            f"{_format_date(event['date'], lang)} · {event['time'] or '—'} · "
            f"{event['title']}"
        )
        with st.container(border=True):
            st.markdown(f"**{label}**")
            details = (
                f"{_kind_label(event['kind'])} · "
                f"{_importance_label(event.get('importance', 'normal'))}"
            )
            if event["notes"]:
                details += f" · {event['notes']}"
            importance = event.get("importance", "normal")
            st.markdown(
                f'<span class="la-importance importance-{importance}">'
                f'{html.escape(_importance_label(importance))}</span>', unsafe_allow_html=True,
            )
            st.caption(details)
            if show_delete:
                confirm = st.checkbox(
                    T("confirm_delete_event"), key=f"del_event_confirm_{event['id']}"
                )
                if st.button(T("delete_event"), key=f"del_event_{event['id']}", disabled=not confirm):
                    store.delete_event(event["id"])
                    st.success(T("event_deleted"))
                    st.rerun()


# --------------------------------------------------------------------------- home
def _dashboard_counts() -> dict[str, int]:
    store = eln_store()
    practica = store.list_practica()
    days = entries = protocols = 0
    for practicum in practica:
        practicum_days = store.list_days(practicum["id"])
        days += len(practicum_days)
        for day in practicum_days:
            summary = store.day_summary(day["id"])
            entries += summary["entries"]
            protocols += summary["protocols"]
    return {
        "practica": len(practica), "days": days, "entries": entries, "protocols": protocols,
    }


def _hero() -> None:
    st.markdown(
        '<div class="la-hero">'
        f'<div class="la-kicker">{html.escape(T("dashboard_kicker"))}</div>'
        f"<h1>{html.escape(T('app'))}</h1>"
        f"<p>{html.escape(T('app_subtitle'))}</p>"
        "</div>",
        unsafe_allow_html=True,
    )


def _section(title: str, note: str = "") -> None:
    st.markdown(
        f'<div class="la-section"><h3>{html.escape(title)}</h3>'
        f"<span>{html.escape(note)}</span></div>",
        unsafe_allow_html=True,
    )


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


def _practicum_cards(store: ELNStore, practica: list[dict]) -> None:
    _section(T("dashboard_practica"), T("dashboard_practica_hint"))
    toolbar = st.columns([1, 1], gap="small")
    with toolbar[0], st.popover(
        T("new_practicum"), icon=":material/create_new_folder:", width="stretch"
    ):
        _new_practicum_form(store, "dashboard_new_practicum")
    if toolbar[1].button(
        T("manage_practica"), key="manage_practica", icon=":material/folder_open:",
        width="stretch",
    ):
        _navigate("projects")
    if not practica:
        st.info(T("folder_empty"))
        return

    colors = [
        (f"folder_open_{item['id']}", _practicum_color(item, index))
        for index, item in enumerate(practica)
    ]
    st.markdown(colored_cards_css(colors, _dark()), unsafe_allow_html=True)
    for row in _chunks(practica, 2):
        columns = st.columns(2)
        for column, practicum in zip(columns, row):
            index = practica.index(practicum)
            color = _practicum_color(practicum, index)
            days = store.list_days(practicum["id"])
            with column, st.container(key=f"practicum_card_{practicum['id']}"):
                if st.button(
                    practicum["name"], key=f"folder_open_{practicum['id']}",
                    icon=":material/folder_shared:", width="stretch",
                    help=T("dashboard_practica_hint"),
                ):
                    _open_practicum(practicum["id"])
                meta = practicum["field"] or T("field")
                st.markdown(
                    f'<div class="la-meta"><span class="la-dot" '
                    f'style="background:{color}"></span>{html.escape(meta)} · '
                    f'{T("folder_days", count=len(days))}</div>',
                    unsafe_allow_html=True,
                )
                with st.popover(
                    T("folder_color"), icon=":material/palette:", width="stretch"
                ):
                    st.caption(T("folder_color_hint"))
                    chosen = st.color_picker(
                        T("folder_color"), value=color,
                        key=f"folder_color_{practicum['id']}",
                    )
                    if normalize_color(chosen) != color:
                        store.set_practicum_color(practicum["id"], chosen)
                        st.rerun()


def _function_tiles() -> None:
    _section(T("quick_start"))
    tiles = (
        ("notebook", "eln_desc", ":material/menu_book:", "#60a5fa"),
        ("gel", "gel_desc", ":material/colorize:", "#60a5fa"),
        ("calculators", "calc_desc", ":material/calculate:", "#60a5fa"),
        ("calendar", "calendar_desc", ":material/calendar_month:", "#60a5fa"),
    )
    st.markdown(
        colored_cards_css(
            [(f"tile_{module}", color) for module, _desc, _icon, color in tiles],
            _dark(),
            height="5.2rem", folder_tab=False,
        ),
        unsafe_allow_html=True,
    )
    for row in (tiles[:2], tiles[2:]):
        columns = st.columns(2)
        for column, (module, description, icon, _color) in zip(columns, row):
            with column:
                if st.button(T(module), key=f"tile_{module}", icon=icon, width="stretch"):
                    _navigate(module)
                st.markdown(
                    f'<div class="la-note">{html.escape(T(description))}</div>',
                    unsafe_allow_html=True,
                )


def _rail_header() -> None:
    st.markdown(
        f'<div class="la-section"><h3>{html.escape(T("calendar"))}</h3>'
        f'<span>{html.escape(_format_date(date.today(), language()))}</span></div>',
        unsafe_allow_html=True,
    )


def _todo_panel(store: ELNStore) -> None:
    todos = store.list_todos()
    calendar = calendar_store()
    open_count = sum(1 for todo in todos if not todo["done"])
    with st.container(border=True):
        _section(T("todo_title"), T("todo_open_count", count=open_count))
        with st.form("dashboard_todo_add", clear_on_submit=True):
            text = st.text_input(
                T("todo_title"), label_visibility="collapsed",
                placeholder=T("todo_placeholder"),
            )
            if st.form_submit_button(
                T("todo_add"), icon=":material/add_task:", type="primary",
                width="stretch",
            ):
                try:
                    store.add_todo(text)
                    st.rerun()
                except ValueError:
                    st.error(T("invalid"))
        if not todos:
            st.caption(T("todo_empty"))
            return
        for todo in todos[:14]:
            check_column, delete_column = st.columns([7, 1], vertical_alignment="center")
            checked = check_column.checkbox(
                todo["text"], value=bool(todo["done"]),
                key=f"todo_done_{todo['id']}",
                help=T("todo_done") if todo["done"] else None,
            )
            if checked != bool(todo["done"]):
                store.set_todo_done(todo["id"], checked)
                _sync_todo_event(calendar, todo, done=checked)
                st.rerun()
            if todo["due_date"]:
                check_column.caption(
                    f"{T('todo_due_short')}: {_format_date(todo['due_date'], language())}"
                )
            if delete_column.button(
                "", icon=":material/delete:", key=f"todo_delete_{todo['id']}",
                help=T("todo_delete"),
            ):
                store.delete_todo(todo["id"])
                calendar.delete_todo_event(todo["id"])
                st.rerun()


def _onboarding() -> None:
    if st.session_state.get("lab_tour_done"):
        return
    step = max(0, min(4, int(st.session_state.get("lab_tour_step", 0))))
    opened = st.session_state.pop("lab_tour_open", False)
    with st.expander(
        f"{T('onboarding_title')} · {T('onboarding_step', step=step + 1)}",
        icon=":material/school:", expanded=bool(opened),
    ):
        st.write(T("onboarding_intro") if step == 0 else T(f"onboarding_{step + 1}_body"))
        st.info(T(f"onboarding_{step + 1}_task"))
        left, middle, right = st.columns([1, 1, 3])
        if left.button(T("onboarding_skip"), key="tour_skip"):
            st.session_state.lab_tour_done = True
            st.rerun()
        if middle.button(T("onboarding_back"), key="tour_back", disabled=step == 0):
            st.session_state.lab_tour_step = step - 1
            st.session_state.lab_tour_open = True
            st.rerun()
        label = T("onboarding_finish") if step == 4 else T("onboarding_next")
        if right.button(label, key="tour_next", type="primary"):
            if step == 4:
                st.session_state.lab_tour_done = True
            else:
                st.session_state.lab_tour_step = step + 1
                st.session_state.lab_tour_open = True
            st.rerun()


def _demo_box() -> None:
    with st.expander(T("demo_box"), icon=":material/science:"):
        st.write(T("demo_hint"))
        existing = st.session_state.get("project")
        needs_confirm = existing is not None and has_project_work(existing)
        confirmed = st.checkbox(T("demo_confirm"), key="lab_demo_confirm", value=not needs_confirm)
        if st.button(T("demo_load"), key="lab_demo_load", disabled=needs_confirm and not confirmed):
            project, tracking = build_demo(language())
            st.session_state.project = project
            st.session_state.demo_tracking = tracking
            st.session_state.active = 0
            st.session_state.selected_lane = 0
            st.session_state.selected_marker = 0
            st.session_state.selected_arrow = 0
            st.session_state.ui_version = st.session_state.get("ui_version", 0) + 1
            st.session_state.crop_version = st.session_state.get("crop_version", 0) + 1
            st.session_state.editor_nonces = {}
            for cache in ("proc_cache", "display_cache", "preview_cache", "export_cache"):
                st.session_state.get(cache, {}).clear()
            st.session_state.lab_module = "gel"
            st.rerun()


def overview_page() -> None:
    lang = language()
    store = eln_store()
    with st.container(key="dashboard_layout"):
        main, rail = st.columns([2.35, 1], gap="large")
        with main, st.container(key="dashboard_main"):
            _hero()
            _onboarding()
            practica = store.list_practica()
            _practicum_cards(store, practica)
            _function_tiles()
            _demo_box()
        with rail, st.container(key="dashboard_rail"):
            _rail_header()
            with st.container(border=True):
                _calendar_controls(calendar_store(), lang, compact=True)
                if st.button(
                    T("open_calendar"), key="dashboard_open_calendar",
                    icon=":material/open_in_new:", width="stretch",
                ):
                    _navigate("calendar")
                st.caption(T("calendar_widget_hint"))
            _todo_panel(store)
            with st.expander(T("upcoming"), icon=":material/event_upcoming:"):
                _upcoming_list(calendar_store(), 5, show_delete=False, lang=lang)

# ----------------------------------------------------------------------- projects
def projects_page() -> None:
    store = eln_store()
    st.title(T("projects"))
    st.caption(T("projects_hint"))
    counts = _dashboard_counts()
    stats = st.columns(4)
    stats[0].metric(T("projects_stats_practica"), counts["practica"])
    stats[1].metric(T("projects_stats_days"), counts["days"])
    stats[2].metric(T("projects_stats_entries"), counts["entries"])
    stats[3].metric(T("projects_stats_protocols"), counts["protocols"])

    with st.expander(T("new_practicum"), icon=":material/create_new_folder:"), st.form("dash_new_practicum"):
        name = st.text_input(T("practicum"))
        field = st.text_input(T("field"))
        color = st.color_picker(T("folder_color"), PRACTICUM_COLORS[0])
        if st.form_submit_button(T("create")):
            try:
                identifier = store.add_practicum(name, field, color)
                st.session_state.eln_practicum_id = identifier
                st.session_state.pop("eln_day_id", None)
                st.rerun()
            except ValueError:
                st.error(T("invalid"))

    practica = store.list_practica()
    if not practica:
        st.info(T("projects_empty"))
        return
    for index, practicum in enumerate(practica):
        days = store.list_days(practicum["id"])
        color = _practicum_color(practicum, index)
        with st.container(border=True):
            title_column, action_column = st.columns([4, 1.2], vertical_alignment="center")
            with title_column:
                st.markdown(
                    f'<h3 style="margin:0"><span class="la-dot" '
                    f'style="background:{color}"></span>{html.escape(practicum["name"])}</h3>',
                    unsafe_allow_html=True,
                )
                st.caption(practicum["field"] or T("field"))
            with action_column:
                if st.button(T("open_module"), key=f"open_practicum_{practicum['id']}",
                             width="stretch"):
                    st.session_state.eln_practicum_id = practicum["id"]
                    st.session_state.pop("eln_day_id", None)
                    _navigate("notebook")
            if not days:
                st.caption(T("projects_no_days"))
                continue
            for day in days:
                summary = store.day_summary(day["id"])
                columns = st.columns([2.2, 3, 1.1, 1.1, 1.1, 1.3], vertical_alignment="center")
                columns[0].markdown(f"**{day['date']}**")
                columns[1].write(day["title"])
                columns[2].caption(f"{summary['entries']} {T('summary_entries')}")
                columns[3].caption(f"{summary['attachments']} {T('summary_attachments')}")
                columns[4].caption(f"{summary['protocols']} {T('summary_protocols')}")
                if columns[5].button(T("projects_open_day"), key=f"open_day_{day['id']}",
                                     width="stretch"):
                    st.session_state.eln_practicum_id = practicum["id"]
                    st.session_state.eln_day_id = day["id"]
                    _navigate("notebook")


# ----------------------------------------------------------------------- calendar
def _new_event_form(store: CalendarStore, lang: str) -> None:
    with st.form("calendar_new_event", clear_on_submit=True):
        title = st.text_input(T("event_title"))
        columns = st.columns(2)
        day = columns[0].date_input(
            T("date"), value=date.today(), format=_date_input_format(lang)
        )
        clock = columns[1].text_input(T("time"), placeholder="09:30")
        columns = st.columns(2)
        kind = columns[0].selectbox(
            T("event_kind"), _kind_options(),
            format_func=lambda value: _kind_label(value),
        )
        importance = columns[1].selectbox(
            T("event_importance"), _importance_options(),
            index=_importance_options().index("normal"),
            format_func=lambda value: _importance_label(value),
        )
        notes = st.text_area(T("event_notes"), height=80)
        if st.form_submit_button(T("add_event"), type="primary"):
            try:
                store.add_event(
                    title, day.isoformat(), clock.strip(), kind, notes,
                    importance=importance,
                )
                st.success(T("event_saved"))
                st.rerun()
            except ValueError:
                st.error(T("invalid"))


def _sync_todo_event(calendar: CalendarStore, todo: dict, *, done: bool | None = None) -> None:
    completed = bool(todo["done"]) if done is None else done
    if todo.get("due_date") and not completed:
        calendar.upsert_todo_event(todo["id"], todo["text"], todo["due_date"])
    else:
        calendar.delete_todo_event(todo["id"])


def _calendar_todo_panel(todos_store: ELNStore, calendar: CalendarStore,
                         lang: str) -> None:
    todos = todos_store.list_todos()
    open_count = sum(1 for todo in todos if not todo["done"])
    with st.container(border=True):
        _section(T("calendar_todos"), T("todo_open_count", count=open_count))
        st.caption(T("calendar_todo_hint"))
        with st.form("calendar_todo_add", clear_on_submit=True):
            text = st.text_input(
                T("todo_title"), label_visibility="collapsed",
                placeholder=T("todo_placeholder"),
            )
            due = st.date_input(
                T("todo_due_date"), value=None, format=_date_input_format(lang)
            )
            if st.form_submit_button(
                T("todo_add"), icon=":material/add_task:", type="primary",
                width="stretch",
            ):
                try:
                    due_value = due.isoformat() if due else ""
                    todo_id = todos_store.add_todo(text, due_value)
                    if due_value:
                        calendar.upsert_todo_event(todo_id, text.strip(), due_value)
                    st.rerun()
                except ValueError:
                    st.error(T("invalid"))
        if not todos:
            st.caption(T("todo_empty"))
            return
        for todo in todos[:12]:
            check_column, delete_column = st.columns([7, 1], vertical_alignment="center")
            checked = check_column.checkbox(
                todo["text"], value=bool(todo["done"]),
                key=f"cal_todo_done_{todo['id']}",
                help=T("todo_done") if todo["done"] else None,
            )
            if checked != bool(todo["done"]):
                todos_store.set_todo_done(todo["id"], checked)
                _sync_todo_event(calendar, todo, done=checked)
                st.rerun()
            if todo["due_date"]:
                check_column.caption(
                    f"{T('todo_due_short')}: {_format_date(todo['due_date'], lang)}"
                )
            if delete_column.button(
                "", icon=":material/delete:", key=f"cal_todo_delete_{todo['id']}",
                help=T("todo_delete"),
            ):
                todos_store.delete_todo(todo["id"])
                calendar.delete_todo_event(todo["id"])
                st.rerun()


def _import_block(store: CalendarStore) -> None:
    with st.expander(T("calendar_sync"), icon=":material/sync:"):
        st.caption(T("calendar_sync_hint"))
        uploaded = st.file_uploader(T("ics_upload"), type=["ics", "ical", "txt"], key="ics_upload")
        if uploaded is not None and st.button(T("ics_import"), key="ics_import_button"):
            try:
                added, updated = store.import_ics(uploaded.getvalue().decode("utf-8", errors="replace"))
                if not added and not updated:
                    st.warning(T("ics_empty"))
                else:
                    st.success(T("ics_imported", added=added, updated=updated))
                    st.rerun()
            except ValueError:
                st.error(T("ics_invalid"))
        st.download_button(
            T("ics_export"), store.export_ics().encode("utf-8"),
            file_name="lab_calendar.ics", mime="text/calendar", key="ics_export_button",
        )
        st.divider()
        st.markdown(f"#### {T('calendar_accounts')}")
        st.caption(T("calendar_accounts_hint"))
        accounts = store.list_accounts()
        for account in accounts:
            with st.container(border=True):
                st.markdown(f"**{account['label']}** · {T('provider_' + account['provider'])}")
                st.caption(account["url"])
                status = account["last_sync"] or T("never_synced")
                st.caption(f"{T('last_sync')}: {status}"
                           + (f" · {account['status']}" if account["status"] else ""))
                sync_column, delete_column = st.columns(2)
                if sync_column.button(T("sync_now"), key=f"sync_{account['id']}",
                                      width="stretch"):
                    try:
                        added, updated = store.sync_account(account["id"])
                        st.success(T("sync_ok", added=added, updated=updated))
                        st.rerun()
                    except (KeyError, ValueError):
                        st.error(T("sync_failed"))
                confirm = delete_column.checkbox(T("account_delete_confirm"),
                                                 key=f"del_account_confirm_{account['id']}")
                if delete_column.button(T("delete"), key=f"del_account_{account['id']}",
                                        disabled=not confirm, width="stretch"):
                    store.delete_account(account["id"])
                    st.success(T("account_deleted"))
                    st.rerun()
        with st.form("calendar_new_account", clear_on_submit=True):
            options = ["google", "apple", "outlook", "caldav", "ical"]
            provider = st.selectbox(
                T("calendar_provider"), options,
                format_func=lambda value: T("provider_" + value),
            )
            label = st.text_input(T("calendar_label"))
            url = st.text_input(T("calendar_url"), placeholder="https://…/basic.ics")
            st.caption(T("calendar_url_hint"))
            if st.form_submit_button(T("add_account")):
                try:
                    store.add_account(provider, label, url)
                    st.success(T("account_added"))
                    st.rerun()
                except ValueError:
                    st.error(T("invalid"))


def calendar_page() -> None:
    lang = language()
    store = calendar_store()
    st.title(T("calendar"))
    st.caption(T("calendar_sync_hint"))
    _calendar_controls(store, lang, compact=False)
    form_column, todo_column = st.columns([1.15, 1], gap="large")
    with form_column:
        st.markdown(f"#### {T('new_event')}")
        _new_event_form(store, lang)
    with todo_column:
        _calendar_todo_panel(eln_store(), store, lang)
    st.divider()
    left, right = st.columns([1.2, 1], gap="large")
    with left:
        st.markdown(f"#### {T('upcoming')}")
        _upcoming_list(store, 12, show_delete=True, lang=lang)
    with right:
        _import_block(store)


# ------------------------------------------------------------- settings and help
def settings_controls() -> None:
    st.markdown(f"#### {T('settings_appearance')}")
    current = language()
    choice = st.selectbox(
        T("settings_language"), ["de", "en"],
        index=0 if current == "de" else 1,
        format_func=lambda value: "Deutsch" if value == "de" else "English",
        key="settings_lang",
    )
    if choice != current:
        st.session_state.lab_lang = choice
        st.rerun()
    dark = st.session_state.get("lab_theme") == "dark"
    is_dark = st.toggle(T("settings_theme"), value=dark, key="settings_theme")
    if is_dark != dark:
        st.session_state.lab_theme = "dark" if is_dark else "light"
        st.session_state.ui_theme = st.session_state.lab_theme
        st.rerun()

    st.divider()
    st.markdown(f"#### {T('settings_data')}")
    st.caption(T("settings_data_hint"))
    st.code(str(data_folder()), language=None)

    st.markdown(f"#### {T('calendar_accounts')}")
    accounts = calendar_store().list_accounts()
    if accounts:
        for account in accounts:
            st.caption(f"{account['label']} · {T('provider_' + account['provider'])} · "
                       f"{account['last_sync'] or T('never_synced')}")
    else:
        st.caption(T("never_synced"))
    if st.button(T("settings_open_calendar"), key="settings_open_calendar", width="stretch"):
        st.session_state.lab_module = "calendar"
        st.rerun()

    st.divider()
    if st.button(T("settings_tour"), key="settings_tour", width="stretch"):
        st.session_state.lab_tour_done = False
        st.session_state.lab_tour_step = 0
        st.session_state.lab_tour_open = True
        st.session_state.lab_module = "home"
        st.rerun()


def help_controls() -> None:
    sections = (
        ("help_nav_title", "help_nav_text"),
        ("help_gel_title", "help_gel_text"),
        ("help_notes_title", "help_notes_text"),
        ("help_calc_title", "help_calc_text"),
        ("help_calendar_title", "help_calendar_text"),
        ("help_privacy_title", "help_privacy_text"),
    )
    for title, body_key in sections:
        st.markdown(f"#### {T(title)}")
        st.write(T(body_key))
    st.divider()
    if st.button(T("onboarding_restart"), key="help_tour", type="primary", width="stretch"):
        st.session_state.lab_tour_done = False
        st.session_state.lab_tour_step = 0
        st.session_state.lab_tour_open = True
        st.session_state.lab_module = "home"
        st.rerun()
