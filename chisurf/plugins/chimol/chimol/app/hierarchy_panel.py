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


class HierarchyDock(QtWidgets.QWidget):
    """Hierarchy panel — content widget (no outer QDockWidget wrapper)."""

    #: Emitted with the rows that should be hidden, whenever that set changes.
    hidden_rows_changed = QtCore.Signal(object)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._model = HierarchyModel()
        self._tree = QtWidgets.QTreeView(self)
        self._tree.setModel(self._model)
        self._tree.setHeaderHidden(True)
        self._tree.setAnimated(True)
        self._tree.setIndentation(16)
        self._tree.setExpandsOnDoubleClick(True)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._tree)
        self._model.visibility_changed.connect(self._on_visibility_changed)

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
