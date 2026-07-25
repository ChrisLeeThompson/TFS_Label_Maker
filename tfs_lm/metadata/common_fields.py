"""Which metadata fields every loaded image has in common."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from . import canonical
from .records import ImageMetadata

logger = logging.getLogger(__name__)


class IntersectionAccumulator:
    """Running intersection of field paths across a batch.

    Intersecting as each image arrives keeps this O(total fields) rather
    than holding every image's path set to combine at the end, which
    matters when a DualBeam TIFF alone contributes ~1,660 paths.

    Images carrying no metadata at all are excluded rather than allowed to
    empty the intersection. Strictly, "common to all dropped images" would
    mean one screenshot wipes the tree; excluding it and reporting the
    skip is the more useful reading, and the count is surfaced so the
    behaviour is visible rather than silent.

    Only fields present in every contributing image survive — there is no
    synthesized cross-dialect group and no per-field variance tracking any
    more. The tree is a selector, not a comparator: the user picks fields,
    and each output label reads that field from its own image. What IS
    tracked is which top-level categories fell out of the intersection,
    so the status bar can say why (e.g. one INI-only image hides the
    whole XML category for the batch).
    """

    def __init__(self) -> None:
        self._common: set[str] | None = None
        self._first_values: dict[str, Any] = {}
        self._contributors = 0
        self._skipped: list[Path] = []
        self._category_counts: dict[str, int] = {}

    @property
    def contributors(self) -> int:
        return self._contributors

    @property
    def skipped(self) -> list[Path]:
        return list(self._skipped)

    def add(self, meta: ImageMetadata) -> None:
        if meta.is_empty:
            self._skipped.append(meta.path)
            return

        paths = set(meta.flat)
        self._contributors += 1
        for category in {p.split(".", 1)[0] for p in paths}:
            self._category_counts[category] = (
                self._category_counts.get(category, 0) + 1
            )

        if self._common is None:
            self._common = paths
            self._first_values = dict(meta.flat)
            return

        self._common &= paths

    def common_paths(self) -> set[str]:
        return set(self._common or ())

    def partial_categories(self) -> list[tuple[str, int]]:
        """Categories some contributing images carry and others lack.

        [(category, count), ...] sorted by category — the reason a whole
        top-level group can vanish from the tree, surfaced in the status
        bar instead of failing silently.
        """

        return sorted(
            (category, count)
            for category, count in self._category_counts.items()
            if count < self._contributors
        )

    def representative_values(self) -> dict[str, Any]:
        """First image's values, for the tree and the preview."""

        if not self._common:
            return {}
        return {p: self._first_values[p] for p in self._common if p in self._first_values}


def summarize(
    accumulator: IntersectionAccumulator, total_images: int, stopped: bool
) -> str:
    """Status line for the end of a parse run."""

    common = len(accumulator.common_paths())
    contributors = accumulator.contributors
    skipped = len(accumulator.skipped)
    partial = accumulator.partial_categories()

    if stopped:
        return f"Parsing stopped — {contributors} of {total_images} read"

    if contributors == 0:
        return "No TFS metadata found in the loaded images"

    # Kept terse on purpose: the category note ("ASVXMLMetadata 2/3")
    # must survive the status bar's width budget — the wordier "in 2 of
    # 3 images" phrasing measured 684 px and elided away exactly the
    # explanation it exists to give. The tree's empty-state label
    # carries the full sentence; this line is the compact ledger.
    parts = []
    if common == 0 and partial:
        parts.append("No shared metadata")
    else:
        parts.append(
            f"{common} field{'' if common == 1 else 's'} common to {contributors} image"
            f"{'' if contributors == 1 else 's'}"
        )
    if partial:
        parts.append(", ".join(
            f"{canonical.GROUP_DISPLAY_TITLES.get(cat, cat)} {count}/{contributors}"
            for cat, count in partial
        ))
    if skipped:
        parts.append(
            f"{skipped} skipped (no metadata)"
        )
    return " — ".join(parts)
