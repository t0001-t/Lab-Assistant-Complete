"""Headless UI smoke tests for the unified Lab Assistant shell."""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from lab_calendar import CalendarStore
from lab_eln import ELNStore
from lab_private_storage import visitor_folder
from lab_theme import shell_css

ROOT = Path(__file__).resolve().parents[1]


def _shell() -> AppTest:
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    app.session_state["_lab_browser_credential"] = "a" * 64
    app.run()
    return app


class ShellTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        env = patch.dict(os.environ, {"LAB_ASSISTANT_DATA_DIR": directory.name,
                                      "LAB_ASSISTANT_STORAGE_MODE": "private"})
        env.start()
        self.addCleanup(env.stop)

    def test_calendar_direct_year_and_month_navigation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"LAB_ASSISTANT_DATA_DIR": temporary}):
            app = _shell()
            app.button(key="nav_calendar").click().run()
            year, month = date.today().year, date.today().month
            app.number_input(key=f"calendar_year_jump_{year}_{month}").set_value(2035).run()
            self.assertEqual(app.session_state["lab_cal_month"], f"2035-{month:02d}")
            app.selectbox(key=f"calendar_month_jump_2035_{month}").set_value(2).run()
            self.assertEqual(app.session_state["lab_cal_month"], "2035-02")
            app.button(key="cal_next").click().run()
            self.assertEqual(app.session_state["lab_cal_month"], "2035-03")
            app.button(key="calendar_jump_today").click().run()
            self.assertEqual(app.session_state["lab_cal_month"], f"{year}-{month:02d}")
            self.assertEqual(list(app.exception), [])

    def test_calendar_colour_rules_for_both_themes(self) -> None:
        for dark in (False, True):
            css = shell_css(dark)
            self.assertIn(".la-cal .la-ev.kind-deadline", css)
            self.assertIn(".la-cal .la-ev.kind-todo.importance-high", css)
            self.assertIn(".la-cal .la-ev.kind-practicum.importance-low", css)

    def test_home_language_and_calculator_switch(self) -> None:
        app = _shell()
        self.assertEqual(list(app.exception), [])
        self.assertTrue(any("Lab Assistant" in block.value for block in app.markdown))
        self.assertEqual(app.button(key="nav_calculators").label, "Laborrechner")
        app.selectbox(key="settings_lang").set_value("en").run()
        self.assertEqual(list(app.exception), [])
        self.assertEqual(app.button(key="nav_calculators").label, "Lab calculators")
        app.button(key="nav_calculators").click().run()
        self.assertEqual(list(app.exception), [])
        self.assertEqual([title.value for title in app.title], ["Lab calculators"])
        self.assertEqual([tab.label for tab in app.tabs],
                         ["Neubauer counting chamber", "Molarity and weighing",
                          "Stock dilution", "PCR and enzyme master mix",
                          "Units", "qPCR analysis"])

    def test_gel_uses_global_sidebar_and_editor_options(self) -> None:
        app = _shell()
        home_nav = [button.label for button in app.sidebar.button][:5]
        self.assertEqual(
            home_nav,
            ["Übersicht", "Notizen", "Gel-Editor", "Laborrechner", "Kalender"],
        )
        app.button(key="nav_gel").click().run()
        self.assertEqual(list(app.exception), [])
        self.assertEqual([button.label for button in app.sidebar.button][:5], home_nav)
        sidebar_text = " ".join(block.value for block in app.sidebar.markdown)
        self.assertNotIn("GelDoc Studio", sidebar_text)
        self.assertNotIn(
            "Farbschema (Abbildung)",
            [field.label for field in app.sidebar.selectbox],
        )
        self.assertIn("GelDoc Studio", " ".join(block.value for block in app.markdown))
        self.assertIn("Projekt speichern", [button.label for button in app.button])
        self.assertEqual([toggle.key for toggle in app.toggle], ["settings_theme"])
        self.assertNotIn(
            "Farbschema (Abbildung)",
            [field.label for field in app.selectbox],
        )
        self.assertIn("Schriftart", [field.label for field in app.selectbox])
        self.assertNotIn("Schriftart", [field.label for field in app.sidebar.selectbox])
        self.assertEqual(app.session_state.project.theme, "light")
        app.toggle(key="settings_theme").set_value(True).run()
        self.assertEqual(list(app.exception), [])
        self.assertEqual(app.session_state.project.theme, "dark")
        self.assertEqual(app.session_state.project.export.theme, "dark")

    def test_settings_theme_and_language(self) -> None:
        app = _shell()
        app.toggle(key="settings_theme").set_value(True).run()
        self.assertEqual(list(app.exception), [])
        self.assertEqual(app.session_state.lab_theme, "dark")
        app.selectbox(key="settings_lang").set_value("en").run()
        self.assertEqual(list(app.exception), [])
        self.assertEqual(app.session_state.lab_lang, "en")
        self.assertEqual(app.toggle(key="settings_theme").label, "Dark mode")

    def test_dashboard_tiles_and_calendar(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = CalendarStore(visitor_folder(Path(temp), "a" * 64))
            store.add_event("Zellpassage", "2026-10-22", "09:30", "incubation")
            with patch.dict(os.environ, {"LAB_ASSISTANT_DATA_DIR": temp}):
                app = _shell()
                self.assertEqual(list(app.exception), [])
                self.assertEqual(app.button(key="tile_notebook").label, "Notizen")
                self.assertEqual(app.button(key="tile_gel").label, "Gel-Editor")
                self.assertIn("Zellpassage", " ".join(block.value for block in app.markdown))
                app.button(key="manage_practica").click().run()
                self.assertEqual(list(app.exception), [])
                self.assertEqual([title.value for title in app.title], ["Praktika & Projekte"])
                app.button(key="nav_calendar").click().run()
                self.assertEqual(list(app.exception), [])
                self.assertEqual([title.value for title in app.title], ["Kalender"])

    def test_dashboard_folder_opens_notebook_day(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = ELNStore(visitor_folder(Path(temp), "a" * 64))
            practicum = store.add_practicum("Biochemie", "Protein")
            day = store.add_day(practicum, "2026-10-21", "SDS-PAGE", "Dr. A", "B")
            with patch.dict(os.environ, {"LAB_ASSISTANT_DATA_DIR": temp}):
                app = _shell()
                self.assertEqual(list(app.exception), [])
                app.button(key=f"folder_open_{practicum}").click().run()
                self.assertEqual(list(app.exception), [])
                self.assertEqual([title.value for title in app.title], ["Notizen"])
                self.assertIn("SDS-PAGE", [item.value for item in app.subheader])
                self.assertEqual(app.button(key=f"day_open_{day}").label,
                                 "V1 · SDS-PAGE")
                self.assertEqual(
                    app.button(key=f"notebook_gel_bridge_{day}").label,
                    "Gel automatisch mit Notizen annotieren",
                )

    def test_calendar_creates_appointment(self) -> None:
        with tempfile.TemporaryDirectory() as temp, patch.dict(
            os.environ, {"LAB_ASSISTANT_DATA_DIR": temp}
        ):
            app = _shell()
            app.button(key="nav_calendar").click().run()
            self.assertEqual(list(app.exception), [])
            app.text_input[0].set_value("Zellpassage")
            app.text_input[1].set_value("09:30")
            next(widget for widget in app.selectbox if widget.label == "Kategorie").set_value("deadline")
            next(widget for widget in app.selectbox if widget.label == "Wichtigkeit").set_value("high")
            next(button for button in app.button
                 if button.label == "Termin speichern").click().run()
            self.assertEqual(list(app.exception), [])
            events = CalendarStore(visitor_folder(Path(temp), "a" * 64)).list_events()
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["title"], "Zellpassage")
            self.assertEqual(events[0]["time"], "09:30")
            self.assertEqual(events[0]["kind"], "deadline")
            self.assertEqual(events[0]["importance"], "high")
            markup = " ".join(block.value for block in app.markdown)
            self.assertIn("kind-deadline importance-high", markup)
            self.assertIn(date.today().strftime("%d.%m.%Y"), markup)

    def test_calendar_todo_with_due_date_creates_and_removes_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp, patch.dict(
            os.environ, {"LAB_ASSISTANT_DATA_DIR": temp}
        ):
            app = _shell()
            app.button(key="nav_calendar").click().run()
            self.assertEqual(list(app.exception), [])
            todo_text = next(field for field in app.text_input
                             if field.label == "Laboraufgaben")
            todo_text.set_value("Abgabe prüfen")
            due = next(field for field in app.date_input
                       if field.label == "Fällig am (optional)")
            due.set_value(date(2026, 10, 24))
            next(button for button in app.button
                 if button.label == "Aufgabe hinzufügen").click().run()
            self.assertEqual(list(app.exception), [])
            events = CalendarStore(visitor_folder(Path(temp), "a" * 64)).list_events()
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["kind"], "todo")
            self.assertEqual(events[0]["date"], "2026-10-24")
            next(box for box in app.checkbox if box.label == "Abgabe prüfen").set_value(True).run()
            self.assertEqual(list(app.exception), [])
            self.assertEqual(CalendarStore(visitor_folder(Path(temp), "a" * 64)).list_events(), [])

    def test_neubauer_form_reports_metrics(self) -> None:
        app = _shell()
        app.button(key="nav_calculators").click().run()
        for field in app.number_input:
            if field.label.startswith("Lebende Zellen"):
                field.set_value(100)
        app.button[0].click().run()
        self.assertEqual(list(app.exception), [])
        metrics = {metric.label: metric.value for metric in app.metric}
        self.assertIn("1.0000e+06", metrics["Lebende Zellen/mL"])
        self.assertIn("1.0000e+06", metrics["Lebende Zellen gesamt"])
        self.assertEqual(metrics["Tote Zellen gesamt"], "0")


class NotebookUITests(unittest.TestCase):
    def test_seeded_day_can_generate_and_save_protocol(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = ELNStore(visitor_folder(Path(temp), "a" * 64))
            practicum = store.add_practicum("Biochemie", "Protein")
            day = store.add_day(practicum, "2026-10-21", "SDS-PAGE", "Dr. A", "B")
            store.add_entry(day, "Messreihe", "text", "Probe A: 42 µL; 37 °C")
            with patch.dict(os.environ, {"LAB_ASSISTANT_DATA_DIR": temp}):
                app = _shell()
                app.button(key="nav_notebook").click().run()
                self.assertEqual(list(app.exception), [])
                self.assertIn("SDS-PAGE", [item.value for item in app.subheader])
                button = next(button for button in app.button
                              if button.label == "Protokoll erstellen")
                button.click().run()
                self.assertEqual(list(app.exception), [])
                self.assertEqual(len(store.list_protocols(day)), 1)
                stats = {metric.label: metric.value for metric in app.metric}
                self.assertEqual(stats["Abschnitte"], "6")
                self.assertEqual(stats["Quellen"], "1/1")
                labels = [area.label for area in app.text_area]
                self.assertIn("Protokoll prüfen und bearbeiten", labels)
                downloads = [button.label for button in app.get("download_button")]
                self.assertIn("PDF herunterladen", downloads)
                self.assertIn("Word-Datei herunterladen", downloads)


if __name__ == "__main__":
    unittest.main()
