"""Owns the loaded image set and, from M5, the parse job that reads it."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Property, QObject, Signal, Slot  # noqa: F401

from .. import defaults
from ..metadata import common_fields
from ..metadata.parse_job import ParseJob
from ..metadata.tree_model import MetadataFilterProxy, MetadataTreeModel
from . import discovery
from .file_list_model import DroppedImagesModel, ParseState

logger = logging.getLogger(__name__)


class ImageSetController(QObject):
    """Validates incoming URLs and holds the resulting image list.

    Both entry points — dropping on the catbug and the Load dialog — land
    in addUrls, so validation, de-duplication and reporting cannot drift
    between them.
    """

    countChanged = Signal()
    statusUpdated = Signal(str)
    progressUpdated = Signal(int, int)
    filesRejected = Signal(list)  # [[display, reason], ...]
    isParsingChanged = Signal()
    fieldsChanged = Signal()
    checkedFieldsChanged = Signal()
    currentImageChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._model = DroppedImagesModel(self)
        # Which image's values the tree and the label preview show.
        # -1 until a batch lands; clamped on every parse completion.
        self._current_index = -1
        # True while the tree is empty because the user stopped a
        # parse — the empty-state label then explains the stop instead
        # of falsely reporting the images unreadable.
        self._last_parse_stopped = False

        # Parented here so their lifetime follows the controller — QML
        # only ever borrows them through constant properties.
        self._tree = MetadataTreeModel(self)
        self._tree_proxy = MetadataFilterProxy(self)
        self._tree_proxy.setSourceModel(self._tree)
        self._tree.checkedChanged.connect(self.checkedFieldsChanged)
        self._tree.capacityReached.connect(self._on_capacity_reached)

        self._job = ParseJob(self)
        self._job.statusUpdated.connect(self.statusUpdated)
        self._job.progressUpdated.connect(self.progressUpdated)
        self._job.isRunningChanged.connect(self.isParsingChanged)
        self._job.fileParsed.connect(self._on_file_parsed)
        self._job.parseComplete.connect(self._on_parse_complete)

    # --- Properties ------------------------------------------------------

    @Property(QObject, constant=True)
    def fileModel(self) -> DroppedImagesModel:
        return self._model

    @Property(int, notify=countChanged)
    def count(self) -> int:
        return self._model.rowCount()

    @Property(int, notify=countChanged)
    def failureCount(self) -> int:
        return self._model.count_in_state(ParseState.FAILED)

    @Property(bool, notify=isParsingChanged)
    def isParsing(self) -> bool:
        return self._job.isRunning

    @Property(QObject, constant=True)
    def fieldsModel(self) -> MetadataTreeModel:
        """The source model — check state is mutated here, by path."""

        return self._tree

    @Property(QObject, constant=True)
    def treeModel(self) -> MetadataFilterProxy:
        """What the TreeView actually displays: the search proxy."""

        return self._tree_proxy

    @Property(int, notify=fieldsChanged)
    def fieldCount(self) -> int:
        # The batch union's leaf count. Backed by the tree, not the
        # live accumulator: the tree is GUI-thread state that only
        # changes on parseComplete, so this can never observe a
        # half-built union mid-parse.
        return self._tree.field_count

    @Property(int, notify=checkedFieldsChanged)
    def checkedFieldCount(self) -> int:
        return self._tree.checkedCount

    @Property(int, notify=currentImageChanged)
    def currentImageIndex(self) -> int:
        return self._current_index

    @Property(str, notify=currentImageChanged)
    def currentImageName(self) -> str:
        paths = self._model.paths()
        if 0 <= self._current_index < len(paths):
            return paths[self._current_index].name
        return ""

    @Property(bool, notify=fieldsChanged)
    def lastParseStopped(self) -> bool:
        # Rides fieldsChanged: the flag only ever flips together with
        # the tree contents it explains.
        return self._last_parse_stopped

    # --- Parsing ---------------------------------------------------------

    def _reparse(self) -> None:
        """Re-read everything.

        A union COULD grow incrementally on add, but whole-batch
        re-parse stays by decision: removal still needs a full recount
        (the union shrinks when the only image carrying a field
        leaves), the per-image metadata dict must drop removed files
        anyway, and re-reading is measured-cheap: ~0.9 s for 50 images,
        on a worker thread.
        """

        self._model.reset_states()
        self._job.parse(self._model.paths())

    def _on_file_parsed(self, path_str: str, ok: bool, reason: str) -> None:
        self._model.set_state(
            Path(path_str), ParseState.OK if ok else ParseState.FAILED, reason
        )

    def _on_parse_complete(self, completed: bool) -> None:
        accumulator = self._job.results.accumulator
        # Preserve the browsing position across an additive re-parse;
        # clamp covers removals and the first batch — in both branches:
        # a stopped run also re-announces the index below, and QML must
        # never see -1 (or an index past the end) beside a populated
        # file list. Until this sat outside the if, stopping a first
        # parse left the nav showing "0 / 30" with a blank filename.
        count = self.count
        self._current_index = (
            max(0, min(count - 1, self._current_index)) if count else -1
        )
        if completed:
            self._last_parse_stopped = False
            self._tree.populate(
                accumulator.union_paths(),
                self._current_flat(),
                presence=accumulator.path_counts(),
                contributors=accumulator.contributors,
            )
        else:
            # A stopped run read only part of the batch. A fragment's
            # union is not the batch's union, and this app never shows
            # a number it cannot stand behind — so the tree empties
            # rather than guesses. The flag lets the tree's empty-state
            # label say "stopped" instead of falsely claiming the
            # images carried no readable metadata.
            self._last_parse_stopped = True
            self._tree.clear_fields()
        self.fieldsChanged.emit()
        self.countChanged.emit()  # failureCount may have moved
        self.currentImageChanged.emit()
        self.statusUpdated.emit(
            common_fields.summarize(accumulator, self.count, not completed)
        )

    def _on_capacity_reached(self) -> None:
        self.statusUpdated.emit(defaults.STATUS_LABEL_FULL)

    @Slot()
    def stopParsing(self) -> None:
        self._job.stop()

    def wait_for_stop(self) -> bool:
        return self._job.wait_for_stop()

    # --- Metadata access -------------------------------------------------

    def metadata_for(self, path: Path):
        return self._job.results.metadata.get(path)

    def _current_flat(self) -> dict:
        """The current image's flat path->value dict; {} when there is
        no current image or it parsed empty/failed — every row then
        honestly dims."""

        paths = self._model.paths()
        if not (0 <= self._current_index < len(paths)):
            return {}
        meta = self.metadata_for(paths[self._current_index])
        return meta.flat if meta is not None else {}

    # --- Image cycling ---------------------------------------------------

    @Slot()
    def nextImage(self) -> None:
        self._cycle_to(self._current_index + 1)

    @Slot()
    def previousImage(self) -> None:
        self._cycle_to(self._current_index - 1)

    @Slot(int)
    def setCurrentImage(self, index: int) -> None:
        self._cycle_to(index)

    def _cycle_to(self, index: int) -> None:
        """Move the viewport to another image. Clamped, never wrapped.

        Refused while parsing — a thread-safety guard, not UX: the
        worker is mutating results.metadata mid-parse, and
        _current_flat must not read it mid-write. The QML side also
        hides the controls, but only this guard is load-bearing.
        """

        if self.isParsing:
            return
        count = self.count
        if count == 0:
            return
        index = max(0, min(count - 1, int(index)))
        if index == self._current_index:
            return
        self._current_index = index
        # Tree first, then announce: LabelController._sync_cells reads
        # tree.display_value inside the currentImageChanged handler.
        self._tree.set_current_image(self._current_flat())
        if self._tree_proxy.searchText:
            # Qt's re-run of a custom filterAcceptsRow on role-filtered
            # dataChanged is version-subtle; re-filter explicitly so a
            # live search tracks the new image's values.
            self._tree_proxy.invalidateRowsFilter()
        self.currentImageChanged.emit()

    # --- Slots -----------------------------------------------------------

    @Slot(list)
    def addUrls(self, urls: list) -> None:
        """Accept URL strings from a drop or the file dialog."""

        if not urls:
            return

        result = discovery.resolve_urls(
            [str(url) for url in urls], already_loaded=self._model.path_set()
        )

        if result.accepted:
            self._model.add_paths(result.accepted)
            self.countChanged.emit()

        for display, reason in result.rejected:
            logger.info("Rejected %r: %s", display, reason)
        if result.rejected:
            self.filesRejected.emit(
                [[display, reason] for display, reason in result.rejected]
            )

        self.statusUpdated.emit(discovery.summarize(result, self.count))

        if result.accepted:
            self._reparse()

    @Slot(int)
    def removeAt(self, index: int) -> None:
        if self._model.remove_at(index):
            self.countChanged.emit()
            self._reparse()

    @Slot()
    def clear(self) -> None:
        if self.count == 0:
            return
        self._job.stop()
        self._model.clear()
        self._job.results.clear()
        self._tree.clear_fields()
        self._current_index = -1
        self._last_parse_stopped = False
        self.countChanged.emit()
        self.fieldsChanged.emit()
        self.currentImageChanged.emit()
        self.statusUpdated.emit("Cleared")

    @Slot(result=list)
    def failures(self) -> list:
        """Pull-style, so the batch signals stay narrow."""

        return [[path, reason] for path, reason in self._model.failures()]

    # --- Python-side API -------------------------------------------------

    def paths(self) -> list[Path]:
        return self._model.paths()
