"""FEI XML to a plain nested dict.

Follows ATC Project Explorer's _extract_xml_element, including its
scope-attribute grouping, with the bulk-element strip kept because it is
worth 35x on the parse.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from typing import Any

logger = logging.getLogger(__name__)

# <Image> and <ImageMetadata> hold base64 thumbnails and per-pixel data.
# On the sample PNG they are 99.9% of an 8.4 MB payload — removing them
# takes the document to 9.9 KB and the ElementTree parse from 35 ms to
# under 1 ms. Nothing downstream reads them.
_BULK_ELEMENTS = ("ImageMetadata", "Image")  # longest first, see _strip_element

_METADATA_OPEN = re.compile(rb"<Metadata[\s>]")
_METADATA_CLOSE = b"</Metadata>"


def decode_payload(raw: bytes) -> str:
    """Decode an XML payload, tolerating the non-UTF-8 bytes TFS emits.

    A latin-1 fallback is required rather than decorative: TFS writes the
    micro sign as a bare 0xB5 byte in otherwise-ASCII payloads, which is
    not valid UTF-8 and would otherwise abort the whole parse.
    """

    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    for encoding in ("utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _strip_element(text, name):
    """Remove every <name>...</name> span using index scanning.

    Works on str or bytes; the literals are built to match the input so
    the same logic serves both. Callers strip bytes where possible, since
    doing it before decoding means only the ~10 KB that survives is ever
    turned into a str.

    The obvious implementation is a non-greedy regex, and it is what the
    reference parser uses — but `<Image>.*?</Image>` with DOTALL over the
    8.4 MB sample payload costs 102 ms, which was 89% of the time spent
    reading that PNG. find() is a linear C scan and does the same job in
    a couple of milliseconds.

    The open tag is matched as `<name>` or `<name ...>` so attributes are
    handled, and the character after the name is checked so that <Image>
    cannot match the start of <ImageMetadata>.
    """

    if isinstance(text, bytes):
        open_prefix = b"<" + name
        close_tag = b"</" + name + b">"
        delimiters = (0x3E, 0x20, 0x09, 0x0D, 0x0A, 0x2F)  # > space tab cr lf /
    else:
        open_prefix = f"<{name}"
        close_tag = f"</{name}>"
        delimiters = (">", " ", "\t", "\r", "\n", "/")

    pieces: list = []
    kept_from = 0     # start of the text not yet copied out
    search_from = 0   # where to look for the next open tag

    while True:
        start = text.find(open_prefix, search_from)
        if start == -1:
            break
        after = start + len(open_prefix)
        # Reject <ImageMetadata> when looking for <Image>. Only the search
        # cursor advances here — kept_from must not move, or the skipped
        # span would be dropped from the output.
        if after < len(text) and text[after] not in delimiters:
            search_from = after
            continue
        end = text.find(close_tag, after)
        if end == -1:
            break
        pieces.append(text[kept_from:start])
        kept_from = end + len(close_tag)
        search_from = kept_from

    if not pieces:
        return text
    pieces.append(text[kept_from:])
    return (b"" if isinstance(text, bytes) else "").join(pieces)


def strip_bulk(xml_text: str) -> str:
    for name in _BULK_ELEMENTS:
        xml_text = _strip_element(xml_text, name)
    return xml_text


def strip_bulk_bytes(raw: bytes) -> bytes:
    """Strip the bulk elements before anything is decoded.

    <Image> alone is 99.74% of the sample PNG's 8.4 MB payload, so doing
    this first means decode_payload only ever sees the ~10 KB that
    matters instead of 8.4 million characters.
    """

    for name in _BULK_ELEMENTS:
        raw = _strip_element(raw, name.encode("ascii"))
    return raw


def extract_metadata_element(raw: bytes) -> bytes | None:
    """Slice the <Metadata>...</Metadata> element out of a larger blob."""

    match = _METADATA_OPEN.search(raw)
    if match is None:
        return None
    start = match.start()
    end = raw.rfind(_METADATA_CLOSE)
    if end == -1 or end < start:
        return None
    return raw[start : end + len(_METADATA_CLOSE)]


def _local_name(tag: str) -> str:
    """Drop the {namespace} prefix ElementTree prepends."""

    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _coerce_text(text: str) -> Any:
    stripped = text.strip()
    if not stripped:
        return ""
    try:
        return int(stripped)
    except ValueError:
        pass
    try:
        return float(stripped)
    except ValueError:
        pass
    return stripped


def _element_to_value(element: ET.Element) -> Any:
    """Convert one element to a scalar, an attribute dict, or a subtree."""

    children = list(element)
    attributes = {
        _local_name(key): value for key, value in element.attrib.items()
    }
    text = (element.text or "").strip()

    if not children:
        if attributes:
            # Attribute-style leaf, e.g. CustomProperties entries:
            # {'name': 'Align Angle', 'value': '0.737...', 'type': ...},
            # and PixelSize: {'unit': 'm', '_text': '5.0E-09'}.
            leaf = dict(attributes)
            if text:
                leaf["_text"] = _coerce_text(text)
            return leaf
        return _coerce_text(text)

    result: dict[str, Any] = {}
    for child in children:
        name = _local_name(child.tag)
        value = _element_to_value(child)

        # Repeated siblings distinguished by a scope attribute become a
        # dict keyed on that scope, which is how CustomSection[scope=
        # "Metrics"] reads as ...CustomSection.Metrics rather than an
        # opaque list index.
        scope = child.attrib.get("scope")
        if scope:
            bucket = result.setdefault(name, {})
            if isinstance(bucket, dict):
                bucket[scope] = value
                continue

        if name in result:
            existing = result[name]
            if isinstance(existing, list):
                existing.append(value)
            else:
                result[name] = [existing, value]
        else:
            result[name] = value

    if text:
        result["_text"] = _coerce_text(text)
    if attributes:
        for key, value in attributes.items():
            result.setdefault(key, value)
    return result


def parse_xml(xml_text: str) -> dict[str, Any]:
    """Parse FEI XML into a nested dict. Returns {} on malformed input."""

    if not xml_text or not xml_text.strip():
        return {}
    try:
        root = ET.fromstring(strip_bulk(xml_text))
    except ET.ParseError as exc:
        logger.warning("XML parse failed: %s", exc)
        return {}
    value = _element_to_value(root)
    return value if isinstance(value, dict) else {}


def parse_xml_bytes(raw: bytes) -> dict[str, Any]:
    """Parse a raw XML payload, stripping bulk elements before decoding."""

    element = extract_metadata_element(raw)
    return parse_xml(decode_payload(strip_bulk_bytes(
        element if element is not None else raw
    )))
