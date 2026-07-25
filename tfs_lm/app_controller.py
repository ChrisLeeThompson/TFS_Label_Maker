"""Root controller exposed to QML as the `appController` context property."""

from __future__ import annotations

import logging

from PySide6.QtCore import Property, QObject, Signal, Slot

from . import defaults, paths
from .export.controller import ExportController, build_tasks
from .images.controller import ImageSetController
from .label.controller import LabelController
from .powerpoint.controller import PowerPointController, build_ppt_items
from .settings.controller import SettingsController

logger = logging.getLogger(__name__)


class AppController(QObject):
    """Owns the sub-controllers and funnels their status/progress to the UI.

    Every background job connects into this object once, at construction,
    and QML binds to `appController` for the lifetime of the window. The
    sibling apps instead re-target their status bar's Connections at
    whichever job is live, which is the sole reason they have to emit the
    final status message before the finished signal — re-targeting nulls
    the binding and drops the last message. Funnelling here removes that
    ordering hazard structurally rather than by convention.
    """

    statusMessageChanged = Signal()
    busyChanged = Signal()
    canStartChanged = Signal()
    progressUpdated = Signal(int, int)  # (current, total); (-1, -1) = indeterminate
    errorOccurred = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._status_message = ""
        self._busy = False
        # True between "export started" and "PowerPoint send started",
        # so busy cannot flicker to idle across the handoff.
        self._ppt_pending = False
        self._ppt_items = []
        self._ppt_snapshot = None

        # Parented to self so lifetime follows the root controller.
        # Label after images/settings: it subscribes to both at
        # construction.
        self._settings = SettingsController(self)
        self._images = ImageSetController(self)
        self._label = LabelController(self._images, self._settings, self)
        self._export = ExportController(self)
        self._powerpoint = PowerPointController(self)

        # Connected once, here, for the lifetime of the app. QML binds to
        # appController and never to a sub-controller that comes and goes,
        # so a status message can never be dropped by a binding that was
        # re-targeted mid-emit.
        self._images.statusUpdated.connect(self._set_status)
        self._images.countChanged.connect(self.canStartChanged)
        self._images.checkedFieldsChanged.connect(self.canStartChanged)
        self._images.progressUpdated.connect(self.progressUpdated)
        self._images.isParsingChanged.connect(self._update_busy)

        self._export.statusUpdated.connect(self._set_status)
        self._export.progressUpdated.connect(self.progressUpdated)
        self._export.isExportingChanged.connect(self._update_busy)
        self._export.exportFinished.connect(self._on_export_finished)

        self._powerpoint.statusUpdated.connect(self._set_status)
        self._powerpoint.progressUpdated.connect(self.progressUpdated)
        self._powerpoint.isSendingChanged.connect(self._update_busy)
        # canStart is relaxed on this flag, so it must re-evaluate.
        self._powerpoint.sendToActivePptChanged.connect(self.canStartChanged)
        # PowerPoint-only mode relaxes canStart the same way (and start()
        # branches on it), so a mode change must re-evaluate too.
        self._settings.outputModeChanged.connect(self.canStartChanged)
        # canStart reads the grid's cell count (custom cells included),
        # which changes without a checkedFieldsChanged when a custom
        # cell is added or removed.
        self._label.countChanged.connect(self.canStartChanged)

    # --- Sub-controllers -------------------------------------------------

    @Property(QObject, constant=True)
    def settings(self) -> SettingsController:
        return self._settings

    @Property(QObject, constant=True)
    def images(self) -> ImageSetController:
        return self._images

    @Property(QObject, constant=True)
    def label(self) -> LabelController:
        return self._label

    @Property(QObject, constant=True)
    def powerpoint(self) -> PowerPointController:
        return self._powerpoint

    # --- Properties ------------------------------------------------------

    @Property(str, notify=statusMessageChanged)
    def statusMessage(self) -> str:
        return self._status_message

    @Property(bool, notify=busyChanged)
    def busy(self) -> bool:
        return self._busy

    def _wants_ppt(self) -> bool:
        """The effective send flag. PowerPoint-Only output IS a send, so
        the mode implies it without mutating the persisted checkbox —
        the stored preference returns untouched when the mode changes
        back."""

        return self._powerpoint.available and (
            self._powerpoint.sendToActivePpt
            or self._settings.outputMode == defaults.OUTPUT_PPT_ONLY
        )

    @Property(bool, notify=canStartChanged)
    def canStart(self) -> bool:
        """An occupied grid cell — checked field or custom text — gives
        something to label; sending to PowerPoint is valid on its own
        (image-only slides), which is how the app doubles as an
        images-to-PowerPoint tool. In PowerPoint-Only mode the send is
        the whole job, so it must be possible — and cells are optional
        there."""

        if self._busy or self._images.isParsing or self._images.count == 0:
            return False
        if self._settings.outputMode == defaults.OUTPUT_PPT_ONLY:
            return self._wants_ppt()  # reduces to powerpoint.available
        return self._label.cellCount > 0 or self._wants_ppt()

    def _update_busy(self) -> None:
        self._set_busy(
            self._images.isParsing
            or self._export.isExporting
            or self._powerpoint.isSending
            or self._ppt_pending
        )

    # --- Internal state --------------------------------------------------

    def _set_status(self, text: str) -> None:
        if text == self._status_message:
            return
        self._status_message = text
        self.statusMessageChanged.emit()

    def _set_busy(self, busy: bool) -> None:
        if busy == self._busy:
            return
        self._busy = busy
        self.busyChanged.emit()
        self.canStartChanged.emit()

    # --- Slots -----------------------------------------------------------

    @Slot()
    def initialize(self) -> None:
        """Deferred past the first paint by QTimer.singleShot in main()."""

        if not paths.output_root_is_writable():
            self.errorOccurred.emit(
                f"Cannot write to the script directory:\n{paths.base_dir()}\n\n"
                "Output cannot be saved until this is resolved."
            )
            self._set_status("Script directory is not writable")
            return

        self._set_status(defaults.STATUS_READY)

    @Slot()
    def start(self) -> None:
        if not self.canStart:
            return
        logger.info("Start requested")

        has_label = self._label.cellCount > 0
        wants_ppt = self._wants_ppt()
        ppt_only = self._settings.outputMode == defaults.OUTPUT_PPT_ONLY

        if ppt_only or not has_label:
            # Nothing will be written in either case — PowerPoint-Only
            # by definition, empty-grid because there is no labelled
            # file to make — so there is no export and no run directory:
            # Start is purely "send these images to PowerPoint".
            # canStart already guarantees wants_ppt here; the check
            # keeps the branch honest if that gate ever loosens.
            if wants_ppt:
                self._start_ppt_send()
            return

        try:
            run_dir = paths.make_run_dir()
        except OSError as exc:
            logger.exception("Could not create the run directory")
            self.errorOccurred.emit(f"Could not create the run directory:\n{exc}")
            return

        tasks, skipped = build_tasks(
            self._images, self._label, self._settings, run_dir
        )
        if not tasks:
            run_dir.rmdir()  # nothing will be written; leave no empty dirs
            self._set_status("Nothing to export — no image parsed successfully")
            return

        if wants_ppt:
            # Captured now, from the same models the export reads, and
            # sent once the export finishes.
            self._ppt_items = build_ppt_items(
                self._images, self._label, self._settings,
                self._powerpoint.addLabelObject,
            )
            self._ppt_snapshot = self._powerpoint.snapshot()
            self._ppt_pending = True

        mode_name = defaults.OUTPUT_NAMES[self._settings.outputMode]
        if not self._export.start_export(tasks, run_dir, skipped, mode_name):
            # Never expected (canStart requires an idle app), but a
            # queued send must not strand busy at True forever.
            self._ppt_pending = False
            self._ppt_items, self._ppt_snapshot = [], None
            self._update_busy()

    def _start_ppt_send(self) -> None:
        """Direct send with no export behind it. With no cells arranged
        build_ppt_items degrades to image-only slides on its own, so the
        label-object flag simply rides along — in PowerPoint-Only mode
        with cells arranged it produces the native label objects."""

        items = build_ppt_items(
            self._images, self._label, self._settings,
            self._powerpoint.addLabelObject,
        )
        if not items:
            self._set_status(defaults.STATUS_PPT_NOTHING)
            return
        self._powerpoint.start_send(items, self._powerpoint.snapshot())

    def _on_export_finished(self, completed: bool) -> None:
        """Chain the queued PowerPoint send once the files are written."""

        if not self._ppt_pending:
            return
        self._ppt_pending = False
        items, snapshot = self._ppt_items, self._ppt_snapshot
        self._ppt_items, self._ppt_snapshot = [], None
        if not completed or not items:
            # A stopped or failed export cancels the send.
            self._update_busy()
            return
        if not self._powerpoint.start_send(items, snapshot):
            self._update_busy()

    @Slot()
    def stop(self) -> None:
        logger.info("Stop requested")
        # Cancel a send queued behind a running export, too.
        self._ppt_pending = False
        self._ppt_items, self._ppt_snapshot = [], None
        if self._images.isParsing:
            self._images.stopParsing()
        if self._export.isExporting:
            self._export.stop()
        if self._powerpoint.isSending:
            self._powerpoint.stop()

    @Slot()
    def shutdown(self) -> None:
        """Join any running jobs. Connected to QGuiApplication.aboutToQuit."""

        logger.info("Shutting down")
        # Nothing may be spawned on the way out.
        self._ppt_pending = False
        # Join before the settings flush: a worker still running while the
        # interpreter tears down is the classic source of exit-time noise.
        self._powerpoint.wait_for_stop()
        self._export.wait_for_stop()
        # The queued jobFinished cannot be delivered any more (the event
        # loop stops spinning after aboutToQuit), so the export report
        # for files already written must be flushed by hand.
        self._export.write_pending_report()
        self._images.wait_for_stop()
        # QSettings buffers writes; without this a change made moments
        # before quitting is silently lost. (Checked fields are
        # deliberately NOT persisted — session-only by user decision.)
        self._settings.flush()
        self._powerpoint.flush()
