"""The shared node-link diagram look: dark backdrop, gradient nodes, curved arrows.

The state-scheme plot established this vocabulary — a circle per node filled with
a radial gradient, a curved arrow per directed edge, a rounded badge on the arrow
carrying its number, all on a dark grid. It reads well because every element is
drawn at a fixed pixel size and the geometry is *hand-routed* rather than left to
a general plotting library, which is exactly what a scientific plotting library is
not for.

Anything else that draws a graph of things-and-relations should look the same, so
the primitives live here rather than inside the one widget that first needed them:

- :func:`paint_backdrop` — the dark panel and its grid.
- :class:`ZoomPan` — the scene ↔ canvas transform, wheel-zoom anchored on the
  pointer, and the inverse every hit test needs.
- :func:`edge_path` — the cubic route between two circles, with the two-way
  offset that keeps a forward and a backward arrow apart.
- :func:`draw_arrow_head`, :func:`draw_badge`, :func:`draw_node` — the marks.

Node coordinates are always in *scene* space (unscaled pixels): a zoom must never
disturb a layout the user arranged by hand, so the zoom is applied at paint time
and inverted on the way back in.
"""
from __future__ import annotations

import math

from qtpy import QtCore, QtGui, QtWidgets

#: Node fills as ``(light, dark)`` radial-gradient stops, indexed by whatever the
#: caller counts by (state index, node kind, …). Cycled rather than exhausted:
#: the palette used to run out after four entries and everything past the third
#: came out the same orange.
NODE_PALETTE: tuple[tuple[str, str], ...] = (
    ("#42a5f5", "#1565c0"),   # blue
    ("#66bb6a", "#2e7d32"),   # green
    ("#ab47bc", "#6a1b9a"),   # purple
    ("#ffa726", "#e65100"),   # orange
    ("#26c6da", "#00838f"),   # cyan
    ("#ec407a", "#ad1457"),   # pink
)

#: Panel fill. Dark, because a graph is mostly ink and a light panel makes every
#: edge fight the background.
BACKDROP = "#151515"

#: Grid pitch in canvas pixels. The grid is a fixed backdrop — it does not zoom,
#: so it stays a reference for *screen* distance rather than scene distance.
GRID_STEP = 35

#: Accent for an edge that carries no rate of its own (an externally driven
#: transition, a selection, a hint).
ACCENT = "#00e5ff"

#: Accent for an ordinary edge.
ACCENT_ALT = "#ff4081"


def paint_backdrop(
    painter: QtGui.QPainter,
    rect: QtCore.QRect,
    *,
    grid_step: int = GRID_STEP,
    colour: str = BACKDROP,
) -> None:
    """Fill *rect* with the dark panel and draw its dashed grid and border.

    Parameters
    ----------
    painter : QtGui.QPainter
        Painter to draw with, in **canvas** coordinates (call this before
        applying any zoom transform).
    rect : QtCore.QRect
        The widget rectangle.
    grid_step : int, optional
        Grid pitch in pixels.
    colour : str, optional
        Panel fill colour.
    """
    painter.fillRect(rect, QtGui.QColor(colour))

    painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 20), 1, QtCore.Qt.DashLine))
    for x in range(grid_step, rect.width(), grid_step):
        painter.drawLine(x, 0, x, rect.height())
    for y in range(grid_step, rect.height(), grid_step):
        painter.drawLine(0, y, rect.width(), y)

    painter.setPen(QtGui.QPen(QtGui.QColor(50, 50, 50), 1))
    painter.drawRect(rect.adjusted(0, 0, -1, -1))


class ZoomPan:
    """The scene ↔ canvas transform of a diagram, and wheel-zoom about a point.

    Held by a widget rather than inherited, because the widget that paints is
    not always the widget that receives the events (the state-scheme section
    owns the state, its canvas child owns the surface).

    Attributes
    ----------
    zoom : float
        Current scale factor, clamped to :attr:`ZOOM_RANGE`.
    origin : QtCore.QPointF
        Canvas-space translation applied before the scale.
    """

    #: Zoom limits. Below the first the labels are unreadable; above the second a
    #: single node fills the canvas and there is nothing left to orient by.
    ZOOM_RANGE = (0.25, 6.0)

    def __init__(self) -> None:
        self.zoom = 1.0
        self.origin = QtCore.QPointF(0.0, 0.0)

    def transform(self) -> QtGui.QTransform:
        """Return the scene → canvas transform."""
        t = QtGui.QTransform()
        t.translate(self.origin.x(), self.origin.y())
        t.scale(self.zoom, self.zoom)
        return t

    def scene_pos(self, point) -> QtCore.QPointF:
        """Map a canvas position back to scene coordinates.

        Every hit test works in scene coordinates, so the inverse has to be
        applied on the way in or clicking a zoomed node would miss it by exactly
        the zoom factor.
        """
        inverse, ok = self.transform().inverted()
        p = QtCore.QPointF(point)
        return inverse.map(p) if ok else p

    def zoom_by(self, delta: float, anchor: QtCore.QPointF) -> bool:
        """Zoom by a wheel *delta*, keeping the scene point under *anchor* fixed.

        Anchoring on the pointer rather than the widget centre is what makes zoom
        usable for inspecting one corner of a busy diagram.

        Returns
        -------
        bool
            Whether the zoom actually changed (a no-op at the limits).
        """
        if not delta:
            return False
        low, high = self.ZOOM_RANGE
        new_zoom = min(high, max(low, self.zoom * (1.0015 ** float(delta))))
        if abs(new_zoom - self.zoom) < 1e-9:
            return False
        scene = self.scene_pos(anchor)
        self.zoom = new_zoom
        self.origin = QtCore.QPointF(
            anchor.x() - scene.x() * new_zoom,
            anchor.y() - scene.y() * new_zoom,
        )
        return True

    def pan_by(self, dx: float, dy: float) -> None:
        """Translate the view by a canvas-space offset."""
        self.origin = QtCore.QPointF(self.origin.x() + dx, self.origin.y() + dy)

    def reset(self) -> None:
        """Return to 1:1, unpanned."""
        self.zoom = 1.0
        self.origin = QtCore.QPointF(0.0, 0.0)


def wheel_anchor(event: QtGui.QWheelEvent) -> QtCore.QPointF:
    """Return a wheel event's position, across the Qt5/Qt6 spellings."""
    try:
        return QtCore.QPointF(event.position())
    except AttributeError:      # Qt5 spelling
        return QtCore.QPointF(event.pos())


def event_pos(event) -> QtCore.QPointF:
    """Return a mouse event's widget position, across the Qt5/Qt6 spellings."""
    try:
        return QtCore.QPointF(event.position())
    except AttributeError:      # Qt5 spelling
        return QtCore.QPointF(event.pos())


def edge_path(
    p_i: QtCore.QPointF,
    p_j: QtCore.QPointF,
    *,
    r_from: float,
    r_to: float,
    two_way: bool = False,
    bow: float | None = None,
):
    """Route a curved edge from circle *p_i* to circle *p_j*.

    The path starts and ends on the circles' rims rather than their centres, so
    an arrowhead lands on the node instead of inside it. A ``two_way`` edge is
    additionally pushed sideways, because a forward and a backward arrow drawn
    on the same curve are one ambiguous line.

    Parameters
    ----------
    p_i, p_j : QtCore.QPointF
        Node centres, in scene coordinates.
    r_from, r_to : float
        Radii of the source and target circles.
    two_way : bool, optional
        Whether the reverse edge is also drawn.
    bow : float, optional
        Signed curvature (perpendicular offset of the mid-point). Defaults to a
        distance-dependent value — wider for a two-way pair.

    Returns
    -------
    tuple
        ``(path, p0, p3, p2, pmid)``: the path, its endpoints, the last control
        point (which gives the arrowhead its angle) and the mid-point (where a
        badge goes). All ``None`` when the nodes coincide.
    """
    dx = p_j.x() - p_i.x()
    dy = p_j.y() - p_i.y()
    dist = math.hypot(dx, dy)
    if dist < 1e-4:
        return None, None, None, None, None

    ux, uy = dx / dist, dy / dist
    px, py = -uy, ux

    if bow is not None:
        h = bow
        offset_side = 7.0 if two_way else 0.0
    elif two_way:
        h = max(24.0, min(50.0, dist * 0.26))
        offset_side = 7.0
    else:
        h = max(10.0, min(22.0, dist * 0.12))
        offset_side = 0.0

    p0 = QtCore.QPointF(
        p_i.x() + ux * r_from + px * offset_side,
        p_i.y() + uy * r_from + py * offset_side,
    )
    p3 = QtCore.QPointF(
        p_j.x() - ux * r_to + px * offset_side,
        p_j.y() - uy * r_to + py * offset_side,
    )

    pmid = QtCore.QPointF(
        (p0.x() + p3.x()) / 2.0 + px * h,
        (p0.y() + p3.y()) / 2.0 + py * h,
    )

    p1 = QtCore.QPointF(
        p0.x() + (pmid.x() - p0.x()) * 0.6, p0.y() + (pmid.y() - p0.y()) * 0.6
    )
    p2 = QtCore.QPointF(
        p3.x() + (pmid.x() - p3.x()) * 0.6, p3.y() + (pmid.y() - p3.y()) * 0.6
    )

    path = QtGui.QPainterPath()
    path.moveTo(p0)
    path.cubicTo(p1, p2, p3)
    return path, p0, p3, p2, pmid


def draw_arrow_head(
    painter: QtGui.QPainter,
    tip: QtCore.QPointF,
    towards: QtCore.QPointF,
    colour: QtGui.QColor,
    pen_width: float = 2.0,
) -> None:
    """Draw a filled arrowhead at *tip*, pointing away from *towards*.

    *towards* is the curve's last control point, so the head follows the curve
    rather than the straight line between the node centres.
    """
    angle = math.atan2(tip.y() - towards.y(), tip.x() - towards.x())
    size = 10.0 + pen_width * 0.5
    head = QtGui.QPolygonF([
        tip,
        QtCore.QPointF(
            tip.x() - size * math.cos(angle - math.pi / 6),
            tip.y() - size * math.sin(angle - math.pi / 6),
        ),
        QtCore.QPointF(
            tip.x() - size * math.cos(angle + math.pi / 6),
            tip.y() - size * math.sin(angle + math.pi / 6),
        ),
    ])
    painter.setBrush(QtGui.QBrush(colour))
    painter.setPen(QtCore.Qt.NoPen)
    painter.drawPolygon(head)


def draw_badge(
    painter: QtGui.QPainter,
    centre: QtCore.QPointF,
    text: str,
    *,
    outline: QtGui.QColor,
    fill: QtGui.QColor | None = None,
    text_colour: QtGui.QColor | None = None,
    min_width: float = 40.0,
    height: float = 20.0,
) -> QtCore.QRectF:
    """Draw a rounded label badge centred on *centre* and return its rectangle.

    The rectangle is returned because it is also the badge's hit box: a caller
    that lets the user click a badge must test against exactly what was drawn.
    """
    font = painter.font()
    font.setPointSize(9)
    font.setBold(True)
    painter.setFont(font)

    width = max(min_width, painter.fontMetrics().horizontalAdvance(text) + 12)
    rect = QtCore.QRectF(
        centre.x() - width / 2.0, centre.y() - height / 2.0, width, height
    )

    painter.setBrush(QtGui.QBrush(fill if fill is not None else QtGui.QColor(20, 20, 20, 225)))
    painter.setPen(QtGui.QPen(outline, 1.2))
    painter.drawRoundedRect(rect, 6, 6)

    painter.setPen(QtGui.QPen(text_colour or QtGui.QColor(255, 255, 255)))
    painter.drawText(rect, QtCore.Qt.AlignCenter, text)
    return rect


def draw_node(
    painter: QtGui.QPainter,
    centre: QtCore.QPointF,
    radius: float,
    colours: tuple[str, str],
    label: str = "",
    *,
    border: QtGui.QColor | None = None,
    border_width: float = 2.0,
    label_point_size: int = 10,
    label_below: bool = False,
    label_plate: bool = False,
    label_max_width: float = 96.0,
) -> None:
    """Draw one node: a radial-gradient disc with its label.

    Parameters
    ----------
    painter : QtGui.QPainter
        Painter, in scene coordinates.
    centre : QtCore.QPointF
        Node centre.
    radius : float
        Disc radius.
    colours : tuple of str
        ``(light, dark)`` gradient stops — an entry of :data:`NODE_PALETTE`.
    label : str, optional
        Text drawn in the disc, or under it when `label_below`.
    border : QtGui.QColor, optional
        Rim colour; a light grey when omitted. Use a bright colour to mark
        selection or a drag.
    border_width : float, optional
        Rim width.
    label_point_size : int, optional
        Label font size.
    label_below : bool, optional
        Draw the label under the disc instead of inside it — the right choice
        when the label is longer than the disc is wide.
    label_plate : bool, optional
        Back the label with a translucent plate. In a dense graph the labels of
        neighbouring nodes overlap each other and the edges between them; the
        plate is what keeps the topmost one readable instead of both becoming
        an unreadable overlay.
    label_max_width : float, optional
        Labels longer than this are elided with an ellipsis, so one long
        parameter name cannot blanket its neighbours.
    """
    rect = QtCore.QRectF(
        centre.x() - radius, centre.y() - radius, 2 * radius, 2 * radius
    )
    grad = QtGui.QRadialGradient(
        centre.x() - radius * 0.3, centre.y() - radius * 0.3, radius * 1.5
    )
    light, dark = colours
    grad.setColorAt(0, QtGui.QColor(light))
    grad.setColorAt(1, QtGui.QColor(dark))

    painter.setBrush(QtGui.QBrush(grad))
    painter.setPen(QtGui.QPen(border or QtGui.QColor(240, 240, 240), border_width))
    painter.drawEllipse(rect)

    if not label:
        return

    font = painter.font()
    font.setBold(True)
    font.setPointSize(label_point_size)
    painter.setFont(font)

    if not label_below:
        painter.setPen(QtGui.QPen(QtCore.Qt.white))
        painter.drawText(rect, QtCore.Qt.AlignCenter, label)
        return

    metrics = painter.fontMetrics()
    text = metrics.elidedText(label, QtCore.Qt.ElideRight, int(label_max_width))
    width = metrics.horizontalAdvance(text) + 6
    height = metrics.height() + 2
    below = QtCore.QRectF(
        centre.x() - width / 2.0, centre.y() + radius + 2.0, width, height
    )
    if label_plate:
        painter.setBrush(QtGui.QBrush(QtGui.QColor(12, 12, 12, 200)))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRoundedRect(below, 3, 3)
    painter.setPen(QtGui.QPen(QtCore.Qt.white))
    painter.drawText(below, QtCore.Qt.AlignCenter, text)


def draw_legend(
    painter: QtGui.QPainter,
    origin: QtCore.QPointF,
    entries,
    *,
    swatch_radius: float = 6.0,
    row_height: float = 18.0,
    width: float = 132.0,
) -> None:
    """Draw a colour key at *origin*, in **canvas** coordinates.

    A node diagram whose colours mean something is unreadable without one, and a
    key that zoomed with the scene would be the first thing to leave the view —
    so this is drawn after the transform is popped.

    Parameters
    ----------
    painter : QtGui.QPainter
        Painter, in canvas coordinates (after the scene transform is popped).
    origin : QtCore.QPointF
        Top-left corner of the key.
    entries : sequence of (str, tuple)
        ``(label, (light, dark))`` pairs.
    swatch_radius : float, optional
        Radius of each colour disc.
    row_height : float, optional
        Height of one row.
    width : float, optional
        Width of the key box.
    """
    if not entries:
        return
    height = row_height * len(entries) + 10.0
    box = QtCore.QRectF(origin.x(), origin.y(), width, height)
    painter.setBrush(QtGui.QBrush(QtGui.QColor(10, 10, 10, 200)))
    painter.setPen(QtGui.QPen(QtGui.QColor(70, 70, 70), 1))
    painter.drawRoundedRect(box, 5, 5)

    font = painter.font()
    font.setBold(False)
    font.setPointSize(8)
    painter.setFont(font)
    for row, (label, colours) in enumerate(entries):
        cy = origin.y() + 5.0 + row_height * (row + 0.5)
        draw_node(
            painter,
            QtCore.QPointF(origin.x() + 12.0, cy),
            swatch_radius,
            colours,
            border=QtGui.QColor(200, 200, 200),
            border_width=1.0,
        )
        painter.setPen(QtGui.QPen(QtGui.QColor(225, 225, 225)))
        painter.setFont(font)
        painter.drawText(
            QtCore.QRectF(origin.x() + 24.0, cy - row_height / 2.0, width - 28.0, row_height),
            QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft,
            label,
        )


def distance_to_curve(point: QtCore.QPointF, path: QtGui.QPainterPath, samples: int = 24) -> float:
    """Return the smallest distance from *point* to a sampled *path*.

    Sampling rather than solving: the paths here are single cubics a couple of
    hundred pixels long, and 24 samples put the error well inside the click
    radius any caller uses.
    """
    best = float("inf")
    for i in range(samples + 1):
        p = path.pointAtPercent(i / samples)
        d = math.hypot(point.x() - p.x(), point.y() - p.y())
        if d < best:
            best = d
    return best


class DiagramCanvas(QtWidgets.QWidget):
    """A widget that paints a node-link diagram on the shared dark backdrop.

    Provides the backdrop, the :class:`ZoomPan` state, wheel zoom and
    background panning. Subclasses implement :meth:`paint_scene` (called with
    the scene transform already applied) and whatever hit testing they need.
    """

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.view = ZoomPan()
        self._panning = False
        self._pan_anchor = QtCore.QPointF(0.0, 0.0)
        self.setMinimumSize(360, 240)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )
        self.setFocusPolicy(QtCore.Qt.StrongFocus)

    # -- painting -------------------------------------------------------------

    def paint_scene(self, painter: QtGui.QPainter) -> None:
        """Paint the diagram in scene coordinates. Subclasses override."""

    def paint_overlay(self, painter: QtGui.QPainter) -> None:
        """Paint on top in canvas coordinates (legends, hints). Optional."""

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:      # noqa: N802 (Qt)
        """Draw the backdrop, then the scene under the current zoom."""
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        paint_backdrop(painter, self.rect())
        painter.save()
        painter.setTransform(self.view.transform(), True)
        self.paint_scene(painter)
        painter.restore()
        self.paint_overlay(painter)
        painter.end()

    # -- view ------------------------------------------------------------------

    def scene_pos(self, point) -> QtCore.QPointF:
        """Map a canvas position to scene coordinates."""
        return self.view.scene_pos(point)

    def reset_view(self) -> None:
        """Return to 1:1, unpanned."""
        self.view.reset()
        self.update()

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:      # noqa: N802 (Qt)
        """Zoom about the pointer."""
        if self.view.zoom_by(event.angleDelta().y(), wheel_anchor(event)):
            self.on_view_changed()
            self.update()
        event.accept()

    def on_view_changed(self) -> None:
        """React to a zoom change (e.g. hide a floating editor). Optional."""

    # -- background panning ----------------------------------------------------

    def begin_pan(self, canvas_pos: QtCore.QPointF) -> None:
        """Start panning the view from *canvas_pos*."""
        self._panning = True
        self._pan_anchor = QtCore.QPointF(canvas_pos)
        self.setCursor(QtCore.Qt.SizeAllCursor)

    def continue_pan(self, canvas_pos: QtCore.QPointF) -> bool:
        """Pan to *canvas_pos*; return whether a pan was in progress."""
        if not self._panning:
            return False
        self.view.pan_by(
            canvas_pos.x() - self._pan_anchor.x(), canvas_pos.y() - self._pan_anchor.y()
        )
        self._pan_anchor = QtCore.QPointF(canvas_pos)
        self.update()
        return True

    def end_pan(self) -> None:
        """Stop panning."""
        if self._panning:
            self._panning = False
            self.unsetCursor()
