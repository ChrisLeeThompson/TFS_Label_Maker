"""Fixed slot grid of the label's cells — an Excel-like matrix.

The user configures rows x columns; every slot is a fixed position
that is either empty, holds one checked field, or holds a user-typed
custom text. Checking fills the first empty slot, unchecking vacates a
slot (holes stay where they are), and a drag moves a cell to an empty
slot or swaps it with an occupant. Custom cells belong to the grid
alone: the tree's sync never touches them, which is what makes them
survive Clear and batch reloads. The grid's slot count minus the
custom cells is exactly the check capacity, enforced where checks happen (the
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
_OMITTED_ROLE = Qt.ItemDataRole.UserRole + 6


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
        # Path -> the slot it last occupied. A slot index is the only
        # record of a placement, so without this the arrangement dies
        # the moment a path vacates — which Clear does to every cell at
        # once. Kept for paths the caller still wants (see sync_cells'
        # `remembered`), single-valued per slot, session-only.
        self._home: dict[str, int] = {}

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
        # A reshape is a dense repack — it already destroys holes by
        # design, so remembered placements from the old shape mean
        # nothing. Rebuilt from where the survivors actually landed,
        # which is also what keeps out-of-range indices from existing.
        self._home = {
            cell.path: i
            for i, cell in enumerate(self._slots)
            if isinstance(cell, CellSpec)
        }
        self.endResetModel()

        self.gridChanged.emit()
        if dropped:
            self.countChanged.emit()
        return dropped

    # --- Content sync ----------------------------------------------------

    def _first_empty_slot(self) -> int | None:
        """The next slot a new check fills: column-wise, down column 1
        then down column 2 (explicit user preference — a two-column
        label reads as two stacks, so it should fill that way too).
        Holes refill at the first column-wise empty. Only the FILL
        order is column-major; reading order everywhere else stays
        row-major (grid geometry, eviction, grouping)."""

        for column in range(self._columns):
            for row in range(self._rows):
                index = row * self._columns + column
                if self._slots[index] is None:
                    return index
        return None

    def _claim_home(self, path: str, index: int) -> None:
        """Record where a path lives, evicting any stale claim on that
        slot — one remembered path per slot, so a return is never
        ambiguous."""

        for other, slot in list(self._home.items()):
            if slot == index and other != path:
                del self._home[other]
        self._home[path] = index

    def sync_cells(
        self, cells: list[CellSpec], remembered: set[str] | None = None
    ) -> None:
        """Reconcile the metadata slots with the checked set.

        Surviving cells KEEP their slots (the user's arrangement is
        sacred), with texts refreshed in place — a new batch changes
        representative values without moving anything. Removed paths
        vacate their slots; new paths return to their remembered slot
        when it is free, else fill column-wise in check order
        (_first_empty_slot). Custom cells are invisible here: never
        vacated, never refreshed — that is their session persistence.

        `remembered` is the set of paths whose PLACEMENT outlives the
        vacancy — the caller's still-wanted set. Clear empties the
        checked projection without touching intent, so without this
        every cell would vacate and the arrangement (holes included)
        would be lost; the refill would even transpose a full grid,
        because check order is row-major after a drag while the fill is
        column-major. Omitted (None) means forget every vacated path,
        which is what a bare model does.
        """

        remembered = remembered or set()
        incoming = {cell.path: cell for cell in cells}
        changed: list[int] = []
        count_moved = False

        for i, slot in enumerate(self._slots):
            if not isinstance(slot, CellSpec):
                continue
            replacement = incoming.pop(slot.path, None)
            if replacement is None:
                self._slots[i] = None
                # The slot is vacated either way; only the memory of it
                # is conditional — an unchecked path is gone for good,
                # a merely-absent one is coming back.
                if slot.path in remembered:
                    self._claim_home(slot.path, i)
                else:
                    self._home.pop(slot.path, None)
                changed.append(i)
                count_moved = True
            else:
                self._claim_home(slot.path, i)
                if replacement != slot:
                    self._slots[i] = replacement
                    changed.append(i)

        additions = [cell for cell in cells if cell.path in incoming]

        def place(cell: CellSpec, index: int) -> None:
            self._slots[index] = cell
            self._claim_home(cell.path, index)
            changed.append(index)

        # Homecomings first, so a returning cell cannot lose its slot to
        # a newcomer that merely sorted earlier.
        homeless = []
        for cell in additions:
            home = self._home.get(cell.path)
            if home is not None and 0 <= home < len(self._slots) \
                    and self._slots[home] is None:
                place(cell, home)
                count_moved = True
            else:
                homeless.append(cell)

        for cell in homeless:
            empty = self._first_empty_slot()
            if empty is None:
                # Capacity is enforced upstream; reaching this means the
                # tree and grid disagree — log loudly, drop quietly.
                logger.warning("No free slot for %s", cell.path)
                break
            place(cell, empty)
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
        # A drag re-homes what it moves: the slot a cell returns to
        # after a Clear is the one the user last parked it in.
        for i in (from_index, to_index):
            cell = self._slots[i]
            if isinstance(cell, CellSpec):
                self._claim_home(cell.path, i)
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
            int(_OMITTED_ROLE): b"omitted",
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
        if role == _OMITTED_ROLE:
            # Custom cells and holes are never omitted; the flag is the
            # policy-resolved ghost state the controller bakes in.
            return isinstance(cell, CellSpec) and cell.omitted
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
