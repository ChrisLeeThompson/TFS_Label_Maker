"""Read TFS metadata out of a PNG by walking its chunks."""

from __future__ import annotations

import logging
import struct
from pathlib import Path
from typing import Any

from . import ini_parse, xml_flatten

logger = logging.getLogger(__name__)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

# Stop as soon as pixel data starts. Every FEI text chunk precedes IDAT,
# so on the 9.1 MB sample this reads 8.4 MB instead of the whole file and
# takes ~1 ms rather than ~88 ms for a whole-file scan. It also yields the
# chunk keyword, which a byte-search for "<Metadata" throws away — and
# that keyword is the only thing distinguishing the XML payload from the
# INI one.
_STOP_CHUNKS = (b"IDAT", b"IEND")

KEYWORD_XML = b"Metadata"
KEYWORD_INI = b"MetadataAsINI"

# Ancillary chunks worth carrying into a watermarked copy. Pillow's
# PngInfo drops these; raw splicing keeps them.
PRESERVE_CHUNKS = frozenset({b"sRGB", b"gAMA", b"pHYs", b"iCCP", b"cHRM", b"tEXt",
                             b"iTXt", b"zTXt", b"tIME"})


def is_png(path: Path) -> bool:
    try:
        with open(path, "rb") as handle:
            return handle.read(8) == PNG_SIGNATURE
    except OSError:
        return False


def read_chunks(path: Path) -> tuple[list[tuple[bytes, bytes]], tuple[int, int, int]]:
    """Chunks before the first IDAT, plus (width, height, bit_depth)."""

    chunks: list[tuple[bytes, bytes]] = []
    dimensions = (0, 0, 0)

    with open(path, "rb") as handle:
        if handle.read(8) != PNG_SIGNATURE:
            raise ValueError("not a PNG file")

        while True:
            header = handle.read(8)
            if len(header) < 8:
                break
            length = struct.unpack(">I", header[:4])[0]
            chunk_type = header[4:8]

            if chunk_type in _STOP_CHUNKS:
                break

            payload = handle.read(length)
            handle.read(4)  # CRC

            if chunk_type == b"IHDR" and len(payload) >= 10:
                width, height = struct.unpack(">II", payload[:8])
                dimensions = (width, height, payload[8])

            chunks.append((chunk_type, payload))

    return chunks, dimensions


def _split_text_chunk(payload: bytes) -> tuple[bytes, bytes]:
    keyword, _, value = payload.partition(b"\x00")
    return keyword, value


def read(path: Path) -> dict[str, Any]:
    """Extract every dialect a PNG carries.

    Returns keys: sections, xml, raw_chunks, width, height, dtype,
    errors.
    """

    out: dict[str, Any] = {
        "sections": {},
        "xml": {},
        "raw_chunks": [],
        "width": 0,
        "height": 0,
        "dtype": "",
        "errors": [],
    }

    chunks, (width, height, bit_depth) = read_chunks(path)
    out["width"] = width
    out["height"] = height
    out["dtype"] = f"uint{bit_depth}" if bit_depth else ""
    out["raw_chunks"] = [
        (chunk_type, payload)
        for chunk_type, payload in chunks
        if chunk_type in PRESERVE_CHUNKS
    ]

    for chunk_type, payload in chunks:
        if chunk_type != b"tEXt":
            continue
        keyword, value = _split_text_chunk(payload)

        if keyword == KEYWORD_XML and value:
            out["xml"] = xml_flatten.parse_xml_bytes(value)
        elif keyword == KEYWORD_INI and value:
            # Empty on the sample image, but TFS clearly intends to fill
            # it, so handle it rather than assume it stays empty.
            out["sections"] = ini_parse.parse_ini(
                xml_flatten.decode_payload(value)
            )
        # Other text chunks (e.g. a base64 MementoItemCollection riding
        # in one, or the sample's hex-string '34665' chunk) are left
        # unparsed on purpose — the user reviewed the Memento data and
        # struck it out as not commonly useful.

    return out
