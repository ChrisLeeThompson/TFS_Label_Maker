"""Parse a batch of images on a worker thread."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from ..jobs.base import BackgroundJob
from .common_fields import UnionAccumulator
from .reader import read_metadata
from .records import ImageMetadata

logger = logging.getLogger(__name__)


@dataclass
class ParseResults:
    """Owned by the job, filled by the worker.

    Passing a container the job already holds avoids reading anything off
    a worker that may be mid-deletion, and keeps 1,600-entry dicts off the
    queued-connection path.
    """

    metadata: dict[Path, ImageMetadata] = field(default_factory=dict)
    failures: list[tuple[Path, str]] = field(default_factory=list)
    accumulator: UnionAccumulator = field(default_factory=UnionAccumulator)
    parsed_count: int = 0

    def clear(self) -> None:
        self.metadata.clear()
        self.failures.clear()
        self.accumulator = UnionAccumulator()
        self.parsed_count = 0


class _ParseWorker(QObject):
    progressUpdated = Signal(int, int)
    statusUpdated = Signal(str)
    fileParsed = Signal(str, bool, str)  # path, ok, reason
    finished = Signal(bool)

    def __init__(
        self,
        paths: list[Path],
        results: ParseResults,
        stop_event: threading.Event,
    ) -> None:
        super().__init__()
        self._paths = paths
        self._results = results
        self._stop = stop_event

    @Slot()
    def run(self) -> None:
        completed = False
        total = len(self._paths)
        try:
            self.progressUpdated.emit(0, total)
            for index, path in enumerate(self._paths, start=1):
                if self._stop.is_set():
                    return

                self.statusUpdated.emit(f"Reading {path.name} ({index}/{total})")
                try:
                    meta = read_metadata(path)
                except Exception as exc:  # noqa: BLE001
                    # A batch is never abandoned because one file is bad;
                    # the row is marked failed and the run carries on.
                    logger.exception("Parse failed for %r", str(path))
                    self._results.failures.append((path, str(exc)))
                    self.fileParsed.emit(str(path), False, str(exc))
                    self.progressUpdated.emit(index, total)
                    continue

                if meta.errors and meta.is_empty:
                    reason = meta.errors[0]
                    self._results.failures.append((path, reason))
                    self.fileParsed.emit(str(path), False, reason)
                else:
                    self._results.metadata[path] = meta
                    self._results.accumulator.add(meta)
                    self._results.parsed_count += 1
                    self.fileParsed.emit(str(path), True, "")

                self.progressUpdated.emit(index, total)
            completed = True
        finally:
            self.finished.emit(completed and not self._stop.is_set())


class ParseJob(BackgroundJob):
    """Reads metadata for the loaded images and accumulates the union
    of their fields."""

    fileParsed = Signal(str, bool, str)
    # Distinct from the base class's jobFinished, which fires for every
    # run including one that was superseded by a restart. Consumers want
    # to know a *final* result landed, not that a thread ended.
    parseComplete = Signal(bool)  # True when it ran to completion

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._paths: list[Path] = []
        self._results = ParseResults()
        self._restart_paths: list[Path] | None = None

    # --- Public API ------------------------------------------------------

    @property
    def results(self) -> ParseResults:
        return self._results

    def parse(self, paths: list[Path]) -> None:
        """Start, or queue a restart if a run is already in flight.

        Restarting is queued rather than joined: waiting here would block
        the GUI thread, and the queued worker.finished could not then be
        delivered, so the join would stall until its timeout. Deferring to
        _on_job_finished guarantees exactly one parse thread ever exists.
        """

        if self._is_running:
            self._restart_paths = list(paths)
            self.stop()
            return

        self._paths = list(paths)
        self._results.clear()
        if not self._paths:
            self.parseComplete.emit(True)
            return
        self.start_job()

    # --- BackgroundJob hooks ---------------------------------------------

    def _make_worker(self, stop_event: threading.Event) -> QObject:
        worker = _ParseWorker(self._paths, self._results, stop_event)
        worker.fileParsed.connect(self.fileParsed)
        return worker

    def _on_job_finished(self, completed: bool) -> None:
        if self._restart_paths is not None:
            paths, self._restart_paths = self._restart_paths, None
            self._paths = paths
            self._results.clear()
            if paths:
                self.start_job()
                return
            self.parseComplete.emit(True)
            return
        self.parseComplete.emit(completed)
