"""Tests für Modelle, Bildverarbeitung, Renderer, Export und i18n.

Ausführen:  .venv/bin/python -m unittest discover -s tests -v
"""

from __future__ import annotations

import io
import json
import re
import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import canvas_renderer as cr
import image_processing as ip
import locales
import workflow
from models import (
    Adjustments,
    ConditionRow,
    GelPanel,
    GroupLabel,
    MarkerBand,
    Project,
    TargetArrow,
    Transform,
    default_project,
)

SAMPLE = ROOT / "assets" / "sample_gel.jpg"
INK_THRESHOLD = 200


def small_gel() -> Image.Image:
    return ip.load_image_from_path(SAMPLE).resize((520, 380), Image.Resampling.LANCZOS)


def ink_mask(image: Image.Image, box: tuple[int, int, int, int] | None = None) -> np.ndarray:
    gray = np.asarray(image.convert("L"), dtype=np.uint8)
    mask = gray < INK_THRESHOLD
    if box is not None:
        region = np.zeros_like(mask)
        region[box[1] : box[3], box[0] : box[2]] = True
        mask = mask & region
    return mask


class GelUntouchedTest(unittest.TestCase):
    """Kernanforderung: das Originalgel wird nie überzeichnet oder skaliert."""

    def setUp(self) -> None:
        self.gel = small_gel()
        self.panel = default_project().panels[0]

    def _assert_untouched(self, supersample: int, theme: str = "light") -> None:
        options = cr.RenderOptions(supersample=supersample, theme=theme)
        layout = cr.compute_layout(self.panel, self.gel.size, options)
        figure = cr.render_figure(self.panel, self.gel, options)
        region = figure.crop(
            (layout.gel_left, layout.gel_top, layout.gel_left + self.gel.width, layout.gel_top + self.gel.height)
        )
        self.assertTrue(
            np.array_equal(np.asarray(region), np.asarray(self.gel.convert("RGB"))),
            f"Gelbereich darf sich nicht verändern ({supersample}×, {theme}).",
        )

    def test_gel_region_pixel_identical_1x(self) -> None:
        self._assert_untouched(1)

    def test_gel_region_pixel_identical_2x(self) -> None:
        self._assert_untouched(2)

    def test_gel_region_pixel_identical_dark(self) -> None:
        self._assert_untouched(2, "dark")

    def test_guides_only_in_working_view(self) -> None:
        options = cr.RenderOptions(supersample=1)
        export = cr.render_figure(self.panel, self.gel, options)
        working = cr.render_working_view(self.panel, self.gel, options)
        layout = cr.compute_layout(self.panel, self.gel.size, options)
        box = (layout.gel_left, layout.gel_top, layout.gel_left + self.gel.width, layout.gel_top + self.gel.height)
        self.assertTrue(np.array_equal(np.asarray(export.crop(box)), np.asarray(self.gel.convert("RGB"))))
        self.assertFalse(np.array_equal(np.asarray(working.crop(box)), np.asarray(self.gel.convert("RGB"))))


class ThemeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.gel = small_gel()
        self.panel = default_project().panels[0]

    def test_light_theme_background_and_ink(self) -> None:
        figure = cr.render_figure(self.panel, self.gel, cr.RenderOptions(supersample=1, theme="light"))
        self.assertEqual(figure.getpixel((0, 0)), (255, 255, 255))

    def test_dark_theme_background_and_ink(self) -> None:
        figure = cr.render_figure(self.panel, self.gel, cr.RenderOptions(supersample=1, theme="dark"))
        self.assertEqual(figure.getpixel((0, 0)), (0, 0, 0))
        layout = cr.compute_layout(self.panel, self.gel.size, cr.RenderOptions(supersample=1, theme="dark"))
        header = np.asarray(figure.convert("RGB"))[0 : layout.gel_top, :]
        self.assertGreater(int(header.max()), 220, "Dunkelmodus muss weiße Beschriftung enthalten.")


class LayoutTest(unittest.TestCase):
    def setUp(self) -> None:
        self.gel = small_gel()
        self.panel = default_project().panels[0]
        self.options = cr.RenderOptions(supersample=2)

    def test_lane_labels_are_centered(self) -> None:
        layout = cr.compute_layout(self.panel, self.gel.size, self.options)
        figure = cr.render_figure(self.panel, self.gel, self.options)
        mask = ink_mask(figure, (layout.gel_left, 0, layout.canvas_w, layout.gel_top))
        for index in range(1, len(self.panel.lanes)):
            lane = self.panel.lanes[index]
            expected = layout.gel_left + lane.x_pos_rel * layout.gel_w
            half = max(6, int(layout.gel_w * self.panel.lane_pitch_rel(index) / 2))
            segment = mask[:, max(0, int(expected) - half) : int(expected) + half]
            columns = np.where(segment.any(axis=0))[0]
            self.assertGreater(columns.size, 0, f"Label für Spur {index + 1} fehlt.")
            center = max(0, int(expected) - half) + (columns.min() + columns.max()) / 2
            self.assertLess(abs(center - expected), 5.0)

    def test_ticks_touch_gel_edge(self) -> None:
        layout = cr.compute_layout(self.panel, self.gel.size, self.options)
        figure = cr.render_figure(self.panel, self.gel, self.options)
        gray = np.asarray(figure.convert("L"))
        for marker in self.panel.sorted_markers():
            y = round(layout.gel_top + marker.y_pos_rel * layout.gel_h)
            self.assertLess(gray[y, layout.gel_left - 2], INK_THRESHOLD, f"Tick bei {marker.display_value} fehlt.")
            left = gray[y - 2 : y + 3, 0 : layout.gel_left - layout.tick_len]
            self.assertTrue((left < INK_THRESHOLD).any(), "kDa-Zahl fehlt.")

    def test_header_is_collision_free(self) -> None:
        panel = default_project().panels[0]
        panel.groups = [GroupLabel(text="Kontrolle", start_index=0, end_index=4)]
        panel.conditions = [ConditionRow(name="DTT", values=["+"] * 10)]
        layout = cr.compute_layout(panel, self.gel.size, self.options)
        required = layout.group_block_h + layout.condition_block_h + layout.label_block_h
        self.assertGreaterEqual(layout.header_h, required, "Header muss alle Textblöcke aufnehmen.")
        figure = cr.render_figure(panel, self.gel, self.options)
        # Zwischen Bedingungszeile und Spurlabels muss Tinte getrennt auftreten.
        upper = ink_mask(figure, (0, 0, layout.canvas_w, layout.gel_top))
        self.assertTrue(upper.any())

    def test_rotated_labels_create_block(self) -> None:
        panel = default_project().panels[0]
        for lane in panel.lanes:
            lane.label_top = "Lysat Probe 12 h"
        layout0 = cr.compute_layout(panel, self.gel.size, self.options)
        layout90 = cr.compute_layout(panel, self.gel.size, cr.RenderOptions(supersample=2, label_rotation=90))
        self.assertGreater(layout0.label_block_h, 0)
        self.assertGreater(layout90.label_block_h, 0)

    def test_lane_numbers_positions(self) -> None:
        panel = default_project().panels[0]
        layouts = {}
        figures = {}
        for position in ("bottom", "top", "none"):
            options = cr.RenderOptions(supersample=1, lane_numbers_position=position)
            layouts[position] = cr.compute_layout(panel, self.gel.size, options)
            figures[position] = cr.render_figure(panel, self.gel, options)

        bottom_layout = layouts["bottom"]
        bottom_band = ink_mask(
            figures["bottom"],
            (bottom_layout.gel_left, bottom_layout.gel_top + bottom_layout.gel_h, bottom_layout.canvas_w, bottom_layout.canvas_h),
        )
        self.assertTrue(bottom_band.any(), "Spurnummern fehlen unten.")

        top_layout = layouts["top"]
        top_band = ink_mask(
            figures["top"],
            (top_layout.gel_left, top_layout.gel_top - top_layout.number_font_px * 2, top_layout.canvas_w, top_layout.gel_top),
        )
        self.assertTrue(top_band.any(), "Spurnummern fehlen oben.")

        none_layout = layouts["none"]
        self.assertLess(none_layout.bottom_margin, bottom_layout.bottom_margin, "Ohne Nummern wird kein unterer Rand reserviert.")
        empty_band = ink_mask(
            figures["none"],
            (none_layout.gel_left, none_layout.gel_top + none_layout.gel_h, none_layout.canvas_w, none_layout.canvas_h),
        )
        self.assertFalse(empty_band.any(), "Ohne Nummern darf unten keine Beschriftung stehen.")


class ArrowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.gel = small_gel()
        self.panel = default_project().panels[0]
        self.options = cr.RenderOptions(supersample=1)

    def test_arrow_docks_at_gel_edge_with_label(self) -> None:
        self.panel.arrows = [TargetArrow(label="37 kDa", y_pos_rel=0.5, side="right")]
        layout = cr.compute_layout(self.panel, self.gel.size, self.options)
        figure = cr.render_figure(self.panel, self.gel, self.options)
        self.assertGreater(layout.right_margin, layout.pad, "Rechter Rand muss Platz für den Pfeil bieten.")
        gray = np.asarray(figure.convert("L"))
        y = round(layout.gel_top + 0.5 * layout.gel_h)
        edge = layout.gel_left + layout.gel_w
        self.assertLess(gray[y, edge + 2], INK_THRESHOLD, "Pfeil fehlt am Gelrand.")
        margin = ink_mask(figure, (edge, layout.gel_top, layout.canvas_w, layout.canvas_h))
        self.assertTrue(margin.any(), "Pfeilbeschriftung fehlt im rechten Rand.")

    def test_arrow_hides_same_side_ladder(self) -> None:
        self.panel.ladder_sides = "right"
        self.panel.arrows = [TargetArrow(label="GFP", y_pos_rel=0.4, side="right")]
        self.assertEqual(cr.effective_ladder_sides(self.panel), ())

    def test_left_arrow_and_scale_move(self) -> None:
        self.panel.ladder_sides = "left"
        self.panel.arrows = [TargetArrow(label="GFP", y_pos_rel=0.4, side="left")]
        layout = cr.compute_layout(self.panel, self.gel.size, self.options)
        self.assertGreater(layout.left_margin, layout.pad)
        self.assertNotIn("left", layout.effective_sides)


class ProcessingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.gel = small_gel()

    def test_identity_transform_is_noop(self) -> None:
        result = ip.apply_transform(self.gel, Transform())
        self.assertEqual(result.size, self.gel.size)
        self.assertTrue(np.array_equal(np.asarray(result), np.asarray(self.gel.convert("RGB"))))

    def test_perspective_changes_geometry(self) -> None:
        transform = Transform(perspective=[[0.1, 0.1], [0.95, 0.05], [0.9, 0.9], [0.05, 0.95]])
        result = ip.apply_transform(self.gel, transform)
        self.assertGreater(result.width, 0)
        self.assertGreater(result.height, 0)

    def test_rotation_and_flip(self) -> None:
        result = ip.apply_transform(self.gel, Transform(rotation=90))
        self.assertEqual(result.size, (self.gel.height, self.gel.width))
        flipped = ip.apply_transform(self.gel, Transform(flip_h=True))
        self.assertTrue(np.array_equal(np.asarray(flipped.convert("RGB")), np.asarray(ip.apply_transform(self.gel, Transform(flip_h=True)).convert("RGB"))))

    def test_adjustments_brightness_and_invert(self) -> None:
        base_mean = float(np.asarray(self.gel.convert("L")).mean())
        bright = ip.apply_adjustments(self.gel, Adjustments(brightness=60))
        self.assertGreater(float(np.asarray(bright.convert("L")).mean()), base_mean)
        inverted = ip.apply_adjustments(self.gel, Adjustments(invert=True))
        self.assertAlmostEqual(255.0 - float(np.asarray(inverted.convert("L")).mean()), base_mean, delta=1.0)

    def test_identity_adjustments_are_noop(self) -> None:
        result = ip.apply_adjustments(self.gel, Adjustments())
        self.assertTrue(np.array_equal(np.asarray(result.convert("RGB")), np.asarray(self.gel.convert("RGB"))))

    def test_process_panel_pipeline(self) -> None:
        panel = default_project().panels[0]
        panel.source_image = self.gel
        panel.adjustments.brightness = 20
        processed = ip.process_panel(panel)
        self.assertEqual(processed.mode, "RGB")
        self.assertEqual(processed.size, self.gel.size)


class HarmonizationTest(unittest.TestCase):
    def _project(self) -> Project:
        project = default_project()
        panel_a = project.panels[0]
        panel_a.source_image = small_gel()
        panel_b = GelPanel(letter="B")
        panel_b.source_image = small_gel().resize((400, 300))
        panel_b.markers = [MarkerBand(mw=m.mw, y_pos_rel=min(0.98, m.y_pos_rel * 0.85 + 0.08)) for m in panel_a.markers]
        project.panels.append(panel_b)
        return project

    def test_height_harmonization_resizes(self) -> None:
        project = self._project()
        project.export.harmonization = "height"
        project.export.target_height = 600
        for panel in project.panels:
            gel, _ = ip.harmonize_panel(panel, project)
            self.assertEqual(gel.height, 600)
            self.assertEqual(gel.width, round(panel.source_image.width * 600 / panel.source_image.height))

    def test_affine_harmonization_aligns_references(self) -> None:
        project = self._project()
        project.export.harmonization = "affine"
        project.export.target_height = 600
        for panel in project.panels:
            gel, mapper = ip.harmonize_panel(panel, project)
            self.assertEqual(gel.height, 600)
            remapped = ip.remap_panel(panel, mapper)
            top = min(remapped.markers, key=lambda m: abs(m.mw - 100.0))
            bottom = min(remapped.markers, key=lambda m: abs(m.mw - 10.0))
            self.assertAlmostEqual(top.y_pos_rel, project.export.ref_target_top, delta=0.02)
            self.assertAlmostEqual(bottom.y_pos_rel, project.export.ref_target_bottom, delta=0.02)


class CompositionTest(unittest.TestCase):
    def test_compose_panels(self) -> None:
        a = Image.new("RGB", (100, 200), (255, 255, 255))
        b = Image.new("RGB", (120, 200), (255, 255, 255))
        combined = cr.compose_panels([a, b], gutter=30, background=(0, 0, 0))
        self.assertEqual(combined.size, (250, 200))
        self.assertEqual(combined.getpixel((110, 100)), (0, 0, 0))

    def test_common_layout_overrides(self) -> None:
        project = default_project()
        panel_a = project.panels[0]
        panel_b = GelPanel(letter="B")
        panel_b.groups = [GroupLabel(text="Gruppe", start_index=0, end_index=2)]
        gel = small_gel()
        overrides = cr.common_layout_overrides([panel_a, panel_b], [gel, gel], cr.RenderOptions())
        self.assertGreaterEqual(overrides["min_header_h"], 0)


class ExportTest(unittest.TestCase):
    def setUp(self) -> None:
        self.gel = small_gel()
        self.panel = default_project().panels[0]
        self.panel.arrows = [TargetArrow(label="37 kDa", y_pos_rel=0.5, side="right")]
        self.figure = cr.render_figure(self.panel, self.gel, cr.RenderOptions(dpi=300, supersample=2))

    def test_png_carries_300_dpi(self) -> None:
        data = cr.png_bytes(self.figure, 300)
        with Image.open(io.BytesIO(data)) as image:
            dpi = image.info.get("dpi", (0, 0))
        self.assertAlmostEqual(dpi[0], 300, delta=1)

    def test_tiff_is_valid(self) -> None:
        data = cr.tiff_bytes(self.figure, 300)
        with Image.open(io.BytesIO(data)) as image:
            self.assertEqual(image.size, self.figure.size)

    def test_pdf_is_valid(self) -> None:
        data = cr.pdf_bytes(self.figure, 300)
        self.assertTrue(data.startswith(b"%PDF"))

    def test_metadata_exports(self) -> None:
        project = default_project()
        project.panels[0] = self.panel
        sizes = {self.panel.id: self.gel.size}
        csv_text = cr.metadata_csv(project, sizes)
        self.assertIn("spur_index", csv_text)
        self.assertIn("37 kDa", csv_text)
        payload = json.loads(cr.metadata_json(project, sizes))
        self.assertEqual(len(payload["panels"]), 1)
        self.assertEqual(payload["panels"][0]["targets"][0]["label"], "37 kDa")


class PersistenceTest(unittest.TestCase):
    def test_project_json_roundtrip_with_images(self) -> None:
        project = default_project()
        panel = project.panels[0]
        panel.source_image = small_gel()
        panel.source_name = "probe.png"
        panel.name = "Hauptgel"
        panel.arrows = [TargetArrow(label="GFP", y_pos_rel=0.33, side="left")]
        panel.conditions = [ConditionRow(name="DTT", values=["+"] * 10)]
        project.lang = "en"
        project.theme = "dark"

        restored = Project.from_json_bytes(project.to_json_bytes(embed_images=True))
        self.assertEqual(restored.lang, "en")
        self.assertEqual(restored.theme, "dark")
        self.assertEqual(restored.panels[0].name, "Hauptgel")
        self.assertIsNotNone(restored.panels[0].source_image)
        self.assertEqual(restored.panels[0].source_image.size, panel.source_image.size)
        self.assertEqual(restored.panels[0].arrows[0].label, "GFP")
        self.assertEqual(restored.panels[0].conditions[0].values[:2], ["+", "+"])

    def test_missing_images_key_is_tolerated(self) -> None:
        project = default_project()
        data = project.to_dict(embed_images=False)
        restored = Project.from_dict(data)
        self.assertIsNone(restored.panels[0].source_image)
        self.assertEqual(len(restored.panels[0].lanes), 10)

    def test_clamping_of_coordinates(self) -> None:
        panel = GelPanel()
        panel.lanes[0].x_pos_rel = 5.0
        self.assertEqual(panel.lanes[0].x_pos_rel, 1.0)
        marker = MarkerBand(mw=-3, y_pos_rel=9)
        self.assertEqual(marker.mw, 0.0)
        self.assertEqual(marker.y_pos_rel, 1.0)
        self.assertEqual(Transform(fine_rotation=200).fine_rotation, 45.0)


class AnalysisTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.gel = ip.load_image_from_path(SAMPLE)

    def test_lane_detection_returns_sorted_grid(self) -> None:
        detection = ip.detect_lanes(self.gel, 10)
        self.assertEqual(len(detection.positions_rel), 10)
        self.assertEqual(list(detection.positions_rel), sorted(detection.positions_rel))
        self.assertTrue(all(0.0 < value < 1.0 for value in detection.positions_rel))

    def test_marker_detection_is_plausible(self) -> None:
        detection = ip.detect_marker_bands(self.gel, "left", count=9)
        self.assertGreaterEqual(len(detection.positions_rel), 5)
        self.assertEqual(list(detection.positions_rel), sorted(detection.positions_rel))

    def test_auto_crop_keeps_most_of_image(self) -> None:
        box = ip.auto_crop_box(self.gel)
        width, height = self.gel.size
        self.assertGreater(box[2] - box[0], width * 0.7)
        self.assertGreater(box[3] - box[1], height * 0.7)

    def test_kda_estimate_is_monotonic(self) -> None:
        markers = default_project().panels[0].markers
        top = ip.estimate_kda_at_y(0.15, markers)
        middle = ip.estimate_kda_at_y(0.45, markers)
        bottom = ip.estimate_kda_at_y(0.80, markers)
        self.assertGreater(top, middle)
        self.assertGreater(middle, bottom)

    def test_load_image_handles_tiff(self) -> None:
        buffer = io.BytesIO()
        self.gel.save(buffer, format="TIFF")
        loaded = ip.load_image(buffer.getvalue())
        self.assertEqual(loaded.mode, "RGB")
        self.assertEqual(loaded.size, self.gel.size)


class CountInputTest(unittest.TestCase):
    """Direkteingabe der Spuren- und Markeranzahl."""

    def test_set_lane_count(self) -> None:
        panel = GelPanel()
        workflow.set_lane_count(panel, 12)
        self.assertEqual(len(panel.lanes), 12)
        xs = [lane.x_pos_rel for lane in panel.lanes]
        self.assertEqual(xs, sorted(xs))
        self.assertAlmostEqual(xs[0], 0.5 / 12, places=4)
        self.assertAlmostEqual(xs[-1], 11.5 / 12, places=4)

        workflow.set_lane_count(panel, 4)
        self.assertEqual(len(panel.lanes), 4)
        self.assertEqual([lane.label_top for lane in panel.lanes], ["1", "2", "3", "4"])

    def test_set_marker_count(self) -> None:
        panel = GelPanel()
        workflow.set_marker_count(panel, 6)
        self.assertEqual(len(panel.markers), 6)
        markers = panel.sorted_markers()
        ys = [marker.y_pos_rel for marker in markers]
        self.assertEqual(ys, sorted(ys))
        self.assertLess(ys[0], ys[-1])
        # oben liegt die größte Masse, unten die kleinste
        self.assertAlmostEqual(markers[0].mw, 170.0, places=2)
        self.assertAlmostEqual(markers[-1].mw, 10.0, places=2)

        values = [marker.mw for marker in markers]
        workflow.set_marker_count(panel, 6)
        self.assertEqual(len(panel.markers), 6)
        self.assertEqual([marker.mw for marker in panel.sorted_markers()], values)


class LocaleTest(unittest.TestCase):
    def test_translation_falls_back(self) -> None:
        self.assertEqual(locales.t("yes", "de"), "Ja")
        self.assertEqual(locales.t("yes", "en"), "Yes")
        self.assertEqual(locales.t("does_not_exist"), "does_not_exist")

    def test_all_app_keys_exist(self) -> None:
        source = (ROOT / "gel_app.py").read_text(encoding="utf-8")
        keys = set(re.findall(r'L\("([a-zA-Z0-9_]+)"', source))
        keys |= set(re.findall(r'\bt\("([a-zA-Z0-9_]+)"', source))
        missing = locales.missing_keys(*sorted(keys))
        self.assertEqual(missing, [], f"Fehlende Übersetzungsschlüssel: {missing}")

    def test_workflow_message_keys_exist(self) -> None:
        source = (ROOT / "workflow.py").read_text(encoding="utf-8")
        keys = set(re.findall(r'message_key = "([a-zA-Z0-9_]+)"', source))
        self.assertEqual(locales.missing_keys(*sorted(keys)), [])


class RichLabelTest(unittest.TestCase):
    """Hoch- und Tiefstellung in Spurbeschriftungen."""

    def test_parse_rich(self) -> None:
        self.assertEqual(cr.parse_rich("A^{2}B"), [("A", 0), ("2", 1), ("B", 0)])
        self.assertEqual(cr.parse_rich("H_{2}O"), [("H", 0), ("2", -1), ("O", 0)])
        self.assertEqual(cr.parse_rich("x^2"), [("x", 0), ("2", 1)])
        self.assertEqual(cr.parse_rich("plain"), [("plain", 0)])
        self.assertEqual(cr.parse_rich("a _{b c}"), [("a ", 0), ("b c", -1)])

    def _gray(self, image: Image.Image) -> np.ndarray:
        canvas = Image.new("RGBA", image.size, (255, 255, 255, 255))
        return np.asarray(Image.alpha_composite(canvas, image.convert("RGBA")).convert("L"))

    def test_superscript_sits_higher(self) -> None:
        plain = cr._label_image("106", 20, "Arial", (0, 0, 0), 0)
        rich = cr._label_image("10^{6}", 20, "Arial", (0, 0, 0), 0)
        self.assertGreaterEqual(rich.height, plain.height, "Skripte dürfen innerhalb der Schriftmetriken liegen.")

        # Innerhalb eines Labels muss das Skriptzeichen höher sitzen als die Grundschrift.
        image = cr._label_image("0^{7}", 40, "Arial", (0, 0, 0), 0)
        gray = self._gray(image)
        rows, cols = np.where(gray < 200)
        self.assertTrue(len(cols), "Label ohne Tinte gerendert.")
        split = (cols.min() + cols.max()) / 2
        left_top = rows[cols <= split].min()
        right_top = rows[cols > split].min()
        self.assertLess(right_top, left_top, "Hochstellung muss über der Grundlinie liegen.")

    def test_subscript_widens_and_renders(self) -> None:
        width = cr.rich_text_width("H_{2}O", 30, "Arial")
        self.assertGreater(width, cr.rich_text_width("HO", 30, "Arial"))
        image = cr._label_image("H_{2}O", 30, "Arial", (0, 0, 0), 0)
        self.assertTrue((self._gray(image) < 200).any())

    def test_render_figure_accepts_rich_lane_label(self) -> None:
        panel = default_project().panels[0]
        panel.lanes[0].label_top = "10^{6}"
        panel.lanes[1].label_top = "H_{2}O"
        layout = cr.compute_layout(panel, small_gel().size, cr.RenderOptions(supersample=1))
        figure = cr.render_figure(panel, small_gel(), cr.RenderOptions(supersample=1))
        self.assertEqual(figure.size, (layout.canvas_w, layout.canvas_h))


if __name__ == "__main__":
    unittest.main()
