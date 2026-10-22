"""Oberflächen-Tests: Start und Dunkelmodus.

Ausführen:  .venv/bin/python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest

DARK_MARKER = "#131313"


def _styles(at: AppTest) -> str:
    return "\n".join(str(element.value) for element in at.markdown)


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
