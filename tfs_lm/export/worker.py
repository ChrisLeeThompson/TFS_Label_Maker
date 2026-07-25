"""The worker-thread half of an export run."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot

from ..label.spec import LabelSpec
from ..label import svg_writer
from . import image_io

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ExportTask:
    """Everything needed to produce one image's outputs.

    Built on the GUI thread from parsed metadata; the worker only
    paints and writes, it never touches live models. Either output path
    may be None when the output mode excludes it.
    """

    source: Path
    svg_path: Path | None
    watermark_path: Path | None
    spec: LabelSpec
    image_unique_id: str = ""

    @property
    def output_count(self) -> int:
        return int(self.svg_path is not None) + int(self.watermark_path is not None)


@dataclass
class ExportResults:
    """Filled in place by the worker; read after the job finishes."""

    run_dir: Path | None = None
    written: list[Path] = field(default_factory=list)
    failures: list[tuple[Path, str]] = field(default_factory=list)
    report_entries: list[dict[str, Any]] = field(default_factory=list)

    def clear(self) -> None:
        self.run_dir = None
        self.written.clear()
        self.failures.clear()
        self.report_entries.clear()


class ExportWorker(QObject):
    """Writes the requested outputs per task, one progress unit each.

    Stop is honoured between whole images (matching the Stop button's
    "after the current image finishes" promise), so a stopped run never
    leaves an image with its SVG written but its watermark missing.
    """

    progressUpdated = Signal(int, int)
    statusUpdated = Signal(str)
    fileWritten = Signal(str, bool, str)  # path, ok, reason
    finished = Signal(bool)

    def __init__(
        self,
        tasks: list[ExportTask],
        results: ExportResults,
        stop_event: threading.Event,
    ) -> None:
        super().__init__()
        self._tasks = tasks
        self._results = results
        self._stop = stop_event

    @Slot()
    def run(self) -> None:
        completed = False
        total = sum(task.output_count for task in self._tasks)
        done = 0
        try:
            for task in self._tasks:
                if self._stop.is_set():
                    return
                entry: dict[str, Any] = {
                    "source": task.source.name,
                    "image_unique_id": task.image_unique_id,
                    "databar_height": task.spec.databar_height,
                    "svg": None,
                    "watermark": None,
                    "errors": [],
                }

                if task.svg_path is not None:
                    self.statusUpdated.emit(f"Writing {task.svg_path.name}")
                    done += self._write_one(
                        task, task.svg_path, entry, "svg",
                        lambda: svg_writer.write_svg(task.svg_path, task.spec),
                    )
                    self.progressUpdated.emit(done, total)

                if task.watermark_path is not None:
                    self.statusUpdated.emit(f"Writing {task.watermark_path.name}")
                    done += self._write_one(
                        task, task.watermark_path, entry, "watermark",
                        lambda: image_io.write_watermark(
                            task.source, task.watermark_path, task.spec
                        ),
                    )
                    self.progressUpdated.emit(done, total)

                self._results.report_entries.append(entry)
            completed = True
        finally:
            self.finished.emit(completed and not self._stop.is_set())

    def _write_one(self, task: ExportTask, target: Path, entry, key, write) -> int:
        """Run one output write with per-file fault isolation.

        Always returns 1 — a failure still consumes its progress unit,
        or the bar would stall short of the total on any error.
        """

        try:
            write()
        except Exception as exc:  # noqa: BLE001 - per-file isolation
            logger.exception("%s failed for %r", key, str(task.source))
            self._results.failures.append((task.source, str(exc)))
            entry["errors"].append(f"{key}: {exc}")
            self.fileWritten.emit(str(task.source), False, str(exc))
        else:
            self._results.written.append(target)
            entry[key] = target.name
            self.fileWritten.emit(str(task.source), True, "")
        return 1
