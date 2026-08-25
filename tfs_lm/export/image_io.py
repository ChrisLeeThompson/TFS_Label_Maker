"""Read source pixels, burn the label, write watermarked copies.

The fidelity contract, proven empirically against the sample files and
hardened by adversarial review:

- TIFF: FEI tags 34680/34682/34683 are re-emitted with their source
  dtype (ASCII in every observed file) and raw bytes, and round-trip
  byte-identically. The source dtype matters: writing them as UNDEFINED
  also round-trips the bytes, but tifffile then returns bytes instead
  of str on re-read and our own XML parse goes empty. software=False,
  description=None, metadata=None keep tags 305/270 out — the sources
  carry neither, so adding one would already break fidelity. tifffile
  hardcodes default XResolution/YResolution/ResolutionUnit even when no
  resolution is passed (verified in its source), so when the SOURCE has
  no resolution tags the defaults are stripped from the written IFD.
- PNG: the output's ancillary chunks are exactly the source's preserved
  set (PRESERVE_CHUNKS), respliced as raw bytes after IHDR. Everything
  ancillary that Qt's encoder emits is dropped: Qt re-encodes loaded
  text chunks (the 8.4 MB Metadata came back as a 5.8 MB iTXt copy)
  and invents an iCCP that the spec forbids next to the original sRGB.
- Pixels: output is 8-bit RGB (per the plan). 16-bit sources scale by
  dtype max (>> 8) on both formats — Qt's own Grayscale16 conversion
  rounds (v*255/65535), which differs by one level on a quarter of the
  range, so PNG pixels are converted through the same numpy path as
  TIFF for one batch-consistent policy.
- Dispatch is by magic bytes (sniff_format), not suffix — FEI software
  has been known to write one format under the other's name, and the
  reader already distrusts suffixes for exactly that reason.
- Originals are never modified; everything lands in the run directory.
"""

from __future__ import annotations

import logging
import struct
import zlib
from pathlib import Path

import numpy as np
from PySide6.QtGui import QImage

from ..label.raster import burn_label
from ..label.spec import LabelSpec
from ..metadata import png_reader
from ..metadata.reader import sniff_format
from ..metadata.tiff_reader import PRESERVE_TAGS, raw_tag_bytes

logger = logging.getLogger(__name__)

_PNG_SIG = b"\x89PNG\r\n\x1a\n"

# Chunks a valid PNG cannot lose. Everything else in Qt's output is
# ancillary and yields to the source's preserved set.
_CRITICAL_CHUNKS = frozenset({b"IHDR", b"PLTE", b"IDAT", b"IEND"})

_RESOLUTION_TAGS = {282, 283, 296}


# --- Pixel conversion -----------------------------------------------------


def _to_rgb8(gray: np.ndarray) -> np.ndarray:
    """Grayscale (uint8/uint16) -> contiguous HxWx3 uint8.

    uint16 scales by dtype max (>> 8): deterministic and batch-
    consistent — per-image autoscale was considered and rejected, and a
    test pins this policy against the real 16-bit samples.
    """

    if gray.ndim != 2:
        raise ValueError(f"expected a 2-D grayscale image, got shape {gray.shape}")
    if gray.dtype == np.uint16:
        gray = (gray >> 8).astype(np.uint8)
    elif gray.dtype != np.uint8:
        raise ValueError(f"unsupported pixel dtype {gray.dtype}")
    return np.ascontiguousarray(np.stack([gray, gray, gray], axis=-1))


# --- TIFF -----------------------------------------------------------------


def _strip_first_ifd_tags(path: Path, codes: set[int]) -> None:
    """Remove entries from a classic TIFF's first IFD, in place.

    tifffile emits default resolution tags unconditionally; a copy of a
    source that had none must not invent them. Entry removal shifts the
    remaining records up — the freed bytes (and the out-of-line RATIONAL
    values they pointed at) become dead space no reader ever visits.
    """

    with open(path, "r+b") as handle:
        header = handle.read(8)
        if header[:2] not in (b"II", b"MM"):
            raise ValueError(f"{path.name} is not a TIFF")
        endian = "<" if header[:2] == b"II" else ">"
        (magic,) = struct.unpack(endian + "H", header[2:4])
        if magic != 42:
            # BigTIFF — tifffile only writes it for >4 GB outputs, which
            # this app never produces; leave it untouched rather than
            # guessing at the 8-byte layout.
            logger.warning("%s: BigTIFF output, default resolution tags kept",
                           path.name)
            return
        (ifd_offset,) = struct.unpack(endian + "I", header[4:8])

        handle.seek(ifd_offset)
        (count,) = struct.unpack(endian + "H", handle.read(2))
        entries = [handle.read(12) for _ in range(count)]
        next_ifd = handle.read(4)

        kept = [
            entry for entry in entries
            if struct.unpack(endian + "H", entry[:2])[0] not in codes
        ]
        if len(kept) == len(entries):
            return

        handle.seek(ifd_offset)
        handle.write(struct.pack(endian + "H", len(kept)))
        for entry in kept:
            handle.write(entry)
        handle.write(next_ifd)


def watermark_tiff(source: Path, dest: Path, spec: LabelSpec) -> None:
    """Burn spec's label into a copy of source, preserving FEI tags."""

    import tifffile

    with tifffile.TiffFile(source) as handle:
        page = handle.pages[0]
        gray = page.asarray()

        extratags = []
        for code in PRESERVE_TAGS:
            tag = page.tags.get(code)
            if tag is None:
                continue
            raw = raw_tag_bytes(source, tag)
            if raw:
                # (code, dtype, count, value, writeonce) — source dtype
                # and raw bytes, so the written tag is the original.
                extratags.append((code, int(tag.dtype), len(raw), raw, True))

        kwargs = {}
        xres = page.tags.get(282)
        yres = page.tags.get(283)
        unit = page.tags.get(296)
        if xres is not None and yres is not None:
            # Exact (numerator, denominator) tuples — never floats,
            # which could re-rationalize differently.
            kwargs["resolution"] = (xres.value, yres.value)
            if unit is not None:
                kwargs["resolutionunit"] = int(unit.value)

    rgb = _to_rgb8(gray)
    height, width = rgb.shape[:2]
    # Zero-copy wrap: the QImage borrows rgb's buffer, so the paint
    # lands directly in the array we hand to tifffile. rgb stays
    # referenced for the QImage's whole life by construction.
    image = QImage(
        rgb.data, width, height, rgb.strides[0], QImage.Format.Format_RGB888
    )
    burn_label(image, spec)

    with tifffile.TiffWriter(dest) as writer:
        writer.write(
            rgb,
            photometric="rgb",
            software=False,      # suppresses tag 305
            description=None,
            metadata=None,       # Required: else tifffile writes a JSON tag 270
            extratags=extratags,
            **kwargs,
        )

    if "resolution" not in kwargs:
        _strip_first_ifd_tags(dest, _RESOLUTION_TAGS)


# --- PNG ------------------------------------------------------------------


def _make_chunk(ctype: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + ctype
        + payload
        + struct.pack(">I", zlib.crc32(ctype + payload) & 0xFFFFFFFF)
    )


def _walk_chunks(raw: bytes):
    """Yield (type, whole_chunk_bytes) for a well-formed PNG."""

    offset = 8
    while offset + 8 <= len(raw):
        (length,) = struct.unpack(">I", raw[offset:offset + 4])
        ctype = raw[offset + 4:offset + 8]
        end = offset + 8 + length + 4
        if end > len(raw):
            raise ValueError("truncated PNG chunk")
        yield ctype, raw[offset:end]
        if ctype == b"IEND":
            return
        offset = end


def _rebuild_with_chunks(dest: Path, extra: list[tuple[bytes, bytes]]) -> None:
    """Make dest's ancillary content exactly `extra`.

    Everything non-critical that Qt's encoder wrote is dropped — its
    pHYs, its iCCP, and its re-encodings of any text chunks it loaded
    from the source — and the preserved originals are inserted after
    IHDR, byte for byte. "The original's wins" as a structural fact.
    """

    raw = dest.read_bytes()
    if raw[:8] != _PNG_SIG:
        raise ValueError(f"{dest.name} is not a PNG")

    out = [_PNG_SIG]
    for ctype, blob in _walk_chunks(raw):
        if ctype == b"IHDR":
            out.append(blob)
            out.extend(_make_chunk(t, payload) for t, payload in extra)
        elif ctype in _CRITICAL_CHUNKS:
            out.append(blob)
        # else: Qt-authored ancillary chunk — dropped.
    dest.write_bytes(b"".join(out))


def _load_png_rgb8(source: Path) -> tuple[QImage, np.ndarray | None]:
    """Decode a PNG to RGB888 using the shared conversion policy.

    16-bit grayscale goes through the same numpy >>8 as the TIFF path —
    Qt's own conversion rounds (v*255/65535), one level off on a
    quarter of the range, which would break batch consistency. The
    returned array (when not None) backs the QImage and must outlive it.
    """

    loaded = QImage(str(source))
    if loaded.isNull():
        raise OSError(f"Qt could not decode {source.name}")

    if loaded.format() == QImage.Format.Format_Grayscale16:
        height, width = loaded.height(), loaded.width()
        bpl = loaded.bytesPerLine()
        rows = np.frombuffer(loaded.constBits(), dtype=np.uint8).reshape(height, bpl)
        gray = rows[:, : width * 2].copy().view(np.uint16).reshape(height, width)
        rgb = _to_rgb8(gray)
        image = QImage(
            rgb.data, width, height, rgb.strides[0], QImage.Format.Format_RGB888
        )
        return image, rgb

    return loaded.convertToFormat(QImage.Format.Format_RGB888), None


def watermark_png(source: Path, dest: Path, spec: LabelSpec) -> None:
    """Burn spec's label into a copy of source, re-splicing the
    original's ancillary chunks (including the 8 MB Metadata tEXt)."""

    image, backing = _load_png_rgb8(source)

    burn_label(image, spec)

    if not image.save(str(dest), "PNG"):
        raise OSError(f"Could not write {dest.name}")
    del backing  # keep the numpy buffer alive through save, then release

    chunks, _ = png_reader.read_chunks(source)
    preserved = [
        (ctype, payload)
        for ctype, payload in chunks
        if ctype in png_reader.PRESERVE_CHUNKS
    ]
    _rebuild_with_chunks(dest, preserved)


# --- Dispatch -------------------------------------------------------------


def write_watermark(source: Path, dest: Path, spec: LabelSpec) -> None:
    """Content-dispatched watermark write. Raises on any failure.

    Sniffed by magic bytes, matching the reader: a TIFF hiding under a
    .png name parses fine at load time, so it must also watermark fine
    (the copy keeps the source's name, lie included).
    """

    fmt = sniff_format(source)
    if fmt == "tiff":
        watermark_tiff(source, dest, spec)
    elif fmt == "png":
        watermark_png(source, dest, spec)
    else:
        raise ValueError(f"unsupported source format: {source.name}")
