"""Checkable tree of every metadata field found anywhere in the batch.

Two classes: MetadataTreeModel holds the FieldNode hierarchy and the
check state that feeds the label matrix; MetadataFilterProxy sits
between it and the QML TreeView to implement search.

The tree is the batch's union and is structurally stable while the
user cycles the current image: Previous/Next never rebuild the tree,
they only swap which image's values the value column shows (fields the
current image lacks render dimmed with an empty value). Partial fields
— present in some contributing images but not all — carry an "n/m"
presence badge; presence is the only cross-image fact shown, so the
tree stays a selector, not a comparator.

Check state is mutated by dotted path string, never by QModelIndex from
QML — paths are the identity currency shared with the accumulator and
the label cells, and they stay valid across the model resets that
indexes do not survive.

Check state is session-only by explicit user decision: nothing about
the selected fields is written to QSettings; a fresh launch starts
clean. Within a session it is durable: a private "desired" intent list
(``_desired``) records what the user has chosen and is mutated only by
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
# synthesized cross-dialect group and no per-field "varies" badge —
# the tree is a selector, not a comparator, so it shows exactly the
# raw categories found in the batch, under the names the ASV Project
# Explorer uses for the same data (display-only: the dotted paths keep
# their Microscope./XML. prefixes, so remembered checks survive).
# Partial fields stay inline in these natural groups; a synthesized
# "Partial." prefix would break canonical's unit/kind lookup, which is
# keyed on the real prefixes.
_GROUP_ORDER = {"Microscope": 0, "XML": 1}
_GROUP_TITLES = canonical.GROUP_DISPLAY_TITLES

_VALUE_ROLE = Qt.ItemDataRole.UserRole + 1
_PATH_ROLE = Qt.ItemDataRole.UserRole + 2
_CHECKED_ROLE = Qt.ItemDataRole.UserRole + 3
_IS_LEAF_ROLE = Qt.ItemDataRole.UserRole + 4
_PRESENCE_COUNT_ROLE = Qt.ItemDataRole.UserRole + 5
_PRESENCE_TOTAL_ROLE = Qt.ItemDataRole.UserRole + 6
_PRESENT_IN_CURRENT_ROLE = Qt.ItemDataRole.UserRole + 7


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
    """The batch's union of fields, one checkable row per value.

    The value column is a VIEWPORT onto one image — the current image
    the user has cycled to — never an aggregate. ``set_current_image``
    swaps that viewport without touching the tree structure or the
    check state, so cycling can never reshuffle grid slots or collapse
    the TreeView's expansion state.

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
        # Presence: path -> contributing images carrying it (the badge's
        # "n"), the contributor total (the "m"), and which known paths
        # the current image has (drives dimming while cycling).
        self._presence: dict[str, int] = {}
        self._contributors = 0
        self._present: set[str] = set()
        # Session intent — what the user has chosen, in pick order.
        # Mutated only by explicit user action (setChecked/clearChecks/
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

    def populate(self, paths, values, presence=None, contributors=0) -> None:
        """Rebuild from a finished parse. Batch, never incremental — a
        removed file can shrink the union, so an incrementally grown
        tree could keep a field no remaining image carries.

        ``values`` is the current image's flat dict (any values dict
        works — paths it lacks simply show empty and dim). ``presence``
        maps path -> contributing-image count for the "n/m" badges;
        None means fully present (the single-image and unit-test case).
        """

        self.beginResetModel()
        path_set = set(paths)
        self._root, self._by_path = build_tree(path_set)
        if presence is None:
            self._contributors = contributors or 1
            self._presence = {path: self._contributors for path in path_set}
        else:
            self._contributors = int(contributors)
            self._presence = dict(presence)
        self._rebuild_display(values)
        self._field_count = sum(1 for n in self._root.walk() if n.is_leaf)
        self._project_checks()
        self.endResetModel()
        # Always re-announce: the projected set differs per batch even
        # when nothing was toggled, and canStart listens to this.
        self.checkedChanged.emit()

    def _rebuild_display(self, values) -> None:
        """Format the current image's values for the known paths.

        A known path absent from ``values`` gets no display entry — it
        renders as an empty value and dims. The em dash stays reserved
        for present-but-empty values, mirroring the export policy's
        distinction between "field missing" and "field blank".
        """

        known = self._by_path
        self._display = {
            path: _display_for(path, value)
            for path, value in values.items()
            if path in known
        }
        self._present = set(self._display)

    def set_current_image(self, values) -> None:
        """Swap which image's values the value column shows.

        Touches neither the tree structure nor the check intent — no
        model reset, so the TreeView's expansion state and the grid's
        slot assignments survive cycling. Announces only the two roles
        that actually changed, one ranged dataChanged per parent node
        (dataChanged cannot span parents in a tree model).
        """

        self._rebuild_display(values)
        self._emit_subtree_changed(
            [_VALUE_ROLE, _PRESENT_IN_CURRENT_ROLE]
        )

    def _emit_subtree_changed(self, roles: list[int]) -> None:
        def visit(parent: FieldNode) -> None:
            children = parent.children
            if not children:
                return
            first = self.createIndex(0, 0, children[0])
            last = self.createIndex(len(children) - 1, 0, children[-1])
            self.dataChanged.emit(first, last, roles)
            for child in children:
                visit(child)

        visit(self._root)

    def clear_fields(self) -> None:
        # Empties the tree and the projection, but not _desired — the
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
        # Guard against the visible state — the checkbox the user sees.
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
        """Adopt the label grid's free slot count as the check limit.

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

    def desired_paths(self) -> list[str]:
        """The session intent, including entries this batch lacks.

        The label grid keeps a cell's placement for exactly as long as
        this list keeps its path: a Clear empties the projection but not
        the intent, so the arrangement returns with the next batch,
        while an uncheck forgets both.
        """

        return list(self._desired)

    def reorder_checked(self, paths: list[str]) -> None:
        """Adopt the grid's reading order as the new check order.

        The guard is against the visible set (the grid only ever
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
        """The formatted value the tree shows for the current image —
        the matrix cell shows the same string, so the two surfaces can
        never disagree about the image being previewed. Empty when the
        current image lacks the path."""

        return self._display.get(path, "")

    def present_in_current(self, path: str) -> bool:
        """Whether the current image carries this path at all —
        present-but-empty counts as present (it has an em dash to
        show); only true absence dims and, under the omit policy,
        ghosts the grid cell."""

        return path in self._present

    @staticmethod
    def display_key(path: str) -> str:
        return canonical.display_key(path)

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
            int(_PRESENCE_COUNT_ROLE): b"presenceCount",
            int(_PRESENCE_TOTAL_ROLE): b"presenceTotal",
            int(_PRESENT_IN_CURRENT_ROLE): b"presentInCurrent",
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
        if role == _PRESENCE_COUNT_ROLE:
            return self._presence.get(node.path, 0) if node.is_leaf else 0
        if role == _PRESENCE_TOTAL_ROLE:
            return self._contributors
        if role == _PRESENT_IN_CURRENT_ROLE:
            # Pure branches never dim; value-bearing rows dim on absence.
            return node.path in self._present if node.is_leaf else True
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
