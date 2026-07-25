"""Burn a label into a QImage — the raster twin of svg_writer.

Same layout, same paint call. If this file ever draws anything itself
instead of delegating to painter.paint_label, the SVG and the watermark
stop being identical by construction.
"""

from __future__ import annotations

import logging

from PySide6.QtGui import QImage, QPainter

from .layout import build_layout
from .painter import paint_label
from .spec import LabelSpec

logger = logging.getLogger(__name__)


def burn_label(image: QImage, spec: LabelSpec) -> None:
    """Paint spec's label onto image, in place.

    The spec's image_width/height must describe this image — the layout
    positions the plate in image coordinates.
    """

    layout = build_layout(spec)

    painter = QPainter()
    if not painter.begin(image):
        raise OSError("QPainter could not open the image for the label burn")
    try:
        paint_label(painter, layout)
    finally:
        painter.end()
