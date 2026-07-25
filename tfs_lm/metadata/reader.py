"""Front door for metadata reading: dispatch, assemble, flatten."""

from __future__ import annotations

import logging
from pathlib import Path

from . import canonical, png_reader, tiff_reader
from .records import ImageMetadata

logger = logging.getLogger(__name__)

_TIFF_MAGIC = (b"II*\x00", b"MM\x00*")
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8"


def sniff_format(path: Path) -> str:
    """Identify a file by its bytes, not its extension.

    FEI software has been known to write JPEG data under a .png name, so
    trusting the suffix would send the wrong reader at the file.
    """

    try:
        with open(path, "rb") as handle:
            head = handle.read(8)
    except OSError:
        return "unknown"

    if head.startswith(_PNG_MAGIC):
        return "png"
    if head.startswith(_TIFF_MAGIC):
        return "tiff"
    if head.startswith(_JPEG_MAGIC):
        return "jpeg"
    return "unknown"


def read_metadata(path: Path) -> ImageMetadata:
    """Read every dialect an image carries and flatten it.

    Never raises for a merely unreadable image: a file with no TFS
    metadata comes back as an ImageMetadata whose is_empty is True, so a
    batch can report it and carry on rather than aborting.
    """

    path = Path(path)
    meta = ImageMetadata(path=path)
    fmt = sniff_format(path)

    try:
        if fmt == "tiff":
            raw = tiff_reader.read(path)
        elif fmt == "png":
            raw = png_reader.read(path)
        else:
            meta.errors.append(f"unsupported or unrecognised format ({fmt})")
            return meta
    except Exception as exc:  # noqa: BLE001 - reported per file, never fatal
        logger.exception("Failed to read metadata from %r", str(path))
        meta.errors.append(str(exc))
        return meta

    meta.width = raw.get("width", 0)
    meta.height = raw.get("height", 0)
    meta.dtype = raw.get("dtype", "")
    meta.sections = raw.get("sections", {}) or {}
    meta.xml = raw.get("xml", {}) or {}
    meta.raw_tags = raw.get("raw_tags", {}) or {}
    meta.raw_chunks = raw.get("raw_chunks", []) or []
    meta.errors.extend(raw.get("errors", []))

    unique_id = raw.get("image_unique_id")
    if unique_id:
        meta.image_unique_id = unique_id  # type: ignore[attr-defined]

    meta.aliases = canonical.discover_aliases(meta.sections)
    meta.databar_height = canonical.databar_height(
        meta.sections, meta.width, meta.height
    )

    flat: dict = {}
    sections_flat = canonical.flatten_sections(meta.sections, meta.aliases)
    flat.update(sections_flat)

    xml_flat: dict = {}
    canonical.flatten(meta.xml, canonical.GROUP_XML, xml_flat)
    flat.update(xml_flat)

    # No synthesized Common.* layer: the tree shows raw dialect paths
    # only, per the user's decision. Cross-image commonality still works
    # within the INI dialect because flatten_sections substituted the
    # ActiveBeam/ActiveScan/ActiveDetector aliases above.
    meta.flat = flat

    if meta.is_empty:
        meta.errors.append("no TFS metadata found")

    logger.debug(
        "Read %r: %d flat paths, dialects=%s, databar=%d",
        path.name,
        len(flat),
        sorted(meta.dialects),
        meta.databar_height,
    )
    return meta
