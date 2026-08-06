"""The parameter-network canvas: fits, their parameters, and the links between.

Drawn with the shared node-link marks in
:mod:`chisurf.gui.widgets.graph_canvas` — the same dark grid, gradient discs and
curved arrows the state-scheme diagram uses — so the two graphs in ChiSurf read
as one idea. This replaces a ``pyqtgraph.GraphItem``, which drew nodes in *data*
coordinates: node size, label offset and arrow length all scaled with the layout,
so a graph was either a cloud of unreadable dots or a handful of huge blobs, and
the arrowheads sat on the node centres rather than on the edges.

Three kinds of edge are drawn, and they are different claims:

- **ownership**, parameter → its fit or group: thin, grey, no head. It is scaffolding.
- **link**, follower → master: a bright arrow with a head, because that is the
  relation the user came here to see and to edit.
- **base**, owner → owner (the *Connect base* option): dashed and dim. It says
  only "these are the things links can run between".

Interaction mirrors what the old widget offered, plus what it should have:
click to select (the selection drives the parameter editors beside the canvas),
drag a node to move it, drag a *fit* to move it with all its parameters, drag one
parameter onto another to link them, and double-click a link arrow to break it.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

from qtpy import QtCore, QtGui, QtWidgets

from chisurf.gui.widgets import graph_canvas as gc

#: Node kind codes, as produced by the graph adapter.
NODE_FIT = 0
NODE_PARAM_FIXED = 1
NODE_PARAM_LINKED = 2
NODE_PARAM_FREE = 3
NODE_GROUP = 4

PARAM_KINDS = frozenset({NODE_PARAM_FIXED, NODE_PARAM_LINKED, NODE_PARAM_FREE})

#: Gradient stops per node kind, drawn from the shared palette so the colours
#: agree with every other diagram in the application.
KIND_COLOURS: Dict[int, Tuple[str, str]] = {
    NODE_FIT: gc.NODE_PALETTE[0],          # blue    — a dataset being fitted
    NODE_PARAM_FIXED: ("#90a4ae", "#455a64"),  # grey — held, not estimated
    NODE_PARAM_LINKED: gc.NODE_PALETTE[1],  # green  — follows another parameter
    NODE_PARAM_FREE: gc.NODE_PALETTE[2],    # purple — free to move
    NODE_GROUP: gc.NODE_PALETTE[3],         # orange — an out-of-fit owner
}

KIND_LABELS: Dict[int, str] = {
    NODE_FIT: "fit",
    NODE_GROUP: "plugin group",
    NODE_PARAM_FREE: "free parameter",
    NODE_PARAM_LINKED: "linked parameter",
    NODE_PARAM_FIXED: "fixed parameter",
}

#: Legend order — owners first, then parameters by how much freedom they have.
LEGEND_ORDER = (NODE_FIT, NODE_GROUP, NODE_PARAM_FREE, NODE_PARAM_LINKED, NODE_PARAM_FIXED)

#: Rim colour of a selected node, and of the first selection specifically. The
#: first click is the *master* when linking, so it cannot look like the second.
SELECTED_RIM = "#ffeb3b"
MASTER_RIM = "#ff5252"

#: How far a click may miss a link arrow and still break it (scene px).
EDGE_HIT_RADIUS = 12.0


class ParameterGraphCanvas(gc.DiagramCanvas):
    """Interactive canvas showing fits, parameters and their links.

    Signals
    -------
    selectionChanged(list)
        Node indices currently selected, oldest first.
    linkRequested(int, int)
        A parameter node was dragged onto another: ``(follower, master)``.
    linkRemovalRequested(int)
        A link arrow was double-clicked; the argument is the follower's node index.
    """

    selectionChanged = QtCore.Signal(list)
    linkRequested = QtCore.Signal(int, int)
    linkRemovalRequested = QtCore.Signal(int)

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        n_selected_nodes: int = 2,
    ) -> None:
        super().__init__(parent)
        #: How many nodes stay selected; the oldest is dropped past this.
        self.n_selected_nodes = n_selected_nodes

        self._pos: Dict[int, QtCore.QPointF] = {}
        #: Layout coordinates as the algorithm produced them, kept so the graph
        #: can be re-fitted when the panel resizes. Without this the fit is done
        #: once, against whatever size the widget had before it was laid out —
        #: which is a 400×300 default — and the network stays in a small clump
        #: in the corner of a large panel.
        self._raw: List[Tuple[float, float]] = []
        self._spread = 1.0
        #: Set once the user drags a node, after which a resize must not undo
        #: the arrangement they made.
        self._user_moved = False
        self._names: List[str] = []
        self._kinds: List[int] = []
        self._edges: List[Tuple[int, int]] = []
        #: Ownership edges, kept apart from link edges so only the latter are
        #: hit-tested for unlinking and only the former move a fit's cluster.
        self._link_edges: List[Tuple[int, int]] = []
        self._owner_edges: List[Tuple[int, int]] = []
        #: Owner-to-owner edges ("Connect base"). Drawn differently from the
        #: parameter-ownership lines because they are a different claim: those
        #: say "this parameter belongs to that fit", these only say "these are
        #: the things parameters can be linked between".
        self._base_edges: List[Tuple[int, int]] = []
        self._owned: Dict[int, List[int]] = {}

        self._selected: List[int] = []
        self._dragged: Optional[int] = None
        self._drag_offset = QtCore.QPointF(0.0, 0.0)
        self._drag_group: List[Tuple[int, QtCore.QPointF]] = []
        #: The in-progress link gesture: ``(source node, current scene point)``.
        self._linking: Optional[Tuple[int, QtCore.QPointF]] = None

        self.node_radius = 13.0
        self.setMouseTracking(True)
        self.setToolTip(
            "Drag a parameter onto another to link it (first → second) · "
            "Shift-drag to move a node instead · drag a fit to move its whole "
            "cluster · double-click a link arrow to break it · wheel to zoom · "
            "drag the background to pan"
        )

    # -- data ------------------------------------------------------------------

    def set_graph(
        self,
        positions: Sequence[Sequence[float]],
        edges: Sequence[Sequence[int]],
        names: Sequence[str],
        kinds: Sequence[int],
        *,
        spread: float = 1.0,
        keep_view: bool = True,
    ) -> None:
        """Replace the graph.

        Parameters
        ----------
        positions : sequence of (x, y)
            Layout coordinates, in the layout algorithm's own units; they are
            fitted to the canvas here.
        edges : sequence of (source, target)
            Index pairs into `positions`.
        names, kinds : sequence
            Per-node label and kind code (see the ``NODE_*`` constants).
        spread : float, optional
            Multiplier on the fitted extent. ``1`` fills the canvas; above it the
            graph grows past the edges (pan and zoom to read it), which is how a
            crowded graph is pulled apart without changing its layout.
        keep_view : bool, optional
            Keep the current zoom/pan. A redraw after a parameter changed should
            not throw away the view the user set up.
        """
        self._names = [str(n) for n in names]
        self._kinds = [int(k) for k in kinds]
        self._edges = [(int(a), int(b)) for a, b in edges]

        self._raw = [(float(p[0]), float(p[1])) for p in positions]
        self._spread = float(spread)
        self._user_moved = False
        self._pos = self._fit_to_canvas(self._raw, self._spread)

        self._link_edges = []
        self._owner_edges = []
        self._base_edges = []
        self._owned = {}
        for a, b in self._edges:
            if self._is_param(a) and self._is_param(b):
                self._link_edges.append((a, b))
            elif self._is_owner(a) and self._is_owner(b):
                self._base_edges.append((a, b))
            else:
                self._owner_edges.append((a, b))
                # ``a`` is the parameter and ``b`` its owner, but a graph read
                # from file may carry either order.
                owner, member = (b, a) if self._is_owner(b) else (a, b)
                if self._is_owner(owner):
                    self._owned.setdefault(owner, []).append(member)

        self._selected = [i for i in self._selected if i < len(self._names)]
        if not keep_view:
            self.view.reset()
        self.update()

    def _fit_to_canvas(
        self, positions: Sequence[Sequence[float]], spread: float = 1.0
    ) -> Dict[int, QtCore.QPointF]:
        """Map layout coordinates into the canvas, preserving aspect ratio.

        A layout algorithm returns whatever range it likes and the old widget
        drew it straight, so the graph's apparent size depended on the layout
        and the "graph scale" spin box had to be nudged until it looked right.
        Fitting to the viewport instead means every layout arrives usable.
        """
        pts = [(float(p[0]), float(p[1])) for p in positions]
        if not pts:
            return {}

        margin = self.node_radius * 3.0 + 18.0
        w = max(self.width(), 400) - 2 * margin
        h = max(self.height(), 300) - 2 * margin

        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        span_x = max(xs) - min(xs)
        span_y = max(ys) - min(ys)
        scale = min(
            w / span_x if span_x > 1e-9 else float("inf"),
            h / span_y if span_y > 1e-9 else float("inf"),
        )
        if not math.isfinite(scale):
            scale = 1.0
        scale *= max(0.05, float(spread))

        cx = (max(xs) + min(xs)) / 2.0
        cy = (max(ys) + min(ys)) / 2.0
        ox = margin + w / 2.0
        oy = margin + h / 2.0
        # Screen y grows downward; a layout's does not, so it is flipped here
        # rather than leaving every graph mirrored against its own literature.
        return {
            i: QtCore.QPointF(ox + (x - cx) * scale, oy - (y - cy) * scale)
            for i, (x, y) in enumerate(pts)
        }

    # -- queries ---------------------------------------------------------------

    def _is_param(self, idx: int) -> bool:
        return 0 <= idx < len(self._kinds) and self._kinds[idx] in PARAM_KINDS

    def _is_owner(self, idx: int) -> bool:
        return 0 <= idx < len(self._kinds) and self._kinds[idx] in (NODE_FIT, NODE_GROUP)

    def _radius(self, idx: int) -> float:
        """Return a node's radius; owners are drawn larger than what they own."""
        return self.node_radius * (1.7 if self._is_owner(idx) else 1.0)

    @property
    def selected_nodes_idx(self) -> List[int]:
        """Return the selected node indices, oldest first."""
        return list(self._selected)

    def clear_selection(self) -> None:
        """Drop the selection and tell whoever is listening."""
        self._selected = []
        self.selectionChanged.emit([])
        self.update()

    def _node_at(self, scene: QtCore.QPointF) -> Optional[int]:
        """Return the index of the node under *scene*, nearest first."""
        best: Optional[int] = None
        best_d = float("inf")
        for i, pt in self._pos.items():
            d = math.hypot(scene.x() - pt.x(), scene.y() - pt.y())
            if d <= self._radius(i) and d < best_d:
                best, best_d = i, d
        return best

    # -- painting --------------------------------------------------------------

    def paint_scene(self, painter: QtGui.QPainter) -> None:
        """Draw ownership edges, link arrows, the drag hint, then the nodes."""
        for a, b in self._base_edges:
            self._draw_base_edge(painter, a, b)
        for a, b in self._owner_edges:
            self._draw_owner_edge(painter, a, b)
        for a, b in self._link_edges:
            self._draw_link_edge(painter, a, b)

        if self._linking is not None:
            src, cursor = self._linking
            start = self._pos.get(src)
            if start is not None:
                painter.setPen(QtGui.QPen(
                    QtGui.QColor(SELECTED_RIM), 2.0, QtCore.Qt.DashLine
                ))
                painter.setBrush(QtCore.Qt.NoBrush)
                painter.drawLine(start, cursor)

        # Parameters, then owners, then the selection: a label plate hides
        # whatever it lands on, so the nodes the user is working with have to be
        # painted last or their own labels disappear under a neighbour's.
        order = sorted(
            self._pos,
            key=lambda i: (i in self._selected, self._is_owner(i)),
        )
        for i in order:
            self._draw_node(painter, i, self._pos[i])

    def _draw_owner_edge(self, painter: QtGui.QPainter, a: int, b: int) -> None:
        pa, pb = self._pos.get(a), self._pos.get(b)
        if pa is None or pb is None:
            return
        path, *_ = gc.edge_path(
            pa, pb, r_from=self._radius(a), r_to=self._radius(b), bow=0.0
        )
        if path is None:
            return
        painter.setPen(QtGui.QPen(QtGui.QColor(150, 155, 165, 130), 1.2))
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawPath(path)

    def _draw_base_edge(self, painter: QtGui.QPainter, a: int, b: int) -> None:
        """Draw an owner-to-owner line: dashed, dim, and behind everything."""
        pa, pb = self._pos.get(a), self._pos.get(b)
        if pa is None or pb is None:
            return
        path, *_ = gc.edge_path(
            pa, pb, r_from=self._radius(a), r_to=self._radius(b), bow=0.0
        )
        if path is None:
            return
        painter.setPen(QtGui.QPen(
            QtGui.QColor(120, 125, 135, 90), 1.0, QtCore.Qt.DashLine
        ))
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawPath(path)

    def _draw_link_edge(self, painter: QtGui.QPainter, a: int, b: int) -> None:
        pa, pb = self._pos.get(a), self._pos.get(b)
        if pa is None or pb is None:
            return
        path, _p0, p3, p2, _pmid = gc.edge_path(
            pa, pb, r_from=self._radius(a), r_to=self._radius(b)
        )
        if path is None:
            return
        colour = QtGui.QColor(gc.ACCENT)
        painter.setPen(QtGui.QPen(
            colour, 2.4, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin
        ))
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawPath(path)
        gc.draw_arrow_head(painter, p3, p2, colour, 2.4)

    def _draw_node(self, painter: QtGui.QPainter, idx: int, pt: QtCore.QPointF) -> None:
        kind = self._kinds[idx] if idx < len(self._kinds) else NODE_PARAM_FREE
        border = None
        border_w = 1.6
        if idx in self._selected:
            first = self._selected[0] == idx and len(self._selected) > 1
            border = QtGui.QColor(MASTER_RIM if first else SELECTED_RIM)
            border_w = 3.0
        gc.draw_node(
            painter,
            pt,
            self._radius(idx),
            KIND_COLOURS.get(kind, gc.NODE_PALETTE[2]),
            self._names[idx] if idx < len(self._names) else "",
            border=border,
            border_width=border_w,
            label_point_size=9 if self._is_owner(idx) else 8,
            label_below=True,
            label_plate=True,
        )

    def paint_overlay(self, painter: QtGui.QPainter) -> None:
        """Draw the colour key, and say so when there is nothing to show."""
        if not self._pos:
            painter.setPen(QtGui.QPen(QtGui.QColor(150, 155, 165)))
            painter.drawText(
                self.rect(),
                QtCore.Qt.AlignCenter,
                "No fits yet — add a fit, then press Redraw.",
            )
            return
        present = [k for k in LEGEND_ORDER if k in set(self._kinds)]
        gc.draw_legend(
            painter,
            QtCore.QPointF(8.0, 8.0),
            [(KIND_LABELS[k], KIND_COLOURS[k]) for k in present],
        )

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:    # noqa: N802 (Qt)
        """Re-fit the graph to the new size, unless the user arranged it."""
        super().resizeEvent(event)
        self._autofit()
        self.update()

    def showEvent(self, event: QtGui.QShowEvent) -> None:        # noqa: N802 (Qt)
        """Fit the graph once the panel is on screen with its real size.

        A hidden widget does not receive resize events — Qt holds them until it
        is shown — so a canvas built into a dock tab that is not the front one
        would otherwise keep the fit it computed against its default size.
        """
        super().showEvent(event)
        self._autofit()

    def _autofit(self) -> None:
        """Re-fit to the current size, unless the user arranged the nodes."""
        if self._raw and not self._user_moved:
            self._pos = self._fit_to_canvas(self._raw, self._spread)

    def refit(self) -> None:
        """Fit the graph back into the panel, discarding any hand arrangement."""
        if self._raw:
            self._pos = self._fit_to_canvas(self._raw, self._spread)
            self._user_moved = False
        self.view.reset()
        self.update()

    # -- interaction -----------------------------------------------------------

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802 (Qt)
        """Select, start a node drag, start a link gesture, or start panning."""
        if event.button() != QtCore.Qt.LeftButton:
            event.ignore()
            return
        canvas_pos = gc.event_pos(event)
        scene = self.scene_pos(canvas_pos)
        idx = self._node_at(scene)

        if idx is None:
            self.begin_pan(canvas_pos)
            event.accept()
            return

        self._select(idx)

        move_only = bool(event.modifiers() & QtCore.Qt.ShiftModifier)
        if self._is_param(idx) and not move_only:
            # Dragging a parameter onto another links them — the gesture this
            # plugin has always had, and the reason it exists. Shift overrides
            # it to reposition the node instead, which the old widget could not
            # do at all.
            self._linking = (idx, scene)
        else:
            self._dragged = idx
            pt = self._pos[idx]
            self._drag_offset = QtCore.QPointF(scene.x() - pt.x(), scene.y() - pt.y())
            # An owner carries its parameters, so a cluster can be pulled clear
            # of the rest of the graph in one gesture.
            self._drag_group = [
                (m, QtCore.QPointF(self._pos[m]))
                for m in self._owned.get(idx, []) if m in self._pos
            ]
            self.setCursor(QtCore.Qt.ClosedHandCursor)
        event.accept()

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:   # noqa: N802 (Qt)
        """Drag a node or cluster, stretch the link line, or pan."""
        canvas_pos = gc.event_pos(event)
        scene = self.scene_pos(canvas_pos)

        if self._linking is not None:
            self._linking = (self._linking[0], scene)
            self.update()
            event.accept()
            return

        if self._dragged is not None:
            old = self._pos[self._dragged]
            new = QtCore.QPointF(
                scene.x() - self._drag_offset.x(), scene.y() - self._drag_offset.y()
            )
            dx, dy = new.x() - old.x(), new.y() - old.y()
            self._pos[self._dragged] = new
            self._user_moved = True
            for member, _start in self._drag_group:
                p = self._pos[member]
                self._pos[member] = QtCore.QPointF(p.x() + dx, p.y() + dy)
            self.update()
            event.accept()
            return

        if self.continue_pan(canvas_pos):
            event.accept()
            return

        over = self._node_at(scene)
        self.setCursor(QtCore.Qt.OpenHandCursor if over is not None else QtCore.Qt.ArrowCursor)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802 (Qt)
        """Finish a drag, or emit the link the gesture asked for."""
        if self._linking is not None:
            src, _ = self._linking
            target = self._node_at(self.scene_pos(gc.event_pos(event)))
            self._linking = None
            self.update()
            if target is not None and target != src and self._is_param(target):
                self.linkRequested.emit(src, target)
            event.accept()
            return

        self._dragged = None
        self._drag_group = []
        self.end_pan()
        self.unsetCursor()
        event.accept()

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802 (Qt)
        """Break the link arrow under the cursor."""
        if event.button() != QtCore.Qt.LeftButton:
            event.ignore()
            return
        scene = self.scene_pos(gc.event_pos(event))
        best: Optional[int] = None
        best_d = EDGE_HIT_RADIUS
        for a, b in self._link_edges:
            pa, pb = self._pos.get(a), self._pos.get(b)
            if pa is None or pb is None:
                continue
            path, *_ = gc.edge_path(
                pa, pb, r_from=self._radius(a), r_to=self._radius(b)
            )
            if path is None:
                continue
            d = gc.distance_to_curve(scene, path)
            if d < best_d:
                best, best_d = a, d
        if best is not None:
            self.linkRemovalRequested.emit(best)
            event.accept()
            return
        event.ignore()

    def on_view_changed(self) -> None:
        """Cancel an in-flight link gesture when the view moves under it."""
        self._linking = None

    def _select(self, idx: int) -> None:
        """Add *idx* to the selection, dropping the oldest past the limit."""
        if idx in self._selected:
            self._selected.remove(idx)
        self._selected.append(idx)
        while len(self._selected) > self.n_selected_nodes:
            self._selected.pop(0)
        self.selectionChanged.emit(list(self._selected))
        self.update()
