"""Owns the PowerPoint settings and the send job."""

from __future__ import annotations

import logging
import sys
import threading
from datetime import datetime

from PySide6.QtCore import Property, QObject, QSettings, Signal

from .. import defaults
from ..export.controller import resolve_cell
from ..jobs.base import BackgroundJob
from ..label.spec import CellSpec, CustomCellSpec, LabelSpec, PlacedCell
from ..metadata import canonical
from . import worker as worker_module
from .worker import PptItem, PptSendResults, PptSendWorker, PptSettings

logger = logging.getLogger(__name__)

# Sorted last, in load order, when an image has no parseable timestamp.
_NO_TIMESTAMP = datetime.min


def _key(name: str) -> str:
    return defaults.SCHEMA_PREFIX + name


def build_ppt_items(images, label, settings, add_label_object: bool) -> list[PptItem]:
    """One PptItem per sendable image, in chronological order.

    Built from the live models rather than ExportTasks so it serves both
    start() branches: the normal one (after the export) and the
    image-only one (no metadata selected, no export at all).

    The picture is always the ORIGINAL source. The notes always carry
    the filename plus the selected metadata, so the values survive even
    when the label object is off or the styling is not wanted.
    """

    placements = label.matrix.placed_cells()
    style = settings.label_style()
    policy = settings.missingFieldPolicy

    items: list[tuple[bool, datetime, int, PptItem]] = []
    for order, source in enumerate(images.paths()):
        meta = images.metadata_for(source)
        if meta is None or meta.is_empty:
            continue

        # This image's values for the arranged cells, formatted exactly
        # as the label would show them — including the missing-field
        # policy: an absent path is dropped (Omit) or dashed (Dash) in
        # the notes and the label object alike. Custom cells are
        # literal — the same text on every image, no per-image
        # resolution. Notes are the data-recovery channel: under Omit
        # a fabricated dash for a field the image never had would be a
        # lie, so the entry is simply not written.
        valued = []
        for row, column, cell in placements:
            if isinstance(cell, CustomCellSpec):
                valued.append((row, column, cell, cell.text))
                continue
            value = resolve_cell(meta, cell.path, policy)
            if value is not None:
                valued.append((row, column, cell, value))

        notes = source.name
        if valued:
            # Custom text appears bare at its grid position; metadata
            # keeps the conventional "key: value" REGARDLESS of the
            # label's separator setting — notes are the data-recovery
            # channel, not the styled label.
            notes += "\n" + ", ".join(
                value if isinstance(cell, CustomCellSpec)
                else f"{cell.key_text}: {value}"
                for _, _, cell, value in valued
            )

        spec = None
        if add_label_object and valued:
            spec = LabelSpec(
                cells=tuple(
                    PlacedCell(
                        cell=cell if isinstance(cell, CustomCellSpec)
                        else CellSpec(
                            path=cell.path,
                            key_text=cell.key_text,
                            value_text=value,
                        ),
                        row=row,
                        column=column,
                    )
                    for row, column, cell, value in valued
                ),
                style=style,
                image_width=meta.width,
                image_height=meta.height,
                databar_height=meta.databar_height,
            )

        acquired = canonical.acquisition_datetime(meta)
        items.append(
            (
                acquired is None,          # untimed images sort last
                acquired or _NO_TIMESTAMP,  # then earliest first
                order,                      # ties keep load order
                PptItem(source=source, notes=notes, label_spec=spec),
            )
        )

    # Earliest first, so the deck reads earliest -> latest top to bottom
    # (slides are inserted in this order). Images acquired at the same
    # instant, and images with no timestamp at all, keep their load
    # order via the trailing index.
    items.sort(key=lambda entry: entry[:3])
    return [entry[3] for entry in items]


class PptSendJob(BackgroundJob):
    """BackgroundJob wrapper so sends share the export job's lifecycle."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.results = PptSendResults()
        self._items: list[PptItem] = []
        self._settings = PptSettings()

    def send(self, items: list[PptItem], settings: PptSettings) -> bool:
        if self.isRunning:
            return False
        self.results.clear()
        self._items = list(items)
        self._settings = settings
        return self.start_job()

    def _make_worker(self, stop_event: threading.Event) -> PptSendWorker:
        return PptSendWorker(self._items, self._settings, self.results, stop_event)


class PowerPointController(QObject):
    """The PowerPoint card's settings plus the send job.

    Settings follow the SettingsController pattern exactly: write
    through to QSettings on every change, early-return when unchanged
    (QML two-way bindings re-enter setters on their own notify).
    """

    transitionSlideEnabledChanged = Signal()
    transitionSlideIndexChanged = Signal()
    imageSlideIndexChanged = Signal()
    sendToActivePptChanged = Signal()
    addLabelObjectChanged = Signal()

    statusUpdated = Signal(str)
    progressUpdated = Signal(int, int)
    isSendingChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._settings = QSettings()
        self._load()

        self._job = PptSendJob(self)
        self._job.statusUpdated.connect(self.statusUpdated)
        self._job.progressUpdated.connect(self.progressUpdated)
        self._job.isRunningChanged.connect(self.isSendingChanged)
        self._job.jobFinished.connect(self._on_job_finished)

    # --- Persistence -----------------------------------------------------

    def _load(self) -> None:
        s = self._settings

        def as_int(name: str, fallback: int, low: int, high: int) -> int:
            try:
                value = int(s.value(_key(name), fallback))
            except (TypeError, ValueError):
                logger.warning("Setting %r was not an integer; using default", name)
                return fallback
            return max(low, min(high, value))

        def as_bool(name: str, fallback: bool) -> bool:
            value = s.value(_key(name), fallback)
            if isinstance(value, bool):
                return value
            return str(value).lower() in ("true", "1", "yes")

        self._transition_enabled = as_bool(
            "transitionSlideEnabled", defaults.TRANSITION_ENABLED_DEFAULT
        )
        self._transition_index = as_int(
            "transitionSlideIndex",
            defaults.TRANSITION_SLIDE_INDEX_DEFAULT,
            defaults.SLIDE_INDEX_MIN,
            defaults.SLIDE_INDEX_MAX,
        )
        self._image_index = as_int(
            "imageSlideIndex",
            defaults.IMAGE_SLIDE_INDEX_DEFAULT,
            defaults.SLIDE_INDEX_MIN,
            defaults.SLIDE_INDEX_MAX,
        )
        self._send_to_active = as_bool(
            "sendToActivePpt", defaults.SEND_TO_ACTIVE_PPT_DEFAULT
        ) and self.available
        self._add_label_object = as_bool(
            "addLabelObject", defaults.ADD_LABEL_OBJECT_DEFAULT
        )

    def _store(self, name: str, value: object) -> None:
        self._settings.setValue(_key(name), value)

    def flush(self) -> None:
        self._settings.sync()

    # --- Properties ------------------------------------------------------

    @Property(bool, constant=True)
    def available(self) -> bool:
        """Sending needs Windows and pywin32; the card disables itself
        rather than failing at Start when either is missing.

        Read through the module (not a from-import) so it reflects the
        real import result at call time — constant for QML because it
        cannot change while the app runs.
        """

        return worker_module.PYWIN32_AVAILABLE and sys.platform == "win32"

    @Property(bool, notify=transitionSlideEnabledChanged)
    def transitionSlideEnabled(self) -> bool:
        return self._transition_enabled

    @transitionSlideEnabled.setter
    def transitionSlideEnabled(self, value: bool) -> None:
        value = bool(value)
        if value == self._transition_enabled:
            return
        self._transition_enabled = value
        self._store("transitionSlideEnabled", value)
        self.transitionSlideEnabledChanged.emit()

    @Property(int, notify=transitionSlideIndexChanged)
    def transitionSlideIndex(self) -> int:
        return self._transition_index

    @transitionSlideIndex.setter
    def transitionSlideIndex(self, value: int) -> None:
        value = max(
            defaults.SLIDE_INDEX_MIN, min(defaults.SLIDE_INDEX_MAX, int(value))
        )
        if value == self._transition_index:
            return
        self._transition_index = value
        self._store("transitionSlideIndex", value)
        self.transitionSlideIndexChanged.emit()

    @Property(int, notify=imageSlideIndexChanged)
    def imageSlideIndex(self) -> int:
        return self._image_index

    @imageSlideIndex.setter
    def imageSlideIndex(self, value: int) -> None:
        value = max(
            defaults.SLIDE_INDEX_MIN, min(defaults.SLIDE_INDEX_MAX, int(value))
        )
        if value == self._image_index:
            return
        self._image_index = value
        self._store("imageSlideIndex", value)
        self.imageSlideIndexChanged.emit()

    @Property(bool, notify=sendToActivePptChanged)
    def sendToActivePpt(self) -> bool:
        return self._send_to_active

    @sendToActivePpt.setter
    def sendToActivePpt(self, value: bool) -> None:
        # Refused when unavailable: canStart is relaxed on this flag, so
        # letting it go true without pywin32 would enable a Start that
        # could only fail.
        value = bool(value) and self.available
        if value == self._send_to_active:
            return
        self._send_to_active = value
        self._store("sendToActivePpt", value)
        self.sendToActivePptChanged.emit()

    @Property(bool, notify=addLabelObjectChanged)
    def addLabelObject(self) -> bool:
        return self._add_label_object

    @addLabelObject.setter
    def addLabelObject(self, value: bool) -> None:
        value = bool(value)
        if value == self._add_label_object:
            return
        self._add_label_object = value
        self._store("addLabelObject", value)
        self.addLabelObjectChanged.emit()

    @Property(bool, notify=isSendingChanged)
    def isSending(self) -> bool:
        return self._job.isRunning

    @property
    def results(self) -> PptSendResults:
        return self._job.results

    # --- Job -------------------------------------------------------------

    def snapshot(self) -> PptSettings:
        """Immutable copy safe to hand to the worker thread."""

        return PptSettings(
            transition_enabled=self._transition_enabled,
            transition_index=self._transition_index,
            image_index=self._image_index,
        )

    def start_send(self, items: list[PptItem], settings: PptSettings) -> bool:
        started = self._job.send(items, settings)
        if started:
            logger.info("PowerPoint send started: %d slides", len(items))
        return started

    def stop(self) -> None:
        self._job.stop()

    def wait_for_stop(self) -> bool:
        return self._job.wait_for_stop()

    def _on_job_finished(self, completed: bool) -> None:
        results = self._job.results
        sent = len(results.sent)
        failed = len(results.failures)

        if results.error_reason:
            self.statusUpdated.emit(results.error_reason)
            return

        if not completed:
            self.statusUpdated.emit(
                f"PowerPoint send stopped — sent {sent} slide"
                f"{'' if sent == 1 else 's'}"
            )
            return

        parts = [f"Sent {sent} slide{'' if sent == 1 else 's'} to PowerPoint"]
        if results.template_mode is False:
            parts.append("generic slides — template layouts not found")
        elif results.transition_fallback:
            parts.append("generic divider — transition layout not found")
        if failed:
            parts.append(f"{failed} failed")
        self.statusUpdated.emit(" — ".join(parts))
