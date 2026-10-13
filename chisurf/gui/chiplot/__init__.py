"""chiplot for Qt hosts: the toolkit-free API of :mod:`chisurf.chiplot` plus :func:`host`.

:mod:`chisurf.chiplot` is the plotting API (panels, grids, the image viewer,
handles, styles, backends) and imports no Qt. This package adds only what a
legacy Qt form needs to show one: :func:`host` (a :class:`PanelHost` or
:class:`ImagePanelHost`, from :mod:`chisurf.gui.chiplot.canvas`), and
re-exports the core, so a Qt call site writes ``from chisurf.gui import chiplot
as cp`` and finds the whole API in one place. Code that draws on an emtk
surface imports :mod:`chisurf.chiplot` and never loads Qt.

Quick start
-----------
>>> from chisurf.gui import chiplot as cp          # doctest: +SKIP
>>> panel = cp.Panel(title="decay")                # doctest: +SKIP
>>> curve = panel.line(x, y, pen="red", width=2)   # doctest: +SKIP
>>> layout.addWidget(cp.host(panel))               # doctest: +SKIP
"""

from __future__ import annotations

from chisurf.chiplot import (  # the toolkit-free API, re-exported for Qt hosts
    Brush,
    Color,
    Colormap,
    ImagePanel,
    LineStyle,
    Orientation,
    Panel,
    PanelGrid,
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
from chisurf.gui.chiplot.canvas import ImagePanelHost, PanelHost, host

__all__ = [
    "ImagePanelHost",
    "host",
    "PanelHost",
    "Panel",
    "ImagePanel",
    "PanelGrid",
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
