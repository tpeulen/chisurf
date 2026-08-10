"""OpenGL backend for chiplot (PRD-64 Phase 5+).

A native OpenGL 2-D renderer behind the same :mod:`base` contract as the
pyqtgraph backend. Data items (curves, scatters, bars, images) are drawn
with shaders + VBOs on a ``QOpenGLWidget`` surface; axes/ticks/text are
overlaid with ``QPainter``.

The rendering core (:mod:`._glcore`) and handle logic (:mod:`._handles`)
are Qt-free; only :mod:`._canvas` imports Qt, and only to obtain a GL
context and paint text. This keeps the path to a non-Qt surface short.

Select with::

    CHISURF_PLOT_BACKEND=opengl

or via the ``gui.plot.backend`` setting.
"""

from __future__ import annotations

from chisurf.gui.chiplot.backends import base
from chisurf.gui.chiplot.backends.opengl._canvas import (
    _GlCanvas, _GlGrid, _GlImageView)


class OpenGLBackend(base.Backend):
    """Factory for OpenGL-backed chiplot canvases.

    Produces :class:`~._canvas._GlCanvas`, :class:`~._canvas._GlGrid`,
    and :class:`~._canvas._GlImageView` instances that satisfy the
    :mod:`base` contract.
    """

    name = "opengl"

    def create_canvas(self, **opts) -> base.Canvas:
        """Create a single-panel OpenGL canvas.

        Parameters
        ----------
        **opts
            Forwarded to :class:`_GlCanvas`.
        """
        return _GlCanvas(**opts)

    def create_grid(self, **opts) -> base.GridCanvas:
        """Create a multi-panel OpenGL grid canvas.

        Parameters
        ----------
        **opts
            Forwarded to :class:`_GlGrid`.
        """
        return _GlGrid(**opts)

    def create_image_view(self, **opts) -> base.ImageViewCanvas:
        """Create an OpenGL image-view canvas.

        Parameters
        ----------
        **opts
            Forwarded to :class:`_GlImageView`.
        """
        return _GlImageView(**opts)

    def configure(self, **global_opts) -> None:
        """Apply process-wide rendering options.

        The OpenGL backend has no global configuration to apply yet; the
        call is accepted for API compatibility.
        """

    def raw_module(self):
        """No passthrough library — this backend is fully native."""
        return None
