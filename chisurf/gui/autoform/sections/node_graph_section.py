"""AutoForm ``node_graph`` section: a read-only node-editor graph, declared in a spec.

Anything whose structure is a **directed graph** — a provenance chain, a pipeline,
a kinetic scheme, an evaluation network — has until now had to be drawn as a list
or a tree, and both lie about it in the same way: a node reached by two paths is
either duplicated or one of its edges is dropped, and that node is usually the
interesting one. ChiSurf already ships a graph renderer
(:class:`~chisurf.gui.widgets.node_editor.node_viewer.NodeViewerWidget`); this
section is the seam that lets a view spec use it without the model importing Qt.

Declare it in a view spec as a custom section::

    {"type": "custom", "key": "node_graph", "title": "Provenance",
     "options": {"source": "provenance_graph",
                 "selected_call": "select_node",
                 "activated_call": "open_node"}}

Options
-------
``source``
    Model **method** (no arguments) returning a graph dict in the node-editor
    JSON schema — ``nodes``, ``edges``, and optional ``meta``. Re-read on every
    AutoForm refresh, so a model that reloads its data redraws here for free.
    Returning ``None`` or ``{}`` clears the view rather than leaving the previous
    graph on screen pretending to describe the new file.
``selected_call``
    Model method called with the selected node dict whenever the selection
    changes. This is how a detail panel beside the graph follows it.
``activated_call``
    Model method called with the node dict on a double-click.
``toolbar``
    Show the viewer's own *Fit* toolbar (default ``false``; the host usually has
    one).
``height``
    Minimum height in pixels (default 320).

The graph is always read-only here: a section that *displays* a structure must
not offer to rewire it, because nothing in the spec says what a rewire would
mean. Editing stays with the node editor itself.
"""

from __future__ import annotations

import logging

from qtpy import QtCore, QtWidgets

from .registry import register_section

logger = logging.getLogger(__name__)


@register_section("node_graph")
class NodeGraphSectionWidget(QtWidgets.QWidget):
    """A read-only node-editor graph bound to a model method."""

    AUTOFORM_REFRESH = True
    _autoform_expanding = True

    def __init__(self, model, target: str = "", **options):
        super().__init__()
        self._model = model
        self._source = str(options.get("source", "") or target or "")
        self._selected_call = str(options.get("selected_call", "") or "")
        self._activated_call = str(options.get("activated_call", "") or "")
        self._last: dict | None = None

        from chisurf.gui.widgets.node_editor.node_viewer import NodeViewerWidget

        self.viewer = NodeViewerWidget(
            read_only=True,
            show_toolbar=bool(options.get("toolbar", False)),
            graph_purpose="autoform_node_graph",
        )
        self.viewer.setMinimumHeight(int(options.get("height", 320) or 320))
        self.viewer.nodeSelected.connect(self._on_selected)
        self.viewer.scene.selectionChanged.connect(self._on_scene_selection)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.viewer, stretch=1)
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Expanding)

        # A double-click on a node collapses it in the editor; here it means
        # "open this". The scene's own handler still runs, so the collapse is
        # harmless and the call goes out on top of it.
        self.viewer.view.viewport().installEventFilter(self)

        self.refresh()

    # -- data ---------------------------------------------------------------

    def _graph(self) -> dict | None:
        """Ask the model for the graph, tolerating a model that has none yet."""
        if not self._source:
            return None
        fn = getattr(self._model, self._source, None)
        if fn is None:
            logger.warning("node_graph: model has no %r", self._source)
            return None
        try:
            return fn() if callable(fn) else fn
        except Exception:
            logger.debug("node_graph: %s failed", self._source, exc_info=True)
            return None

    def refresh(self) -> None:
        """Re-read the graph from the model and redraw only when it changed.

        The **structure** decides whether to redraw; ``meta`` does not. A model
        that reports the current selection through ``meta.focus`` hands back a
        different dict on every click, and reloading on that reset the zoom and
        recentred the view on each selection — the graph jumped away from what
        the user was reading, every time they read it.
        """
        data = self._graph()
        if not data or not data.get("nodes"):
            if self._last is not None:
                self.viewer.clear_graph()
                self._last = None
            return
        structure = (data.get("nodes"), data.get("edges"))
        if structure != self._last:
            self._last = structure
            self.viewer.load_graph_dict(data)
        focus = str((data.get("meta") or {}).get("focus") or "")
        if focus:
            self.select(focus)

    def select(self, node_id: str) -> None:
        """Select the node with *node_id*, bringing it into view if it is not.

        Deliberately not ``centerOn``: a selection made *in* the graph would then
        yank the view sideways under the cursor. ``ensureVisible`` scrolls only
        when the node is actually off screen, which is the case the caller cares
        about (a click in the artifact list).
        """
        from chisurf.gui.widgets.node_editor.node_item import NodeGraphicsItem

        for item in self.viewer.scene.items():
            if not isinstance(item, NodeGraphicsItem):
                continue
            if str(getattr(item.model, "id", "")) != str(node_id):
                continue
            if item.isSelected():
                return
            self.viewer.scene.clearSelection()
            item.setSelected(True)
            self.viewer.view.ensureVisible(item, 40, 40)
            return

    # -- selection ----------------------------------------------------------

    def _call(self, name: str, payload: dict) -> None:
        if not name:
            return
        fn = getattr(self._model, name, None)
        if not callable(fn):
            logger.warning("node_graph: model has no callable %r", name)
            return
        try:
            fn(payload)
        except Exception:
            logger.debug("node_graph: %s failed", name, exc_info=True)

    def _on_selected(self, node: dict) -> None:
        self._call(self._selected_call, node)

    def _on_scene_selection(self) -> None:
        """Report an emptied selection, which ``nodeSelected`` never does.

        The viewer emits only when something *is* selected, so clicking the empty
        canvas left the detail panel still describing the node the user had just
        deselected — a panel that quietly disagrees with the graph beside it.
        """
        if self.viewer.scene.selectedItems():
            return
        self._call(self._selected_call, {})

    def eventFilter(self, obj, event):  # noqa: N802 (Qt override)
        """Turn a double-click on a node into ``activated_call``."""
        if (
            self._activated_call
            and event.type() == QtCore.QEvent.MouseButtonDblClick
            and self.viewer.scene.selectedItems()
        ):
            node = self.viewer.selected_node()
            if node:
                self._call(self._activated_call, node)
        return super().eventFilter(obj, event)
