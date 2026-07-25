"""Write one label as a standalone SVG, through the shared painter.

The SVG contains just the label (translated to its own origin), sized
as it would be burned into its image — so dropping it onto that image
at native scale in PowerPoint reproduces the watermark exactly.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path

from PySide6.QtCore import QRectF, QSize
from PySide6.QtGui import QPainter
from PySide6.QtSvg import QSvgGenerator

from .layout import build_layout
from .painter import paint_label
from .spec import LabelSpec

logger = logging.getLogger(__name__)


def write_svg(path: Path, spec: LabelSpec) -> None:
    """Render spec's label to path. Raises on I/O or paint failure."""

    layout = build_layout(spec)

    width = max(1, math.ceil(layout.width))
    height = max(1, math.ceil(layout.height))

    generator = QSvgGenerator()
    generator.setFileName(str(path))
    generator.setTitle(path.stem)
    generator.setDescription("TFS Label Maker label")
    generator.setSize(QSize(width, height))
    generator.setViewBox(QRectF(0, 0, width, height))
    # QSvgGenerator defaults to 72 DPI while QImage is 96. Fonts use
    # setPixelSize so glyphs are safe either way, but geometry passed in
    # device-independent units is not — pin the resolution to the raster
    # backend's so the two can never disagree.
    generator.setResolution(96)

    painter = QPainter()
    if not painter.begin(generator):
        raise OSError(f"Could not open {path} for SVG painting")
    try:
        # The layout is in image coordinates; shift the label to the
        # SVG's origin.
        painter.translate(-layout.x, -layout.y)
        paint_label(painter, layout)
    finally:
        painter.end()

    logger.debug("Wrote %s", path.name)
