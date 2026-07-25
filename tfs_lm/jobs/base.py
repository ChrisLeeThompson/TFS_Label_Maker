"""Shared QThread + worker scaffolding for background work."""

from __future__ import annotations

import logging
import threading

from PySide6.QtCore import Property, QObject, QThread, Signal, Slot

from .. import defaults

logger = logging.getLogger(__name__)


class BackgroundJob(QObject):
    """A cancellable unit of work running on its own QThread.

    Follows the sibling apps' lifecycle exactly: a worker QObject moved
    onto a fresh QThread, a four-link teardown chain, and cancellation via
    a threading.Event rather than QThread.requestInterruption.

    The Event matters. requestInterruption is only observable through
    QThread.currentThread(), which couples the worker to Qt and makes it
    untestable off a thread; an Event is a plain object the worker polls
    at its own safe points, and it can be checked from a unit test with no
    Qt event loop at all.

    A fresh Event is created per run — workers never share state across
    runs, so a stop request cannot leak into the next job.

    Results are NOT carried on the finished signal. The job creates a
    result container up front and hands it to the worker, so reading it
    afterwards cannot race worker deletion, and large dicts are never
    deep-copied across a queued connection.
    """

    isRunningChanged = Signal()
    statusUpdated = Signal(str)
    progressUpdated = Signal(int, int)  # (current, total); (-1, -1) = indeterminate
    jobFinished = Signal(bool)  # True when it ran to completion

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: QObject | None = None
        self._stop_event: threading.Event | None = None
        self._is_running = False
        self._completed = False

    # --- Properties ------------------------------------------------------

    @Property(bool, notify=isRunningChanged)
    def isRunning(self) -> bool:
        return self._is_running

    # --- Subclass hooks --------------------------------------------------

    def _make_worker(self, stop_event: threading.Event) -> QObject:
        """Build the worker. It must expose run(), progressUpdated,
        statusUpdated and finished(bool)."""

        raise NotImplementedError

    def _on_job_finished(self, completed: bool) -> None:
        """Called on the GUI thread once the thread has fully unwound."""

    # --- Lifecycle -------------------------------------------------------

    def start_job(self) -> bool:
        if self._is_running:
            logger.debug("%s: already running", type(self).__name__)
            return False

        self._completed = False
        self._stop_event = threading.Event()

        thread = QThread()
        worker = self._make_worker(self._stop_event)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)

        # Signal-to-signal re-emit keeps the job's public surface stable
        # whatever the worker is.
        worker.progressUpdated.connect(self.progressUpdated)
        worker.statusUpdated.connect(self.statusUpdated)
        worker.finished.connect(self._on_worker_finished)

        # Teardown chain.
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_thread_finished)

        self._thread = thread
        self._worker = worker
        self._is_running = True
        self.isRunningChanged.emit()

        thread.start()
        return True

    @Slot()
    def stop(self) -> None:
        """Ask the worker to stop at its next safe point. Idempotent."""

        if not self._is_running or self._stop_event is None:
            return
        if self._stop_event.is_set():
            return
        logger.info("%s: stop requested", type(self).__name__)
        self.statusUpdated.emit("Stop requested...")
        self._stop_event.set()

    @property
    def stop_requested(self) -> bool:
        return self._stop_event is not None and self._stop_event.is_set()

    def _on_worker_finished(self, completed: bool) -> None:
        self._completed = completed

    def _on_thread_finished(self) -> None:
        if self._thread is None and not self._is_running:
            # Already settled synchronously by wait_for_stop; this queued
            # delivery arrived afterwards and must not fire a second
            # jobFinished.
            return
        # Cleared only now, after the thread's event loop has unwound, so
        # that "_thread is not None" reliably means "still alive".
        self._thread = None
        self._worker = None
        self._is_running = False
        self.isRunningChanged.emit()
        self._on_job_finished(self._completed)
        self.jobFinished.emit(self._completed)

    def wait_for_stop(self, timeout_ms: int = defaults.THREAD_JOIN_TIMEOUT_MS) -> bool:
        """Stop and join, for application shutdown.

        Calls thread.quit() directly rather than relying on the queued
        worker.finished -> thread.quit link: during shutdown the GUI
        thread is blocked here and cannot deliver queued slots, so waiting
        for that link would deadlock until the timeout.
        """

        thread = self._thread
        if thread is None:
            return True
        self.stop()
        thread.quit()
        if not thread.wait(timeout_ms):
            logger.warning(
                "%s: worker did not finish within %d ms",
                type(self).__name__,
                timeout_ms,
            )
            return False

        # The thread is genuinely joined now, but _on_thread_finished is a
        # queued slot and cannot run while this call blocks the GUI
        # thread, so isRunning would keep reporting True for a thread that
        # no longer exists. Settle the observable state here instead.
        #
        # The QThread reference is deliberately NOT cleared: its own
        # deleteLater is still pending, and dropping the last Python
        # reference to a QThread with a queued deleteLater risks the
        # wrapper destroying an object Qt is about to delete.
        if self._is_running:
            self._is_running = False
            self.isRunningChanged.emit()
        return True
