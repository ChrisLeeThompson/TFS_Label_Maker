"""Measure a LabelSpec into pixel-exact geometry, once.

build_layout is the only place fonts are measured. Every backend —
the SVG writer, the QImage raster, and the PowerPoint object builder —
consumes the same LabelLayout, so the outputs are identical by
construction rather than by discipline.

Each metadata cell is TWO texts: the key and the value, laid in their
own zones. Zones are shared per column (key zone = widest key in the
column, value zone = widest value), so keys and values line up
vertically; style.key_alignment / value_alignment position each text
inside its zone, and style.key_separator appends label-wide punctuation
to the keys. A custom cell is ONE text spanning the whole cell.

Mandatory: QFont.setPixelSize, never point sizes. A point size renders
1.333x larger on the 96 DPI QImage than in the 72 DPI SVG; pixel sizes
are device-independent (pinned by the renderer-parity test).
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QFont, QFontMetricsF

from .. import defaults
from .spec import CustomCellSpec, LabelSpec


@dataclass(frozen=True, slots=True)
class LaidText:
    """One text with its resolved position (image coordinates)."""

    text: str
    x: float         # left edge
    baseline: float  # QPainter.drawText baseline


@dataclass(frozen=True, slots=True)
class ZoneRect:
    """Axis-aligned box in image coordinates — plain floats, no Qt."""

    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True, slots=True)
class LaidCell:
    """One placed metadata cell: its two resolved texts plus the zone
    boxes they sit in. Painters draw the texts; PowerPoint builds one
    text box per zone so the native object mirrors the burn-in."""

    key: LaidText
    value: LaidText
    key_zone: ZoneRect
    value_zone: ZoneRect


@dataclass(frozen=True, slots=True)
class LaidCustom:
    """One placed custom cell: a single text spanning the whole cell."""

    text: LaidText
    zone: ZoneRect


@dataclass(frozen=True, slots=True)
class LabelLayout:
    """Plain rects and strings — everything a painter needs, no Qt state
    beyond value types, safe to hand across threads."""

    # Plate, in image coordinates.
    x: float
    y: float
    width: float
    height: float
    radius: float
    border_width: float

    # Style, resolved.
    background_color: str    # #RRGGBB / #AARRGGBB
    background_opacity: int  # 0..100
    border_color: str
    font_family: str
    font_pixel_size: int
    font_color: str

    cells: tuple[LaidCell | LaidCustom, ...]

    @property
    def texts(self) -> tuple[LaidText, ...]:
        """Flat paint order — key then value per cell, one per custom."""

        out: list[LaidText] = []
        for cell in self.cells:
            if isinstance(cell, LaidCustom):
                out.append(cell.text)
            else:
                out.append(cell.key)
                out.append(cell.value)
        return tuple(out)


def make_font(layout: LabelLayout) -> QFont:
    """The one QFont construction every backend shares."""

    font = QFont(layout.font_family)
    font.setPixelSize(layout.font_pixel_size)
    return font


def _aligned_x(zone_x: float, zone_w: float, text_w: float, alignment: int) -> float:
    """Left edge of a text laid inside its zone."""

    if alignment == defaults.ALIGN_CENTER:
        return zone_x + (zone_w - text_w) / 2
    if alignment == defaults.ALIGN_RIGHT:
        return zone_x + zone_w - text_w
    return zone_x  # ALIGN_LEFT, and the safe fallback


def build_layout(spec: LabelSpec) -> LabelLayout:
    """Measure the spec's placed cells and put the plate in its corner.

    The user's grid arrangement is honored with empty rows and columns
    trimmed: only rows/columns that hold at least one cell take space,
    and the occupied cells keep their relative positions. Per column,
    the key zone fits the widest key (separator included) and the value
    zone the widest value; a column's width is that pair plus the
    key/value gap — or a wider custom text, which contributes only to
    the column total so a long note never disturbs the zone alignment.
    style.align_columns unifies BOTH zone maxima across columns, so
    every column takes the widest column's width and cells align across
    columns. All dimensional style values scale with image width so the
    label covers the same fraction of a 768 px and a 4395 px image.
    """

    style = spec.style
    scale = style.scale_for(spec.image_width)

    font_px = max(1, round(style.font_size * scale))
    probe = QFont(style.font_family)
    probe.setPixelSize(font_px)
    metrics = QFontMetricsF(probe)

    padding = defaults.CELL_PADDING_PX * scale
    col_gap = defaults.COLUMN_GAP_PX * scale
    row_gap = defaults.ROW_GAP_PX * scale
    kv_gap = defaults.KEY_VALUE_GAP_PX * scale
    separator = defaults.SEPARATOR_SUFFIXES[style.key_separator]

    # Trim: rank only the rows/columns that actually hold cells.
    used_rows = sorted({placed.row for placed in spec.cells})
    used_cols = sorted({placed.column for placed in spec.cells})
    row_rank = {row: i for i, row in enumerate(used_rows)}
    col_rank = {col: i for i, col in enumerate(used_cols)}
    n_rows = max(1, len(used_rows))
    n_cols = max(1, len(used_cols))

    # The separator is part of the key for measurement AND rendering,
    # so the key zone grows to hold it. Custom cells carry no suffix.
    def key_display(cell) -> str:
        return f"{cell.key_text}{separator}"

    key_w = [0.0] * n_cols
    val_w = [0.0] * n_cols
    custom_w = [0.0] * n_cols
    for placed in spec.cells:
        c = col_rank[placed.column]
        if isinstance(placed.cell, CustomCellSpec):
            custom_w[c] = max(
                custom_w[c], metrics.horizontalAdvance(placed.cell.text)
            )
        else:
            key_w[c] = max(
                key_w[c], metrics.horizontalAdvance(key_display(placed.cell))
            )
            val_w[c] = max(
                val_w[c], metrics.horizontalAdvance(placed.cell.value_text)
            )
    if style.align_columns and spec.cells:
        key_w = [max(key_w)] * n_cols
        val_w = [max(val_w)] * n_cols

    # A column is its key/value pair — or a wider custom note, whose
    # width is quarantined to the column total (never the zones).
    if spec.cells:
        col_widths = [
            max(key_w[c] + kv_gap + val_w[c], custom_w[c])
            for c in range(n_cols)
        ]
    else:
        col_widths = [0.0]

    row_height = metrics.height()
    content_width = sum(col_widths) + col_gap * (n_cols - 1)
    content_height = n_rows * row_height + row_gap * (n_rows - 1)
    width = content_width + 2 * padding
    height = content_height + 2 * padding

    margin = style.margin * scale
    if style.position in (defaults.POSITION_UPPER_LEFT, defaults.POSITION_LOWER_LEFT):
        x = margin
    else:
        x = spec.image_width - margin - width
    if style.position in (defaults.POSITION_UPPER_LEFT, defaults.POSITION_UPPER_RIGHT):
        y = margin
    else:
        # bottom_offset is already zero unless a databar exists AND the
        # position is on the bottom edge (LabelSpec.bottom_offset).
        y = spec.image_height - margin - height - spec.bottom_offset

    laid: list[LaidCell | LaidCustom] = []
    for placed in spec.cells:
        r = row_rank[placed.row]
        c = col_rank[placed.column]
        col_x = x + padding + sum(col_widths[:c]) + col_gap * c
        row_top = y + padding + r * (row_height + row_gap)
        baseline = row_top + metrics.ascent()

        if isinstance(placed.cell, CustomCellSpec):
            zone = ZoneRect(col_x, row_top, col_widths[c], row_height)
            laid.append(LaidCustom(
                text=LaidText(placed.cell.text, zone.x, baseline),
                zone=zone,
            ))
            continue

        key_zone = ZoneRect(col_x, row_top, key_w[c], row_height)
        value_zone = ZoneRect(
            col_x + key_w[c] + kv_gap, row_top, val_w[c], row_height
        )
        key_text = key_display(placed.cell)
        key_adv = metrics.horizontalAdvance(key_text)
        val_adv = metrics.horizontalAdvance(placed.cell.value_text)
        laid.append(LaidCell(
            key=LaidText(
                key_text,
                _aligned_x(key_zone.x, key_zone.width, key_adv,
                           style.key_alignment),
                baseline,
            ),
            value=LaidText(
                placed.cell.value_text,
                _aligned_x(value_zone.x, value_zone.width, val_adv,
                           style.value_alignment),
                baseline,
            ),
            key_zone=key_zone,
            value_zone=value_zone,
        ))

    return LabelLayout(
        x=x,
        y=y,
        width=width,
        height=height,
        radius=style.corner_radius * scale,
        border_width=style.border_thickness * scale if style.has_border else 0.0,
        background_color=style.background_color,
        background_opacity=style.background_opacity,
        border_color=style.border_color,
        font_family=style.font_family,
        font_pixel_size=font_px,
        font_color=style.font_color,
        cells=tuple(laid),
    )
