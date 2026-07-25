"""Owns the export job: task assembly, lifecycle, and the end summary."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from PySide6.QtCore import Property, QObject, Signal

from .. import defaults
from ..jobs.base import BackgroundJob
from ..label.spec import CellSpec, CustomCellSpec, LabelSpec, PlacedCell
from ..metadata import canonical
from . import report
from .worker import ExportResults, ExportTask, ExportWorker

logger = logging.getLogger(__name__)


def format_for_label(meta, path: str) -> str:
    """One image's value for one checked path, formatted for the label.

    canonical.format_for_path over this image's raw value — kept here so
    callers with an ImageMetadata in hand don't repeat the fetch, and so
    the tree, the preview and the output can never disagree.
    """

    return canonical.format_for_path(path, meta.get(path))


def build_tasks(images, label, settings, run_dir: Path) -> tuple[list[ExportTask], int]:
    """Per-image tasks from the current checked set and settings.

    Runs on the GUI thread, so it may read live models freely; the
    worker gets only frozen snapshots. Returns (tasks, skipped) where
    skipped counts images that never parsed and get no label.
    """

    # The user's grid arrangement, shared by every image in the batch;
    # only the VALUES differ per image.
    placements = label.matrix.placed_cells()
    style = settings.label_style()
    mode = settings.outputMode
    wants_svg = defaults.output_writes_svg(mode)
    wants_watermark = defaults.output_writes_watermark(mode)

    tasks: list[ExportTask] = []
    skipped = 0
    # Discovery de-dupes by resolved path, so two different files with
    # the SAME NAME from different folders are a legal batch — their
    # outputs must not overwrite each other in the flat run dir.
    used_stems: set[str] = set()

    def unique_stem(stem: str) -> str:
        candidate = stem
        n = 2
        while candidate.lower() in used_stems:
            candidate = f"{stem}_{n}"
            n += 1
        used_stems.add(candidate.lower())
        return candidate

    for source in images.paths():
        meta = images.metadata_for(source)
        if meta is None or meta.is_empty:
            skipped += 1
            continue
        cells = tuple(
            PlacedCell(
                # A custom cell is literal, identical on every image —
                # the shared frozen instance passes straight through.
                # Metadata cells resolve THIS image's value.
                cell=placed if isinstance(placed, CustomCellSpec) else CellSpec(
                    path=placed.path,
                    key_text=placed.path.rsplit(".", 1)[-1],
                    value_text=format_for_label(meta, placed.path),
                ),
                row=row,
                column=column,
            )
            for row, column, placed in placements
        )
        spec = LabelSpec(
            cells=cells,
            style=style,
            image_width=meta.width,
            image_height=meta.height,
            databar_height=meta.databar_height,
        )
        stem = unique_stem(source.stem)
        tasks.append(
            ExportTask(
                source=source,
                svg_path=(run_dir / f"{stem}_label.svg") if wants_svg else None,
                # The copy keeps the original's name (suffixed _2, _3...
                # only on a same-name collision) so the sibling tools
                # find it by the name they already know.
                watermark_path=(
                    run_dir / f"{stem}{source.suffix}" if wants_watermark else None
                ),
                spec=spec,
                image_unique_id=getattr(meta, "image_unique_id", "") or "",
            )
        )
    return tasks, skipped


class ExportJob(BackgroundJob):
    """BackgroundJob wrapper so exports share the parse job's lifecycle."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.results = ExportResults()
        self._tasks: list[ExportTask] = []

    def export(self, tasks: list[ExportTask], run_dir: Path) -> bool:
        if self.isRunning:
            return False
        self.results.clear()
        self.results.run_dir = run_dir
        self._tasks = list(tasks)
        return self.start_job()

    def _make_worker(self, stop_event: threading.Event) -> ExportWorker:
        return ExportWorker(self._tasks, self.results, stop_event)


class ExportController(QObject):
    """Funnels the job's signals and words the end-of-run summary."""

    statusUpdated = Signal(str)
    progressUpdated = Signal(int, int)
    isExportingChanged = Signal()
    # Emitted AFTER the report is written and the summary status is set,
    # so anything chained off it (the PowerPoint send) cannot race them.
    exportFinished = Signal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._job = ExportJob(self)
        self._skipped = 0
        self._mode_name = ""
        self._report_written = True  # nothing pending before the first run
        self._job.statusUpdated.connect(self.statusUpdated)
        self._job.progressUpdated.connect(self.progressUpdated)
        self._job.isRunningChanged.connect(self.isExportingChanged)
        self._job.jobFinished.connect(self._on_job_finished)

    @Property(bool, notify=isExportingChanged)
    def isExporting(self) -> bool:
        return self._job.isRunning

    @property
    def results(self) -> ExportResults:
        return self._job.results

    def start_export(
        self,
        tasks: list[ExportTask],
        run_dir: Path,
        skipped: int,
        mode_name: str = "",
    ) -> bool:
        self._skipped = skipped
        self._mode_name = mode_name
        self._report_written = False
        started = self._job.export(tasks, run_dir)
        if started:
            logger.info(
                "Export started: %d images -> %r", len(tasks), str(run_dir)
            )
        return started

    def stop(self) -> None:
        self._job.stop()

    def wait_for_stop(self) -> bool:
        return self._job.wait_for_stop()

    def write_pending_report(self) -> None:
        """Shutdown path only. wait_for_stop joins the worker, but the
        queued jobFinished can never be delivered once the event loop
        has stopped spinning — without this, quitting mid-export loses
        the report for every file already written."""

        if self._report_written:
            return
        results = self._job.results
        if results.run_dir is None:
            return
        self._report_written = True
        report.write_report(
            results.run_dir, self._mode_name, results.report_entries, stopped=True
        )

    def _on_job_finished(self, completed: bool) -> None:
        results = self._job.results
        wrote = len(results.written)
        failed = len(results.failures)
        run_name = results.run_dir.name if results.run_dir else "?"

        if results.run_dir is not None and not self._report_written:
            self._report_written = True
            report.write_report(
                results.run_dir,
                self._mode_name,
                results.report_entries,
                stopped=not completed,
            )

        if not completed:
            parts = [f"Export stopped — wrote {wrote} of {wrote + failed} started"]
        else:
            parts = [
                f"Wrote {wrote} file{'' if wrote == 1 else 's'} to {run_name}"
            ]
        if failed:
            parts.append(f"{failed} failed")
        if self._skipped:
            parts.append(f"{self._skipped} skipped (no metadata)")
        self.statusUpdated.emit(" — ".join(parts))
        self.exportFinished.emit(completed)
