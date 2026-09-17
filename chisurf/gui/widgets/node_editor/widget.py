"""The node editor as a ``QWidget``, for the places ChiSurf still needs one.

The editor itself is :class:`~.emtk_control.GraphControl`, which knows nothing
about Qt. This module is the twelve lines that put it in a window: a
:func:`emtk.qt_host.ControlHost` around the control, plus the Qt signals the
existing consumers connect to.

Keeping the split is the point of the rewrite. The same control is what a
browser host draws and what a headless test drives, so there is one editor
rather than one per surface -- which is exactly what the ``QGraphicsScene``
version could not offer, since every one of its nodes *was* a Qt object.
"""

from __future__ import annotations

import json
import logging

from emtk.qt_host import ControlHost
from qtpy import QtCore, QtWidgets

from .document import GraphDocument
from .emtk_control import GraphControl, NodeContentRenderer

__all__ = ["NodeGraphWidget"]

logger = logging.getLogger(__name__)

#: Point size the editor's text is drawn at. The controls inside a node are
#: monospaced, as emtk's are throughout.
DEFAULT_FONT_PT: float = 9.0

#: The editor's backdrop. emtk's node editor paints its own grid over this, so
#: it only shows through where the grid does not reach.
DEFAULT_BACKGROUND: tuple = (30, 32, 38, 255)


class NodeGraphWidget(QtWidgets.QWidget):
    """A node editor in a widget, over one :class:`~.document.GraphDocument`.

    Parameters
    ----------
    parent : QtWidgets.QWidget, optional
        Qt parent.
    read_only : bool
        Refuse edits. Navigation and selection still work.
    content : NodeContentRenderer, optional
        What to draw inside node bodies.
    show_minimap : bool
        Draw the corner minimap.

    Attributes
    ----------
    graphChanged : QtCore.Signal
        Emitted after any edit that changed the graph.
    nodeSelected : QtCore.Signal
        Emitted with the selected node's serialised form.
    edgeSelected : QtCore.Signal
        Emitted with the selected edge's serialised form.
    nodeActivated : QtCore.Signal
        Emitted with the node's serialised form on a double-click *on* a node.
    selectionCleared : QtCore.Signal
        Emitted when the selection empties -- the background was clicked, the
        selection was deleted, or a new graph was loaded. ``nodeSelected``
        only ever fires when something *is* selected, so a host whose detail
        panel follows the graph needs this to know when to stop describing.
    """

    graphChanged = QtCore.Signal()
    nodeSelected = QtCore.Signal(dict)
    edgeSelected = QtCore.Signal(dict)
    nodeActivated = QtCore.Signal(dict)
    selectionCleared = QtCore.Signal()

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        *,
        read_only: bool = False,
        content: NodeContentRenderer | None = None,
        show_minimap: bool = True,
    ) -> None:
        super().__init__(parent)
        self.control = GraphControl(
            GraphDocument(),
            read_only=read_only,
            content=content,
            on_change=self._on_control_changed,
            on_select=self._on_control_selected,
        )
        self.control.show_minimap = bool(show_minimap)

        self.host = ControlHost(
            self.control,
            font_pt=DEFAULT_FONT_PT,
            background=DEFAULT_BACKGROUND,
            parent=self,
        )
        # Focus so the editor can receive Delete and the fit shortcut; without
        # it the keys go to whatever had focus last and the editor looks
        # unresponsive to the keyboard.
        self.host.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.host.setMouseTracking(True)
        # Watched, not overridden: the double-click still reaches the control
        # (and folds the node, where editing is allowed) -- the filter only
        # listens, which is how a read-only viewer still gets ``nodeActivated``.
        self.host.installEventFilter(self)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.host)

    # -- what the consumers call ----------------------------------------

    @property
    def document(self) -> GraphDocument:
        """The graph currently loaded.

        Returns
        -------
        GraphDocument
        """
        return self.control.document

    def load_graph_dict(self, data: dict) -> None:
        """Replace the graph from schema v1.

        Parameters
        ----------
        data : dict
            A graph as ``json_schema.md`` describes it.
        """
        self.control.set_document(GraphDocument.from_dict(data or {}))
        self.host.update()

    def load_graph_from_json(self, text: str) -> None:
        """Replace the graph from a JSON string.

        Parameters
        ----------
        text : str
            JSON in schema v1.
        """
        self.load_graph_dict(json.loads(text))

    def load_graph_from_file(self, path) -> None:
        """Replace the graph from a JSON file.

        Parameters
        ----------
        path : str or pathlib.Path
            The file to read.
        """
        with open(path, encoding="utf-8") as handle:
            self.load_graph_from_json(handle.read())

    def graph_dict(self) -> dict:
        """Serialise the graph.

        Returns
        -------
        dict
            Schema v1.
        """
        return self.control.document.to_dict()

    def to_json(self) -> str:
        """Serialise the graph to a JSON string.

        Returns
        -------
        str
        """
        return self.control.document.to_json()

    def save_graph_to_file(self, path) -> None:
        """Write the graph to a JSON file.

        Parameters
        ----------
        path : str or pathlib.Path
            The file to write.
        """
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(self.to_json())

    def clear_graph(self) -> None:
        """Empty the graph."""
        self.control.set_document(GraphDocument(), fit=False)
        self.host.update()

    def fit_graph(self) -> None:
        """Frame the whole graph.

        Notes
        -----
        Takes effect on the next repaint, not on this call: fitting needs the
        measured size of every node, and a node has no size until it has been
        drawn. Calling this before the first paint and expecting it to have
        happened is what renders a graph as a speck in the middle of the view.
        """
        self.control.fit()
        self.host.update()

    def set_read_only(self, read_only: bool) -> None:
        """Allow or refuse edits.

        Parameters
        ----------
        read_only : bool
            ``True`` to refuse them.
        """
        self.control.read_only = bool(read_only)
        self.control._sync_positions()
        self.host.update()

    def selected_node(self) -> dict:
        """The selected node's serialised form.

        Returns
        -------
        dict
            Empty when nothing is selected.
        """
        from emtk import nodes

        chosen = nodes.get_selected_nodes(self.control.editor)
        if not chosen:
            return {}
        node = self.control.document.node_for_number(chosen[0])
        return self.control._node_payload(node) if node is not None else {}

    def selected_edge(self) -> dict:
        """The selected edge's serialised form.

        Returns
        -------
        dict
            Empty when nothing is selected.
        """
        from emtk import nodes

        chosen = nodes.get_selected_links(self.control.editor)
        if not chosen:
            return {}
        edge = self.control.document.edge_for_link(chosen[0])
        return self.control._edge_payload(edge) if edge is not None else {}

    def select_node(self, node_id: str, reveal: bool = True) -> bool:
        """Select the node with *node_id*, as a programmatic selection.

        Parameters
        ----------
        node_id : str
            The node to select. Unknown ids are refused, not ignored, so a
            caller whose model drifted from the picture finds out.
        reveal : bool
            Pan the node into view when it is off screen. Never recentres:
            a selection made in the graph must not yank the view sideways
            under the cursor, so this only scrolls when it has to -- the same
            contract the scene viewer's ``ensureVisible`` had.

        Returns
        -------
        bool
            ``True`` when the node exists and is now the selection.
        """
        from emtk import nodes

        node = self.document.node(str(node_id))
        if node is None:
            return False
        number = self.document.node_number(node.id)
        if not nodes.is_node_selected(self.control.editor, number):
            nodes.clear_node_selection(self.control.editor)
            nodes.clear_link_selection(self.control.editor)
            nodes.select_node(self.control.editor, number)
        if reveal:
            self._reveal_node(number)
        self.host.update()
        return True

    def _reveal_node(self, number: int) -> None:
        """Pan the node into the visible box, only when it is not in it.

        Parameters
        ----------
        number : int
            The node's renderer number (its index in the document).

        Notes
        -----
        A node not drawn yet measures ``(0, 0)``; the nominal floor below
        keeps such a node from sitting exactly under an edge and counting as
        visible while showing only its title bar's first pixels.
        """
        from emtk import nodes

        editor = self.control.editor
        canvas = editor.canvas
        pos = nodes.get_node_grid_space_pos(editor, number)
        width, height = nodes.get_node_dimensions(editor, number)
        width = max(width, 40.0)
        height = max(height, 24.0)

        _, _, box_w, box_h = self.control._box
        margin = 40.0
        # Editor space: grid space after zoom and pan, relative to the box.
        nx = pos[0] * canvas.zoom + canvas.panning[0]
        ny = pos[1] * canvas.zoom + canvas.panning[1]
        dx = dy = 0.0
        if nx < margin or width > box_w - 2.0 * margin:
            dx = margin - nx
        elif nx + width > box_w - margin:
            dx = (box_w - margin) - (nx + width)
        if ny < margin or height > box_h - 2.0 * margin:
            dy = margin - ny
        elif ny + height > box_h - margin:
            dy = (box_h - margin) - (ny + height)
        if dx or dy:
            canvas.panning = (canvas.panning[0] + dx, canvas.panning[1] + dy)

    def eventFilter(self, obj, event):  # noqa: N802 (Qt override)
        """Turn a double-click on a node into :attr:`nodeActivated`.

        The node is identified by hover, not by selection: hover is the node
        under the *pointer*, which is what a double-click means, while the
        selection may still be the node the previous click chose.
        """
        if obj is self.host and event.type() == QtCore.QEvent.MouseButtonDblClick:
            from emtk import nodes

            number = nodes.is_node_hovered(self.control.editor)
            if number is not None:
                node = self.control.document.node_for_number(number)
                if node is not None:
                    self.nodeActivated.emit(self.control._node_payload(node))
        return super().eventFilter(obj, event)

    # -- bridges from the control ---------------------------------------

    def _on_control_changed(self) -> None:
        """Repaint and tell the host the graph moved."""
        self.host.update()
        self.graphChanged.emit()

    def _on_control_selected(self, kind: str, payload: dict) -> None:
        """Re-emit a selection as the Qt signal consumers connect to.

        Parameters
        ----------
        kind : str
            ``"node"``, ``"edge"``, or ``"none"`` when the selection emptied.
        payload : dict
            The selected object's serialised form; ``{}`` for ``"none"``.
        """
        if kind == "node":
            self.nodeSelected.emit(payload)
        elif kind == "edge":
            self.edgeSelected.emit(payload)
        elif kind == "none":
            self.selectionCleared.emit()
