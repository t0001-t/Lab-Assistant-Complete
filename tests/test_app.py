"""Oberflächen-Tests: Start und Dunkelmodus.

Ausführen:  .venv/bin/python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest

import canvas_renderer as cr
from demo_project import build_demo

DARK_MARKER = "#131313"


def _styles(at: AppTest) -> str:
    return "\n".join(str(element.value) for element in at.markdown)



class EditorPerformanceTest(unittest.TestCase):
    def test_editing_skips_exports_and_reuses_preview(self) -> None:
        app = AppTest.from_file(str(ROOT / "gel_app.py"), default_timeout=60)
        project = build_demo()[0]
        original = project.panels[0].source_image.tobytes()
        app.session_state["project"] = project
        with patch.object(cr, "png_bytes", wraps=cr.png_bytes) as png, patch.object(
            cr, "render_figure", wraps=cr.render_figure,
        ) as render:
            app.run()
            self.assertEqual(list(app.exception), [])
            png.assert_not_called()
            self.assertEqual(render.call_count, 1)
            app.run()
            self.assertEqual(list(app.exception), [])
            png.assert_not_called()
            self.assertEqual(render.call_count, 1)
        self.assertEqual(project.panels[0].source_image.tobytes(), original)


class DarkModeTest(unittest.TestCase):
    """Die Oberfläche startet hell und lässt sich auf Dunkelmodus umschalten."""

    def test_start_is_light_and_without_image(self) -> None:
        at = AppTest.from_file(str(ROOT / "gel_app.py"), default_timeout=60)
        at.run()
        self.assertEqual(list(at.exception), [])
        self.assertEqual(len(at.image), 0)
        self.assertNotIn(DARK_MARKER, _styles(at))
        self.assertEqual([toggle.label for toggle in at.toggle], ["Dunkelmodus"])
        self.assertEqual(
            [tab.label for tab in at.tabs][:4],
            ["1 · Import & Geometrie", "2 · Spuren & Labels", "Spuren & Labels", "Typografie"],
        )
        self.assertIn("Farbschema (Abbildung)", [field.label for field in at.sidebar.selectbox])
        self.assertNotIn("Schriftart", [field.label for field in at.sidebar.selectbox])
        self.assertIn("Schriftart", [field.label for field in at.selectbox])

    def test_toggle_adds_dark_styles(self) -> None:
        at = AppTest.from_file(str(ROOT / "gel_app.py"), default_timeout=60)
        at.run()
        at.toggle[0].set_value(True).run()
        self.assertEqual(list(at.exception), [])
        styles = _styles(at)
        self.assertIn(DARK_MARKER, styles)
        # Tabellen (glide-data-grid) werden über CSS-Variablen mitgefärbt.
        self.assertIn("--gdg-bg-cell", styles)

    def test_toggle_back_to_light(self) -> None:
        at = AppTest.from_file(str(ROOT / "gel_app.py"), default_timeout=60)
        at.run()
        at.toggle[0].set_value(True).run()
        at.toggle[0].set_value(False).run()
        self.assertNotIn(DARK_MARKER, _styles(at))


if __name__ == "__main__":
    unittest.main()
