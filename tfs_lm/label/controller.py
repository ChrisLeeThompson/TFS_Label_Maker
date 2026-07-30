"""Bridges the checked metadata fields into the label slot grid."""

from __future__ import annotations

import logging

from PySide6.QtCore import Property, QObject, Signal, Slot

from .. import defaults
from ..metadata import formatting
from .matrix_model import LabelMatrixModel
from .spec import CellSpec, CustomCellSpec

logger = logging.getLogger(__name__)


class LabelController(QObject):
    """Owns the slot-grid model and keeps it in step with the tree.

    Data flows one way: tree checks -> cells (on every checkedChanged,
    including the rebuild after each parse; also on currentImageChanged
    — the cells show the CURRENT image's values — and on a
    missing-field policy flip, which re-resolves the ghost state); the
    grid shape follows the labelRows/labelColumns settings, and the
    grid's FREE slot count (slots minus custom text cells) is pushed
    into the tree as its check capacity. Two flows go back the other
    way: drag reorder pushes the grid's reading order into the tree's
    (session-only) check order, and drag-out delete unchecks the
    dragged field. Custom text cells live entirely on this side — the
    tree never learns about them beyond the capacity they consume.
    """

    gridChanged = Signal()
    countChanged = Signal()

    def __init__(self, images, settings, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._images = images
        self._settings = settings
        self._matrix = LabelMatrixModel(self)

        images.checkedFieldsChanged.connect(self._sync_cells)
        # Cycling swaps which image's values the cells show; a policy
        # flip re-resolves the ghost state. Parse completion fires both
        # checkedFieldsChanged and currentImageChanged — the second
        # sync is a no-op because the matrix diffs value-equal cells.
        images.currentImageChanged.connect(self._sync_cells)
        settings.missingFieldPolicyChanged.connect(self._sync_cells)
        settings.labelColumnsChanged.connect(self._apply_grid)
        settings.labelRowsChanged.connect(self._apply_grid)
        self._matrix.countChanged.connect(self.countChanged)
        self._matrix.gridChanged.connect(self.gridChanged)

        self._apply_grid()
        self._sync_cells()

    # --- Sync ------------------------------------------------------------

    def _apply_grid(self) -> None:
        """Adopt the configured grid shape, evicting what no longer fits.

        Ordering is load-bearing: the grid's reading-order eviction is
        THE eviction. The dropped paths are unchecked FIRST, so that by
        the time the tree's capacity tightens the checked set already
        fits and set_capacity has nothing further to evict. Applying
        capacity first let two disagreeing policies (reading-order tail
        vs check-order tail) evict their union — with divergent orders
        a one-step shrink could wipe the entire selection (reproduced
        before this ordering was fixed). Dropped custom cells simply
        vanish — nothing to uncheck — and are already gone from the
        matrix by the time _push_capacity re-counts them.
        """

        rows = self._settings.labelRows
        columns = self._settings.labelColumns
        tree = self._images.fieldsModel

        dropped = self._matrix.set_grid(rows, columns)
        for entry in dropped:
            if isinstance(entry, CellSpec):
                tree.setChecked(entry.path, False)
        self._push_capacity()
        self._sync_cells()

    def _push_capacity(self) -> None:
        """The tree may check exactly the slots custom cells don't hold."""

        self._images.fieldsModel.set_capacity(
            self._matrix.capacity - self._matrix.custom_count
        )

    def _sync_cells(self) -> None:
        """Rebuild the metadata cells for the CURRENT image.

        A path the current image lacks resolves per the missing-field
        policy, here as in the output: Omit ghosts the cell (empty
        value + omitted flag for the QML dim), Dash shows the em dash.
        Present-but-blank values arrive from the tree already dashed —
        only true absence goes through the policy.
        """

        tree = self._images.fieldsModel
        omit = (
            self._settings.missingFieldPolicy == defaults.MISSING_FIELD_OMIT
        )
        cells = []
        for path in tree.checked_paths():
            absent = not tree.present_in_current(path)
            cells.append(CellSpec(
                path=path,
                key_text=tree.display_key(path),
                value_text=(
                    formatting.EMPTY_DISPLAY if absent and not omit
                    else tree.display_value(path)
                ),
                omitted=absent and omit,
            ))
        self._matrix.sync_cells(cells)

    # --- Properties ------------------------------------------------------

    @Property(QObject, constant=True)
    def matrix(self) -> LabelMatrixModel:
        return self._matrix

    @Property(int, notify=countChanged)
    def cellCount(self) -> int:
        return self._matrix.occupied_count

    @Property(int, notify=countChanged)
    def customCount(self) -> int:
        return self._matrix.custom_count

    @Property(int, notify=gridChanged)
    def rows(self) -> int:
        return self._matrix.rows

    @Property(int, notify=gridChanged)
    def columns(self) -> int:
        return self._matrix.columns

    # --- Slots -----------------------------------------------------------

    @Slot(int, int, result=bool)
    def moveCell(self, from_index: int, to_index: int) -> bool:
        ok = self._matrix.move(from_index, to_index)
        if ok:
            self._images.fieldsModel.reorder_checked(
                self._matrix.reading_order_paths()
            )
            logger.info("Label cell moved %d -> %d", from_index, to_index)
        return ok

    @Slot(int, str, result=bool)
    def setCustomText(self, index: int, text: str) -> bool:
        """Create, edit, or (with empty text) remove a custom cell."""

        ok = self._matrix.set_custom_text(index, text)
        if ok:
            self._push_capacity()
            logger.info("Custom cell %d set (%d chars)", index, len(text.strip()))
        return ok

    @Slot(int, result=bool)
    def removeCell(self, slot_index: int) -> bool:
        """Drag-out delete: dropping a cell outside the plate removes it.

        A metadata cell is removed by UNCHECKING its field — the tree's
        checkedChanged re-syncs the grid and vacates the slot, and, as
        with any uncheck, the remembered session intent forgets the
        path too. A custom cell is the grid's own; it is vacated
        directly and the freed slot returns to the tree's capacity.
        """

        slots = self._matrix.slots()
        if not (0 <= slot_index < len(slots)) or slots[slot_index] is None:
            return False
        entry = slots[slot_index]
        if isinstance(entry, CustomCellSpec):
            self._matrix.set_custom_text(slot_index, "")
            self._push_capacity()
            logger.info("Custom cell %d removed by drag-out", slot_index)
            return True
        self._images.fieldsModel.setChecked(entry.path, False)
        logger.info(
            "Label cell %d removed by drag-out (%s)", slot_index, entry.path
        )
        return True
