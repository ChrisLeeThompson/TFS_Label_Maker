"""Checkable tree of the metadata fields common to the loaded batch.

Two classes: MetadataTreeModel holds the FieldNode hierarchy and the
check state that feeds the label matrix; MetadataFilterProxy sits
between it and the QML TreeView to implement search.

Check state is mutated by dotted path string, never by QModelIndex from
QML — paths are the identity currency shared with the accumulator and
the label cells, and they stay valid across the model resets that
indexes do not survive.

Check state is SESSION-ONLY by explicit user decision: nothing about
the selected fields is written to QSettings; a fresh launch starts
clean. Within a session it is durable: a private "desired" intent list
(``_desired``) records what the user has chosen and is mutated ONLY by
explicit user action — never by ``populate``. The visible check state
(``_checked``) is always the pure projection of that intent onto the
current batch: ``[p for p in _desired if p is a live leaf][:capacity]``.

So a field absent from one batch falls out of the projection but stays
in the intent, and reappears checked the moment a later batch carries
it again (the in-memory twin of the removed ``v1/checkedFields`` store);
Clear empties the tree but preserves the intent. Only "Deselect all"
and explicitly unchecking a field forget intent.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import (
    Property,
    QAbstractItemModel,
    QModelIndex,
    QObject,
    QSortFilterProxyModel,
    Qt,
    Signal,
    Slot,
)

from .. import defaults
from . import canonical
from .records import FieldNode

logger = logging.getLogger(__name__)

# Fixed presentation order of the dialect groups. There is no
# synthesized cross-dialect group and no per-field "varies" badge any
# more — the tree is a selector, not a comparator, so it shows exactly
# the raw categories the files share, under the names the ASV Project
# Explorer uses for the same data (display-only: the dotted paths keep
# their Microscope./XML. prefixes, so persisted checks survive).
_GROUP_ORDER = {"Microscope": 0, "XML": 1}
_GROUP_TITLES = canonical.GROUP_DISPLAY_TITLES

_VALUE_ROLE = Qt.ItemDataRole.UserRole + 1
_PATH_ROLE = Qt.ItemDataRole.UserRole + 2
_CHECKED_ROLE = Qt.ItemDataRole.UserRole + 3
_IS_LEAF_ROLE = Qt.ItemDataRole.UserRole + 4


def _display_for(path: str, value) -> str:
    """canonical.format_for_path, but total. An exception here would
    abort populate mid-reset and blank the whole tree over one exotic
    value — a NaN in a real sample's INI already caught the formatter
    out once. Canonical-aware so the tree shows the same "3 kV" the
    label output writes."""

    try:
        return canonical.format_for_path(path, value)
    except Exception:  # noqa: BLE001 — fault isolation on external data
        logger.exception("Could not format %r for display", value)
        return str(value)


def build_tree(paths: set[str]) -> tuple[FieldNode, dict[str, FieldNode]]:
    """Grow a FieldNode hierarchy from dotted flat paths.

    Children come out alphabetically (case-insensitive) at every level —
    the source is a set, so there is no insertion order to preserve —
    except the top level, which follows the fixed dialect-group order.

    A path can be both value-bearing and a branch (FEI XML puts text on
    elements that also have children); is_leaf marks "has a value", not
    "has no children".
    """

    root = FieldNode(key="", path="")
    by_path: dict[str, FieldNode] = {}

    def node_for(dotted: str) -> FieldNode:
        node = by_path.get(dotted)
        if node is not None:
            return node
        head, _, key = dotted.rpartition(".")
        parent = node_for(head) if head else root
        node = parent.add(FieldNode(key=key, path=dotted))
        by_path[dotted] = node
        return node

    for path in sorted(paths, key=str.lower):
        node_for(path).is_leaf = True

    root.children.sort(
        key=lambda n: (_GROUP_ORDER.get(n.key, len(_GROUP_ORDER)), n.key.lower())
    )
    return root, by_path


class MetadataTreeModel(QAbstractItemModel):
    """The batch's common fields, one checkable row per value.

    The model owns strong references to every FieldNode (via _root and
    _by_path). That is not housekeeping: PySide will not keep a Python
    object alive from a raw internalPointer(), and dropping the nodes
    while QML holds indexes is the classic hand-written-tree-model
    crash. Nodes are only ever replaced wholesale inside a model reset.
    """

    checkedChanged = Signal()
    capacityReached = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._root = FieldNode(key="", path="")
        self._by_path: dict[str, FieldNode] = {}
        self._display: dict[str, str] = {}
        self._field_count = 0
        # Session intent — what the user has chosen, in pick order.
        # Mutated ONLY by explicit user action (setChecked/clearChecks/
        # set_capacity shrink/reorder), never by populate. Durable within
        # the session, unbounded (the projection applies the cap).
        self._desired: list[str] = []
        # Live projection of _desired onto the current batch, capped.
        # This is what QML and the label grid read; check order is
        # preserved — "the order I picked them".
        self._checked: list[str] = []
        self._checked_set: set[str] = set()
        # The label grid's slot count; the grid controls re-set it when
        # the user resizes the matrix.
        self._capacity = defaults.MAX_CELLS

    # --- Population ------------------------------------------------------

    def populate(self, common_paths, values) -> None:
        """Rebuild from a finished parse. Batch, never incremental — the
        intersection shrinks monotonically, so an incrementally grown
        tree could show a field that a later file then removes."""

        self.beginResetModel()
        self._root, self._by_path = build_tree(set(common_paths))
        self._display = {
            path: _display_for(path, values[path])
            for path in common_paths
            if path in values
        }
        self._field_count = sum(1 for n in self._root.walk() if n.is_leaf)
        self._project_checks()
        self.endResetModel()
        # Always re-announce: the projected set differs per batch even
        # when nothing was toggled, and canStart listens to this.
        self.checkedChanged.emit()

    def clear_fields(self) -> None:
        # Empties the tree AND the projection, but NOT _desired — the
        # user's intent survives Clear and returns on the next batch.
        self.populate(set(), {})

    def _project_checks(self) -> None:
        """Recompute the live projection from intent; never mutate intent.

        The visible checked set is exactly the desired paths that are
        live leaves in the current batch, in desired order, capped. A
        field the batch lacks is simply absent from the projection while
        staying in ``_desired``, so it returns when a later batch has it.
        Called inside a model reset (no per-row notify needed).
        """

        self._checked = [
            path for path in self._desired
            if (node := self._by_path.get(path)) is not None and node.is_leaf
        ][: self._capacity]
        self._checked_set = set(self._checked)

    def _reproject_and_notify(self) -> None:
        """Re-project after an intent change and announce the delta.

        dataChanged only for the rows whose checkbox flipped (symmetric
        difference), and one checkedChanged if the visible set changed.
        """

        before = self._checked_set
        self._project_checks()
        for path in before ^ self._checked_set:
            node = self._by_path.get(path)
            if node is not None:
                self._notify_row(node)
        if before ^ self._checked_set:
            self.checkedChanged.emit()

    # --- Check state -----------------------------------------------------

    @Slot(str, bool)
    def setChecked(self, path: str, checked: bool) -> None:
        node = self._by_path.get(path)
        if node is None or not node.is_leaf:
            return
        # Guard against the VISIBLE state — the checkbox the user sees.
        if checked == (path in self._checked_set):
            return
        # Capacity is gated on the live projection: a refused check
        # never enters _desired, so it is not remembered.
        if checked and len(self._checked) >= self._capacity:
            self.capacityReached.emit()
            # The delegate's checkbox has already painted itself checked;
            # announcing the (unchanged) role snaps it back.
            self._notify_row(node)
            return
        if checked:
            if path not in self._desired:
                self._desired.append(path)
        else:
            if path in self._desired:
                self._desired.remove(path)
        self._reproject_and_notify()

    @Slot()
    def clearChecks(self) -> None:
        """Forget the whole session intent in one announcement — the one
        action that clears dormant (currently-absent) desired fields too.
        A full clear as individual unchecks would rebuild the label
        matrix once per field."""

        if not self._desired:
            return
        self._desired.clear()
        self._reproject_and_notify()

    def set_capacity(self, capacity: int) -> None:
        """Adopt the label grid's FREE slot count as the check limit.

        Zero is legal: custom text cells occupy slots without being
        checks, so an all-custom grid leaves no room for any field.
        Shrinking below the current selection forgets the overflow from
        the END of check order (a grid shrink is an explicit give-up, so
        it drops from intent, not just the projection) — the most
        recently picked fields yield first, never the earliest choices.
        """

        capacity = max(0, int(capacity))
        if capacity == self._capacity:
            return
        self._capacity = capacity
        present = [
            p for p in self._desired
            if (n := self._by_path.get(p)) is not None and n.is_leaf
        ]
        overflow = present[capacity:]
        if overflow:
            drop = set(overflow)
            self._desired = [p for p in self._desired if p not in drop]
        self._reproject_and_notify()

    @Property(int, notify=checkedChanged)
    def checkedCount(self) -> int:
        return len(self._checked)

    def checked_paths(self) -> list[str]:
        """In check order — the label matrix's initial cell order."""

        return list(self._checked)

    def reorder_checked(self, paths: list[str]) -> None:
        """Adopt the grid's reading order as the new check order.

        The guard is against the VISIBLE set (the grid only ever
        reorders the cells it shows). The new visible order is written
        to the FRONT of the intent, with dormant/absent desired entries
        preserved after it — so a visible-subset drag never loses intent
        that this batch happens not to show. Deliberately emits nothing:
        the grid already displays the new arrangement, and a
        checkedChanged bounce would rebuild it out from under the drop.
        """

        if len(paths) != len(self._checked) or set(paths) != self._checked_set:
            logger.warning("Reorder rejected: path set does not match")
            return
        visible = set(paths)
        self._desired = list(paths) + [p for p in self._desired if p not in visible]
        self._checked = list(paths)
        self._checked_set = set(self._checked)

    def display_value(self, path: str) -> str:
        """The formatted value the tree shows — the matrix cell shows
        the same string, so the two surfaces can never disagree."""

        return self._display.get(path, "")

    @staticmethod
    def display_key(path: str) -> str:
        return path.rsplit(".", 1)[-1]

    # --- Python-side queries ---------------------------------------------

    @property
    def field_count(self) -> int:
        return self._field_count

    def leaf_paths(self) -> list[str]:
        return [n.path for n in self._root.walk() if n.is_leaf]

    # --- QAbstractItemModel ----------------------------------------------

    def roleNames(self):  # noqa: N802 - Qt override
        return {
            int(Qt.ItemDataRole.DisplayRole): b"display",
            int(_VALUE_ROLE): b"value",
            int(_PATH_ROLE): b"path",
            int(_CHECKED_ROLE): b"checked",
            int(_IS_LEAF_ROLE): b"isLeaf",
        }

    def index(self, row: int, column: int, parent: QModelIndex = QModelIndex()) -> QModelIndex:
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        node = parent.internalPointer() if parent.isValid() else self._root
        return self.createIndex(row, column, node.children[row])

    def parent(self, index: QModelIndex = QModelIndex()) -> QModelIndex:
        if not index.isValid():
            return QModelIndex()
        node = index.internalPointer()
        parent = node.parent
        if parent is None or parent is self._root:
            return QModelIndex()
        grand = parent.parent if parent.parent is not None else self._root
        return self.createIndex(grand.children.index(parent), 0, parent)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.column() > 0:
            return 0
        node = parent.internalPointer() if parent.isValid() else self._root
        return len(node.children)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 1

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        node: FieldNode = index.internalPointer()
        if role == Qt.ItemDataRole.DisplayRole:
            if node.parent is self._root:
                return _GROUP_TITLES.get(node.key, node.key)
            return node.key
        if role == _VALUE_ROLE:
            return self._display.get(node.path, "")
        if role == _PATH_ROLE:
            return node.path
        if role == _CHECKED_ROLE:
            return node.path in self._checked_set
        if role == _IS_LEAF_ROLE:
            return node.is_leaf
        return None

    def _notify_row(self, node: FieldNode) -> None:
        parent = node.parent
        if parent is None:
            return
        idx = self.createIndex(parent.children.index(node), 0, node)
        self.dataChanged.emit(idx, idx, [_CHECKED_ROLE])


class MetadataFilterProxy(QSortFilterProxyModel):
    """ATC-style search: case-insensitive substring over the displayed
    key and value text; a match keeps its ancestors visible
    (recursiveFilteringEnabled) and reveals all of its descendants
    (autoAcceptChildRows) — searching "pattern" must show
    PatternCenterPositionPx and its X/Y children.
    """

    searchTextChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._raw = ""
        self._needle = ""
        self.setRecursiveFilteringEnabled(True)
        self.setAutoAcceptChildRows(True)

    @Property(str, notify=searchTextChanged)
    def searchText(self) -> str:
        return self._raw

    @searchText.setter
    def searchText(self, text: str) -> None:
        if text == self._raw:
            return
        self._raw = text
        self._needle = text.strip().lower()
        self.invalidateRowsFilter()
        self.searchTextChanged.emit()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:  # noqa: N802
        if not self._needle:
            return True
        model = self.sourceModel()
        idx = model.index(source_row, 0, source_parent)
        key = str(model.data(idx, Qt.ItemDataRole.DisplayRole) or "")
        if self._needle in key.lower():
            return True
        value = str(model.data(idx, _VALUE_ROLE) or "")
        return self._needle in value.lower()
