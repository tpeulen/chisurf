"""The WebGPU renderer as a Qt widget -- chimol's viewport, drawn from WGSL.

What this is
------------
:class:`WgpuRenderer` is chimol's renderer: the viewer
draws chimol's viewport, and since the OpenGL renderer was removed it is the
only backend that draws at all -- through the same WGSL a browser will compile.
A machine with no WebGPU adapter gets :class:`~.headless.SceneSink`, which
builds scenes and rasterises nothing: honest about having no window, rather
than opening an empty one.

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
The object panel's pop-up menus and the wizard beyond hover/click/drag routing.
Everything else the OpenGL renderer draws is here: the molecule, the object
panel, the sequence strip, 3-D labels, the depth-outline silhouette, and atom
picking. The chrome and the labels are composited as a textured quad at the end
of the render pass rather than painted over the surface -- see
:mod:`.gui_overlay` for why the two obvious Qt arrangements do not work.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import numpy as np
from qtpy import QtCore, QtWidgets

from .base import Renderer
from .camera_state import DEFAULT_VIEWPORT, CameraState
from .pack import pack_scene
from .scene import Scene

__all__ = [
    "DEFAULT_BACKEND",
    "WgpuRenderer",
    "default_renderer",
    "is_available",
    "selected_backend",
]

#: The backend chimol draws with. WGSL is the one source the desktop and the
#: browser share, and since the OpenGL renderer was removed it is the only
#: drawing backend there is -- the setting survives because a second one
#: (a browser canvas, a headless tracer) is the point of the arrangement.
DEFAULT_BACKEND = "wgpu"

#: Wheel notch to distance ratio. Multiplicative so one step feels the same on a
#: peptide and on a ribosome; PyMOL's own zoom is a ratio for the same reason.
WHEEL_STEP = 1.1


def is_available() -> bool:
    """Whether this machine can create a WebGPU adapter.

    Checked rather than assumed: the fallback has to be the OpenGL renderer, and
    a viewer that opens to a blank widget is worse than one that opens on the
    old backend.
    """
    from .gpu import api as wgpu
    from .gpu import native

    if not native.is_available():
        return False
    try:
        import rendercanvas.qt  # noqa: F401
    except Exception:
        return False
    try:
        return wgpu.gpu.request_adapter_sync(power_preference="high-performance") is not None
    except Exception:
        return False


def selected_backend() -> str:
    """Which backend the user asked for: ``"wgpu"`` or ``"opengl"``.

    ``CHIMOL_RENDERER`` wins, then the ``renderer.backend`` display-config key,
    then the default -- which is **wgpu**. The environment variable stays
    because it is what makes a bug report reproducible either way without
    editing a config file.
    """
    from ..config import _DISPLAY_CONFIG

    choice = os.environ.get("CHIMOL_RENDERER", "").strip().lower()
    if not choice:
        section = _DISPLAY_CONFIG.get("renderer")
        if isinstance(section, dict):
            choice = str(section.get("backend", "")).strip().lower()
    return choice or DEFAULT_BACKEND


def default_renderer():
    """The renderer class the viewer builds when it is given none.

    :class:`WgpuRenderer` when this machine can create a WebGPU adapter, and
    :class:`~.headless.SceneSink` when it cannot -- a scene-only backend, which
    is honest about having no window rather than opening an empty one. There is
    no OpenGL renderer to fall back to any more; the WGSL one replaced it.

    The refusal is logged rather than silent: "chimol shows nothing today" is a
    much harder question to answer than "chimol said it had no adapter".
    """
    import logging

    if not is_available():
        logging.getLogger(__name__).warning(
            "no WebGPU adapter is available; chimol will build scenes but draw "
            "nothing. Check that `wgpu` and `rendercanvas` are installed and "
            "that this machine has a supported GPU."
        )
        from .headless import SceneSink

        return SceneSink
    return WgpuRenderer


@dataclass
class Label:
    """One 3-D label: a world position, its text, and its colour."""

    pos: np.ndarray
    text: str
    color: tuple


def _collect_labels(packed) -> list:
    """Pull ``kind == "text"`` geometry out of a packed scene.

    Labels are the one thing in a scene that is not geometry at all -- a string
    at a point -- so they leave the GPU path here and rejoin it as glyphs in the
    composited chrome image.
    """
    labels: list[Label] = []
    if packed is None:
        return labels
    for obj in packed.objects:
        geom = obj.geometry
        if geom.kind != "text":
            continue
        texts = geom.meta.get("labels", [])
        positions = np.asarray(geom.positions, dtype=float)
        colours = geom.colors
        for i in range(min(len(texts), positions.shape[0])):
            rgba = (1.0, 1.0, 1.0, 1.0)
            if colours is not None and i < colours.shape[0]:
                rgba = tuple(float(c) for c in colours[i][:4])
            labels.append(Label(positions[i], str(texts[i]), rgba))
    return labels


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

        # Qt destroys an embedded widget without a closeEvent, so rendercanvas
        # keeps it registered as open; at aboutToQuit its loop probes the dead
        # wrapper and PyQt raises RuntimeError where the loop expects
        # AttributeError, killing app shutdown. Writing the flags through the
        # captured instance dict survives the C++ half's death, so the loop
        # skips both the probe and the close() call.
        def _mark_closed(*_args, _d=self.__dict__):
            _d["_is_closed"] = True
            _d["_rc_closed_by_loop"] = True

        self.destroyed.connect(_mark_closed)

        self._controller = controller
        self.init_camera_state(DEFAULT_VIEWPORT)

        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )

        self._packed = None
        #: Everything this frame draws: the scene's objects, plus the grid when
        #: it is visible. See :meth:`_rebuild_draw_data`.
        self._draw_data: list = []
        self._labels: list[Label] = []
        self._last_pos: Optional[QtCore.QPoint] = None
        self._press_pos: Optional[QtCore.QPoint] = None
        self._panning = False
        #: Whether the press was consumed by the panel, so the drag belongs to
        #: it rather than to the camera.
        self._gui_grab = False
        #: A traced frame shown over the scene column, or None for the live view.
        self._ray_image = None
        self._background_source = None
        #: The rubber-band selection box while it is being dragged, in widget
        #: pixels. Chrome like the panel and the labels, so it is composited with
        #: them: it has to appear in a grab of the viewport for a screenshot to
        #: show what was selected.
        self._select_rect: Optional[QtCore.QRect] = None
        self._drag_selecting = False
        self._drag_start: Optional[QtCore.QPoint] = None
        self._drag_button = None
        self._drag_action: Optional[str] = None
        self._drag_modifiers = QtCore.Qt.NoModifier
        self._press_mods = QtCore.Qt.NoModifier
        self._press_button = None
        self._right_dragged = False

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
        from .gpu import api as wgpu

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
        """Store the scene, pack it for upload, and collect its labels.

        Packing here rather than per frame: it normalises dtypes and validates
        indices, which is work proportional to the scene and not to the frame
        rate. A 374k-triangle space-fill repacked every frame is the difference
        between a viewer and a slideshow.
        """
        # A traced frame is a still of a scene that no longer exists, and
        # leaving it up means the viewport shows a picture of something the
        # commands have already changed.
        self.clear_ray_image()
        self.scene = scene
        self._packed = pack_scene(scene) if scene is not None else None
        self._labels = _collect_labels(self._packed)
        # A new scene means new geometry; the buffers cached for
        # the old one are dead weight and the chrome must not be a frame behind.
        self._rebuild_draw_data()
        self.update()

    def clear(self) -> None:
        """Drop the scene and repaint."""
        self.set_scene(None)

    def set_grid_visible(self, visible: bool) -> None:
        """Show or hide the ground grid, and rebuild what is drawn.

        The flag alone proves nothing -- it is the draw list that has to change,
        and a setter that only records the flag is how a menu item comes to
        toggle a value nothing reads.
        """
        CameraState.set_grid_visible(self, visible)
        self._rebuild_draw_data()
        self.update()

    def configure_grid(self, size: float, spacing: float) -> None:
        """Set the grid's extent and spacing, and rebuild it."""
        CameraState.configure_grid(self, size, spacing)
        self._rebuild_draw_data()
        self.update()

    def _rebuild_draw_data(self) -> None:
        """The list of things this frame draws: the scene, plus the grid.

        Held rather than derived per frame so that "is the grid being drawn?"
        has an answer that does not require rendering, and so the grid's
        geometry -- which depends on the scene's radius, not on the camera -- is
        built when the scene changes rather than sixty times a second.
        """
        from .pack import PackedObject

        objects = list(self._packed.objects) if self._packed is not None else []
        if self._grid_visible:
            radius = self._packed.radius if self._packed is not None else self._target_radius
            grid = self._build_grid_draw_data(radius)
            if grid is not None:
                objects.append(
                    PackedObject(id="grid", geometry=grid, render_mode="overlay")
                )
        self._draw_data = objects

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
        CameraState.set_background_color(self, color)
        self.update()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """Track the framebuffer size the projection is built from."""
        super().resizeEvent(event)
        width, height = self._physical_size()
        self.resize_viewport(width, height)

    # -- the chrome's share of the widget ------------------------------------

    def scene_width(self) -> int:
        """Width left for the molecule once the object panel has its column.

        In the **widget's** logical pixels, not the surface's device ones. Two
        different sizes live in this class and confusing them is a real bug: the
        contract (framing, picking, the panel's own layout) is logical, and only
        the GPU target is in device pixels. Reporting the surface size here made
        the aspect ratio stale until the first ``resizeEvent``, so a viewer that
        had been resized but not shown framed for the wrong shape.

        The panel is a *column*, not an overlay: drawn on top it would hide the
        molecule it describes, and the part it hides is the part you just moved
        out from under it. An undocked panel floats, and takes no column.
        """
        gui = self._internal_gui
        if gui is None or not (gui.visible and gui.docked):
            return max(int(self.width()), 1)
        return max(int(self.width()) - int(gui.column_width), 1)

    def scene_height(self) -> int:
        """Height left once the sequence strip has its band, in logical pixels."""
        gui = self._internal_gui
        strip = int(gui.sequence_height()) if gui is not None else 0
        return max(int(self.height()) - strip, 1)

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
        ratio = self._ratio()
        strip = (self.height() - self.scene_height()) * ratio
        return (
            0.0,
            float(strip),
            float(self.scene_width() * ratio),
            float(self.scene_height() * ratio),
        )

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
        """The clear colour as linear RGB.

        Resolved once by :meth:`~.camera_state.CameraState.set_background_color`,
        so this is only a narrowing from RGBA.
        """
        return tuple(float(c) for c in self.get_background_color()[:3])

    # -- drawing -------------------------------------------------------------

    def _draw(self) -> None:
        """Render one frame into the canvas' current texture."""
        width, height = self._physical_size()
        if (width, height) != (self._gpu.width, self._gpu.height):
            CameraState.resize(self, width, height)
            self._gpu.resize(width, height)

        texture = self._context.get_current_texture()
        background = self._background_rgb()
        if not self._draw_data:
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
            self._frame_scene(),
            self.get_view_state(),
            background=background,
            lighting=self._resolved_rig(),
            target_radius=self._target_radius,
            viewport=self._scene_viewport(),
            overlay=self._chrome_image(),
            chrome=self._chrome_quads(),
        )

    def _chrome_quads(self) -> Optional[np.ndarray]:
        """The panel, strip, menus and transport as GPU quads.

        Returns
        -------
        numpy.ndarray or None
            ``(n, 12)`` float32 for ``ui.wgsl``, or ``None`` when there is no
            panel to draw.

        Notes
        -----
        Built **every frame**, and the absence of a cache is the change. The
        panel used to be rasterised into a full-viewport image by ``QPainter``
        -- *9.6 ms of a 21 ms frame* with a quarter of a million beads on screen
        -- which was expensive enough that it could not be repainted when it
        changed. It was repainted on a *timer* instead, so the panel was allowed
        to lag by up to ``CHROME_INTERVAL``, and the whole arrangement was
        bypassed for any scene carrying labels because labels move with the
        camera.

        A frame of chrome is 313-608 quads. Rebuilding that costs less than
        deciding whether it needed rebuilding, so the panel is now simply always
        current -- and the staleness, the timer, the sampled-signature cache and
        the ``invalidate_chrome`` calls that worked around them are gone with it.
        """
        gui = self._internal_gui
        if gui is None:
            return None

        from .gui_overlay import refresh_gui_state
        from .ui.quad_painter import QuadPainter

        refresh_gui_state(gui, self._controller)
        # `self._width`/`self._height` are **device** pixels: `_draw` resizes
        # the camera from `_physical_size()`. The panel must be laid out in
        # **logical** pixels and scaled back up as the quads are built, which is
        # exactly what the QPainter path did (`paint_chrome_into` took
        # `width / ratio`).
        #
        # Both halves matter, and getting either alone is worse than getting
        # neither. Laying out in device pixels draws the panel correctly and
        # hit-tests it in the wrong coordinates, so it looks fine and ignores
        # every click. Scaling that by the ratio as well puts it off the right
        # edge of the window entirely.
        ratio = self._ratio()
        gui.layout(int(self._width / ratio), int(self._height / ratio))
        painter = QuadPainter(scale=ratio)
        gui.paint(painter)
        vertices = painter.vertices()
        return vertices if len(vertices) else None

    def _chrome_image(self) -> Optional[np.ndarray]:
        """Labels, the traced frame and the selection box, as one image.

        Returns
        -------
        numpy.ndarray or None
            ``(h, w, 4)`` premultiplied RGBA, or ``None`` -- which is the usual
            answer, and the point.

        Notes
        -----
        What is left on the texture path after the panel moved to quads, and it
        is three things that genuinely are images or are drawn once: a
        ray-traced frame, the 3-D labels, and the rubber-band selection box.

        None of them is present in an ordinary frame, so an ordinary frame now
        rasterises **nothing** on the CPU and uploads **nothing** -- where
        before it uploaded a viewport-sized image whenever the panel's timer
        expired, and every single frame if the scene had labels.
        """
        from .gui_overlay import paint_chrome

        if not self._labels and self._ray_image is None and self._select_rect is None:
            return None
        return self._paint_chrome_now(paint_chrome)

    def _paint_chrome_now(self, paint_chrome) -> Optional[np.ndarray]:
        """Rasterise the chrome, unconditionally.

        Parameters
        ----------
        paint_chrome : callable
            The painter from :mod:`.gui_overlay`.

        Returns
        -------
        numpy.ndarray or None
        """
        return paint_chrome(
            # The panel is drawn as quads now; what is left here is the traced
            # frame, the labels and the selection box.
            None,
            self._controller,
            self._width,
            self._height,
            self._ratio(),
            labels=self._labels,
            project=self.project_to_screen,
            # First, so everything else is chrome drawn *over* the traced frame
            # exactly as it is drawn over the live scene.
            ray_image=self._ray_image,
            ray_rect=self.ray_image_rect(),
            select_rect=self._select_rect,
        )

    # -- the traced frame ----------------------------------------------------

    def scene_pixel_size(self) -> tuple[int, int]:
        """The size ``ray`` traces at when given none.

        The *scene column*, not the widget: the panel owns a column and the
        sequence viewer a band, so tracing the widget's full size traces a wider
        field than the viewport shows -- measured once at 59 % of the image width
        against the viewport's 70 %, and shifted right, because the viewport
        centres the scene in its column while the trace centred it in the image.
        PyMOL has the same rectangle and the same rule.

        Device pixels rather than logical ones, so a default trace and a
        screenshot of the same window come out the same size on a retina
        display, where they otherwise differ by a factor of two.
        """
        ratio = self._ratio()
        return (
            max(int(round(self.scene_width() * ratio)), 1),
            max(int(round(self.scene_height() * ratio)), 1),
        )

    def ray_image_rect(self) -> QtCore.QRect:
        """Where a traced frame is shown: the scene column, under the strip.

        Exposed rather than computed inline so the containment can be asserted
        exactly. A pixel probe cannot: the panel's background is semi-transparent
        and would darken an out-of-bounds image rather than replace it.
        """
        return QtCore.QRect(
            0, self.scene_origin_y(), self.scene_width(), max(self.scene_height(), 1)
        )

    def show_ray_image(self, image) -> bool:
        """Display a traced frame over the scene, keeping the chrome.

        Over the *scene column only*, which is the whole point: a traced image
        stretched across the widget puts the picture where the chrome goes, and
        the panel is what tells you which object you are looking at.
        """
        if image is None or (hasattr(image, "isNull") and image.isNull()):
            return False
        self._ray_image = image
        self.update()
        return True

    def clear_ray_image(self) -> bool:
        """Drop the traced frame and go back to the live view."""
        if self._ray_image is None:
            return False
        self._ray_image = None
        self.update()
        return True

    def get_background_image(self):
        """The backdrop source the viewer last set, if any."""
        return self._background_source

    def set_background_image(self, source) -> None:
        """Set a backdrop behind the molecule.

        Transparency is invisible against one flat colour: a surface at alpha
        0.4 over black is merely a darker surface, because there is nothing
        behind it for the eye to catch. Give the background structure and the
        same surface reads as glass immediately.

        Parameters
        ----------
        source : str, QImage, numpy.ndarray or None
            A name from :data:`~.backdrop.BACKDROPS`, a path, an image already
            in hand, or ``None`` / ``"off"`` to clear it.

        Raises
        ------
        ValueError
            If a path was given and cannot be read -- a background that silently
            does not appear is indistinguishable from one that is not supported.
        """
        from qtpy import QtGui

        if source is None or (
            isinstance(source, str) and source.strip().lower() in ("", "off", "none")
        ):
            self._background_source = source
            self._background_image = None
            self.update()
            return

        image = None
        if isinstance(source, QtGui.QImage):
            image = source
        elif isinstance(source, np.ndarray):
            from .gui_overlay import image_from_rgb

            image = image_from_rgb(source)
        elif isinstance(source, str):
            from .backdrop import BACKDROPS

            if source.strip().lower() not in BACKDROPS:
                loaded = QtGui.QImage(source)
                if loaded.isNull():
                    raise ValueError(f"cannot read background image: {source}")
                image = loaded
            # A named backdrop is generated at paint time, at the widget's size.

        # Recorded only once the source has resolved: setting it up front leaves
        # a refused path as the reported background, so `bg_image` names a
        # picture that never loaded and is not on screen.
        self._background_source = source
        self._background_image = image
        self.update()

    # -- the ground grid -----------------------------------------------------

    #: How many grid lines span the scene, whatever its size.
    GRID_LINES_ACROSS = 20

    def _build_grid_draw_data(self, radius: float):
        """Build the ground grid as line geometry, or ``None`` if it is degenerate.

        The spacing is derived from the extent rather than taken as an absolute.
        ``grid.spacing`` is 1.0 in *scene* units while a protein's radius is a
        couple of hundred, so a fixed spacing draws ~415 lines each way: an
        aliased grey sheet that buries the molecule instead of a reference plane
        behind it.
        """
        import math

        from .pack import PackedGeometry

        half = max(float(self._grid[0]), float(radius) * 1.2)
        spacing = max(
            float(self._grid[1]), 2.0 * half / float(max(1, self.GRID_LINES_ACROSS))
        )
        if spacing <= 0.0:
            return None
        lines = []
        n = int(math.ceil(half / spacing))
        for i in range(-n, n + 1):
            x = i * spacing
            lines.append([[x, -half, 0.0], [x, half, 0.0]])
            lines.append([[-half, x, 0.0], [half, x, 0.0]])
        if not lines:
            return None
        positions = np.asarray(lines, dtype=np.float32).reshape(-1, 3)
        # Faint: it is a reference, not a subject. At full strength a grid drawn
        # across the molecule competes with it for attention.
        colors = np.tile(
            np.array([0.55, 0.55, 0.55, 0.5], dtype=np.float32), (positions.shape[0], 1)
        )
        return PackedGeometry(
            kind="line", positions=positions, colors=colors, meta={"width": 1.0}
        )

    # -- screen-space chrome -------------------------------------------------

    def paint_screen_space(self, painter) -> None:
        """Draw everything that lives in screen space into ``painter``.

        The traced frame, the labels, the panel, the sequence strip and the
        selection box, in that order -- the same order and the same code the
        composited chrome uses, because a screenshot helper that paints them a
        second way is a second thing to keep at parity.
        """
        from .gui_overlay import paint_chrome_into

        paint_chrome_into(
            painter,
            self._internal_gui,
            self._controller,
            int(self.width()),
            int(self.height()),
            labels=self._labels,
            project=self.project_to_screen,
            ray_image=self._ray_image,
            ray_rect=self.ray_image_rect(),
            select_rect=self._select_rect,
        )

    # -- labels --------------------------------------------------------------

    def project_to_screen(self, points):
        """Project scene points to widget pixels; see :class:`CameraState`.

        Inherited unchanged, and that is worth stating: :meth:`scene_width` and
        :meth:`scene_height` report the *widget's* logical pixels, so the shared
        projection already speaks the same units as Qt's mouse events and a
        ``QPainter``. Mixing in the surface's device pixels here is a factor of
        two on a retina display -- the difference between hitting an atom and
        hitting the one beside it.
        """
        return CameraState.project_to_screen(self, points)

    def _resolved_rig(self):
        """The configured light rig with the viewer's overrides applied.

        ``set_lighting`` speaks ChimeraX's names (``key_light_intensity`` and
        friends) and the rig uses its own, so the mapping happens once, here.
        """
        from .lighting import CHIMERAX_NAMES, resolve_light_rig

        rig = resolve_light_rig()
        overrides = {
            CHIMERAX_NAMES[name]: float(value)
            for name, value in self.lighting_parameters().items()
            if name in CHIMERAX_NAMES
        }
        return rig.replace(**overrides) if overrides else rig

    def grab_image(self, chrome: bool = True) -> np.ndarray:
        """Render the current view offscreen and return ``(h, w, 3)`` uint8.

        A window's own framebuffer cannot be read back portably, and a
        screenshot helper that pastes a widget grab captures the compositor's
        idea of the surface rather than the render. Re-rendering through the
        same code into an offscreen target gives the frame itself.

        Parameters
        ----------
        chrome : bool, optional
            Include the panel, the sequence strip and the labels -- i.e. produce
            what the window actually shows. The first version of this omitted
            them, which made a labels screenshot come back with the molecule and
            no labels: the feature looked unimplemented when only the grab was
            incomplete. Pass ``False`` for the bare molecule, which is what a
            comparison against the OpenGL baseline's scene column wants.
        """
        from .wgpu_backend import WgpuMeshRenderer

        offscreen = WgpuMeshRenderer(
            self._gpu.width, self._gpu.height, device=self._gpu.device
        )
        return offscreen.render(
            self._frame_scene(),
            self.get_view_state(),
            background=self._background_rgb(),
            lighting=self._resolved_rig(),
            target_radius=self._target_radius,
            viewport=self._scene_viewport() if chrome else None,
            overlay=self._chrome_image() if chrome else None,
        )

    def _frame_scene(self):
        """The packed scene this frame draws, grid included."""
        from .pack import PackedScene

        base = self._packed
        return PackedScene(
            objects=list(self._draw_data),
            center=base.center if base is not None else np.zeros(3, dtype=np.float32),
            radius=base.radius if base is not None else 1.0,
        )

    # -- mouse ---------------------------------------------------------------

    #: The mode-table actions that drag a selection box. `box` is Maestro's
    #: plain-left cell, and it is the one an ad-hoc handler forgets -- the block
    #: on screen draws `Box` and the drag rotates the camera instead.
    _BOX_ACTIONS = ("+box", "-box", "sele", "box")

    #: Click actions the viewer knows how to act on.
    _CLICK_ACTIONS = ("+/-", "sele", "pkat", "+box", "-box", "orig")

    #: Manhattan pixels a press may wander and still count as a click.
    CLICK_SLOP = 4

    def _action_for(self, button, modifiers) -> str:
        """What this button and these modifiers do, per the mode table.

        Asked of the same table the mouse-mode block on screen draws, so what
        the panel promises and what the mouse does cannot drift apart. Deriving
        it here instead is how the block came to advertise a subtract-box that
        panned the camera.
        """
        from ..mouse_modes import action_of

        try:
            return action_of(self._internal_gui.mouse_mode, button, modifiers)
        except Exception:
            return "none"

    def _start_box_drag(self, event, modifiers) -> bool:
        """Begin a selection box if this press is bound to one.

        Shared by every button, because which button carries a box is the mode
        table's business, not the handler's: ``+Box`` is shift-left, ``-Box`` is
        shift-middle in the three-button modes and shift-right in the
        two-button ones.
        """
        action = self._action_for(event.button(), modifiers)
        if action not in self._BOX_ACTIONS:
            return False
        self._drag_selecting = True
        self._drag_start = event.pos()
        self._drag_modifiers = modifiers
        self._drag_action = action
        self._drag_button = event.button()
        self._select_rect = QtCore.QRect(self._drag_start, QtCore.QSize(0, 0))
        self.update()
        event.accept()
        return True

    def _end_box_drag(self, event) -> None:
        """Apply the dragged box and clear it, whatever it ended up enclosing."""
        rect = self._select_rect or QtCore.QRect()
        self._select_rect = None
        self._drag_selecting = False
        self._drag_start = None
        self._drag_button = None
        self.update()
        if self._controller is None:
            self._drag_action = None
            return
        if rect.width() > 2 and rect.height() > 2:
            self._controller.handle_rect_selection(
                rect, self._drag_modifiers, self._drag_action
            )
        elif self._drag_action is not None:
            # A box that was never dragged is a **click**, and it has to act
            # like one: ctrl-shift-left is `Sele`, so the press claims it as a
            # rubber band, and a plain ctrl-shift *click* -- which is how anyone
            # coming from PyMOL selects a residue -- then falls through a
            # zero-size rectangle and does nothing at all.
            self._controller.handle_mouse_click(event, self._drag_action)
        self._drag_action = None

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """Route a press: the panel first, then the mode table.

        The panel is offered it *first*, as in qtgl: otherwise a click meant for
        a menu also starts rotating the molecule, and the model spins away under
        the menu that just opened.
        """
        pos = event.pos()
        gui = self._internal_gui
        # About to move the camera or pick, so a traced still stops being true.
        if gui is None or not gui.wants(float(pos.x()), float(pos.y())):
            self.clear_ray_image()
        if gui is not None and gui.mouse_press(
            float(pos.x()),
            float(pos.y()),
            right=event.button() == QtCore.Qt.RightButton,
            modifiers=event.modifiers(),
            # The panel opens its menus on a *double* click (`DblClk Menu` in
            # the mouse-mode block), and Qt delivers that as its own event type.
            # Dropping the flag leaves every menu in the panel unreachable while
            # single clicks keep working, so the panel looks alive and inert.
            double=event.type() == QtCore.QEvent.MouseButtonDblClick,
        ):
            self._gui_grab = True
            self.update()
            event.accept()
            return

        modifiers = event.modifiers()
        if event.button() == QtCore.Qt.RightButton:
            # The right button carries a box too -- `-Box` is shift-right in the
            # two-button modes -- so the table is asked before the press is
            # deferred, or that cell of the block names a gesture nothing starts.
            if self._start_box_drag(event, modifiers):
                return
            # Defer: a right *drag* dollies; a right *click* is a click.
            self._last_pos = pos
            self._press_pos = pos
            self._press_mods = modifiers
            self._press_button = event.button()
            event.accept()
            return

        if event.button() in (QtCore.Qt.LeftButton, QtCore.Qt.MiddleButton):
            action = self._action_for(event.button(), modifiers)
            if action == "move":
                self._panning = True
                self._last_pos = pos
                event.accept()
                return
            if self._start_box_drag(event, modifiers):
                return
            # A non-box press is a candidate click, or the start of a drag that
            # rotates. PyMOL decides on *release*: a press that never dragged
            # fires the `single_*` cell, so the click action and the drag action
            # can differ.
            self._press_pos = pos
            self._press_mods = modifiers
            self._press_button = event.button()
            self._last_pos = pos
            event.accept()
            return

        self._last_pos = pos
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """A double click is a press that says so; the panel opens menus on it."""
        self.mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """Drag the box, the panel, or the camera -- whatever the press began.

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
        elif gui is not None and gui.has_menu():
            # An open menu owns the pointer. Rotating the molecule under it is
            # never what a drag across a menu meant.
            event.accept()
            return

        if self._drag_selecting and self._drag_start is not None:
            self._select_rect = QtCore.QRect(self._drag_start, pos).normalized()
            self.update()
            event.accept()
            return

        if self._last_pos is None or not event.buttons():
            return
        last = self._last_pos
        if self._panning:
            ratio = self._ratio()
            self.pan((pos.x() - last.x()) * ratio, (pos.y() - last.y()) * ratio)
        elif event.buttons() & QtCore.Qt.RightButton:
            # Right drag dollies, as PyMOL's `cButModeTransZ` does.
            self._right_dragged = True
            self.dolly(WHEEL_STEP ** ((pos.y() - last.y()) / 40.0))
        else:
            self.orbit((last.x(), last.y()), (pos.x(), pos.y()))
        self._last_pos = pos
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """End the gesture, and turn a press that never moved into a click."""
        if self._panning:
            self._panning = False
            self._last_pos = None
            self._press_pos = None
            event.accept()
            return

        if self._gui_grab:
            self._gui_grab = False
            if self._internal_gui is not None:
                self._internal_gui.release()
            self.update()
            event.accept()
            return

        if self._drag_selecting and event.button() == self._drag_button:
            self._end_box_drag(event)
            event.accept()
            return

        press, self._press_pos = self._press_pos, None
        self._last_pos = None
        if press is not None and self._controller is not None:
            delta = event.pos() - press
            if abs(delta.x()) <= self.CLICK_SLOP and abs(delta.y()) <= self.CLICK_SLOP:
                self._handle_click(event)
        self._right_dragged = False
        event.accept()

    def _handle_click(self, event) -> None:
        """Fire the mode table's *click* cell for the press that just ended.

        PyMOL keeps a separate row for clicks, so a press that never dragged can
        mean something other than the drag it would have been -- plain left
        drags (`Rota`) but clicks (`+/-`). Where that row says nothing, the
        modified cell the press resolved still applies: ctrl-middle is `PkAt`
        whether or not it moved.
        """
        from ..mouse_modes import click_action_of

        mode = self._internal_gui.mouse_mode if self._internal_gui else "viewing"
        try:
            click = click_action_of(mode, self._press_button, self._press_mods)
        except Exception:
            click = "none"
        if click in ("none", "", None):
            click = self._action_for(self._press_button, self._press_mods)
        if click not in self._CLICK_ACTIONS:
            return
        try:
            self._controller.handle_mouse_click(event, click)
        except Exception:  # pragma: no cover - a viewer that refuses the click
            return
        self.update()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """Offer the key to the viewer before Qt's default handling."""
        handler = getattr(self._controller, "handle_key_event", None)
        if callable(handler):
            try:
                if handler(event):
                    self.update()
                    event.accept()
                    return
            except Exception:  # pragma: no cover - viewer-side refusal
                pass
        super().keyPressEvent(event)

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """Dolly the camera, or move the clipping slab when shift is held.

        Whichever axis carries the delta: **macOS turns shift+scroll into a
        horizontal scroll** before the application sees it, so a shifted wheel
        arrives with ``angleDelta().y() == 0`` and everything in ``x()``.
        Reading only ``y`` is why shift+wheel did nothing on a Mac while a
        synthetic event in a test -- which sets ``y`` -- worked perfectly.
        """
        angle = event.angleDelta()
        raw = angle.y() if angle.y() else angle.x()
        if not raw:
            return
        steps = int(raw / 120.0)
        if steps == 0:
            # A trackpad sends many small deltas rather than 120-unit notches;
            # truncating them to zero makes the gesture do nothing at all.
            steps = 1 if raw > 0 else -1

        pos = event.position() if hasattr(event, "position") else event.posF()
        gui = self._internal_gui
        if gui is not None:
            # Over an open menu the wheel scrolls the menu -- PyMOL's `CPopUp`
            # takes the scroll buttons. A menu longer than the window is the
            # ordinary case for the Action menu on a small viewport, and zooming
            # the molecule underneath it is never what was meant.
            if gui.has_menu():
                if gui.scroll_menu(pos.x(), pos.y(), steps):
                    self.update()
                event.accept()
                return
            # Over the sequence, the wheel scrolls the sequence.
            if gui.sequence_visible and gui.sequence_strip_contains(pos.x(), pos.y()):
                if gui.scroll_sequence(-steps * 5):
                    self.update()
                event.accept()
                return

        # The camera is about to move, so a traced still stops being true.
        self.clear_ray_image()
        modifiers = event.modifiers()
        if modifiers & (QtCore.Qt.ShiftModifier | QtCore.Qt.ControlModifier):
            # Ctrl is PyMOL's `MvSZ`: the camera goes with the slab, so it stays
            # put against the molecule and the view dollies instead.
            if self.move_slab(steps, dolly=bool(modifiers & QtCore.Qt.ControlModifier)):
                self.announce_clipping()
        else:
            self.dolly(WHEEL_STEP ** (-steps))
        self.update()
        event.accept()
