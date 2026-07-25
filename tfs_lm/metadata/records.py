"""Data structures describing one image's metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Dialect tags, used to explain to the user why a field is or is not
# available across a mixed batch.
DIALECT_INI = "ini"
DIALECT_XML = "xml"


@dataclass(slots=True)
class ImageMetadata:
    """Everything read from one image, in every dialect it carries.

    The dialects are kept separate rather than merged: they use
    different names and units for the same quantities, and merging early
    would lose the information needed to explain a missing field. The
    canonical layer maps across them on top of this.

    Tag 34680 (the base64 MementoItemCollection) is deliberately not a
    dialect any more: the user reviewed its content and struck it out
    as not commonly useful. Its raw bytes still ride along in raw_tags
    so watermarked copies preserve the original file untouched.
    """

    path: Path
    width: int = 0
    height: int = 0
    dtype: str = ""

    # Dialect 1 — INI, from TIFF tag 34682 or a PNG MetadataAsINI chunk.
    # tifffile hands this over already parsed into {section: {key: value}}
    # with typed values; missing values come through as ''.
    sections: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Dialect 2 — FEI XML, from TIFF tag 34683 or a PNG Metadata chunk.
    xml: dict[str, Any] = field(default_factory=dict)

    # Raw tag bytes kept for the watermark round trip, so the output can
    # carry byte-identical FEI tags.
    raw_tags: dict[int, bytes] = field(default_factory=dict)
    # PNG ancillary chunks, same purpose: [(type, payload), ...].
    raw_chunks: list[tuple[bytes, bytes]] = field(default_factory=list)

    # Canonical section name -> the name this image actually uses, e.g.
    # {"Beam*": "EBeam", "Scan*": "EScan", "Detector*": "TLD"}.
    aliases: dict[str, str] = field(default_factory=dict)

    # Dotted path -> value, across every dialect. The tree, the field
    # intersection and the label cells all key off these.
    flat: dict[str, Any] = field(default_factory=dict)

    databar_height: int = 0
    errors: list[str] = field(default_factory=list)

    # From EXIF tag 34665. Captured here because the tag itself cannot be
    # carried into a watermarked copy — it is an IFD pointer, so its bytes
    # are a file-relative offset — and the export report records it
    # instead so the link back to the original survives.
    image_unique_id: str = ""

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def has_ini(self) -> bool:
        return bool(self.sections)

    @property
    def has_xml(self) -> bool:
        return bool(self.xml)

    @property
    def has_databar(self) -> bool:
        return self.databar_height > 0

    @property
    def dialects(self) -> set[str]:
        present = set()
        if self.sections:
            present.add(DIALECT_INI)
        if self.xml:
            present.add(DIALECT_XML)
        return present

    @property
    def is_empty(self) -> bool:
        """No usable metadata at all — a screenshot, or a stripped file."""

        return not (self.sections or self.xml)

    def get(self, dotted_path: str, default: Any = None) -> Any:
        return self.flat.get(dotted_path, default)


@dataclass(slots=True)
class FieldNode:
    """One node in the metadata tree.

    Nodes are built once per batch and handed to the model. `parent` is
    required so QAbstractItemModel.parent() can walk back up.
    """

    key: str
    path: str
    is_leaf: bool = False
    children: list["FieldNode"] = field(default_factory=list)
    parent: "FieldNode | None" = None

    def add(self, child: "FieldNode") -> "FieldNode":
        child.parent = self
        self.children.append(child)
        return child

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()

    def leaves(self):
        for node in self.walk():
            if node.is_leaf:
                yield node
