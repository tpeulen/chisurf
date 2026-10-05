"""A kinetic state scheme, drawn by emtk.

The fit window's "State Scheme" page shows a model's rate scheme as a
node-link diagram: states as discs, each non-zero rate as a curved arrow with
its value on a badge, the externally driven transition (a laser) as ``k_exc``.
The marks are the shared node-link vocabulary of
:mod:`chisurf.gui.widgets.graph_canvas` -- dark grid, gradient discs, cyan and
pink arrows -- so this diagram and the Qt form section look like one tool.

Two halves, neither of which imports Qt:

* :class:`SchemeBinding` reads the scheme from the model, whatever shape the
  model keeps it in, and writes a rate, a preset, a file back;
* :class:`SchemeCanvas` is an emtk control: the view (node positions, arc
  bows, zoom and pan, all kept in an unscaled *scene* space so a zoom never
  disturbs a layout arranged by hand), the drawing, and the gestures -- drag a
  node, drag an arc's badge to bend it, drag the background to pan, wheel to
  zoom about the pointer, double-click a badge to type a new rate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np

__all__ = ["SchemeBinding", "SchemeCanvas", "Edge", "edge_route"]

Point = tuple[float, float]

#: Disc fills, ``(light, dark)`` by state index, cycled.
NODE_PALETTE = (
    ("#4fc3f7", "#0277bd"),
    ("#81c784", "#2e7d32"),
    ("#ba68c8", "#6a1b9a"),
    ("#ffb74d", "#e65100"),
    ("#e57373", "#c62828"),
    ("#fff176", "#f9a825"),
    ("#26c6da", "#00838f"),
    ("#ec407a", "#ad1457"),
)
BACKDROP = (21, 21, 21)
GRID_STEP = 35.0
ACCENT = (0, 229, 255)
ACCENT_ALT = (255, 64, 129)
NODE_RADIUS = 26.0
ZOOM_RANGE = (0.25, 6.0)


def _align():
    from emtk.painter import ALIGN_LEFT, ALIGN_VCENTER

    return ALIGN_LEFT | ALIGN_VCENTER


def _hex(colour: str) -> tuple[int, int, int]:
    colour = colour.lstrip("#")
    return tuple(int(colour[i:i + 2], 16) for i in (0, 2, 4))


def edge_route(p_i: Point, p_j: Point, *, r_from: float = NODE_RADIUS,
               r_to: float = NODE_RADIUS, two_way: bool = False, bow: float | None = None):
    """Route a curved edge from circle *p_i* to circle *p_j*.

    The same geometry as :func:`chisurf.gui.widgets.graph_canvas.edge_path`:
    endpoints on the rims, a two-way pair pushed apart sideways, a signed bow.

    Returns
    -------
    tuple or None
        ``(p0, p1, p2, p3, mid)`` -- the cubic's control points and the badge
        position; ``None`` when the nodes coincide.
    """
    dx, dy = p_j[0] - p_i[0], p_j[1] - p_i[1]
    dist = math.hypot(dx, dy)
    if dist < 1e-4:
        return None
    ux, uy = dx / dist, dy / dist
    px, py = -uy, ux
    if bow is not None:
        h, side = bow, (7.0 if two_way else 0.0)
    elif two_way:
        h, side = max(24.0, min(50.0, dist * 0.26)), 7.0
    else:
        h, side = max(10.0, min(22.0, dist * 0.12)), 0.0
    p0 = (p_i[0] + ux * r_from + px * side, p_i[1] + uy * r_from + py * side)
    p3 = (p_j[0] - ux * r_to + px * side, p_j[1] - uy * r_to + py * side)
    mid = ((p0[0] + p3[0]) / 2.0 + px * h, (p0[1] + p3[1]) / 2.0 + py * h)
    p1 = (p0[0] + (mid[0] - p0[0]) * 0.6, p0[1] + (mid[1] - p0[1]) * 0.6)
    p2 = (p3[0] + (mid[0] - p3[0]) * 0.6, p3[1] + (mid[1] - p3[1]) * 0.6)
    return p0, p1, p2, p3, mid


@dataclass
class Edge:
    """One drawn transition."""

    i: int
    j: int
    rate: float
    label: str
    colour: tuple
    width: float
    excitation: bool
    route: tuple


class _RateMatrixScheme:
    """A bare rate-matrix group seen in the saturation model's shape (``.dark``)."""

    def __init__(self, group, labels=None):
        self.dark = group
        self.state_labels = list(labels) if labels else None
        self.excitation_edge = None

    @property
    def n_states(self) -> int:
        return int(getattr(self.dark, "n_states", 0) or 0)


class SchemeBinding:
    """The model's scheme: read it, change a rate, a preset, a file.

    Parameters
    ----------
    model : object
        The fit's model.
    target : str
        Attribute holding the scheme when the model has no ``saturation``.
    labels_attr : str
        Where state names come from for a bare rate matrix.
    excitation_edge : sequence of int, optional
        The pumped transition, when the view spec declares one.
    on_changed : callable, optional
        Called after a rate, preset or file changed the model.
    """

    def __init__(self, model, target: str = "saturation", labels_attr: str = "state_names",
                 excitation_edge=None, on_changed: Callable[[], None] | None = None) -> None:
        self.model = model
        self.target = target or "saturation"
        self.labels_attr = labels_attr
        self.declared_excitation = tuple(excitation_edge) if excitation_edge else None
        self.on_changed = on_changed

    def scheme(self):
        """The scheme to draw (with ``n_states`` and ``dark.rate_values``), or ``None``."""
        model = self.model
        obj = getattr(model, "saturation", None)
        if obj is None:
            obj = getattr(model, self.target, None)
        if obj is not None and not hasattr(obj, "dark") and hasattr(obj, "rate_matrix"):
            labels = getattr(model, self.labels_attr, None)
            if callable(labels):
                try:
                    labels = labels()
                except Exception:
                    labels = None
            obj = _RateMatrixScheme(obj, labels)
        if obj is None or not hasattr(obj, "dark") or not hasattr(obj, "n_states"):
            return None
        return obj

    def n_states(self) -> int:
        scheme = self.scheme()
        return int(scheme.n_states) if scheme is not None else 0

    def rates(self) -> np.ndarray:
        """The flat ``n * n`` rate list, row = source state."""
        scheme = self.scheme()
        if scheme is None:
            return np.zeros(0)
        return np.asarray(scheme.dark.rate_values, dtype=float)

    def labels(self) -> list[str]:
        scheme = self.scheme()
        n = self.n_states()
        raw = getattr(scheme, "state_labels", None) or [f"S{i}" for i in range(n)]
        return [str(label).split(" ")[0] for label in raw]

    def excitation(self):
        """The pumped transition ``(i, j)``; the scheme's own word wins over the spec."""
        scheme = self.scheme()
        edge = getattr(scheme, "excitation_edge", self.declared_excitation)
        return tuple(edge) if edge else None

    def set_rate(self, i: int, j: int, value: float) -> None:
        """Write one rate into the model's matrix."""
        scheme = self.scheme()
        if scheme is None:
            return
        n = int(scheme.n_states)
        values = list(scheme.dark.rate_values)
        index = int(i) * n + int(j)
        if 0 <= index < len(values):
            values[index] = float(value)
            scheme.dark.rate_values = values
            self._changed()

    def preset_names(self) -> list[str]:
        source = getattr(self.model, "scheme_names", None)
        if callable(source):
            try:
                return [str(n) for n in source()]
            except Exception:
                return []
        return []

    def preset(self) -> str:
        return str(getattr(self.model, "scheme_preset", ""))

    def set_preset(self, name: str) -> None:
        if hasattr(self.model, "scheme_preset"):
            self.model.scheme_preset = str(name)
            self._changed()

    def can_save(self) -> bool:
        return callable(getattr(self.model, "save_scheme_to_file", None))

    def can_load(self) -> bool:
        return callable(getattr(self.model, "load_scheme_from_file", None))

    def load(self, path: str) -> None:
        if self.can_load():
            self.model.load_scheme_from_file(path)
            self._changed()

    def save(self, path: str) -> None:
        if self.can_save():
            self.model.save_scheme_to_file(path)

    def _changed(self) -> None:
        if self.on_changed is not None:
            self.on_changed()

    def edges(self, coords: dict[int, Point], bows: dict) -> list[Edge]:
        """The transitions to draw: every non-zero rate, and the pumped one."""
        n = self.n_states()
        rates = self.rates()
        excitation = self.excitation()
        out: list[Edge] = []

        def rate(a, b):
            k = a * n + b
            return float(rates[k]) if k < len(rates) else 0.0

        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                k = rate(i, j)
                pumped = excitation is not None and (i, j) == excitation
                if k <= 0.0 and not pumped:
                    continue
                two_way = rate(j, i) > 0.0 or (excitation is not None and (j, i) == excitation)
                route = edge_route(coords[i], coords[j], two_way=two_way, bow=bows.get((i, j)))
                if route is None:
                    continue
                if pumped and k <= 0.0:
                    colour, width, label = ACCENT, 2.5, "k_exc"
                else:
                    width = max(1.8, 1.8 + 2.2 * math.log10(k + 1.0))
                    touches = excitation is None or excitation[0] in (i, j)
                    colour = ACCENT if touches else ACCENT_ALT
                    label = f"{k:.2f}"
                out.append(Edge(i, j, k, label, colour, width, pumped and k <= 0.0, route))
        return out


def default_layout(n: int, width: float, height: float) -> dict[int, Point]:
    """The starting positions: Jablonski for 3, a grid for 4, a ring otherwise."""
    w, h = max(360.0, width), max(240.0, height)
    if n == 3:
        return {0: (w * 0.25, h * 0.72), 1: (w * 0.50, h * 0.25), 2: (w * 0.75, h * 0.72)}
    if n == 4:
        return {0: (w * 0.25, h * 0.72), 1: (w * 0.25, h * 0.25),
                2: (w * 0.75, h * 0.25), 3: (w * 0.75, h * 0.72)}
    cx, cy = w / 2.0, h / 2.0
    radius = min(w, h) / 2.0 - 55.0
    return {i: (cx + radius * math.cos(2.0 * math.pi * i / max(n, 1) - math.pi / 2.0),
                cy + radius * math.sin(2.0 * math.pi * i / max(n, 1) - math.pi / 2.0))
            for i in range(n)}


class SchemeCanvas:
    """The diagram as an emtk control (draw / press / drag / release / scroll / hover)."""

    def __init__(self, binding: SchemeBinding) -> None:
        self.binding = binding
        self.coords: dict[int, Point] = {}
        self.bows: dict[tuple[int, int], float] = {}
        self.zoom = 1.0
        self.origin = (0.0, 0.0)
        #: ``(i, j)`` of the rate whose badge was double-clicked, while it is typed.
        self.editing: tuple[int, int] | None = None
        self.edit_anchor: Point | None = None
        self._n = -1
        self._laid_out_for: tuple = ()
        #: Whether the user moved a node, bent an arc, panned or zoomed: until
        #: then the default layout follows the canvas size.
        self.arranged = False
        self._box = (0.0, 0.0, 0.0, 0.0)
        self._drag: tuple | None = None
        self._hover: int | None = None
        self._badges: dict[tuple[int, int], tuple] = {}
        self._refresh: Callable[[], None] | None = None

    # -- the view ------------------------------------------------------ #
    def set_refresh_target(self, callback) -> None:
        self._refresh = callback

    def refresh(self) -> None:
        if self._refresh is not None:
            self._refresh()

    def to_canvas(self, p: Point) -> Point:
        x, y, *_ = self._box
        return (x + self.origin[0] + p[0] * self.zoom, y + self.origin[1] + p[1] * self.zoom)

    def to_scene(self, px: float, py: float) -> Point:
        x, y, *_ = self._box
        return ((px - x - self.origin[0]) / self.zoom, (py - y - self.origin[1]) / self.zoom)

    def ensure_layout(self) -> int:
        """Lay the states out; again on a resize, until the user arranged them.

        The first frame of a page can come before its dock has its real size,
        so a layout fixed then stays crammed into a corner of the final one.
        """
        n = self.binding.n_states()
        size = (round(self._box[2]), round(self._box[3]))
        if n != self._n or len(self.coords) != n:
            self.arranged = False
            self.bows = {}
        if n != self._n or len(self.coords) != n or (not self.arranged and size != self._laid_out_for):
            self.coords = default_layout(n, self._box[2], self._box[3])
            self._laid_out_for = size
            self._n = n
        return n

    def reset_view(self) -> None:
        """Back to 1:1, unpanned, with the default layout for the current size."""
        self.zoom, self.origin = 1.0, (0.0, 0.0)
        self.arranged = False
        self._laid_out_for = ()

    def zoom_about(self, notches: float, px: float, py: float) -> None:
        low, high = ZOOM_RANGE
        new = min(high, max(low, self.zoom * (1.0015 ** (120.0 * float(notches)))))
        scene = self.to_scene(px, py)
        x, y, *_ = self._box
        self.arranged = True
        self.zoom = new
        self.origin = (px - x - scene[0] * new, py - y - scene[1] * new)

    # -- hit tests ----------------------------------------------------- #
    def node_at(self, px: float, py: float) -> int | None:
        sx, sy = self.to_scene(px, py)
        for i, (cx, cy) in self.coords.items():
            if math.hypot(sx - cx, sy - cy) <= NODE_RADIUS:
                return i
        return None

    def badge_at(self, px: float, py: float) -> tuple[int, int] | None:
        for key, (bx, by, bw, bh) in self._badges.items():
            if bx <= px <= bx + bw and by <= py <= by + bh:
                return key
        return None

    # -- drawing ------------------------------------------------------- #
    def draw(self, p, x: float, y: float, w: float, h: float) -> None:
        from emtk.drawlist import DrawList

        self._box = (x, y, w, h)
        dl = DrawList(p)
        p.fill_rect(x, y, w, h, BACKDROP)
        # White at 8% over the backdrop, as the Qt canvas drew it; a solid
        # colour, because a line's alpha is not honoured by every painter.
        grid = (31, 31, 31)
        gx = x + GRID_STEP
        while gx < x + w:
            dl.add_line((gx, y), (gx, y + h), grid)
            gx += GRID_STEP
        gy = y + GRID_STEP
        while gy < y + h:
            dl.add_line((x, gy), (x + w, gy), grid)
            gy += GRID_STEP
        dl.add_rect((x, y), (x + w, y + h), (50, 50, 50))
        n = self.ensure_layout()
        if n <= 0:
            p.text(x + 12, y + 12, w - 24, p.line_height(), 0,
                   "This model has no rate scheme to draw.", (170, 170, 170))
            return
        p.push_clip(x, y, w, h)
        try:
            self._badges = {}
            for edge in self.binding.edges(self.coords, self.bows):
                self._draw_edge(dl, p, edge)
            labels = self.binding.labels()
            for i in range(n):
                self._draw_node(dl, p, i, labels[i] if i < len(labels) else f"S{i}")
        finally:
            p.pop_clip()

    def _draw_edge(self, dl, p, edge: Edge) -> None:
        p0, p1, p2, p3, mid = (self.to_canvas(q) for q in edge.route)
        width = edge.width * self.zoom
        dl.add_bezier_cubic(p0, p1, p2, p3, edge.colour, width, 24)
        angle = math.atan2(p3[1] - p2[1], p3[0] - p2[0])
        size = (10.0 + edge.width * 0.5) * self.zoom
        left = (p3[0] - size * math.cos(angle - math.pi / 6), p3[1] - size * math.sin(angle - math.pi / 6))
        right = (p3[0] - size * math.cos(angle + math.pi / 6), p3[1] - size * math.sin(angle + math.pi / 6))
        dl.add_triangle_filled(p3, left, right, edge.colour)
        text_w = p.text_width(edge.label)
        bw, bh = max(40.0, text_w + 12.0), max(20.0, p.line_height() + 6.0)
        bx, by = mid[0] - bw / 2.0, mid[1] - bh / 2.0
        fill = (0, 140, 170, 230) if edge.excitation else (20, 20, 20, 225)
        if self.editing == (edge.i, edge.j):
            fill = (90, 20, 20, 240)
        dl.add_rect_filled((bx, by), (bx + bw, by + bh), fill, 6.0)
        dl.add_rect((bx, by), (bx + bw, by + bh), edge.colour, 6.0, 0, 1.2)
        p.text(bx + (bw - text_w) / 2.0, by, text_w + 2.0, bh, _align(), edge.label, (255, 255, 255))
        self._badges[(edge.i, edge.j)] = (bx, by, bw, bh)

    def _draw_node(self, dl, p, i: int, label: str) -> None:
        cx, cy = self.to_canvas(self.coords[i])
        r = NODE_RADIUS * self.zoom
        light, dark = (_hex(c) for c in NODE_PALETTE[i % len(NODE_PALETTE)])
        # A radial gradient, highlight up-left: concentric discs from dark to light.
        steps = 10
        for s in range(steps):
            t = s / (steps - 1)
            colour = tuple(int(dark[k] + (light[k] - dark[k]) * t) for k in range(3))
            rad = r * (1.0 - 0.75 * t)
            off = r * 0.3 * t
            dl.add_circle_filled((cx - off, cy - off), rad, colour, 32)
        dragged = self._drag is not None and self._drag[0] == "node" and self._drag[1] == i
        rim = (255, 235, 59) if dragged else (240, 240, 240)
        dl.add_circle((cx, cy), r, rim, 32, 3.0 if dragged else 2.0)
        tw = p.text_width(label)
        p.text(cx - tw / 2.0, cy - p.line_height() / 2.0, tw + 2.0, p.line_height(), _align(),
               label, (255, 255, 255), True)

    # -- gestures ------------------------------------------------------ #
    def press(self, px, py, x=0.0, y=0.0, w=0.0, h=0.0, modifiers=0, clicks=1):
        if clicks >= 2:
            badge = self.badge_at(px, py)
            if badge is not None:
                self.editing = badge
                bx, by, bw, bh = self._badges[badge]
                self.edit_anchor = (bx + bw / 2.0, by + bh / 2.0)
                self.refresh()
                return True
        self.editing = None
        node = self.node_at(px, py)
        if node is not None:
            sx, sy = self.to_scene(px, py)
            cx, cy = self.coords[node]
            self._drag = ("node", node, (sx - cx, sy - cy))
            return True
        badge = self.badge_at(px, py)
        if badge is not None:
            self._drag = ("arc", badge)
            return True
        self._drag = ("pan", (px, py))
        return True

    def drag(self, px, py, *_):
        if self._drag is None:
            return
        self.arranged = True
        kind = self._drag[0]
        if kind == "node":
            _, i, (ox, oy) = self._drag
            sx, sy = self.to_scene(px, py)
            self.coords[i] = (sx - ox, sy - oy)
        elif kind == "arc":
            i, j = self._drag[1]
            (ax, ay), (bx, by) = self.coords[i], self.coords[j]
            dist = math.hypot(bx - ax, by - ay)
            if dist > 1e-4:
                ux, uy = (bx - ax) / dist, (by - ay) / dist
                sx, sy = self.to_scene(px, py)
                mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
                self.bows[(i, j)] = (sx - mx) * -uy + (sy - my) * ux
        elif kind == "pan":
            lx, ly = self._drag[1]
            self.origin = (self.origin[0] + px - lx, self.origin[1] + py - ly)
            self._drag = ("pan", (px, py))

    def release(self, *_):
        self._drag = None

    def hover(self, px, py, *_):
        self._pointer = (px, py)
        self._hover = self.node_at(px, py)

    def scroll(self, rows, *_):
        # Rows are sign-flipped notches: three rows a notch, down positive.
        x, y, w, h = self._box
        px, py = getattr(self, "_pointer", (x + w / 2.0, y + h / 2.0))
        self.zoom_about(-float(rows) / 3.0, px, py)
        return 0

    def tooltip_at(self, px, py):
        badge = self.badge_at(px, py)
        if badge is not None:
            return ("Double-click to type a new rate; drag to bend the arrow.", f"badge{badge}")
        if self.node_at(px, py) is not None:
            return ("Drag to move the state; drag the background to pan, wheel to zoom.", "node")
        return ""
