"""List model of the images currently loaded."""

from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path

from PySide6.QtCore import QAbstractListModel, QByteArray, QModelIndex, Qt

logger = logging.getLogger(__name__)


class ParseState(str, Enum):
    PENDING = "pending"
    OK = "ok"
    FAILED = "failed"


class DroppedImagesModel(QAbstractListModel):
    """The loaded image set, in the order the user added it.

    Rows carry a parse state so a batch can report per-file failures
    without aborting: a file that fails to parse stays in the list marked
    FAILED rather than vanishing, which is what lets the status bar say
    "48 of 50" and still name the two that did not work.
    """

    FileNameRole = Qt.ItemDataRole.UserRole + 1
    FilePathRole = Qt.ItemDataRole.UserRole + 2
    ParseStateRole = Qt.ItemDataRole.UserRole + 3
    FailureReasonRole = Qt.ItemDataRole.UserRole + 4

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._paths: list[Path] = []
        self._states: dict[Path, ParseState] = {}
        self._reasons: dict[Path, str] = {}

    # --- QAbstractListModel ---------------------------------------------

    def rowCount(self, parent=QModelIndex()) -> int:
        # A list model has no children under a valid index; returning the
        # row count there would make the view recurse forever.
        if parent.isValid():
            return 0
        return len(self._paths)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._paths)):
            return None
        path = self._paths[index.row()]
        if role in (self.FileNameRole, Qt.ItemDataRole.DisplayRole):
            return path.name
        if role == self.FilePathRole:
            return str(path)
        if role == self.ParseStateRole:
            return self._states.get(path, ParseState.PENDING).value
        if role == self.FailureReasonRole:
            return self._reasons.get(path, "")
        return None

    def roleNames(self) -> dict[int, QByteArray]:
        return {
            self.FileNameRole: QByteArray(b"fileName"),
            self.FilePathRole: QByteArray(b"filePath"),
            self.ParseStateRole: QByteArray(b"parseState"),
            self.FailureReasonRole: QByteArray(b"failureReason"),
        }

    # --- Mutation --------------------------------------------------------

    def add_paths(self, paths: list[Path]) -> int:
        """Append paths. Returns how many were added."""

        if not paths:
            return 0
        first = len(self._paths)
        last = first + len(paths) - 1
        self.beginInsertRows(QModelIndex(), first, last)
        for path in paths:
            self._paths.append(path)
            self._states[path] = ParseState.PENDING
        self.endInsertRows()
        return len(paths)

    def remove_at(self, row: int) -> bool:
        if not (0 <= row < len(self._paths)):
            return False
        self.beginRemoveRows(QModelIndex(), row, row)
        path = self._paths.pop(row)
        self._states.pop(path, None)
        self._reasons.pop(path, None)
        self.endRemoveRows()
        return True

    def clear(self) -> None:
        if not self._paths:
            return
        self.beginResetModel()
        self._paths.clear()
        self._states.clear()
        self._reasons.clear()
        self.endResetModel()

    def set_state(
        self, path: Path, state: ParseState, reason: str = ""
    ) -> None:
        try:
            row = self._paths.index(path)
        except ValueError:
            return
        self._states[path] = state
        if reason:
            self._reasons[path] = reason
        else:
            self._reasons.pop(path, None)
        index = self.index(row, 0)
        self.dataChanged.emit(
            index, index, [self.ParseStateRole, self.FailureReasonRole]
        )

    def reset_states(self) -> None:
        """Mark every row pending again, before a fresh parse run."""

        if not self._paths:
            return
        for path in self._paths:
            self._states[path] = ParseState.PENDING
        self._reasons.clear()
        self.dataChanged.emit(
            self.index(0, 0),
            self.index(len(self._paths) - 1, 0),
            [self.ParseStateRole, self.FailureReasonRole],
        )

    # --- Queries ---------------------------------------------------------

    def paths(self) -> list[Path]:
        return list(self._paths)

    def path_set(self) -> set[Path]:
        """Used by discovery to reject files that are already loaded."""

        return set(self._paths)

    def failures(self) -> list[tuple[str, str]]:
        return [
            (str(path), self._reasons.get(path, ""))
            for path in self._paths
            if self._states.get(path) is ParseState.FAILED
        ]

    def count_in_state(self, state: ParseState) -> int:
        return sum(1 for s in self._states.values() if s is state)
