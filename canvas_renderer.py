"""Canvas- und Rendering-Engine für SDS-PAGE-Abbildungen.

Grundprinzip
------------
Das (bereits entworfene und ggf. gefilterte) Gel wird **niemals** verändert
oder überzeichnet. Die Engine rendert zunächst einen Canvas in der Theme-
Hintergrundfarbe mit Kopfzeile, Skala und Zielbanden-Pfeilen und setzt das
Gel anschließend pixelgenau in die dafür vorgesehene Fläche ein. Hilfslinien
existieren nur in der separat gerenderten Arbeitsansicht (``guides=True``).

Der obere Rahmen wird kollisionsfrei aus den tatsächlichen Text-Bounding-
Boxes (``PIL.ImageFont.getbbox``) berechnet: Panel-Buchstabe, Gruppen-
überschriften mit Trennlinie, Bedingungszeilen und Spuren-Labels
(0°/45°/90°) überlappen sich dadurch nie.
"""

from __future__ import annotations

import csv
import io
import json
import math
import os
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, ConfigDict

from models import (
    ExportSettings,
    GelPanel,
    Project,
    Theme,
    clamp,
)

RGB = tuple[int, int, int]
GuideMode = Literal["lanes", "markers", "arrows", "all"]

# ----------------------------------------------------------------------
# Theme
# ----------------------------------------------------------------------
THEMES: dict[str, dict[str, RGB]] = {
    "light": {
        "background": (255, 255, 255),
        "ink": (17, 17, 17),
        "guide_lane": (96, 165, 250),
        "guide_marker": (96, 165, 250),
        "guide_arrow": (198, 40, 40),
    },
    "dark": {
        "background": (0, 0, 0),
        "ink": (255, 255, 255),
        "guide_lane": (96, 165, 250),
        "guide_marker": (147, 197, 253),
        "guide_arrow": (248, 113, 113),
    },
}


class RenderOptions(BaseModel):
    """Physikalische, typografische und thematische Exporteinstellungen."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    theme: Theme = "light"
    dpi: int = 300
    supersample: int = 2
    font_family: str = "Arial"
    font_scale: float = 1.0
    label_rotation: int = 0
    lane_numbers_position: str = "bottom"
    show_lane_labels_bottom: bool = False

    @classmethod
    def from_settings(cls, settings: ExportSettings) -> RenderOptions:
        return cls(
            theme=settings.theme,
            dpi=settings.dpi,
            supersample=settings.supersample,
            font_family=settings.font_family,
            font_scale=settings.font_scale,
            label_rotation=settings.label_rotation,
            lane_numbers_position=settings.lane_numbers_position,
            show_lane_labels_bottom=settings.show_lane_labels_bottom,
        )

    def validated(self) -> RenderOptions:
        return RenderOptions(
            theme=self.theme if self.theme in THEMES else "light",
            dpi=int(clamp(self.dpi, 72, 1200)),
            supersample=int(clamp(self.supersample, 1, 3)),
            font_family=self.font_family,
            font_scale=float(clamp(self.font_scale, 0.6, 2.0)),
            label_rotation=self.label_rotation if self.label_rotation in (0, 45, 90) else 0,
            lane_numbers_position=(
                self.lane_numbers_position if self.lane_numbers_position in ("none", "top", "bottom") else "bottom"
            ),
            show_lane_labels_bottom=bool(self.show_lane_labels_bottom),
        )

    @property
    def colors(self) -> dict[str, RGB]:
        return THEMES[self.theme if self.theme in THEMES else "light"]


# ----------------------------------------------------------------------
# Layout
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class Layout:
    """Pixelgeometrie des finalen Canvas (Bezugsauflösung = Gelauflösung)."""

    canvas_w: int
    canvas_h: int
    gel_left: int
    gel_top: int
    gel_w: int
    gel_h: int
    header_h: int
    left_margin: int
    right_margin: int
    bottom_margin: int
    tick_len: int
    tick_gap: int
    pad: int
    column_left: int
    column_right: int
    label_font_px: int
    number_font_px: int
    letter_font_px: int
    arrow_len: int
    arrow_gap: int
    label_block_h: int
    group_block_h: int
    condition_block_h: int
    effective_sides: tuple[str, ...]

    def scaled(self, factor: float) -> dict[str, float]:
        """Geometrie für den HTML-Editor (Bildkoordinaten × factor)."""
        return {
            key: round(getattr(self, key) * factor, 2)
            for key in (
                "canvas_w",
                "canvas_h",
                "gel_left",
                "gel_top",
                "gel_w",
                "gel_h",
                "header_h",
                "left_margin",
                "right_margin",
                "bottom_margin",
                "tick_len",
                "tick_gap",
                "pad",
                "label_font_px",
                "number_font_px",
                "letter_font_px",
                "arrow_len",
                "arrow_gap",
                "label_block_h",
            )
        }


# ----------------------------------------------------------------------
# Schriften
# ----------------------------------------------------------------------
_FONT_CANDIDATES: dict[str, tuple[tuple[str, int], ...]] = {
    "Arial": (
        ("/System/Library/Fonts/Supplemental/Arial.ttf", 0),
        ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 0),
        ("/Library/Fonts/Arial.ttf", 0),
        ("C:/Windows/Fonts/arial.ttf", 0),
        ("/usr/share/fonts/truetype/msttcorefonts/Arial.ttf", 0),
        ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 0),
    ),
    "Helvetica": (
        ("/System/Library/Fonts/Helvetica.ttc", 0),
        ("/System/Library/Fonts/HelveticaNeue.ttc", 0),
        ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 0),
    ),
    "Roboto": (
        ("/System/Library/Fonts/Roboto-Regular.ttf", 0),
        ("/usr/share/fonts/truetype/roboto/unhinted/RobotoTTF/Roboto-Regular.ttf", 0),
        ("/usr/share/fonts/truetype/roboto/Roboto-Regular.ttf", 0),
        ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 0),
    ),
    "DejaVu Sans": (
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 0),
        ("/Library/Fonts/DejaVuSans.ttf", 0),
    ),
}

_BOLD_SUFFIXES = {
    "Arial": ("Arial Bold.ttf", "LiberationSans-Bold.ttf"),
    "Helvetica": ("Helvetica-Bold.ttc", "HelveticaNeue-Bold.ttc"),
    "Roboto": ("Roboto-Bold.ttf", "LiberationSans-Bold.ttf"),
    "DejaVu Sans": ("DejaVuSans-Bold.ttf",),
}

FONT_FAMILIES = tuple(_FONT_CANDIDATES)


def available_font_families() -> list[str]:
    """Schriftfamilien, für die auf dem System eine Datei existiert."""
    found: list[str] = []
    for family, candidates in _FONT_CANDIDATES.items():
        if any(os.path.exists(path) for path, _ in candidates):
            found.append(family)
    return found or ["DejaVu Sans"]


@lru_cache(maxsize=512)
def load_font(
    size: int, family: str = "Arial", bold: bool = False
) -> ImageFont.FreeTypeFont:
    """Lädt eine TrueType-Schrift mit deterministischem Fallback."""
    size = max(6, int(size))
    candidates = list(_FONT_CANDIDATES.get(family, _FONT_CANDIDATES["Arial"]))

    if bold:
        paths = [path for path, _ in candidates]
        suffixes = _BOLD_SUFFIXES.get(family, ())
        bold_candidates: list[tuple[str, int]] = []
        for suffix in suffixes:
            for path in paths:
                bold_candidates.append((str(Path(path).with_name(suffix)), 0))
        bold_candidates.extend(
            [
                ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 0),
                ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 0),
            ]
        )
        candidates = bold_candidates + candidates

    for path, index in candidates:
        if not path or not os.path.exists(path):
            continue
        try:
            return ImageFont.truetype(path, size=size, index=index)
        except (OSError, ValueError):
            continue

    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # sehr alte Pillow-Versionen
        return ImageFont.load_default()


def text_width(text: str, font: ImageFont.FreeTypeFont) -> int:
    if not text:
        return 0
    left, _, right, _ = font.getbbox(text)
    return int(right - left)


#: Skript-Marker für Hoch- und Tiefstellung.
_SUPER = 1
_SUB = -1


def parse_rich(text: str) -> list[tuple[str, int]]:
    """Zerlegt ``text`` in (Segment, Skript)-Paare.

    Hochstellung mit ``^{...}`` (oder kurz ``^2``), Tiefstellung mit ``_{...}``
    (oder kurz ``_2``). Alles andere bleibt normaler Text.
    """
    segments: list[tuple[str, int]] = []
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            segments.append(("".join(buffer), 0))
            buffer.clear()

    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char == "\\" and index + 1 < length and text[index + 1] in "\\^_{}":
            buffer.append(text[index + 1])
            index += 2
            continue
        if char in "^_" and index + 1 < length and text[index + 1] not in " \t":
            marker = _SUPER if char == "^" else _SUB
            cursor = index + 1
            if text[cursor] == "{":
                end = cursor + 1
                chunk_chars = []
                while end < length and text[end] != "}":
                    if text[end] == "\\" and end + 1 < length and text[end + 1] in "\\^_{}":
                        end += 1
                    chunk_chars.append(text[end])
                    end += 1
                if end == length:
                    buffer.append(text[index:])
                    index = length
                    continue
                else:
                    chunk = "".join(chunk_chars)
                    index = end + 1
            else:
                end = cursor
                while end < length and text[end] not in " \t^_":
                    end += 1
                chunk = text[cursor:end]
                index = end
            flush()
            if chunk:
                segments.append((chunk, marker))
            continue
        buffer.append(char)
        index += 1
    flush()
    return segments or [("", 0)]


def _script_fonts(size: int, family: str) -> tuple[ImageFont.FreeTypeFont, ImageFont.FreeTypeFont]:
    """Basis- und verkleinerte Skriptschrift für ein Label."""
    size = max(6, int(size))
    return load_font(size, family), load_font(max(6, round(size * 0.68)), family)


def rich_text_width(text: str, size: int, family: str) -> int:
    """Breite eines Labels inklusive Hoch-/Tiefstellungs-Markierung."""
    base_font, script_font = _script_fonts(size, family)
    return math.ceil(sum(
        float((script_font if marker else base_font).getlength(chunk))
        for chunk, marker in parse_rich(text)
    ))


def _line_height(font: ImageFont.FreeTypeFont) -> int:
    _, top, _, bottom = font.getbbox("Ag")
    return int(bottom - top)


# ----------------------------------------------------------------------
# Textfitting
# ----------------------------------------------------------------------
def _ellipsize(text: str, font: ImageFont.FreeTypeFont, max_width: int, measure=None) -> str:
    measure = measure or (lambda value: text_width(value, font))
    if measure(text) <= max_width:
        return text
    ellipsis = "…"
    low, high = 0, len(text)
    while low < high:
        mid = (low + high + 1) // 2
        if measure(text[:mid] + ellipsis) <= max_width:
            low = mid
        else:
            high = mid - 1
    return (text[:low] + ellipsis).strip()


def _wrap_words(
    text: str, font: ImageFont.FreeTypeFont, max_width: int, max_lines: int, measure=None
) -> list[str]:
    measure = measure or (lambda value: text_width(value, font))
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if measure(candidate) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    if len(lines) > max_lines:
        head = lines[: max_lines - 1]
        tail = " ".join(lines[max_lines - 1 :])
        lines = head + [_ellipsize(tail, font, max_width, measure=measure)]
    return lines


def fit_label(
    text: str,
    max_width: int,
    base_size: int,
    family: str,
    min_scale: float = 0.6,
) -> tuple[list[str], int]:
    """Passt ein Label an die verfügbare Breite an (max. zwei Zeilen)."""
    text = text.strip()
    if not text:
        return [""], base_size

    base_size = max(6, int(base_size))
    min_size = max(6, round(base_size * min_scale))
    for size in range(base_size, min_size - 1, -1):
        def measure(value: str, _size: int = size) -> int:
            return rich_text_width(value, _size, family)

        if measure(text) <= max_width:
            return [text], size
        lines = _wrap_words(text, None, max_width, max_lines=2, measure=measure)
        if len(lines) > 1 and all(measure(line) <= max_width for line in lines):
            return lines, size
    return [_ellipsize(text, None, max_width, measure=lambda value: rich_text_width(value, min_size, family))], min_size


def _label_image(
    text: str,
    size: int,
    family: str,
    color: RGB,
    rotation: int,
) -> Image.Image:
    """Rendert ein Label (inkl. Hoch-/Tiefstellung) und dreht es bei Bedarf."""
    lines = text.split("\n") if text else [""]
    size = max(6, int(size))
    base_font, script_font = _script_fonts(size, family)
    ascent, descent = base_font.getmetrics()
    # Word-like proportions: scripts share the text baseline and move relative
    # to the em size. Bounds come from actual glyphs, including accents/descenders.
    offsets = {0: 0, _SUPER: -round(size * 0.38), _SUB: round(size * 0.16)}
    layouts = []
    for line in lines:
        runs = []
        x = 0.0
        left, top, right, bottom = 0.0, -ascent, 0.0, descent
        for chunk, marker in parse_rich(line):
            font = script_font if marker else base_font
            offset = offsets[marker]
            box = font.getbbox(chunk, anchor="ls")
            left = min(left, x + box[0])
            right = max(right, x + box[2])
            top = min(top, offset + box[1])
            bottom = max(bottom, offset + box[3])
            runs.append((x, offset, chunk, font))
            x += float(font.getlength(chunk))
        layouts.append((runs, left, top, max(right, x), bottom))
    padding = 4
    gap = max(2, round(size * 0.15))
    width = max(1, math.ceil(max(r-l for _, l, _, r, _ in layouts)) + padding * 2)
    height = max(1, int(sum(b-t for _, _, t, _, b in layouts) + gap * (len(lines)-1)) + padding * 2)
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    y = padding
    for runs, left, top, right, bottom in layouts:
        origin = (width - (right-left)) / 2 - left
        baseline = y - top
        for x, offset, chunk, font in runs:
            draw.text((origin+x, baseline+offset), chunk, font=font, fill=(*color, 255), anchor="ls")
        y += bottom-top+gap

    if rotation:
        image = image.rotate(rotation, expand=True, resample=Image.Resampling.BICUBIC)
    return image


# ----------------------------------------------------------------------
# Layout
# ----------------------------------------------------------------------
def effective_ladder_sides(panel: GelPanel) -> tuple[str, ...]:
    """Skalenseiten unter Berücksichtigung der Zielbanden-Pfeile."""
    if panel.ladder_sides == "both":
        sides = {"left", "right"}
    else:
        sides = {panel.ladder_sides}
    if panel.arrows_on("left"):
        sides.discard("left")
    if panel.arrows_on("right"):
        sides.discard("right")
    return tuple(side for side in ("left", "right") if side in sides)


def _lane_label_images(
    panel: GelPanel,
    options: RenderOptions,
    gel_w: int,
    label_font_px: int,
    color: RGB,
) -> list[tuple[int, Image.Image]]:
    """Erzeugt die (gedrehten) Labelbilder aller Spuren."""
    result: list[tuple[int, Image.Image]] = []
    rotation = options.label_rotation
    for index, lane in enumerate(panel.lanes):
        if not lane.label_top.strip():
            continue
        pitch = max(12, gel_w * panel.lane_pitch_rel(index))
        if rotation == 45:
            max_width = max(12, int(pitch * 0.95))
        elif rotation == 90:
            max_width = max(12, int(pitch * 2.2))
        else:
            max_width = max(12, int(pitch - 4))
        lines, size = fit_label(lane.label_top, max_width, label_font_px, options.font_family)
        image = _label_image("\n".join(lines), size, options.font_family, color, rotation)
        result.append((index, image))
    return result


def _group_block_height(panel: GelPanel, options: RenderOptions, label_font_px: int) -> int:
    if not panel.groups:
        return 0
    line_h = _line_height(load_font(label_font_px, options.font_family))
    row = int(line_h * 1.35)
    return row * len(panel.groups)


def _condition_block_height(panel: GelPanel, number_font_px: int) -> int:
    if not panel.conditions:
        return 0
    row = int(number_font_px * 1.45)
    return row * len(panel.conditions)


def compute_layout(
    panel: GelPanel,
    gel_size: tuple[int, int],
    options: RenderOptions,
    *,
    min_header_h: int = 0,
    min_bottom: int = 0,
    min_left: int = 0,
    min_right: int = 0,
) -> Layout:
    """Berechnet Ränder, Schriftgrößen und Canvas-Maße kollisionsfrei."""
    options = options.validated()
    gel_w, gel_h = gel_size
    scale = options.font_scale

    label_px = round(clamp(gel_h * 0.030 * scale, 10, 180))
    number_px = round(clamp(gel_h * 0.026 * scale, 8, 160))
    letter_px = round(clamp(gel_h * 0.038 * scale, 12, 220))
    tick_len = round(clamp(gel_h * 0.011 * scale, 4, 40))
    tick_gap = round(clamp(gel_h * 0.007 * scale, 3, 32))
    pad = round(clamp(gel_h * 0.009, 3, 48))

    color = options.colors["ink"]
    label_images = _lane_label_images(panel, options, gel_w, label_px, color)
    label_block_h = max((image.height for _, image in label_images), default=0)
    group_block_h = _group_block_height(panel, options, label_px)
    condition_block_h = _condition_block_height(panel, number_px)

    letter_h = _line_height(load_font(letter_px, options.font_family, bold=True))
    lane_numbers_top_h = int(number_px * 1.7) if options.lane_numbers_position == "top" else 0
    blocks = [letter_h]
    if group_block_h:
        blocks.append(group_block_h)
    if condition_block_h:
        blocks.append(condition_block_h)
    if label_block_h:
        blocks.append(label_block_h)
    if lane_numbers_top_h:
        blocks.append(lane_numbers_top_h)
    header_h = int(pad + sum(blocks) + pad * len(blocks))

    # Zielbanden-Pfeile im Außenrand.
    arrow_font = load_font(number_px, options.font_family)
    arrow_len = max(16, round(gel_w * 0.05))
    arrow_gap = max(4, round(number_px * 0.5))

    def arrow_margin(side: str) -> int:
        arrows = panel.arrows_on(side)
        if not arrows:
            return 0
        widest = max((text_width(a.label, arrow_font) for a in arrows), default=0)
        return int(pad + arrow_len + arrow_gap + widest + pad)

    # kDa-Skala.
    number_font = load_font(number_px, options.font_family)
    values = [m.display_value for m in panel.markers if m.visible]
    widest_number = max((text_width(value, number_font) for value in values), default=0)
    unit_width = text_width(panel.unit, number_font)
    column_width = max(widest_number, unit_width, number_px)
    scale_margin = int(pad + column_width + tick_gap + tick_len + pad)

    sides = effective_ladder_sides(panel)
    left_margin = pad
    right_margin = pad
    if "left" in sides:
        left_margin = max(left_margin, scale_margin)
    if "right" in sides:
        right_margin = max(right_margin, scale_margin)
    left_margin = max(left_margin, arrow_margin("left"), min_left)
    right_margin = max(right_margin, arrow_margin("right"), min_right)

    # Unterer Rand: Spurnummern oder 45°-Labels.
    if options.show_lane_labels_bottom and any(lane.label_bottom.strip() for lane in panel.lanes):
        bottom = int(number_px * 1.6)
    elif options.lane_numbers_position == "bottom":
        bottom = int(number_px * 1.7)
    else:
        bottom = max(4, round(gel_h * 0.012))
    bottom = max(bottom, min_bottom)

    header_h = max(header_h, min_header_h)

    return Layout(
        canvas_w=int(left_margin + gel_w + right_margin),
        canvas_h=int(header_h + gel_h + bottom),
        gel_left=int(left_margin),
        gel_top=int(header_h),
        gel_w=int(gel_w),
        gel_h=int(gel_h),
        header_h=int(header_h),
        left_margin=int(left_margin),
        right_margin=int(right_margin),
        bottom_margin=int(bottom),
        tick_len=tick_len,
        tick_gap=tick_gap,
        pad=pad,
        column_left=pad,
        column_right=pad + column_width,
        label_font_px=label_px,
        number_font_px=number_px,
        letter_font_px=letter_px,
        arrow_len=arrow_len,
        arrow_gap=arrow_gap,
        label_block_h=label_block_h,
        group_block_h=group_block_h,
        condition_block_h=condition_block_h,
        effective_sides=sides,
    )


# ----------------------------------------------------------------------
# Zeichnen: Kopf
# ----------------------------------------------------------------------
def _draw_condition_symbol(
    draw: ImageDraw.ImageDraw, value: str, xy: tuple[float, float], size: int, fill: RGB,
) -> bool:
    """Einzelne Plus-/Minuszeichen ohne Abhängigkeit von installierten Glyphen."""
    symbol = value.strip()
    minus = symbol in {"-", "−", "–", "—", "﹣", "－"}
    if not minus and symbol not in {"+", "＋"}:
        return False
    x, y = xy
    half = max(2, round(size * 0.28))
    width = max(1, round(size * 0.075))
    draw.line((x - half, y, x + half, y), fill=fill, width=width)
    if not minus:
        draw.line((x, y - half, x, y + half), fill=fill, width=width)
    return True


def _draw_header(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    panel: GelPanel,
    layout: Layout,
    options: RenderOptions,
    scale: int,
) -> None:
    color = options.colors["ink"]
    pad = layout.pad * scale
    family = options.font_family
    gel_left = layout.gel_left * scale
    gel_w = layout.gel_w * scale

    letter_font = load_font(layout.letter_font_px * scale, family, bold=True)
    cursor = pad
    draw.text((pad, cursor), panel.letter, font=letter_font, fill=color, anchor="la")
    cursor += layout.letter_font_px * scale + pad * 0.6

    def lane_x(rel: float) -> float:
        return gel_left + rel * gel_w

    # Gruppenüberschriften mit Trennlinie.
    if panel.groups:
        font = load_font(layout.label_font_px * scale, family, bold=True)
        line_h = _line_height(font)
        row_h = line_h * 1.35
        underline_w = max(1, round(scale * 1.0))
        for group in panel.groups:
            if not group.text:
                continue
            start = min(group.start_index, len(panel.lanes) - 1)
            end = min(max(group.end_index, start), len(panel.lanes) - 1)
            x0 = lane_x(panel.lanes[start].x_pos_rel)
            x1 = lane_x(panel.lanes[end].x_pos_rel)
            center = (x0 + x1) / 2.0
            draw.text(
                (center, cursor + row_h * 0.5),
                group.text,
                font=font,
                fill=color,
                anchor="mm",
            )
            if group.underline:
                y = cursor + row_h - 1.5 * scale
                draw.line([(x0, y), (x1, y)], fill=color, width=underline_w)
            cursor += row_h

    # Bedingungs-Matrix.
    if panel.conditions:
        font = load_font(layout.number_font_px * scale, family)
        row_h = layout.number_font_px * 1.45 * scale
        pitch = layout.gel_w * scale / max(1, len(panel.lanes))
        for condition in panel.conditions:
            y = cursor + row_h * 0.5
            draw.text((pad, y), condition.name, font=font, fill=color, anchor="lm")
            for index, lane in enumerate(panel.lanes):
                value = condition.value_for(index)
                if not value:
                    continue
                xy = (lane_x(lane.x_pos_rel), y)
                if _draw_condition_symbol(draw, value, xy, layout.number_font_px * scale, color):
                    continue
                text = _ellipsize(value, font, int(pitch - 2 * scale))
                draw.text(xy, text, font=font, fill=color, anchor="mm")
            cursor += row_h

    # Spuren-Labels (0°/45°/90°).
    label_images = _lane_label_images(panel, options, layout.gel_w, layout.label_font_px, color)
    if label_images and layout.label_block_h:
        band_top = cursor
        center_y = band_top + layout.label_block_h * scale / 2.0
        for index, image in label_images:
            scaled = (
                image
                if scale == 1
                else image.resize(
                    (image.width * scale, image.height * scale),
                    Image.Resampling.LANCZOS,
                )
            )
            x = lane_x(panel.lanes[index].x_pos_rel)
            box = (
                round(x - scaled.width / 2),
                round(center_y - scaled.height / 2),
            )
            canvas.paste(scaled, box, scaled)
        cursor += layout.label_block_h * scale

    # Spurnummern direkt über dem Gel.
    if options.lane_numbers_position == "top":
        font = load_font(layout.number_font_px * scale, family)
        row_h = layout.number_font_px * 1.7 * scale
        center_y = cursor + row_h / 2.0
        for index, lane in enumerate(panel.lanes):
            draw.text(
                (lane_x(lane.x_pos_rel), center_y),
                str(index + 1),
                font=font,
                fill=color,
                anchor="mm",
            )


# ----------------------------------------------------------------------
# Zeichnen: Skala
# ----------------------------------------------------------------------
def _draw_scale_side(
    draw: ImageDraw.ImageDraw,
    panel: GelPanel,
    layout: Layout,
    options: RenderOptions,
    scale: int,
    side: Literal["left", "right"],
) -> None:
    color = options.colors["ink"]
    family = options.font_family
    number_font = load_font(layout.number_font_px * scale, family)
    tick_width = max(1, round(layout.gel_h * 0.0018)) * scale
    gel_top = layout.gel_top * scale
    gel_h = layout.gel_h * scale

    if side == "left":
        gel_edge = layout.gel_left * scale
        tick_outer = gel_edge - layout.tick_len * scale
        number_x = tick_outer - layout.tick_gap * scale
        draw.text(
            (layout.column_left * scale, (layout.gel_top - layout.pad * 0.65) * scale),
            panel.unit,
            font=number_font,
            fill=color,
            anchor="ls",
        )
        number_anchor = "rm"
        tick_from, tick_to = tick_outer, gel_edge
    else:
        gel_edge = (layout.gel_left + layout.gel_w) * scale
        tick_outer = gel_edge + layout.tick_len * scale
        number_x = tick_outer + layout.tick_gap * scale
        draw.text(
            (
                (layout.canvas_w - layout.pad) * scale,
                (layout.gel_top - layout.pad * 0.65) * scale,
            ),
            panel.unit,
            font=number_font,
            fill=color,
            anchor="rs",
        )
        number_anchor = "lm"
        tick_from, tick_to = gel_edge, tick_outer

    for marker in panel.sorted_markers():
        y = round(gel_top + marker.y_pos_rel * gel_h)
        draw.line([(tick_from, y), (tick_to, y)], fill=color, width=tick_width)
        draw.text(
            (number_x, y),
            marker.display_value,
            font=number_font,
            fill=color,
            anchor=number_anchor,
        )


# ----------------------------------------------------------------------
# Zeichnen: Zielbanden-Pfeile
# ----------------------------------------------------------------------
def _draw_arrows(
    draw: ImageDraw.ImageDraw,
    panel: GelPanel,
    layout: Layout,
    options: RenderOptions,
    scale: int,
    side: Literal["left", "right"],
) -> None:
    arrows = sorted(panel.arrows_on(side), key=lambda a: a.y_pos_rel)
    if not arrows:
        return
    color = options.colors["ink"]
    font = load_font(layout.number_font_px * scale, options.font_family)
    gel_top = layout.gel_top * scale
    gel_h = layout.gel_h * scale
    left = layout.gel_left * scale
    right = (layout.gel_left + layout.gel_w) * scale
    head = max(4 * scale, round(layout.arrow_len * scale * 0.45))
    line_w = max(1, round(layout.gel_h * 0.0022)) * scale

    line_h = _line_height(font)
    min_spacing = line_h + 4 * scale
    label_ys: list[float] = []
    for arrow in arrows:
        y = gel_top + arrow.y_pos_rel * gel_h
        label_ys.append(y)
    # Labels kollisionsfrei auseinanderschieben (Pfeilspitze bleibt exakt).
    for index in range(1, len(label_ys)):
        if label_ys[index] - label_ys[index - 1] < min_spacing:
            label_ys[index] = label_ys[index - 1] + min_spacing

    for arrow, label_y in zip(arrows, label_ys, strict=True):
        y = round(gel_top + arrow.y_pos_rel * gel_h)
        if side == "right":
            tail = right + layout.arrow_len * scale
            draw.line([(right, y), (tail, y)], fill=color, width=line_w)
            draw.polygon(
                [(right, y), (right + head, y - head * 0.55), (right + head, y + head * 0.55)],
                fill=color,
            )
            draw.text(
                (tail + layout.arrow_gap * scale, round(label_y)),
                arrow.label,
                font=font,
                fill=color,
                anchor="lm",
            )
        else:
            tail = left - layout.arrow_len * scale
            draw.line([(tail, y), (left, y)], fill=color, width=line_w)
            draw.polygon(
                [(left, y), (left - head, y - head * 0.55), (left - head, y + head * 0.55)],
                fill=color,
            )
            draw.text(
                (tail - layout.arrow_gap * scale, round(label_y)),
                arrow.label,
                font=font,
                fill=color,
                anchor="rm",
            )


# ----------------------------------------------------------------------
# Zeichnen: unterer Rand
# ----------------------------------------------------------------------
def _draw_bottom(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    panel: GelPanel,
    layout: Layout,
    options: RenderOptions,
    scale: int,
) -> None:
    color = options.colors["ink"]
    font = load_font(layout.number_font_px * scale, options.font_family)
    gel_left = layout.gel_left * scale
    gel_w = layout.gel_w * scale
    top = (layout.gel_top + layout.gel_h) * scale

    if options.show_lane_labels_bottom and any(
        lane.label_bottom.strip() for lane in panel.lanes
    ):
        for lane in panel.lanes:
            text = lane.label_bottom.strip()
            if not text:
                continue
            image = _label_image(text, layout.number_font_px * scale, options.font_family, color, 45)
            x = gel_left + lane.x_pos_rel * gel_w
            canvas.paste(
                image,
                (round(x - image.width / 2), round(top + 2 * scale)),
                image,
            )
        return

    if options.lane_numbers_position != "bottom":
        return
    y = top + layout.bottom_margin * scale / 2.0
    for index, lane in enumerate(panel.lanes):
        x = gel_left + lane.x_pos_rel * gel_w
        draw.text((x, y), str(index + 1), font=font, fill=color, anchor="mm")


# ----------------------------------------------------------------------
# Arbeitsansicht (Hilfslinien)
# ----------------------------------------------------------------------
def _dashed_line(
    draw: ImageDraw.ImageDraw,
    start: tuple[float, float],
    end: tuple[float, float],
    fill: tuple[int, int, int, int],
    width: int,
    dash: int,
    gap: int,
) -> None:
    x0, y0 = start
    x1, y1 = end
    length = max(abs(x1 - x0), abs(y1 - y0))
    if length <= 0:
        return
    steps = int(length)
    position = 0
    while position < steps:
        segment_end = min(position + dash, steps)
        if x0 == x1:
            draw.line([(x0, y0 + position), (x0, y0 + segment_end)], fill=fill, width=width)
        else:
            draw.line([(x0 + position, y0), (x0 + segment_end, y0)], fill=fill, width=width)
        position += dash + gap


def add_guides(
    figure: Image.Image,
    panel: GelPanel,
    layout: Layout,
    options: RenderOptions | None = None,
    mode: GuideMode = "all",
    selected_lane: int | None = None,
    selected_marker: int | None = None,
    selected_arrow: int | None = None,
) -> Image.Image:
    """Arbeitsansicht: Hilfslinien nur für Editor/Vorschau (nie im Export)."""
    options = (options or RenderOptions()).validated()
    colors = options.colors
    base = figure.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    gel_top = layout.gel_top
    gel_bottom = layout.gel_top + layout.gel_h
    gel_left = layout.gel_left
    gel_right = layout.gel_left + layout.gel_w

    if mode in ("lanes", "all"):
        for index, lane in enumerate(panel.lanes):
            x = round(gel_left + lane.x_pos_rel * layout.gel_w)
            active = index == selected_lane
            color = (*colors["guide_lane"], 235 if active else 160)
            _dashed_line(draw, (x, gel_top), (x, gel_bottom), color, 3 if active else 2, 18, 12)
            handle_h = max(8, layout.header_h // 3)
            draw.rounded_rectangle((x - 10, gel_top - handle_h, x + 10, gel_top), radius=3, fill=color)

    if mode in ("markers", "all"):
        for index, marker in enumerate(panel.sorted_markers()):
            y = round(gel_top + marker.y_pos_rel * layout.gel_h)
            active = index == selected_marker
            color = (*colors["guide_marker"], 235 if active else 155)
            _dashed_line(draw, (gel_left, y), (gel_right, y), color, 3 if active else 2, 16, 14)

    if mode in ("arrows", "all"):
        for index, arrow in enumerate(panel.visible_arrows()):
            y = round(gel_top + arrow.y_pos_rel * layout.gel_h)
            active = index == selected_arrow
            color = (*colors["guide_arrow"], 255 if active else 190)
            if arrow.side == "right":
                draw.line([(gel_right, y), (layout.canvas_w - layout.pad, y)], fill=color, width=3 if active else 2)
            else:
                draw.line([(layout.pad, y), (gel_left, y)], fill=color, width=3 if active else 2)

    return Image.alpha_composite(base, overlay).convert("RGB")


# ----------------------------------------------------------------------
# Hauptrenderer
# ----------------------------------------------------------------------
def render_figure(
    panel: GelPanel,
    gel: Image.Image,
    options: RenderOptions | None = None,
    *,
    guides: bool = False,
    guide_mode: GuideMode = "all",
    selected_lane: int | None = None,
    selected_marker: int | None = None,
    selected_arrow: int | None = None,
    layout: Layout | None = None,
    min_header_h: int = 0,
    min_bottom: int = 0,
    min_left: int = 0,
    min_right: int = 0,
) -> Image.Image:
    """Rendert die publikationsfertige Abbildung eines Panels.

    Das Gel wird erst nach dem Herunterskalieren der Beschriftungsebene
    pixelgenau eingesetzt und bleibt dadurch garantiert unverändert.
    """
    options = (options or RenderOptions()).validated()
    gel = gel.convert("RGB")
    if layout is None:
        layout = compute_layout(
            panel,
            gel.size,
            options,
            min_header_h=min_header_h,
            min_bottom=min_bottom,
            min_left=min_left,
            min_right=min_right,
        )
    factor = options.supersample

    canvas = Image.new(
        "RGB",
        (layout.canvas_w * factor, layout.canvas_h * factor),
        options.colors["background"],
    )
    draw = ImageDraw.Draw(canvas)

    _draw_header(canvas, draw, panel, layout, options, factor)
    _draw_bottom(canvas, draw, panel, layout, options, factor)
    if "left" in layout.effective_sides:
        _draw_scale_side(draw, panel, layout, options, factor, "left")
    if "right" in layout.effective_sides:
        _draw_scale_side(draw, panel, layout, options, factor, "right")
    _draw_arrows(draw, panel, layout, options, factor, "left")
    _draw_arrows(draw, panel, layout, options, factor, "right")

    if factor > 1:
        canvas = canvas.resize((layout.canvas_w, layout.canvas_h), Image.Resampling.LANCZOS)

    canvas.paste(gel, (layout.gel_left, layout.gel_top))

    if not guides:
        return canvas
    return add_guides(
        canvas,
        panel,
        layout,
        options,
        mode=guide_mode,
        selected_lane=selected_lane,
        selected_marker=selected_marker,
        selected_arrow=selected_arrow,
    )


def render_working_view(
    panel: GelPanel,
    gel: Image.Image,
    options: RenderOptions | None = None,
    selected_lane: int | None = None,
    selected_marker: int | None = None,
    selected_arrow: int | None = None,
) -> Image.Image:
    """Abbildung inklusive sichtbarer Hilfslinien (nur Arbeitsansicht)."""
    return render_figure(
        panel,
        gel,
        options,
        guides=True,
        guide_mode="all",
        selected_lane=selected_lane,
        selected_marker=selected_marker,
        selected_arrow=selected_arrow,
    )


# ----------------------------------------------------------------------
# Multi-Panel-Komposition
# ----------------------------------------------------------------------
def common_layout_overrides(
    panels: list[GelPanel],
    gels: list[Image.Image],
    options: RenderOptions,
) -> dict[str, int]:
    """Einheitliche Kopf-/Fußhöhen für eine kombinierte Multi-Gel-Figur."""
    header = 0
    bottom = 0
    for panel, gel in zip(panels, gels, strict=True):
        layout = compute_layout(panel, gel.size, options)
        header = max(header, layout.header_h)
        bottom = max(bottom, layout.bottom_margin)
    return {"min_header_h": header, "min_bottom": bottom}


def compose_panels(
    figures: Iterable[Image.Image],
    gutter: int = 40,
    background: RGB = (255, 255, 255),
) -> Image.Image:
    """Setzt einzeln gerenderte Panels nahtlos nebeneinander."""
    figures = [figure.convert("RGB") for figure in figures]
    if not figures:
        raise ValueError("Mindestens eine Abbildung erforderlich.")
    height = max(figure.height for figure in figures)
    gutter = max(0, int(gutter))
    width = sum(figure.width for figure in figures) + gutter * (len(figures) - 1)
    canvas = Image.new("RGB", (width, height), background)
    x = 0
    for figure in figures:
        canvas.paste(figure, (x, 0))
        x += figure.width + gutter
    return canvas


# ----------------------------------------------------------------------
# Export
# ----------------------------------------------------------------------
def png_bytes(image: Image.Image, dpi: int = 300) -> bytes:
    buffer = io.BytesIO()
    # optimize=True kostet ein Vielfaches der Rechenzeit (hier ~0,6 s statt ~0,08 s)
    # und spart nur wenige Prozent Dateigröße.
    image.save(buffer, format="PNG", dpi=(dpi, dpi), compress_level=6)
    return buffer.getvalue()


def tiff_bytes(image: Image.Image, dpi: int = 300) -> bytes:
    buffer = io.BytesIO()
    image.convert("RGB").save(
        buffer, format="TIFF", dpi=(dpi, dpi), compression="tiff_lzw"
    )
    return buffer.getvalue()


def pdf_bytes(image: Image.Image, dpi: int = 300) -> bytes:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PDF", resolution=float(dpi), quality=95)
    return buffer.getvalue()


# ----------------------------------------------------------------------
# Metadaten
# ----------------------------------------------------------------------
def lanes_csv(panel: GelPanel) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        ["panel", "spur_index", "probenbezeichnung", "unteres_label", "x_position_rel", "spurrolle", "marker_kda"]
    )
    marker_values = "; ".join(m.display_value for m in panel.sorted_markers())
    for index, lane in enumerate(panel.lanes):
        writer.writerow(
            [
                panel.letter,
                index + 1,
                lane.label_top,
                lane.label_bottom,
                f"{lane.x_pos_rel:.4f}",
                "marker" if panel.is_marker_lane(index) else "probe",
                marker_values if panel.is_marker_lane(index) else "",
            ]
        )
    return "\ufeff" + buffer.getvalue()


def markers_csv(panel: GelPanel, gel_size: tuple[int, int]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["panel", "marker_index", "kda", "unit", "y_position_rel", "y_position_pct", "y_position_px", "sichtbar"])
    _, gel_h = gel_size
    for index, marker in enumerate(panel.markers, start=1):
        writer.writerow(
            [
                panel.letter,
                index,
                marker.display_value,
                marker.unit,
                f"{marker.y_pos_rel:.4f}",
                f"{marker.y_pos_rel * 100:.2f}",
                round(marker.y_pos_rel * gel_h),
                "ja" if marker.visible else "nein",
            ]
        )
    return "\ufeff" + buffer.getvalue()


def targets_csv(panel: GelPanel, gel_size: tuple[int, int]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["panel", "ziel_index", "zielbezeichnung", "seite", "y_position_rel", "y_position_px", "sichtbar"])
    _, gel_h = gel_size
    for index, arrow in enumerate(panel.arrows, start=1):
        writer.writerow(
            [
                panel.letter,
                index,
                arrow.label,
                arrow.side,
                f"{arrow.y_pos_rel:.4f}",
                round(arrow.y_pos_rel * gel_h),
                "ja" if arrow.visible else "nein",
            ]
        )
    return "\ufeff" + buffer.getvalue()


def metadata_csv(project: Project, gel_sizes: dict[str, tuple[int, int]]) -> str:
    """Kombinierter CSV-Report: Spuren, Bedingungen, Marker und Zielbanden."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    for panel in project.panels:
        gel_size = gel_sizes.get(panel.id, (0, 0))
        writer.writerow([f"# Panel {panel.letter}", panel.name, panel.source_name])
        _write_panel_metadata(writer, panel, gel_size)
        writer.writerow([])
    return "\ufeff" + buffer.getvalue()


def _write_panel_metadata(writer, panel: GelPanel, gel_size: tuple[int, int]) -> None:
    _, gel_h = gel_size
    writer.writerow(["spur_index", "probenbezeichnung", "unteres_label", "x_position_rel", "spurrolle"])
    for index, lane in enumerate(panel.lanes):
        writer.writerow(
            [
                index + 1,
                lane.label_top,
                lane.label_bottom,
                f"{lane.x_pos_rel:.4f}",
                "marker" if panel.is_marker_lane(index) else "probe",
            ]
        )
    for condition in panel.conditions:
        writer.writerow(["bedingung", condition.name, *condition.values])
    for group in panel.groups:
        writer.writerow(["gruppe", group.text, group.start_index + 1, group.end_index + 1])
    writer.writerow(["marker_index", "kda", "y_position_rel", "y_position_px", "sichtbar"])
    for index, marker in enumerate(panel.markers, start=1):
        writer.writerow(
            [
                index,
                marker.display_value,
                f"{marker.y_pos_rel:.4f}",
                round(marker.y_pos_rel * gel_h),
                "ja" if marker.visible else "nein",
            ]
        )
    writer.writerow(["ziel_index", "zielbezeichnung", "seite", "y_position_rel", "y_position_px", "sichtbar"])
    for index, arrow in enumerate(panel.arrows, start=1):
        writer.writerow(
            [
                index,
                arrow.label,
                arrow.side,
                f"{arrow.y_pos_rel:.4f}",
                round(arrow.y_pos_rel * gel_h),
                "ja" if arrow.visible else "nein",
            ]
        )


def targets_json(panel: GelPanel) -> list[dict]:
    return [
        {
            "index": index + 1,
            "label": arrow.label,
            "side": arrow.side,
            "y_pos_rel": round(arrow.y_pos_rel, 4),
            "visible": arrow.visible,
        }
        for index, arrow in enumerate(panel.arrows)
    ]


def metadata_json(project: Project, gel_sizes: dict[str, tuple[int, int]]) -> str:
    """Strukturierter JSON-Report aller Panels, Spuren, Bedingungen und Banden."""
    payload = {
        "project": project.name,
        "version": project.version,
        "lang": project.lang,
        "theme": project.theme,
        "export": project.export.model_dump(mode="json"),
        "panels": [
            {
                "letter": panel.letter,
                "name": panel.name,
                "source": panel.source_name,
                "gel_size_px": list(gel_sizes.get(panel.id, (0, 0))),
                "unit": panel.unit,
                "ladder_sides": panel.ladder_sides,
                "lanes": [
                    {
                        "index": index + 1,
                        "sample": lane.label_top,
                        "bottom": lane.label_bottom,
                        "x_pos_rel": round(lane.x_pos_rel, 4),
                        "role": "marker" if panel.is_marker_lane(index) else "sample",
                    }
                    for index, lane in enumerate(panel.lanes)
                ],
                "conditions": [
                    {"name": condition.name, "values": list(condition.values)}
                    for condition in panel.conditions
                ],
                "groups": [
                    {
                        "text": group.text,
                        "from_lane": group.start_index + 1,
                        "to_lane": group.end_index + 1,
                    }
                    for group in panel.groups
                ],
                "markers": [
                    {
                        "index": index + 1,
                        "mw": marker.mw,
                        "unit": marker.unit,
                        "y_pos_rel": round(marker.y_pos_rel, 4),
                        "visible": marker.visible,
                    }
                    for index, marker in enumerate(panel.markers)
                ],
                "targets": targets_json(panel),
            }
            for panel in project.panels
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)
