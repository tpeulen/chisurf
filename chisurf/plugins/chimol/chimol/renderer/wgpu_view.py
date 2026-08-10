"""The WebGPU renderer as a Qt widget -- chimol's viewport, drawn from WGSL.

What this is
------------
:class:`WgpuRenderer` is a drop-in for :class:`~.qtgl.QtGLRenderer`: the viewer
picks it with ``MolView(renderer_factory=WgpuRenderer)``, or by setting
``CHIMOL_RENDERER=wgpu``. It satisfies the same contract, holds the same camera,
and draws the same scene -- through the same WGSL a browser will compile.

Why it is small
---------------
Everything a renderer holds rather than draws is in
:class:`~.camera_state.CameraState`, and everything it draws is in
:class:`~.wgpu_backend.WgpuMeshRenderer`. This module is the seam between them
plus the mouse: what is left once the state and the shading are somewhere both
backends can reach them. That is the point of the arrangement -- the offscreen
comparison harness and this widget run *the same* `render_into`, so a picture
verified against the OpenGL baseline is the picture the window shows. Two paths
that merely "do the same thing" would drift, and this port has already found
three constants that did.

What it does not do yet
-----------------------
Picking, the silhouette post-pass, and 3-D labels. The in-viewport chrome -- the
object panel and the sequence strip -- *is* here, composited as a textured quad
at the end of the render pass rather than painted over the surface; see
:mod:`.gui_overlay` for why the two obvious Qt arrangements do not work.
"""
from __future__ import annotations

import os
from typing import Optional

import numpy as np
from qtpy import QtCore, QtWidgets

from .base import Renderer
from .camera_state import DEFAULT_VIEWPORT, CameraState
from .pack import pack_scene
from .scene import Scene

__all__ = ["WgpuRenderer", "renderer_factory_from_env", "is_available"]

#: Wheel notch to distance ratio. Multiplicative so one step feels the same on a
#: peptide and on a ribosome; PyMOL's own zoom is a ratio for the same reason.
WHEEL_STEP = 1.1


def is_available() -> bool:
    """Whether this machine can create a WebGPU adapter.

    Checked rather than assumed: the fallback has to be the OpenGL renderer, and
    a viewer that opens to a blank widget is worse than one that opens on the
    old backend.
    """
    try:
        import wgpu  # noqa: F401
        import rendercanvas.qt  # noqa: F401
    except Exception:
        return False
    try:
        return wgpu.gpu.request_adapter_sync(power_preference="high-performance") is not None
    except Exception:
        return False


def renderer_factory_from_env(default=None):
    """Return the renderer class ``CHIMOL_RENDERER`` selects, or ``default``.

    ``wgpu`` picks this backend, anything else (or nothing) leaves the caller's
    default in place. An environment variable rather than a config key for now,
    because this is how the port is being *exercised* -- the choice becomes a
    display-config setting when it stops being an experiment.

    Falls back to ``default`` with a warning when WebGPU asks for a backend the
    machine cannot give, since the alternative is a window with nothing in it.
    """
    import logging

    if os.environ.get("CHIMOL_RENDERER", "").strip().lower() != "wgpu":
        return default
    if not is_available():
        logging.getLogger(__name__).warning(
            "CHIMOL_RENDERER=wgpu but no WebGPU adapter is available; "
            "falling back to the OpenGL renderer"
        )
        return default
    return WgpuRenderer


def _make_widget_base():
    """Return ``rendercanvas``'s Qt widget class, importing Qt first.

    ``rendercanvas.qt`` raises on import unless a Qt binding is already
    imported, and the message reads like a missing dependency rather than an
    ordering rule. ``qtpy`` above has done it, so this only has to happen after.
    """
    from rendercanvas.qt import QRenderWidget

    return QRenderWidget


class WgpuRenderer(_make_widget_base(), CameraState, Renderer):
    """Draw a chimol scene into a Qt widget with WebGPU.

    Parameters
    ----------
    controller : object, optional
        The :class:`~.view.MolView` driving this renderer.
    parent : QWidget, optional
        Parent widget.
    """

    def __init__(self, controller: object = None, parent: object = None) -> None:
        super().__init__(parent=parent)
        self._controller = controller
        self.init_camera_state(DEFAULT_VIEWPORT)

        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )

        self._packed = None
        self._last_pos: Optional[QtCore.QPoint] = None
        self._panning = False
        #: Whether the press was consumed by the panel, so the drag belongs to
        #: it rather than to the camera.
        self._gui_grab = False

        # The object panel and the sequence strip, composited as a textured
        # quad at the end of the render pass -- see :mod:`.gui_overlay` for the
        # two Qt-child arrangements that were tried first and why neither works
        # over a presented surface.
        from .internal_gui import InternalGui

        self._internal_gui = InternalGui()
        self.internal_gui = self._internal_gui

        from .wgpu_backend import WgpuMeshRenderer

        self._context = self.get_context("wgpu")
        width, height = self._physical_size()
        # One device, shared: the context is configured against it and the
        # renderer draws with it. A texture created by one device cannot be
        # drawn into by another, and that failure surfaces as a validation error
        # deep inside the first frame rather than at setup.
        fmt = self._configure_surface()
        self._gpu = WgpuMeshRenderer(width, height, format=fmt, device=self._device)
        self.request_draw(self._draw)

    # -- setup ---------------------------------------------------------------

    #: Surface formats to try, in order. ``rgba8unorm`` first and deliberately:
    #: it is the format the offscreen comparison renders into, so the window and
    #: the images judged against the OpenGL baseline are the same picture. An
    #: sRGB surface gamma-encodes on write and would make the window brighter
    #: than everything the port has been verified against.
    #:
    #: The list is *tried*, not queried, because the presentation path decides
    #: what it accepts and the two paths here differ: a native surface prefers
    #: ``bgra8unorm``, while the bitmap fallback (which is what a Qt widget gets
    #: on this machine) rejects it outright.
    SURFACE_FORMATS = ("rgba8unorm", "rgba8unorm-srgb", "bgra8unorm")

    def _configure_surface(self) -> str:
        """Configure the canvas context and return the format it accepted."""
        import wgpu

        adapter = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
        self._device = adapter.request_device_sync()

        candidates = list(self.SURFACE_FORMATS)
        try:
            preferred = self._context.get_preferred_format()
        except Exception:
            preferred = None
        if preferred and preferred not in candidates:
            candidates.append(preferred)

        errors = []
        for fmt in candidates:
            try:
                self._context.configure(device=self._device, format=fmt)
            except Exception as exc:
                errors.append(f"{fmt}: {exc}")
                continue
            return fmt
        raise RuntimeError(
            "no usable surface format for the WebGPU canvas: " + "; ".join(errors)
        )

    def _physical_size(self) -> tuple[int, int]:
        """Framebuffer size in device pixels, never zero.

        A widget that has not been laid out reports 0, and a zero-sized surface
        is a validation error rather than an empty picture.
        """
        try:
            width, height = self.get_physical_size()
        except Exception:
            ratio = float(self.devicePixelRatioF())
            width, height = int(self.width() * ratio), int(self.height() * ratio)
        return max(int(width), 1), max(int(height), 1)

    # -- the Renderer contract ----------------------------------------------

    def widget(self):
        """This renderer *is* the widget."""
        return self

    def set_scene(self, scene: Optional[Scene]) -> None:
        """Store the scene and pack it for upload.

        Packing here rather than per frame: it normalises dtypes and validates
        indices, which is work proportional to the scene and not to the frame
        rate. A 374k-triangle space-fill repacked every frame is the difference
        between a viewer and a slideshow.
        """
        self.scene = scene
        self._packed = pack_scene(scene) if scene is not None else None
        self.update()

    def clear(self) -> None:
        """Drop the scene and repaint."""
        self.set_scene(None)

    def update(self) -> None:  # type: ignore[override]
        """Ask for a repaint.

        Overrides ``QWidget.update`` deliberately: the viewer calls
        ``renderer.update()`` and a rendercanvas widget repaints from its own
        draw request, not from a Qt paint event.
        """
        self.update_count += 1
        try:
            self.request_draw()
        except Exception:
            pass

    def set_background_color(self, color) -> None:
        """Store the clear colour and repaint."""
        super().set_background_color(color)
        self.update()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """Track the framebuffer size the projection is built from."""
        super().resizeEvent(event)
        width, height = self._physical_size()
        self.resize_viewport(width, height)

    # -- the chrome's share of the widget ------------------------------------

    def scene_width(self) -> int:
        """Width left for the molecule once the object panel has its column.

        The panel is a *column*, not an overlay: drawn on top it would hide the
        molecule it describes, and the part it hides is the part you just moved
        out from under it. An undocked panel floats, and takes no column.
        """
        gui = self._internal_gui
        if gui is None or not (gui.visible and gui.docked):
            return max(self._width, 1)
        return max(self._width - int(gui.column_width * self._ratio()), 1)

    def scene_height(self) -> int:
        """Height left once the sequence strip has its band."""
        gui = self._internal_gui
        strip = int(gui.sequence_height()) if gui is not None else 0
        return max(self._height - int(strip * self._ratio()), 1)

    def _ratio(self) -> float:
        """Device pixels per logical pixel.

        The chrome lays itself out in *logical* pixels, because that is what a
        ``QPainter`` on a widget uses; the surface is in device pixels. Mixing
        the two puts the molecule under the panel on any high-DPI screen.
        """
        try:
            return float(self.devicePixelRatioF())
        except Exception:
            return 1.0

    def _scene_viewport(self) -> tuple[float, float, float, float]:
        """The molecule's rectangle in the surface, in device pixels.

        The strip is at the *top*, so the viewport starts below it -- WebGPU's
        framebuffer origin is top-left, where GL's is bottom-left and the same
        band falls out of a shorter viewport with no offset. That difference is
        exactly the kind that renders correctly upside down.
        """
        gui = self._internal_gui
        ratio = self._ratio()
        strip = int((gui.sequence_height() if gui is not None else 0) * ratio)
        return (0.0, float(strip), float(self.scene_width()), float(self.scene_height()))

    def resize_viewport(self, width: int, height: int) -> None:
        """Set the viewport for both the camera and the GPU renderer.

        Named apart from ``resize`` because ``QWidget.resize`` already means
        something else, and a renderer that silently resizes its window when the
        viewer meant to tell it a viewport size is a hard bug to see.
        """
        CameraState.resize(self, width, height)
        self._gpu.resize(width, height)
        self.update()

    def _background_rgb(self) -> tuple[float, float, float]:
        """The clear colour as linear RGB, whatever form it was stored in.

        By shape, not by ``isinstance(tuple, list)``: the command layer's colour
        parser returns a **numpy array**, which is neither, and a test against
        those two types silently fell through to black -- ``bg_color white`` did
        nothing and reported success.
        """
        from ..colors import as_rgba

        raw = self._background
        rgba = as_rgba(raw)
        if rgba is None:
            return (0.0, 0.0, 0.0)
        return tuple(float(c) for c in rgba[:3])

    # -- drawing -------------------------------------------------------------

    def _draw(self) -> None:
        """Render one frame into the canvas' current texture."""
        width, height = self._physical_size()
        if (width, height) != (self._gpu.width, self._gpu.height):
            CameraState.resize(self, width, height)
            self._gpu.resize(width, height)

        texture = self._context.get_current_texture()
        background = self._background_rgb()
        if self._packed is None or not self._packed.objects:
            # Still clear: a viewer with nothing loaded shows its background,
            # not whatever was in the buffer.
            self._gpu.render_into(
                texture.create_view(),
                pack_scene(None),
                self.get_view_state(),
                background=background,
            )
            return
        self._gpu.render_into(
            texture.create_view(),
            self._packed,
            self.get_view_state(),
            background=background,
            lighting=self._resolved_rig(),
            target_radius=self._target_radius,
            viewport=self._scene_viewport(),
            overlay=self._chrome_image(),
        )

    def _chrome_image(self) -> Optional[np.ndarray]:
        """The panel and strip as a premultiplied RGBA image, or ``None``.

        Repainted per frame rather than cached. It is a few hundred glyphs
        against a scene of tens of thousands of triangles, and every attempt at
        a dirty flag here has the same failure mode as the sequence colours the
        panel itself re-reads every frame: colouring is a *command*, there is no
        signal for it, and a cache invalidated by the events anyone thinks of
        goes stale on the one they did not.
        """
        from .gui_overlay import paint_chrome

        gui = self._internal_gui
        if gui is None:
            return None
        return paint_chrome(
            gui, self._controller, self._width, self._height, self._ratio()
        )

    def _resolved_rig(self):
        """The configured light rig with the viewer's overrides applied.

        ``set_lighting`` speaks ChimeraX's names (``key_light_intensity`` and
        friends) and the rig uses its own, so the mapping happens once, here.
        """
        from .lighting import CHIMERAX_NAMES, resolve_light_rig

        rig = resolve_light_rig()
        overrides = {
            CHIMERAX_NAMES[name]: float(value)
            for name, value in self.lighting_state.items()
            if name in CHIMERAX_NAMES
        }
        return rig.replace(**overrides) if overrides else rig

    def grab_image(self) -> np.ndarray:
        """Render the current view offscreen and return ``(h, w, 3)`` uint8.

        A window's own framebuffer cannot be read back portably, and a
        screenshot helper that pastes a widget grab captures the compositor's
        idea of the surface rather than the render. Re-rendering through the
        same code into an offscreen target gives the frame itself.
        """
        from .wgpu_backend import WgpuMeshRenderer

        offscreen = WgpuMeshRenderer(
            self._gpu.width, self._gpu.height, device=self._gpu.device
        )
        packed = self._packed if self._packed is not None else pack_scene(None)
        return offscreen.render(
            packed,
            self.get_view_state(),
            background=self._background_rgb(),
            lighting=self._resolved_rig(),
            target_radius=self._target_radius,
        )

    # -- mouse ---------------------------------------------------------------

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """Offer the press to the panel, then begin a camera drag.

        The panel is offered it *first*, as in qtgl: otherwise a click meant for
        a menu also starts rotating the molecule, and the model spins away under
        the menu that just opened.
        """
        pos = event.pos()
        gui = self._internal_gui
        if gui is not None and gui.mouse_press(
            float(pos.x()),
            float(pos.y()),
            right=event.button() == QtCore.Qt.RightButton,
            modifiers=event.modifiers(),
        ):
            self._gui_grab = True
            self.update()
            event.accept()
            return

        self._last_pos = pos
        modifiers = event.modifiers()
        self._panning = bool(
            event.button() == QtCore.Qt.MiddleButton
            or (
                event.button() == QtCore.Qt.LeftButton
                and modifiers & QtCore.Qt.ShiftModifier
            )
        )
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """Orbit, pan or dolly, following the decision the press made.

        Keyed on what the press decided rather than re-derived from the button:
        deriving it here is what once made ctrl-left rotate when the mode table
        said pan.
        """
        pos = event.pos()
        gui = self._internal_gui
        if self._gui_grab:
            if gui is not None and gui.is_dragging() and gui.drag(
                float(pos.x()), float(pos.y())
            ):
                self.update()
            event.accept()
            return
        if gui is not None and not event.buttons():
            if gui.mouse_move(float(pos.x()), float(pos.y())):
                self.update()
            if gui.wants(float(pos.x()), float(pos.y())):
                event.accept()
                return

        if self._last_pos is None or not event.buttons():
            return
        last, cur = self._last_pos, event.pos()
        ratio = float(self.devicePixelRatioF())
        if self._panning:
            self.pan((cur.x() - last.x()) * ratio, (cur.y() - last.y()) * ratio)
        elif event.buttons() & QtCore.Qt.RightButton:
            # Right drag dollies, as PyMOL's `cButModeTransZ` does.
            self.dolly(WHEEL_STEP ** ((cur.y() - last.y()) / 40.0))
        else:
            self.orbit(
                (last.x() * ratio, last.y() * ratio),
                (cur.x() * ratio, cur.y() * ratio),
            )
        self._last_pos = cur
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """End the drag, in the panel and in the camera."""
        if self._internal_gui is not None:
            self._internal_gui.release()
            self.update()
        self._gui_grab = False
        self._last_pos = None
        self._panning = False
        event.accept()

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """Dolly the camera, by a ratio per notch."""
        delta = event.angleDelta().y()
        if not delta:
            return
        self.dolly(WHEEL_STEP ** (-delta / 120.0))
        self.update()
        event.accept()
