"""WebGPU backend for chiplot — the native renderer.

A GPU 2-D renderer behind the same :mod:`base` contract as the pyqtgraph
backend, so selecting it changes no call site.

Why WebGPU rather than OpenGL
-----------------------------
OpenGL is deprecated on macOS and what remains is a GL 2.1 feature set emulated
over Metal — no dependable point size, no ``texture1D``, and a compositing
conflict with ``QPainter`` that loses the frame. WebGPU is one API and one
shader text across macOS, Linux, Windows and the browser, which is also why the
molecular viewer's renderer targets it. The shader lives in ``wgsl/`` and is
shared rather than transpiled.

Layout
------

===================  ========================================================
:mod:`._view`        data <-> clip <-> pixel mapping (no Qt, no GPU)
:mod:`._gpu`         device, pipelines, offscreen render, stroke/marker geometry
:mod:`._handles`     the drawn objects; each contributes geometry, not draw calls
:mod:`._canvas`      the Qt widget: blit the rendered image, draw the chrome
``wgsl/plot2d.wgsl`` the shader, shared with any future browser surface
===================  ========================================================

Select with::

    CHISURF_PLOT_BACKEND=wgpu

or via the ``gui.plot.backend`` setting.
"""

from __future__ import annotations

from chisurf.gui.chiplot.backends import base
from chisurf.gui.chiplot.backends.wgpu._canvas import _WgpuCanvas, _WgpuGrid, _WgpuImageView
from chisurf.gui.chiplot.backends.wgpu._gpu import adapter_info, is_available


class WgpuBackend(base.Backend):
    """Factory for WebGPU-backed chiplot canvases."""

    name = "wgpu"

    def create_canvas(self, **opts) -> base.Canvas:
        """Create a single-panel canvas.

        Parameters
        ----------
        **opts
            Forwarded to :class:`~._canvas._WgpuCanvas`.
        """
        return _WgpuCanvas(**opts)

    def create_grid(self, **opts) -> base.GridCanvas:
        """Create a multi-panel grid canvas.

        Parameters
        ----------
        **opts
            Forwarded to :class:`~._canvas._WgpuGrid`.
        """
        return _WgpuGrid(**opts)

    def create_image_view(self, **opts) -> base.ImageViewCanvas:
        """Create an image-view canvas.

        Parameters
        ----------
        **opts
            Forwarded to :class:`~._canvas._WgpuImageView`.
        """
        return _WgpuImageView(**opts)

    def configure(self, **global_opts) -> None:
        """Apply process-wide rendering options.

        There is no global state to configure: antialiasing is always on and
        the background is a per-canvas property.
        """

    def raw_module(self):
        """No passthrough library — this backend is fully native."""
        return None


__all__ = ["WgpuBackend", "adapter_info", "is_available"]
