"""Device, adapter and canvas plumbing for :mod:`chisurf.gui.chigame`.

This is the only module that talks to the graphics API's setup surface. Games
never import ``wgpu`` themselves; they receive a :class:`GpuContext` from the
engine.

Two canvas flavours are supported and they are not the same code path:

* an embedded Qt widget, which presents through a real swapchain;
* an offscreen canvas, which renders to a bitmap and is what headless tests and
  screenshot verification use.

A headless capture therefore proves the *scene*, not presentation. That
divergence is deliberate and recorded in the engine concept.
"""

from __future__ import annotations

import dataclasses
from typing import Any

# ``rendercanvas.qt`` refuses to import until a Qt binding has been imported,
# and its error reads like a missing dependency rather than an ordering
# problem. Establishing the binding here means no game has to remember.
import qtpy.QtWidgets  # noqa: F401

import wgpu

#: Texture format requested when a context cannot state a preference.
FALLBACK_FORMAT = "rgba8unorm-srgb"

_ADAPTER: Any = None
_DEVICE: Any = None


def get_device() -> Any:
    """Return the process-wide graphics device, creating it on first use.

    One device is shared by every canvas, because pipelines, buffers and
    textures are only interchangeable within a device.

    Returns
    -------
    wgpu.GPUDevice
        The shared device.
    """
    global _ADAPTER, _DEVICE
    if _DEVICE is None:
        _ADAPTER = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
        _DEVICE = _ADAPTER.request_device_sync()
    return _DEVICE


def get_adapter() -> Any:
    """Return the adapter backing :func:`get_device`.

    Returns
    -------
    wgpu.GPUAdapter
        The shared adapter. Its ``info`` names the backend actually in use,
        which is worth logging when a render looks wrong.
    """
    if _ADAPTER is None:
        get_device()
    return _ADAPTER


@dataclasses.dataclass
class GpuContext:
    """A configured canvas and the device that draws into it.

    Attributes
    ----------
    canvas : object
        The ``rendercanvas`` canvas. For the Qt flavour this is also a
        ``QWidget`` and can be docked, themed and grabbed like any other.
    context : object
        The canvas' wgpu context, already configured.
    device : wgpu.GPUDevice
        The shared device.
    format : str
        The texture format the context was configured with. Query it rather
        than assuming: a real window commonly prefers a BGRA format while the
        offscreen path prefers RGBA.
    """

    canvas: Any
    context: Any
    device: Any
    format: str

    @property
    def size(self) -> tuple[int, int]:
        """Physical size of the canvas in pixels.

        Returns
        -------
        tuple of int
            ``(width, height)``, never smaller than ``(1, 1)`` so that a
            collapsed dock cannot produce a zero-sized render target.
        """
        w, h = self.canvas.get_physical_size()
        return max(1, int(w)), max(1, int(h))


def _configure(canvas: Any) -> GpuContext:
    """Configure a canvas against the shared device.

    Parameters
    ----------
    canvas : object
        A ``rendercanvas`` canvas.

    Returns
    -------
    GpuContext
        The configured context.
    """
    device = get_device()
    context = canvas.get_context("wgpu")
    try:
        fmt = context.get_preferred_format(get_adapter())
    except Exception:
        fmt = FALLBACK_FORMAT
    context.configure(device=device, format=fmt)
    return GpuContext(canvas=canvas, context=context, device=device, format=fmt)


def create_widget(parent: Any = None, *, size: tuple[int, int] | None = None) -> GpuContext:
    """Create a canvas that is a ``QWidget`` and can be embedded in ChiSurf.

    Parameters
    ----------
    parent : QWidget, optional
        Parent widget.
    size : tuple of int, optional
        Initial logical size. Omitted leaves it to the layout.

    Returns
    -------
    GpuContext
        A configured context whose ``canvas`` is a ``QWidget``.
    """
    from rendercanvas.qt import QRenderWidget

    canvas = QRenderWidget(parent=parent)
    _mark_canvas_closed_on_destroy(canvas)
    if size is not None:
        canvas.set_logical_size(*size)
    return _configure(canvas)


def _mark_canvas_closed_on_destroy(canvas) -> None:
    """Tell rendercanvas the canvas is gone when Qt destroys it.

    Qt destroys an embedded widget without a ``closeEvent``, so rendercanvas
    keeps it registered as open; at ``aboutToQuit`` its loop probes the dead
    wrapper and PyQt raises ``RuntimeError`` where the loop expects
    ``AttributeError``, killing app shutdown. The flags are written through the
    captured instance dict, which survives the C++ half's death, so the loop
    skips both the probe and the ``close()`` call.
    """
    d = canvas.__dict__

    def _mark(*_args, _d=d):
        _d["_is_closed"] = True
        _d["_rc_closed_by_loop"] = True

    canvas.destroyed.connect(_mark)


def create_offscreen(size: tuple[int, int] = (960, 540)) -> GpuContext:
    """Create a windowless canvas for tests and screenshot verification.

    Parameters
    ----------
    size : tuple of int, optional
        Pixel size of the render target.

    Returns
    -------
    GpuContext
        A configured context with no window attached.
    """
    from rendercanvas.offscreen import RenderCanvas

    return _configure(RenderCanvas(size=size))
