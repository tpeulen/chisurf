"""chiplot — ChiSurf's renderer-neutral plotting API, toolkit-free.

chiplot is the single seam through which ChiSurf draws 2-D plots. Call sites
use this package; they never import a rendering library directly. The backend
(emtk, drawn through its own painter) is selected at runtime; another renderer
can be registered without touching any call site.

This package is the toolkit-free core: the panel API (:class:`PlotAPI`,
the grid and image view controls (:mod:`chisurf.chiplot.backends`), the handles,
the styles. Nothing in it imports a toolkit (``test/test_chiplot_core_qt_free.py``
greps the source). Widget wrappers are the optional host layer
:mod:`chisurf.gui.chiplot`, which re-exports everything here.

Quick start
-----------
>>> from chisurf import chiplot as cp              # doctest: +SKIP
>>> panel = cp.Panel(title="decay")                # doctest: +SKIP
>>> curve = panel.line(x, y, pen="red", width=2)   # doctest: +SKIP
>>> panel.set_labels(left="counts", bottom="t / ns")  # doctest: +SKIP
>>> panel.set_log(y=True)                          # doctest: +SKIP
>>> region = panel.region((1.0, 4.0), movable=True)  # doctest: +SKIP
>>> region.on_change(lambda lo, hi: print(lo, hi)) # doctest: +SKIP

Public surface
--------------
- Panels: :class:`Panel` (an emtk control), :class:`PlotAPI` (what every panel shares),
  :class:`ImagePanel` (the image viewer: picture, colour ramp, frame slider; an emtk control).
- Styles: :class:`Color`, :class:`Pen`, :class:`Brush`, :class:`Colormap`,
  :class:`LineStyle`, and the coercers :func:`to_color` / :func:`to_pen` /
  :func:`to_brush` / :func:`colormap` / :func:`to_colormap` / :func:`int_color`.
- Handle enums: :class:`Symbol`, :class:`Orientation`.
- Backend control: :func:`configure`, :func:`set_backend`, :func:`get_backend`.
"""

from __future__ import annotations

from chisurf.chiplot import backends, canvas, handles, style
from chisurf.chiplot.backends import available_backends, get_backend, set_backend
from chisurf.chiplot.canvas import Panel, PlotAPI
from chisurf.chiplot.image_panel import ImagePanel
from chisurf.chiplot.handles import Orientation, Symbol
from chisurf.chiplot.style import (
    Brush,
    Color,
    Colormap,
    LineStyle,
    Pen,
    colormap,
    int_color,
    to_brush,
    to_color,
    to_colormap,
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
    "Panel",
    "ImagePanel",
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
