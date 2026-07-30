"""Every metadata field found anywhere in the loaded batch."""

from __future__ import annotations

import logging
from pathlib import Path

from . import canonical
from .records import ImageMetadata

logger = logging.getLogger(__name__)


class UnionAccumulator:
    """Union of field paths across a batch, with per-path presence counts.

    Counting as each image arrives keeps this O(union) — one int per
    distinct path, never a retained per-image path set — which matters
    when a DualBeam TIFF alone contributes hundreds of paths (measured
    on the sample batch: 11 TIFFs, union 413 vs intersection 171).

    Images carrying no metadata at all are excluded and reported. A
    union cannot be emptied by a screenshot the way the old intersection
    could, but excluding it keeps ``contributors`` honest — it is the
    "m" in the tree's "n/m" presence badges — and surfaces the skip
    count instead of silently counting an image that offered nothing.

    The tree remains a selector, not a comparator: the union plus
    per-path counts exist so PARTIAL fields (present in only some
    images) are selectable and badged "n/m" — presence is the only
    cross-image fact tracked. There is no value comparison and no
    per-field "varies" state. Which top-level categories fell out of
    full presence is still tracked so the status bar can say why a
    group is partial (e.g. one INI-only image against an XML batch).
    """

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}
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
        for path in paths:
            self._counts[path] = self._counts.get(path, 0) + 1

    def union_paths(self) -> set[str]:
        return set(self._counts)

    def path_counts(self) -> dict[str, int]:
        """path -> number of contributing images carrying it."""

        return dict(self._counts)

    def partial_categories(self) -> list[tuple[str, int]]:
        """Categories some contributing images carry and others lack.

        [(category, count), ...] sorted by category — the reason a whole
        top-level group shows partial badges, surfaced in the status
        bar instead of left for the user to infer field by field.
        """

        return sorted(
            (category, count)
            for category, count in self._category_counts.items()
            if count < self._contributors
        )


def summarize(
    accumulator: UnionAccumulator, total_images: int, stopped: bool
) -> str:
    """Status line for the end of a parse run."""

    total = len(accumulator.union_paths())
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
    parts = [
        f"{total} field{'' if total == 1 else 's'} across {contributors} image"
        f"{'' if contributors == 1 else 's'}"
    ]
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
