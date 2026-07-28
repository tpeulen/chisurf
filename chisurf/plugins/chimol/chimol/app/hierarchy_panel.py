"""The panel that shows how a structure is organised, and switches parts of it off.

The tree comes from whichever reader read the file -- an RMF from IMP names its
nodes explicitly, an integrative mmCIF describes the same shape as entities and
the asym units that copy them. Each node knows which rows of the coordinate array
belong to it, which is what makes the check boxes possible: switching off
``Nup84`` is "do not draw these 10,560 beads", not a change of representation.
"""

from qtpy import QtCore, QtWidgets

from ..io.hierarchy import HierarchyNode

RmfHierarchyNode = HierarchyNode


class HierarchyModel(QtCore.QAbstractItemModel):
    """Qt model over a :class:`HierarchyNode` tree, with per-node visibility."""

    #: Emitted when a node's check state changes: (node, visible).
    visibility_changed = QtCore.Signal(object, bool)

    def __init__(self, root_node: HierarchyNode | None = None, parent=None):
        super().__init__(parent)
        self._root_node = root_node
        #: Nodes the user has switched off, by identity.
        self._hidden: set[int] = set()

    def set_root_node(self, node: HierarchyNode | None):
        """Replace the tree, clearing whatever was switched off in the old one."""
        self.beginResetModel()
        self._root_node = node
        self._hidden.clear()
        self.endResetModel()

    # ------------------------------------------------------------------ #
    # Shape
    # ------------------------------------------------------------------ #
    def rowCount(self, parent=QtCore.QModelIndex()):
        """How many children *parent* has; the root is the one top-level row."""
        if not self._root_node:
            return 0
        if not parent.isValid():
            return 1  # Root
        node = parent.internalPointer()
        return len(node.children)

    def columnCount(self, parent=QtCore.QModelIndex()):
        """One column: the tree is a list of names."""
        return 1

    def index(self, row, column, parent=QtCore.QModelIndex()):
        """Return the index of *parent*'s *row*-th child."""
        if not self.hasIndex(row, column, parent):
            return QtCore.QModelIndex()
        if not parent.isValid():
            return self.createIndex(row, column, self._root_node)
        parent_node = parent.internalPointer()
        if row < len(parent_node.children):
            child_node = parent_node.children[row]
            return self.createIndex(row, column, child_node)
        return QtCore.QModelIndex()

    def parent(self, index):
        """Return the index of *index*'s parent.

        A parent index has to carry the parent's own **row among its siblings**,
        or the view cannot place it. Returning row 0 for every parent, and
        calling the root's children top-level while row 0 of the top level was
        the root itself, made the model contradict itself: the tree drew the
        root twice and dropped the whole molecule level, so the nuclear pore's
        544 chains appeared as one flat list with the 31 nucleoporins that group
        them nowhere to be seen.
        """
        if not index.isValid():
            return QtCore.QModelIndex()
        node = index.internalPointer()
        if node is self._root_node:
            return QtCore.QModelIndex()
        parent_node = getattr(node, "parent", None)
        if parent_node is None:
            return QtCore.QModelIndex()
        return self.createIndex(self._row_of(parent_node), 0, parent_node)

    @staticmethod
    def _row_of(node) -> int:
        """Which row *node* occupies among its siblings.

        The root is the single row of the top level; anything else is found by
        identity in its parent's child list.
        """
        parent_node = getattr(node, "parent", None)
        if parent_node is None:
            return 0
        for row, child in enumerate(parent_node.children):
            if child is node:
                return row
        return 0

    # ------------------------------------------------------------------ #
    # Contents
    # ------------------------------------------------------------------ #
    def flags(self, index):
        """Every node is selectable and carries a check box."""
        if not index.isValid():
            return QtCore.Qt.NoItemFlags
        return (
            QtCore.Qt.ItemIsEnabled
            | QtCore.Qt.ItemIsSelectable
            | QtCore.Qt.ItemIsUserCheckable
        )

    def data(self, index, role=QtCore.Qt.DisplayRole):
        """Return the node's label, check state or tooltip, by *role*."""
        if not index.isValid():
            return None
        node = index.internalPointer()
        if role == QtCore.Qt.DisplayRole:
            label = f"{node.name} [{node.node_type}]"
            count = len(getattr(node, "atom_indices", ()) or ())
            return f"{label} — {count}" if count else label
        if role == QtCore.Qt.CheckStateRole:
            return self._check_state(node)
        if role == QtCore.Qt.ToolTipRole:
            count = len(getattr(node, "atom_indices", ()) or ())
            return (
                f"{node.node_type.title()} {node.name}\n{count} particles\n"
                "Un-check to hide them in the viewer."
            )
        return None

    def setData(self, index, value, role=QtCore.Qt.CheckStateRole):
        """Switch a node -- and everything under it -- on or off.

        A parent is not a thing of its own here: checking ``Nup84`` means
        checking its sixteen copies, because what is drawn are the copies' rows.
        """
        if not index.isValid() or role != QtCore.Qt.CheckStateRole:
            return False
        node = index.internalPointer()
        visible = QtCore.Qt.CheckState(value) != QtCore.Qt.Unchecked
        self._set_visible(node, visible)

        # The node's own subtree changed, and every ancestor's tri-state with it.
        top = index
        while top.isValid():
            self.dataChanged.emit(top, top, [QtCore.Qt.CheckStateRole])
            top = self.parent(top)
        self._emit_subtree_changed(index)
        self.visibility_changed.emit(node, visible)
        return True

    def _emit_subtree_changed(self, index) -> None:
        rows = self.rowCount(index)
        if rows:
            first = self.index(0, 0, index)
            last = self.index(rows - 1, 0, index)
            self.dataChanged.emit(first, last, [QtCore.Qt.CheckStateRole])
            for row in range(rows):
                self._emit_subtree_changed(self.index(row, 0, index))

    def _set_visible(self, node, visible: bool) -> None:
        if visible:
            self._hidden.discard(id(node))
        else:
            self._hidden.add(id(node))
        for child in node.children:
            self._set_visible(child, visible)

    def _check_state(self, node):
        """Read a node's check state from its leaves upward."""
        if not node.children:
            return (
                QtCore.Qt.Unchecked
                if id(node) in self._hidden
                else QtCore.Qt.Checked
            )
        states = {self._check_state(child) for child in node.children}
        if states == {QtCore.Qt.Checked}:
            return QtCore.Qt.Checked
        if states == {QtCore.Qt.Unchecked}:
            return QtCore.Qt.Unchecked
        return QtCore.Qt.PartiallyChecked

    def hidden_rows(self) -> list[int]:
        """Every coordinate row currently switched off.

        Returns
        -------
        list of int
            Row indices, deduplicated. Taken from the *leaves*, since a parent
            is switched off exactly when all of its children are.
        """
        rows: set[int] = set()

        def walk(node) -> None:
            if not node.children:
                if id(node) in self._hidden:
                    rows.update(getattr(node, "atom_indices", ()) or ())
                return
            for child in node.children:
                walk(child)

        if self._root_node is not None:
            walk(self._root_node)
        return sorted(rows)


class HierarchyFilter(QtCore.QSortFilterProxyModel):
    """Free-text filter that keeps a matching node's ancestors and descendants.

    A plain row filter is useless on a tree: matching ``Nup84`` hides the
    ``MOLECULE`` row it lives under, and Qt then has nothing to show it beneath.
    So a row survives when it matches, when any of its **descendants** match (or
    the branch to a hit disappears), or when one of its **ancestors** matches --
    the last is what lets a search for a molecule show the copies inside it
    rather than an empty expandable row.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        #: The needle, lower-cased. Held here rather than read back from Qt:
        #: ``setFilterFixedString`` populates ``filterRegExp`` on Qt 5 and
        #: ``filterRegularExpression`` on Qt 6, so reading the wrong one returns
        #: an empty pattern and *every row passes* -- a filter that silently
        #: does nothing, which is what happened first.
        self._needle = ""

    def set_filter_text(self, text: str) -> None:
        """Set the free-text needle and re-run the filter.

        Parameters
        ----------
        text : str
            Matched case-insensitively as a substring of a node's label. Empty
            shows everything.
        """
        self._needle = str(text or "").strip().lower()
        self.invalidateFilter()

    @property
    def needle(self) -> str:
        """The current filter text, lower-cased."""
        return self._needle

    def filterAcceptsRow(self, row: int, parent: QtCore.QModelIndex) -> bool:  # noqa: N802 - Qt API
        """Whether *row* under *parent* survives the current filter."""
        if not self._needle:
            return True
        index = self.sourceModel().index(row, 0, parent)
        if not index.isValid():
            return False
        if self._matches(index) or self._any_ancestor_matches(parent):
            return True
        return self._any_descendant_matches(index)

    def _matches(self, index: QtCore.QModelIndex) -> bool:
        """Whether this one node's text matches."""
        text = self.sourceModel().data(index, QtCore.Qt.DisplayRole)
        return self._needle in str(text or "").lower()

    def _any_ancestor_matches(self, index: QtCore.QModelIndex) -> bool:
        """Whether any node above this one matches."""
        while index.isValid():
            if self._matches(index):
                return True
            index = index.parent()
        return False

    def _any_descendant_matches(self, index: QtCore.QModelIndex) -> bool:
        """Whether any node below this one matches."""
        model = self.sourceModel()
        for row in range(model.rowCount(index)):
            child = model.index(row, 0, index)
            if self._matches(child) or self._any_descendant_matches(child):
                return True
        return False


class HierarchyDock(QtWidgets.QWidget):
    """Hierarchy panel — content widget (no outer QDockWidget wrapper)."""

    #: Emitted with the rows that should be hidden, whenever that set changes.
    hidden_rows_changed = QtCore.Signal(object)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._model = HierarchyModel()
        # The filter sits between the model and the view, so *what is typed*
        # never touches *what is switched off*: the check boxes act on the
        # source model, and clearing the search brings the tree back exactly as
        # it was. A filter that hid rows by un-checking them would silently
        # change the picture, which is the opposite of a search.
        self._filter = HierarchyFilter(self)
        self._filter.setSourceModel(self._model)
        self._filter.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self._filter.setRecursiveFilteringEnabled(True)

        self._search = QtWidgets.QLineEdit(self)
        self._search.setPlaceholderText("Filter (e.g. Nup84)")
        self._search.setClearButtonEnabled(True)
        self._search.setToolTip(
            "Show only nodes whose name matches. Filtering changes what the "
            "tree lists, never what is drawn -- the check boxes do that."
        )
        self._search.textChanged.connect(self._on_search_changed)

        self._tree = QtWidgets.QTreeView(self)
        self._tree.setModel(self._filter)
        self._tree.setHeaderHidden(True)
        self._tree.setAnimated(True)
        self._tree.setIndentation(16)
        self._tree.setExpandsOnDoubleClick(True)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self._search)
        layout.addWidget(self._tree)
        self._model.visibility_changed.connect(self._on_visibility_changed)

    def _on_search_changed(self, text: str) -> None:
        """Apply the filter, expanding to the hits so they are visible.

        A filtered tree that stays collapsed shows the user a root row and
        nothing else, which reads as "no matches" when there are plenty.
        """
        self._filter.set_filter_text(text)
        if str(text or "").strip():
            self._tree.expandAll()
        else:
            self._tree.collapseAll()
            self._tree.expandToDepth(1)

    def _on_visibility_changed(self, _node, _visible) -> None:
        self.hidden_rows_changed.emit(self._model.hidden_rows())

    def set_hierarchy(self, root_node: HierarchyNode | None) -> None:
        """Show *root_node*'s tree, expanded to the level below the root."""
        self._model.set_root_node(root_node)
        if root_node is not None:
            self._tree.expandToDepth(1)

    @property
    def model(self) -> HierarchyModel:
        """The tree model behind the view."""
        return self._model

    @property
    def tree_view(self) -> QtWidgets.QTreeView:
        """The view itself, for tests and for callers that need to expand it."""
        return self._tree

    @property
    def search_field(self) -> QtWidgets.QLineEdit:
        """The filter box above the tree."""
        return self._search

    @property
    def filter_model(self) -> HierarchyFilter:
        """The proxy the view actually shows; the source model keeps the state."""
        return self._filter
