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
    commonFieldsChanged = Signal()
    checkedFieldsChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._model = DroppedImagesModel(self)

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

    @Property(int, notify=commonFieldsChanged)
    def commonFieldCount(self) -> int:
        # Backed by the tree, not the live accumulator: the tree is
        # GUI-thread state that only changes on parseComplete, so this
        # can never observe a half-built intersection mid-parse.
        return self._tree.field_count

    @Property(int, notify=checkedFieldsChanged)
    def checkedFieldCount(self) -> int:
        return self._tree.checkedCount

    # --- Parsing ---------------------------------------------------------

    def _reparse(self) -> None:
        """Re-read everything.

        The intersection shrinks monotonically as images are added, so
        there is no way to extend a previous result incrementally — a
        field common to the first three images may not survive the fourth.
        Re-reading is also cheap: ~0.9 s for 50 images, on a worker thread.
        """

        self._model.reset_states()
        self._job.parse(self._model.paths())

    def _on_file_parsed(self, path_str: str, ok: bool, reason: str) -> None:
        self._model.set_state(
            Path(path_str), ParseState.OK if ok else ParseState.FAILED, reason
        )

    def _on_parse_complete(self, completed: bool) -> None:
        accumulator = self._job.results.accumulator
        if completed:
            self._tree.populate(
                accumulator.common_paths(),
                accumulator.representative_values(),
            )
        else:
            # A stopped run read only part of the batch. Fields common
            # to that fragment may not be common to the files never
            # reached, and this app never shows a number it cannot
            # stand behind — so the tree empties rather than guesses.
            self._tree.clear_fields()
        self.commonFieldsChanged.emit()
        self.countChanged.emit()  # failureCount may have moved
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

    def common_paths(self) -> set[str]:
        return self._job.results.accumulator.common_paths()

    def representative_values(self) -> dict:
        return self._job.results.accumulator.representative_values()

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
        self.countChanged.emit()
        self.commonFieldsChanged.emit()
        self.statusUpdated.emit("Cleared")

    @Slot(result=list)
    def failures(self) -> list:
        """Pull-style, so the batch signals stay narrow."""

        return [[path, reason] for path, reason in self._model.failures()]

    # --- Python-side API -------------------------------------------------

    def paths(self) -> list[Path]:
        return self._model.paths()
