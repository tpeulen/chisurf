"""chiplot — ChiSurf's renderer-neutral plotting API.

chiplot is the single seam through which ChiSurf draws 2-D plots. Call sites
use this package; they never import a rendering library directly. A backend
(pyqtgraph today, an OpenGL renderer later) is selected at runtime and can be
swapped without touching any call site.

Quick start
-----------
>>> from chisurf.gui import chiplot as cp          # doctest: +SKIP
>>> plot = cp.Plot(title="decay")                  # doctest: +SKIP
>>> curve = plot.line(x, y, pen="red", width=2)    # doctest: +SKIP
>>> plot.set_labels(left="counts", bottom="t / ns")  # doctest: +SKIP
>>> plot.set_log(y=True)                           # doctest: +SKIP
>>> region = plot.region((1.0, 4.0), movable=True) # doctest: +SKIP
>>> region.on_change(lambda lo, hi: print(lo, hi)) # doctest: +SKIP

Public surface
--------------
- Widgets: :class:`Plot`, :class:`Grid`.
- Styles: :class:`Color`, :class:`Pen`, :class:`Brush`, :class:`Colormap`,
  :class:`LineStyle`, and the coercers :func:`to_color` / :func:`to_pen` /
  :func:`to_brush` / :func:`colormap` / :func:`int_color`.
- Handle enums: :class:`Symbol`, :class:`Orientation`.
- Backend control: :func:`configure`, :func:`set_backend`, :func:`get_backend`.
"""

from __future__ import annotations

from chisurf.gui.chiplot.backends import get_backend, set_backend
from chisurf.gui.chiplot.canvas import Grid, PanelPlot, Plot
from chisurf.gui.chiplot.handles import Orientation, Symbol
from chisurf.gui.chiplot.style import (
    Brush,
    Color,
    Colormap,
    LineStyle,
    Pen,
    colormap,
    int_color,
    to_brush,
    to_color,
    to_pen,
)


def configure(**global_opts) -> None:
    """Apply process-wide rendering options to the active backend.

    Parameters
    ----------
    **global_opts
        Backend-recognised global options (e.g. ``antialias=True``,
        ``background="w"``, ``foreground="k"``). Unknown keys are the backend's
        responsibility.
    """
    get_backend().configure(**global_opts)


__all__ = [
    "Plot",
    "Grid",
    "PanelPlot",
    "Color",
    "Pen",
    "Brush",
    "Colormap",
    "LineStyle",
    "Symbol",
    "Orientation",
    "to_color",
    "to_pen",
    "to_brush",
    "colormap",
    "int_color",
    "configure",
    "set_backend",
    "get_backend",
]
