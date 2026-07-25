"""Fixed slot grid of the label's cells — an Excel-like matrix.

The user configures rows x columns; every slot is a fixed position
that is either empty, holds one checked field, or holds a user-typed
custom text. Checking fills the first empty slot, unchecking vacates a
slot (holes stay where they are), and a drag moves a cell to an empty
slot or swaps it with an occupant. Custom cells belong to the grid
alone: the tree's sync never touches them, which is what makes them
survive Clear and batch reloads. The grid's slot count minus the
custom cells IS the check capacity, enforced where checks happen (the
metadata tree) — this model never re-implements it.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    Qt,
    Signal,
)

from .. import defaults
from .spec import CellSpec, CustomCellSpec

logger = logging.getLogger(__name__)

_PATH_ROLE = Qt.ItemDataRole.UserRole + 1
_KEY_ROLE = Qt.ItemDataRole.UserRole + 2
_VALUE_ROLE = Qt.ItemDataRole.UserRole + 3
_OCCUPIED_ROLE = Qt.ItemDataRole.UserRole + 4
_CUSTOM_ROLE = Qt.ItemDataRole.UserRole + 5


class LabelMatrixModel(QAbstractListModel):
    """rows x columns slots, row-major; each slot CellSpec,
    CustomCellSpec, or None."""

    countChanged = Signal()   # occupied count changed
    gridChanged = Signal()    # rows/columns (and thus slot count) changed

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._rows = defaults.ROWS_DEFAULT
        self._columns = defaults.COLUMNS_DEFAULT
        self._slots: list[CellSpec | CustomCellSpec | None] = (
            [None] * (self._rows * self._columns)
        )

    # --- Grid shape ------------------------------------------------------

    @property
    def rows(self) -> int:
        return self._rows

    @property
    def columns(self) -> int:
        return self._columns

    @property
    def capacity(self) -> int:
        return self._rows * self._columns

    def set_grid(self, rows: int, columns: int) -> list[CellSpec | CustomCellSpec]:
        """Reshape the grid, repacking occupants in reading order.

        Returns the ENTRIES that no longer fit (reading-order tail) so
        the caller can uncheck the metadata ones — a placed field must
        never exist without a slot. Dropped custom cells just vanish;
        there is nothing to uncheck.
        """

        rows = max(1, min(defaults.MAX_ROWS, int(rows)))
        columns = max(1, min(defaults.MAX_COLUMNS, int(columns)))
        if rows == self._rows and columns == self._columns:
            return []

        occupants = [cell for cell in self._slots if cell is not None]
        capacity = rows * columns
        kept, dropped = occupants[:capacity], occupants[capacity:]

        self.beginResetModel()
        self._rows = rows
        self._columns = columns
        self._slots = kept + [None] * (capacity - len(kept))
        self.endResetModel()

        self.gridChanged.emit()
        if dropped:
            self.countChanged.emit()
        return dropped

    # --- Content sync ----------------------------------------------------

    def sync_cells(self, cells: list[CellSpec]) -> None:
        """Reconcile the metadata slots with the checked set.

        Surviving cells KEEP their slots (the user's arrangement is
        sacred), with texts refreshed in place — a new batch changes
        representative values without moving anything. Removed paths
        vacate their slots; new paths fill the first empty slot in
        check order. Custom cells are invisible here: never vacated,
        never refreshed — that is their session persistence.
        """

        incoming = {cell.path: cell for cell in cells}
        changed: list[int] = []
        count_moved = False

        for i, slot in enumerate(self._slots):
            if not isinstance(slot, CellSpec):
                continue
            replacement = incoming.pop(slot.path, None)
            if replacement is None:
                self._slots[i] = None
                changed.append(i)
                count_moved = True
            elif replacement != slot:
                self._slots[i] = replacement
                changed.append(i)

        additions = [cell for cell in cells if cell.path in incoming]
        for cell in additions:
            try:
                empty = self._slots.index(None)
            except ValueError:
                # Capacity is enforced upstream; reaching this means the
                # tree and grid disagree — log loudly, drop quietly.
                logger.warning("No free slot for %s", cell.path)
                break
            self._slots[empty] = cell
            changed.append(empty)
            count_moved = True

        for i in changed:
            idx = self.index(i, 0)
            self.dataChanged.emit(idx, idx)
        if count_moved:
            self.countChanged.emit()

    # --- Custom cells ----------------------------------------------------

    def set_custom_text(self, index: int, text: str) -> bool:
        """Create, edit, or (with empty text) remove a custom cell.

        Rules: text is stripped; empty slot + text -> create; custom
        slot + text -> replace in place; custom slot + empty -> vacate;
        empty slot + empty -> no-op False; metadata slot -> refused
        False (the tree owns it). Emits dataChanged for the slot and
        countChanged when occupancy moved.
        """

        if not (0 <= index < len(self._slots)):
            return False
        slot = self._slots[index]
        if isinstance(slot, CellSpec):
            return False
        text = text.strip()

        if slot is None:
            if not text:
                return False
            self._slots[index] = CustomCellSpec(text=text)
            occupancy_moved = True
        elif text:
            if slot.text == text:
                return True  # committed unchanged — nothing to announce
            self._slots[index] = CustomCellSpec(text=text)
            occupancy_moved = False
        else:
            self._slots[index] = None
            occupancy_moved = True

        idx = self.index(index, 0)
        self.dataChanged.emit(idx, idx)
        if occupancy_moved:
            self.countChanged.emit()
        return True

    @property
    def custom_count(self) -> int:
        return sum(1 for cell in self._slots if isinstance(cell, CustomCellSpec))

    # --- Reorder ---------------------------------------------------------

    def move(self, from_index: int, to_index: int) -> bool:
        """Move a cell to an empty slot, or swap with the occupant."""

        n = len(self._slots)
        if not (0 <= from_index < n) or not (0 <= to_index < n):
            return False
        if from_index == to_index:
            return False
        if self._slots[from_index] is None:
            return False

        self._slots[from_index], self._slots[to_index] = (
            self._slots[to_index],
            self._slots[from_index],
        )
        # Both slots changed content (occupied state included) — without
        # these announcements the QML cells never repaint after a drag.
        # Guarded by test_move_announces_both_slots; a mutation probe
        # proved the suite was blind to their loss before it existed.
        for i in (from_index, to_index):
            idx = self.index(i, 0)
            self.dataChanged.emit(idx, idx)
        return True

    # --- Queries ---------------------------------------------------------

    @property
    def occupied_count(self) -> int:
        return sum(1 for cell in self._slots if cell is not None)

    def placed_cells(self) -> list[tuple[int, int, CellSpec | CustomCellSpec]]:
        """(row, column, cell) for every occupied slot, reading order."""

        return [
            (i // self._columns, i % self._columns, cell)
            for i, cell in enumerate(self._slots)
            if cell is not None
        ]

    def reading_order_paths(self) -> list[str]:
        """Checked paths in grid order — metadata cells only, because
        the consumer (reorder_checked) requires exact set equality with
        the tree's checked set."""

        return [
            cell.path for cell in self._slots if isinstance(cell, CellSpec)
        ]

    def slots(self) -> list[CellSpec | CustomCellSpec | None]:
        return list(self._slots)

    # --- QAbstractListModel ----------------------------------------------

    def roleNames(self):  # noqa: N802 - Qt override
        return {
            int(_PATH_ROLE): b"path",
            int(_KEY_ROLE): b"keyText",
            int(_VALUE_ROLE): b"valueText",
            int(_OCCUPIED_ROLE): b"occupied",
            int(_CUSTOM_ROLE): b"custom",
        }

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._slots)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._slots)):
            return None
        cell = self._slots[index.row()]
        if role == _OCCUPIED_ROLE:
            return cell is not None
        if role == _CUSTOM_ROLE:
            return isinstance(cell, CustomCellSpec)
        if cell is None:
            return "" if role in (_PATH_ROLE, _KEY_ROLE, _VALUE_ROLE) else None
        if isinstance(cell, CustomCellSpec):
            # The custom string reads as a value with no key: the QML
            # delegate shows valueText and renders it spanning the cell.
            if role == _VALUE_ROLE:
                return cell.text
            if role in (_PATH_ROLE, _KEY_ROLE):
                return ""
            return None
        if role == _PATH_ROLE:
            return cell.path
        if role == _KEY_ROLE:
            return cell.key_text
        if role == _VALUE_ROLE:
            return cell.value_text
        return None
