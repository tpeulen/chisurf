"""Draw the posterior's structure: what constrains what, and what is one measurement.

The render data comes from :mod:`chisurf.core.fitting.graphview`, which is
Qt-free and laid out already; this module is only paint. Three tabs, following
the vocabulary probabilistic-graphical-model tools settled on:

- **Structure** — parameters against the datasets that constrain them.
- **Dependence** — parameters alone, edges weighted by how much the pair
  constrains itself. A pair at ±1 is one measurement and a direction the data
  does not constrain. Weighted by ``|r|`` where only a covariance is available,
  and by mutual information measured from the draws where there are draws --
  the difference matters, because a pair lying on a curve has ``|r| ≈ 0`` and
  is drawn warm rather than not at all.
- **Junction tree** — the cliques an elimination order produces, and what they
  share.
"""

from __future__ import annotations

import math

from qtpy import QtWidgets

import chisurf.core.fitting
from chisurf.core.fitting import graphview as gv
from chisurf.gui.chiplot import Plot as ChiPlot
from chisurf.gui.chiplot import style as S
from chisurf.gui.plots.plotbase import Plot

#: Node fill by kind. Parameters are shaded by uncertainty on top of this, so
#: the entry for ``parameter`` is only the well-determined end of the ramp.
KIND_SYMBOL = {
    "parameter": "o",
    "dataset": "s",
    "clique": "d",
    "separator": "t",
}


def _uncertainty_colour(value) -> str:
    """Return a hex colour for a normalised uncertainty in ``[0, 1]``.

    Pale blue-green where the data has pinned the parameter down, hot orange
    where it has not, so an unconstrained parameter is the thing the eye lands
    on first. ``None`` -- no error estimate at all -- is grey, which must not
    read as either end of the ramp.
    """
    if value is None:
        return "#808080"
    v = float(min(1.0, max(0.0, value)))
    # Teal (well determined) -> amber -> red (poorly determined).
    stops = ((0.0, (0x3C, 0xB4, 0xA0)), (0.5, (0xE0, 0xB8, 0x4C)), (1.0, (0xD9, 0x53, 0x4F)))
    for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
        if v <= p1:
            t = 0.0 if p1 == p0 else (v - p0) / (p1 - p0)
            rgb = tuple(int(round(a + (b - a) * t)) for a, b in zip(c0, c1))
            return "#{:02x}{:02x}{:02x}".format(*rgb)
    return "#d9534f"


class PosteriorGraphPlot(Plot):
    """Tabbed structure / correlation / junction-tree views of the posterior."""

    name = "Posterior graph"

    def __init__(self, fit: chisurf.core.fitting.fit.Fit, **kwargs):
        """Build the tabs; the plots are filled on :meth:`update`."""
        super().__init__(fit)
        self.fit = fit
        # ``Plot`` already installs the layout; adding another silently detaches
        # every child.
        self.tabs = QtWidgets.QTabWidget()
        self.layout.addWidget(self.tabs)

        self._views = []
        for title in ("Structure", "Dependence", "Junction tree"):
            page = QtWidgets.QWidget()
            page_layout = QtWidgets.QVBoxLayout(page)
            page_layout.setContentsMargins(4, 4, 4, 4)
            plot = ChiPlot()
            plot.set_aspect_locked(False)
            plot.set_axis_visible(left=False, bottom=False)
            plot.set_interactive(menu=True)
            page_layout.addWidget(plot.canvas.widget(), 1)
            notes = QtWidgets.QLabel("")
            notes.setWordWrap(True)
            notes.setTextFormat(1)  # Qt::RichText
            page_layout.addWidget(notes, 0)
            self.tabs.addTab(page, title)
            self._views.append((plot, notes))

    def update(self, *args, **kwargs) -> None:
        """Rebuild all three views from the current fit."""
        super().update(*args, **kwargs)
        builders = (gv.structure_view, gv.correlation_view, gv.junction_tree_view)
        for (plot, notes), build in zip(self._views, builders):
            try:
                view = build(self.fit)
            except Exception as e:
                plot.clear()
                notes.setText(f"<i>could not build this view: {e}</i>")
                continue
            self._draw(plot, view)
            self._write_notes(notes, view)

    @staticmethod
    def _write_notes(label: QtWidgets.QLabel, view: gv.GraphView) -> None:
        """Put the legend and any findings under the plot."""
        parts = [f"<span style='color:#888'>{view.legend}</span>"]
        for note in view.notes:
            parts.append(f"<b>&#9888;</b> {note}")
        label.setText("<br>".join(parts))

    @staticmethod
    def _draw(plot: ChiPlot, view: gv.GraphView) -> None:
        """Paint one :class:`~chisurf.core.fitting.graphview.GraphView`."""
        plot.clear()
        plot.set_title(view.title)
        positions = {n.key: (n.x, n.y) for n in view.nodes}

        # Fit the frame to the content rather than assuming the full [-1, 1]
        # square: a junction tree is often a chain, which lays out as a line and
        # would otherwise be drawn hairline-thin across an empty square canvas.
        xs = [n.x for n in view.nodes] or [0.0]
        ys = [n.y for n in view.nodes] or [0.0]
        y_lo, y_hi = min(ys), max(ys)
        # A degenerate (one-dimensional) layout still needs a frame with height,
        # or every offset below gets multiplied by nothing.
        y_span = max(y_hi - y_lo, 0.5)
        y_lo, y_hi = y_lo - 0.22 * y_span, y_hi + 0.14 * y_span
        # Offsets must be a fraction of the *displayed* range, not a fixed
        # number of layout units. The aspect is deliberately not locked, so when
        # the y-range collapses a constant offset throws every label clean off
        # the node it names.
        label_drop = 0.055 * (y_hi - y_lo)
        x_centre = 0.5 * (min(xs) + max(xs))

        # Edges first, so nodes sit on top of them rather than under.
        for edge in view.edges:
            if edge.source not in positions or edge.target not in positions:
                continue
            x0, y0 = positions[edge.source]
            x1, y1 = positions[edge.target]
            weight = float(max(0.0, min(1.0, edge.weight)))
            if edge.kind == "correlation":
                width = 1.0 + 5.0 * weight
                shade = int(round(90 + 140 * weight))
                colour = f"#{shade:02x}{shade // 2:02x}{shade:02x}"
            elif edge.kind == "dependence":
                # Coupled, but not along a straight line. Drawn warm rather than
                # violet so it cannot be mistaken for an ordinary correlation:
                # the two call for different responses, and the whole point of
                # measuring it was that a correlation coefficient misses it.
                width = 1.0 + 5.0 * weight
                shade = int(round(110 + 120 * weight))
                colour = f"#{shade:02x}{shade // 2:02x}3a"
            elif edge.kind == "separator":
                width, colour = 2.0, "#7f9fbf"
            else:
                width, colour = 1.4, "#9a9a9a"
            plot.line([x0, x1], [y0, y1], pen=S.to_pen(colour, width=width))
            if edge.label:
                # Offset perpendicular to the edge, or the text sits on the line
                # it describes and neither can be read.
                dx, dy = x1 - x0, y1 - y0
                length = math.hypot(dx, dy) or 1.0
                nx_, ny_ = -dy / length, dx / length
                # The normal flips with the edge's direction, which would put
                # two labels for the same separator on opposite sides of the
                # same chain. Always offset upwards.
                if ny_ < 0.0:
                    nx_, ny_ = -nx_, -ny_
                # Off-centre, not at the midpoint: two edges that cross do so
                # near their midpoints, so midpoint labels land on top of each
                # other exactly where the picture is already busiest.
                t = 0.36
                # A centred label beside a *vertical* edge overlaps it however
                # far it is pushed sideways, because half its own width comes
                # straight back. Anchoring it on the side facing the line makes
                # it grow away from the line instead, whatever it says.
                if abs(nx_) > abs(ny_):
                    # ...and it must grow *inwards*. A label pushed away from a
                    # near-vertical edge at the edge of the frame runs straight
                    # off it, so the side is chosen by where the room is.
                    if 0.5 * (x0 + x1) > x_centre:
                        nx_ = -abs(nx_)
                    else:
                        nx_ = abs(nx_)
                    anchor = (0.0, 0.5) if nx_ > 0.0 else (1.0, 0.5)
                else:
                    anchor = (0.5, 0.5)
                plot.text(
                    edge.label,
                    (x0 + t * dx + 0.4 * label_drop * nx_, y0 + t * dy + label_drop * ny_),
                    color="#b0b0b0",
                    anchor=anchor,
                )

        # Nodes, grouped by (symbol, colour) so each marker style is one call.
        grouped: dict = {}
        for node in view.nodes:
            symbol = KIND_SYMBOL.get(node.kind, "o")
            colour = _uncertainty_colour(node.value) if node.kind == "parameter" else "#5a7fa8"
            grouped.setdefault((symbol, colour, node.size), []).append(node)
        for (symbol, colour, size), members in grouped.items():
            plot.scatter(
                [n.x for n in members],
                [n.y for n in members],
                size=16.0 * float(size),
                brush=colour,
                pen=S.to_pen("#202020", width=1.0),
                symbol=symbol,
            )

        for node in view.nodes:
            # Below the marker, so a label never sits on the node it names.
            plot.text(node.label, (node.x, node.y - label_drop), color="#e8e8e8", anchor=(0.5, 0.0))

        x_span = max(max(xs) - min(xs), 0.5)
        plot.set_range(
            x=(min(xs) - 0.14 * x_span, max(xs) + 0.14 * x_span),
            y=(y_lo, y_hi),
            padding=0.0,
        )
        plot.grid(x=False, y=False)
