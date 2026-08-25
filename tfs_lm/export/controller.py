"""Owns the export job: task assembly, lifecycle, and the end summary."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from PySide6.QtCore import Property, QObject, Signal

from .. import defaults
from ..jobs.base import BackgroundJob
from ..label.spec import CellSpec, CustomCellSpec, LabelSpec, PlacedCell
from ..metadata import canonical, formatting
from . import report
from .worker import ExportResults, ExportTask, ExportWorker

logger = logging.getLogger(__name__)

# Reasons an image contributes no outputs at all; recorded verbatim in
# export_report.json's "skipped" list and counted in the end summary.
SKIP_NO_METADATA = "no metadata"
SKIP_NO_FIELDS = "no selected fields present"


def format_for_label(meta, path: str) -> str:
    """One image's value for one checked path, formatted for the label.

    canonical.format_for_path over this image's raw value — kept here so
    callers with an ImageMetadata in hand don't repeat the fetch, and so
    the tree, the preview and the output can never disagree.
    """

    return canonical.format_for_path(path, meta.get(path))


def resolve_cell(meta, path: str, policy: int) -> str | None:
    """This image's label text for a checked path, or None to omit.

    Presence is PATH membership in the image's metadata: a present-but-
    empty value formats to the em dash under both policies; only true
    absence consults the missing-field policy. Deliberately raise-free
    (dict membership plus the total formatter chain) — build_tasks and
    build_ppt_items run unguarded on the GUI thread.
    """

    if path in meta.flat:
        return format_for_label(meta, path)
    if policy == defaults.MISSING_FIELD_DASH:
        return formatting.EMPTY_DISPLAY
    return None


def build_tasks(
    images, label, settings, run_dir: Path
) -> tuple[list[ExportTask], list[tuple[Path, str]]]:
    """Per-image tasks from the current checked set and settings.

    Runs on the GUI thread, so it may read live models freely; the
    worker gets only frozen snapshots. Returns (tasks, skips) where
    skips is [(source, reason)] for images that get no outputs at all:
    never parsed, or — under the Omit policy — no selected field
    present and no custom cell. Such images write nothing at all, not even a
    watermark copy: an unlabelled copy inside a labelled_images_* run
    dir would misrepresent the run, so the report carries the reason
    instead.
    """

    # The user's grid arrangement, shared by every image in the batch;
    # only the values differ per image — and, under the Omit policy,
    # which of the arranged cells this image's label actually carries.
    placements = label.matrix.placed_cells()
    style = settings.label_style()
    policy = settings.missingFieldPolicy
    mode = settings.outputMode
    wants_svg = defaults.output_writes_svg(mode)
    wants_watermark = defaults.output_writes_watermark(mode)

    tasks: list[ExportTask] = []
    skips: list[tuple[Path, str]] = []
    # Discovery de-dupes by resolved path, so two different files with
    # the same name from different folders are a legal batch — their
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
            skips.append((source, SKIP_NO_METADATA))
            continue
        cells = []
        for row, column, placed in placements:
            if isinstance(placed, CustomCellSpec):
                # A custom cell is literal, identical on every image —
                # the shared frozen instance passes straight through.
                cells.append(PlacedCell(cell=placed, row=row, column=column))
                continue
            # Metadata cells resolve this image's own value; an absent
            # path omits the cell or dashes it, per the policy. The
            # layout's rank-based trim then collapses any row/column
            # the omissions emptied — for this image only.
            value = resolve_cell(meta, placed.path, policy)
            if value is None:
                continue
            cells.append(PlacedCell(
                cell=CellSpec(
                    path=placed.path,
                    key_text=canonical.display_key(placed.path),
                    value_text=value,
                ),
                row=row,
                column=column,
            ))
        if not cells:
            skips.append((source, SKIP_NO_FIELDS))
            continue
        spec = LabelSpec(
            cells=tuple(cells),
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
    return tasks, skips


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
    # Emitted after the report is written and the summary status is set,
    # so anything chained off it (the PowerPoint send) cannot race them.
    exportFinished = Signal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._job = ExportJob(self)
        self._skips: list[tuple[Path, str]] = []
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
        skips: list[tuple[Path, str]],
        mode_name: str = "",
    ) -> bool:
        self._skips = list(skips)
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
            results.run_dir,
            self._mode_name,
            results.report_entries,
            stopped=True,
            skipped=self._serialized_skips(),
        )

    def _serialized_skips(self) -> list[dict[str, str]]:
        return [
            {"source": source.name, "reason": reason}
            for source, reason in self._skips
        ]

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
                skipped=self._serialized_skips(),
            )

        if not completed:
            parts = [f"Export stopped — wrote {wrote} of {wrote + failed} files"]
        else:
            parts = [
                f"Wrote {wrote} file{'' if wrote == 1 else 's'} to {run_name}"
            ]
        if failed:
            parts.append(f"{failed} failed")
        no_meta = sum(1 for _, r in self._skips if r == SKIP_NO_METADATA)
        no_fields = sum(1 for _, r in self._skips if r == SKIP_NO_FIELDS)
        if no_meta:
            parts.append(f"{no_meta} skipped ({SKIP_NO_METADATA})")
        if no_fields:
            parts.append(f"{no_fields} skipped ({SKIP_NO_FIELDS})")
        self.statusUpdated.emit(" — ".join(parts))
        self.exportFinished.emit(completed)
