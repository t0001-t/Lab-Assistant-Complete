import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw, ImageFont

import canvas_renderer as cr
from models import ConditionRow, default_project


class TypographyRegressionTest(unittest.TestCase):
    def test_incomplete_markup_is_literal(self):
        self.assertEqual(cr.parse_rich('Fe^{2+'), [('Fe^{2+', 0)])

    def test_accented_multiline_scripts_are_not_clipped(self):
        for size in (12, 24, 48):
            for angle in (0, 90, 270):
                image = cr._label_image('É^{Åg}\nH_{2}O', size, 'Arial', (0,0,0), angle)
                box = image.getbbox()
                self.assertIsNotNone(box)
                self.assertGreater(box[0], 0)
                self.assertGreater(box[1], 0)
                self.assertLess(box[2], image.width)
                self.assertLess(box[3], image.height)

    def test_plain_text_uses_font_advance(self):
        font, _ = cr._script_fonts(30, 'Arial')
        self.assertAlmostEqual(cr.rich_text_width('AV fi',30,'Arial'), font.getlength('AV fi'), delta=1)


class ConditionSymbolTest(unittest.TestCase):
    def test_unicode_minus_matches_ascii_without_system_fonts(self):
        panel = default_project(2).panels[0]
        panel.conditions = [ConditionRow(name="Test", values=["−", "+"])]
        gel = Image.new("RGB", (240, 120), "white")
        for theme in ("light", "dark"):
            for quality in (1, 2):
                options = cr.RenderOptions(theme=theme, supersample=quality)
                panel.conditions[0].values[0] = "−"
                with patch.object(cr, "load_font", side_effect=lambda size, *a, **kw: ImageFont.load_default(size=size)):
                    unicode_image = cr.render_figure(panel, gel, options)
                    self.assertEqual(panel.conditions[0].values[0], "−")
                    panel.conditions[0].values[0] = "-"
                    ascii_image = cr.render_figure(panel, gel, options)
                self.assertEqual(unicode_image.tobytes(), ascii_image.tobytes())

    def test_standalone_signs_are_lines_but_text_is_preserved(self):
        for symbol in ("-", "−", "–", "—", "﹣", "－", "+", "＋"):
            image = Image.new("RGB", (40, 40), "white")
            draw = ImageDraw.Draw(image)
            self.assertTrue(cr._draw_condition_symbol(draw, symbol, (20, 20), 24, (0, 0, 0)))
            self.assertEqual(image.getpixel((20, 20)), (0, 0, 0))
            self.assertEqual(image.getpixel((20, 15)), (0, 0, 0) if symbol in {"+", "＋"} else (255, 255, 255))
        image = Image.new("RGB", (40, 40), "white")
        before = image.tobytes()
        self.assertFalse(cr._draw_condition_symbol(ImageDraw.Draw(image), "−1 mM", (20, 20), 24, (0, 0, 0)))
        self.assertEqual(image.tobytes(), before)
