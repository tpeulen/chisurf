"""chiplot for Qt hosts: the toolkit-free API of :mod:`chisurf.chiplot` plus its ``QWidget`` wrappers.

:mod:`chisurf.chiplot` is the plotting API (panels, handles, styles, backends)
and imports no Qt. This package adds the widgets a Qt layout embeds --
:class:`Plot`, :class:`Grid`, :class:`ImageView` and :func:`host` (from
:mod:`chisurf.gui.chiplot.canvas`) -- and re-exports everything else, so a Qt
call site writes ``from chisurf.gui import chiplot as cp`` and finds the whole
API in one place. Code that draws on an emtk surface imports
:mod:`chisurf.chiplot` instead and never loads Qt.

Quick start
-----------
>>> from chisurf.gui import chiplot as cp          # doctest: +SKIP
>>> plot = cp.Plot(title="decay")                  # doctest: +SKIP
>>> curve = plot.line(x, y, pen="red", width=2)    # doctest: +SKIP
"""

from __future__ import annotations

from chisurf.chiplot import (  # the toolkit-free API, re-exported for Qt hosts
    Brush,
    Color,
    Colormap,
    LineStyle,
    Orientation,
    Panel,
    Pen,
    PlotAPI,
    Symbol,
    available_backends,
    backends,
    colormap,
    configure,
    get_backend,
    handles,
    int_color,
    set_backend,
    style,
    to_brush,
    to_color,
    to_colormap,
    to_pen,
)
from chisurf.gui.chiplot import canvas  # the Qt widgets' module (not the core's ``canvas``)
from chisurf.gui.chiplot.canvas import Grid, ImageView, PanelPlot, Plot, host

__all__ = [
    "Plot",
    "Grid",
    "ImageView",
    "host",
    "PanelPlot",
    "Panel",
    "PlotAPI",
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
    "to_colormap",
    "colormap",
    "int_color",
    "configure",
    "set_backend",
    "get_backend",
    "available_backends",
    "backends",
    "canvas",
    "handles",
    "style",
]
