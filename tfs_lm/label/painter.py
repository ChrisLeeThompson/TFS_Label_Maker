"""The single source of truth for how a label looks.

Every backend paints by calling paint_label with an already-measured
LabelLayout — the SVG writer, the M9 raster burn-in and the M10 preview
provider must never draw a plate or a glyph themselves.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen

from .layout import LabelLayout, make_font


def paint_label(painter: QPainter, layout: LabelLayout) -> None:
    """Draw the plate, border and cell texts of one label."""

    painter.save()
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        plate = QRectF(layout.x, layout.y, layout.width, layout.height)

        background = QColor(layout.background_color)
        background.setAlphaF(
            background.alphaF() * (layout.background_opacity / 100.0)
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        painter.drawRoundedRect(plate, layout.radius, layout.radius)

        if layout.border_width > 0:
            pen = QPen(QColor(layout.border_color))
            pen.setWidthF(layout.border_width)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            # Inset by half the pen so the stroke stays inside the
            # plate instead of straddling the image edge at the margins.
            inset = layout.border_width / 2
            painter.drawRoundedRect(
                plate.adjusted(inset, inset, -inset, -inset),
                max(0.0, layout.radius - inset),
                max(0.0, layout.radius - inset),
            )

        painter.setFont(make_font(layout))
        painter.setPen(QColor(layout.font_color))
        for laid in layout.texts:
            painter.drawText(QPointF(laid.x, laid.baseline), laid.text)
    finally:
        painter.restore()
