"""Read TFS metadata out of a TIFF via tifffile."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from . import xml_flatten

logger = logging.getLogger(__name__)

TAG_EXIF = 34665        # IFD pointer — see the note in raw_tag_bytes
TAG_FEI_SFEG = 34680    # base64 <MementoItemCollection> — preserved, not parsed
TAG_FEI_HELIOS = 34682  # INI, pre-parsed by tifffile
TAG_FEI_TITAN = 34683   # FEI XML

# Tags copied byte-for-byte into a watermarked output. 34665 is absent on
# purpose: it is dtype 13 (IFD pointer), so its four bytes are a
# file-relative offset rather than content, and copying them into a
# different file would point at nothing.
#
# 34680 is preserved but no longer decoded for the tree: the user
# reviewed its ~1,200 key/value pairs and judged them not commonly
# useful, so parsing was struck out while the watermark round trip
# still carries the original bytes forward.
PRESERVE_TAGS = (TAG_FEI_SFEG, TAG_FEI_HELIOS, TAG_FEI_TITAN)


def raw_tag_bytes(path: Path, tag) -> bytes | None:
    """Read a tag's on-disk bytes so they can be re-emitted verbatim."""

    offset = getattr(tag, "valueoffset", None)
    count = getattr(tag, "count", None)
    if not offset or not count:
        return None
    try:
        with open(path, "rb") as handle:
            handle.seek(offset)
            return handle.read(count)
    except OSError:
        logger.exception("Could not read raw bytes for tag %s", tag.code)
        return None


def read(path: Path) -> dict[str, Any]:
    """Extract every dialect a TIFF carries.

    Only the IFD is read — tifffile is lazy, so this costs ~2 ms even on
    a 19 MB image, and the pixel data is never touched.
    """

    import tifffile

    out: dict[str, Any] = {
        "sections": {},
        "xml": {},
        "raw_tags": {},
        "width": 0,
        "height": 0,
        "dtype": "",
        "errors": [],
    }

    with tifffile.TiffFile(path) as handle:
        page = handle.pages[0]
        shape = getattr(page, "shape", ())
        if len(shape) >= 2:
            out["height"], out["width"] = int(shape[0]), int(shape[1])
        out["dtype"] = str(getattr(page, "dtype", "") or "")

        tags = page.tags

        helios = tags.get(TAG_FEI_HELIOS)
        if helios is not None and isinstance(helios.value, dict):
            out["sections"] = helios.value

        titan = tags.get(TAG_FEI_TITAN)
        if titan is not None and isinstance(titan.value, str) and titan.value.strip():
            out["xml"] = xml_flatten.parse_xml(titan.value)

        for code in PRESERVE_TAGS:
            tag = tags.get(code)
            if tag is None:
                continue
            raw = raw_tag_bytes(path, tag)
            if raw:
                out["raw_tags"][code] = raw

        # Captured for the export report, since the tag itself cannot be
        # carried across into a new file.
        exif = tags.get(TAG_EXIF)
        if exif is not None and isinstance(exif.value, dict):
            unique_id = exif.value.get("ImageUniqueID")
            if unique_id:
                out["image_unique_id"] = str(unique_id)

    return out
