"""chimol's viewport, with no toolkit in it: the draw path and the gestures.

What this is
------------
:class:`CanvasRenderer` is everything :class:`~.wgpu_view.WgpuRenderer` did
except being a ``QWidget``. It configures the surface, packs the scene, builds
the chrome's quads, renders the frame, and decides what a press, a drag, a wheel
notch and a key mean -- none of which is a window system's business.

What is left in a host, then, is small and genuinely toolkit-shaped: creating
the surface, turning that toolkit's events into the calls below, and rasterising
the one overlay that is still an image (see :meth:`_composite_overlay`).

Why it is a mixin over a canvas
-------------------------------
``rendercanvas`` already is the seam. Its Qt widget, its GLFW window and its
offscreen canvas are all ``BaseRenderCanvas``, and the four methods this class
needs from one -- ``get_context``, ``request_draw``, ``get_physical_size`` and
``add_event_handler`` -- are the same on every backend. So the surface is
reached through :meth:`_surface`, which a canvas *subclass* answers with itself
and a canvas *owner* answers with the canvas it holds. That is what lets the Qt
widget stay a widget while the Qt-free host is a plain object with a window
beside it, on **one** draw path rather than two.

A second copy of that path is exactly what this class exists to prevent. The
port that produced it started from a viewport whose rendering and whose mouse
handling were interleaved with ``QMouseEvent`` and ``QRect``; copying it for a
GLFW window would have given chimol two viewports that agree today, disagree in
a month, and are compared by nobody.

What a host still owns
----------------------
* the surface, and the loop that pumps it;
* the translation of its own events into :meth:`on_pointer_press` and friends;
* :meth:`_composite_overlay` -- the labels, the traced frame and the selection
  box, which are rasterised with a painter rather than built as quads. Without a
  toolkit there is no painter, and the honest answer is ``None``: the molecule,
  the panel, the menus, the sequence strip and the command line are all quads
  and all draw.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass

import numpy as np

from ..host.events import (
    LEFT_BUTTON,
    MIDDLE_BUTTON,
    NO_BUTTON,
    NO_MODIFIER,
    RIGHT_BUTTON,
    PointerEvent,
    Rect,
)
from .base import Renderer
from .camera_state import DEFAULT_VIEWPORT, CameraState
from .pack import pack_scene
from .scene import Scene

__all__ = [
    "DEFAULT_BACKEND",
    "WHEEL_STEP",
    "CanvasRenderer",
    "Label",
    "collect_labels",
    "selected_backend",
]

#: The backend chimol draws with. WGSL is the one source the desktop and the
#: browser share, and since the OpenGL renderer was removed it is the only
#: drawing backend there is -- the setting survives because a second one
#: (a browser canvas, a headless tracer) is the point of the arrangement.
DEFAULT_BACKEND = "wgpu"

#: How many frame intervals the frame-rate readout averages over.
_FPS_WINDOW = 30

#: A gap longer than this is an idle viewport rather than a slow frame.
_IDLE_GAP = 0.25

#: How often the frame-rate readout publishes a new number. It is part of the
#: chrome, so every change rebuilds the chrome -- see `_measured_fps`.
_FPS_REPORT_INTERVAL = 0.5

#: Wheel notch to distance ratio. Multiplicative so one step feels the same on a
#: peptide and on a ribosome; PyMOL's own zoom is a ratio for the same reason.
WHEEL_STEP = 1.1


def selected_backend() -> str:
    """Which backend the user asked for: ``"wgpu"`` or ``"opengl"``.

    ``CHIMOL_RENDERER`` wins, then the ``renderer.backend`` display-config key,
    then the default -- which is **wgpu**. The environment variable stays
    because it is what makes a bug report reproducible either way without
    editing a config file.

    Returns
    -------
    str
    """
    from ..config import _DISPLAY_CONFIG

    choice = os.environ.get("CHIMOL_RENDERER", "").strip().lower()
    if not choice:
        section = _DISPLAY_CONFIG.get("renderer")
        if isinstance(section, dict):
            choice = str(section.get("backend", "")).strip().lower()
    return choice or DEFAULT_BACKEND


def _layout_flag(name: str, default: bool = True) -> bool:
    """One boolean chrome setting from the `layout` display section.

    Parameters
    ----------
    name : str
        The key in the ``layout`` section.
    default : bool, optional
        What to answer when the section has no opinion.

    Returns
    -------
    bool
    """
    from ..config import _DISPLAY_CONFIG

    section = _DISPLAY_CONFIG.get("layout")
    if isinstance(section, dict):
        return bool(section.get(name, default))
    return default


def _window_snap_enabled() -> bool:
    """Whether dragged windows snap to the viewport's edges (`window_snap`)."""
    return _layout_flag("window_snap", True)


def _chrome_scale() -> float:
    """How big the in-viewport chrome draws, from the display configuration.

    Returns
    -------
    float
        ``layout.ui_scale``, or :attr:`InternalGui.DEFAULT_UI_SCALE` when the
        configuration has no opinion.
    """
    from ..config import _DISPLAY_CONFIG
    from .internal_gui import InternalGui

    section = _DISPLAY_CONFIG.get("layout")
    if isinstance(section, dict):
        try:
            return float(section.get("ui_scale", InternalGui.DEFAULT_UI_SCALE))
        except (TypeError, ValueError):
            pass
    return InternalGui.DEFAULT_UI_SCALE


@dataclass
class Label:
    """One 3-D label: a world position, its text, and its colour."""

    pos: np.ndarray
    text: str
    color: tuple


def collect_labels(packed) -> list:
    """Pull ``kind == "text"`` geometry out of a packed scene.

    Labels are the one thing in a scene that is not geometry at all -- a string
    at a point -- so they leave the GPU path here and rejoin it as glyphs in the
    composited chrome image.

    Parameters
    ----------
    packed : PackedScene or None
        The scene to search, or ``None`` for no labels at all.

    Returns
    -------
    list of Label
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


def _as_rgba_array(image) -> "np.ndarray | None":
    """Return *image* as ``(h, w, 4)`` uint8 premultiplied RGBA, or ``None``.

    Arrays only. This briefly accepted a ``QImage`` too, and converting one
    meant ``from qtpy import QtGui`` -- inside the module whose entire purpose
    is to be the draw path *without* a toolkit. The producer was fixed instead:
    the ray tracer hands on its NumPy array, and the Qt paint path converts at
    its own end, where Qt already lives.

    Parameters
    ----------
    image : numpy.ndarray or None
        ``(h, w, 3)`` or ``(h, w, 4)``; float input is taken as 0..1.

    Returns
    -------
    numpy.ndarray or None
        ``None`` for anything unreadable -- the caller then draws nothing,
        which is better than raising inside a paint pass.
    """
    if image is None or not isinstance(image, np.ndarray):
        return None

    arr = np.asarray(image)
    if arr.ndim != 3 or arr.shape[0] < 1 or arr.shape[1] < 1:
        return None
    if arr.dtype != np.uint8:
        scale = 255.0 if np.issubdtype(arr.dtype, np.floating) else 1.0
        arr = np.clip(np.asarray(arr, dtype=float) * scale, 0, 255).astype(np.uint8)
    if arr.shape[2] == 3:
        # Opaque, and premultiplied is the same thing at alpha 255.
        out = np.empty(arr.shape[:2] + (4,), dtype=np.uint8)
        out[..., :3] = arr
        out[..., 3] = 255
        return out
    if arr.shape[2] == 4:
        return np.ascontiguousarray(arr)
    return None


class CanvasRenderer(CameraState, Renderer):
    """Draw a chimol scene into a ``rendercanvas`` surface with WebGPU.

    Not constructed directly: a host mixes this into (or holds) a canvas and
    calls :meth:`init_viewport` once the surface exists.
    """

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

    #: How many grid lines span the scene, whatever its size.
    GRID_LINES_ACROSS = 20

    #: The mode-table actions that drag a selection box. `box` is Maestro's
    #: plain-left cell, and it is the one an ad-hoc handler forgets -- the block
    #: on screen draws `Box` and the drag rotates the camera instead.
    _BOX_ACTIONS = ("+box", "-box", "sele", "box")

    #: Click actions the viewer knows how to act on.
    _CLICK_ACTIONS = ("+/-", "sele", "pkat", "+box", "-box", "orig")

    #: Manhattan pixels a press may wander and still count as a click.
    CLICK_SLOP = 4

    # -- setup ---------------------------------------------------------------

    def _surface(self):
        """The ``rendercanvas`` canvas this draws into.

        Returns
        -------
        rendercanvas.base.BaseRenderCanvas
            ``self`` for a host that *is* a canvas (the Qt widget), and the
            held canvas for one that merely owns one.
        """
        return self

    def init_viewport(self, controller: object = None) -> None:
        """Build the camera, the chrome and the GPU renderer for this surface.

        Parameters
        ----------
        controller : object, optional
            The :class:`~.view.MolView` driving this renderer.
        """
        self._controller = controller
        self.init_camera_state(DEFAULT_VIEWPORT)

        self._packed = None
        #: Everything this frame draws: the scene's objects, plus the grid when
        #: it is visible. See :meth:`_rebuild_draw_data`.
        self._draw_data: list = []
        self._labels: list[Label] = []
        self._last_pos: tuple[float, float] | None = None
        self._press_pos: tuple[float, float] | None = None
        self._panning = False
        #: Whether the press was consumed by the panel, so the drag belongs to
        #: it rather than to the camera.
        self._gui_grab = False
        #: A traced frame shown over the scene column, or None for the live view.
        self._ray_image = None
        #: Last chrome build: ``(key, vertices)``. See `_chrome_quads`.
        self._chrome_cache: tuple | None = None
        #: Recent frame intervals, for the debug frame-rate readout.
        self._frame_times: list[float] = []
        self._last_frame_time: float | None = None
        #: The frame rate as *shown*, and when it was last published.
        self._fps_published = 0.0
        self._fps_published_at = 0.0
        self._background_source = None
        self._background_image = None
        #: The rubber-band selection box while it is being dragged, in viewport
        #: pixels. Chrome like the panel and the labels, so it is composited with
        #: them: it has to appear in a grab of the viewport for a screenshot to
        #: show what was selected.
        self._select_rect: Rect | None = None
        self._drag_selecting = False
        self._drag_start: tuple[float, float] | None = None
        self._drag_button = NO_BUTTON
        self._drag_action: str | None = None
        self._drag_modifiers = NO_MODIFIER
        self._press_mods = NO_MODIFIER
        self._press_button = NO_BUTTON
        self._right_dragged = False

        # The object panel and the sequence strip, composited as a textured
        # quad at the end of the render pass -- see :mod:`.gui_overlay` for the
        # two Qt-child arrangements that were tried first and why neither works
        # over a presented surface.
        from .internal_gui import InternalGui

        self._internal_gui = InternalGui()
        self.internal_gui = self._internal_gui

        from .wgpu_backend import WgpuMeshRenderer

        surface = self._surface()
        self._context = surface.get_context("wgpu")
        width, height = self._physical_size()
        # One device, shared: the context is configured against it and the
        # renderer draws with it. A texture created by one device cannot be
        # drawn into by another, and that failure surfaces as a validation error
        # deep inside the first frame rather than at setup.
        fmt = self._configure_surface()
        self._gpu = WgpuMeshRenderer(width, height, format=fmt, device=self._device)
        surface.request_draw(self._draw)

    def _configure_surface(self) -> str:
        """Configure the canvas context and return the format it accepted.

        Returns
        -------
        str

        Raises
        ------
        RuntimeError
            When no candidate format is accepted by the presentation path.
        """
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

        A surface that has not been laid out reports 0, and a zero-sized surface
        is a validation error rather than an empty picture.

        Returns
        -------
        tuple of int
        """
        try:
            width, height = self._surface().get_physical_size()
        except Exception:
            ratio = self._ratio()
            width, height = int(self.width() * ratio), int(self.height() * ratio)
        return max(int(width), 1), max(int(height), 1)

    def _ratio(self) -> float:
        """Device pixels per logical pixel.

        The chrome lays itself out in *logical* pixels, because that is what a
        painter on a window uses; the surface is in device pixels. Mixing the
        two puts the molecule under the panel on any high-DPI screen.

        Returns
        -------
        float
        """
        try:
            return float(self._surface().get_pixel_ratio())
        except Exception:
            return 1.0

    # -- the Renderer contract ----------------------------------------------

    def widget(self):
        """Return the toolkit widget to embed, of which there is none.

        Returns
        -------
        None
            The viewer guards its Qt chrome on the renderer *being* a widget
            rather than on there being one, so ``None`` is the honest answer.
        """
        return None

    def set_scene(self, scene: Scene | None) -> None:
        """Store the scene, pack it for upload, and collect its labels.

        Packing here rather than per frame: it normalises dtypes and validates
        indices, which is work proportional to the scene and not to the frame
        rate. A 374k-triangle space-fill repacked every frame is the difference
        between a viewer and a slideshow.

        Parameters
        ----------
        scene : Scene or None
            What to draw from now on; ``None`` clears the viewport.
        """
        # A traced frame is a still of a scene that no longer exists, and
        # leaving it up means the viewport shows a picture of something the
        # commands have already changed.
        self.clear_ray_image()
        self.scene = scene
        self._packed = pack_scene(scene) if scene is not None else None
        self._labels = collect_labels(self._packed)
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

        Parameters
        ----------
        visible : bool
            Whether the grid is drawn.
        """
        CameraState.set_grid_visible(self, visible)
        self._rebuild_draw_data()
        self.update()

    def configure_grid(self, size: float, spacing: float) -> None:
        """Set the grid's extent and spacing, and rebuild it.

        Parameters
        ----------
        size, spacing : float
            Half-extent and line spacing, in scene units.
        """
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

    def update(self) -> None:
        """Ask for a repaint.

        A ``rendercanvas`` surface repaints from its own draw request, not from
        a toolkit's paint event, so this is the one call the viewer makes.
        """
        self.update_count += 1
        try:
            self._surface().request_draw()
        except Exception:
            pass

    def set_background_color(self, color) -> None:
        """Store the clear colour and repaint.

        Parameters
        ----------
        color : object
            Anything :meth:`CameraState.set_background_color` resolves.
        """
        CameraState.set_background_color(self, color)
        self.update()

    # -- the chrome's share of the surface ------------------------------------

    def scene_width(self) -> int:
        """Width left for the molecule once the object panel has its column.

        In **logical** pixels, not the surface's device ones. Two different
        sizes live in this class and confusing them is a real bug: the contract
        (framing, picking, the panel's own layout) is logical, and only the GPU
        target is in device pixels. Reporting the surface size here made the
        aspect ratio stale until the first resize, so a viewer that had been
        resized but not shown framed for the wrong shape.

        The panel is a *column*, not an overlay: drawn on top it would hide the
        molecule it describes, and the part it hides is the part you just moved
        out from under it. An undocked panel floats, and takes no column.

        Returns
        -------
        int
        """
        gui = self._internal_gui
        if gui is None or not (gui.visible and gui.docked):
            return max(int(self.width()), 1)
        # The *effective* width: a folded panel gives its column back to the
        # molecule, and asking for `column_width` would keep reserving it.
        return max(int(self.width()) - int(gui.effective_column_width()), 1)

    def scene_height(self) -> int:
        """Height left once the sequence strip has its band, in logical pixels.

        Returns
        -------
        int
        """
        gui = self._internal_gui
        # The whole top band -- menu bar *and* sequence strip. Asking for the
        # strip alone drew the molecule under the bar.
        strip = int(gui.top_band_height()) if gui is not None else 0
        return max(int(self.height()) - strip, 1)

    def _scene_viewport(self) -> tuple[float, float, float, float]:
        """The molecule's rectangle in the surface, in device pixels.

        The strip is at the *top*, so the viewport starts below it -- WebGPU's
        framebuffer origin is top-left, where GL's is bottom-left and the same
        band falls out of a shorter viewport with no offset. That difference is
        exactly the kind that renders correctly upside down.

        Returns
        -------
        tuple of float
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

        Named apart from ``resize`` because a toolkit's ``resize`` already means
        something else, and a renderer that silently resizes its window when the
        viewer meant to tell it a viewport size is a hard bug to see.

        Parameters
        ----------
        width, height : int
            Device pixels.
        """
        CameraState.resize(self, width, height)
        self._gpu.resize(width, height)
        self.update()

    def _background_rgb(self) -> tuple[float, float, float]:
        """The clear colour as linear RGB.

        Resolved once by :meth:`~.camera_state.CameraState.set_background_color`,
        so this is only a narrowing from RGBA.

        Returns
        -------
        tuple of float
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
            # not whatever was in the buffer -- and it still shows its **panel**.
            # The object list, the mouse-mode block and the sequence strip are
            # how you load something in the first place; a viewer that hides its
            # own controls until it has a molecule cannot be given one. This
            # path used to omit `chrome`, so `disable all` made the whole panel
            # disappear.
            self._gpu.render_into(
                texture.create_view(),
                pack_scene(None),
                self.get_view_state(),
                background=background,
                chrome=self._chrome_quads(),
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

    def _measured_fps(self) -> float:
        """Frames per second over a short window, or ``0.0``.

        Averaged rather than taken from the last interval: a single frame's
        time swings enough to be unreadable, and the question being asked --
        "did that change make it slower" -- is about the average anyway.

        A gap longer than :data:`_IDLE_GAP` is the viewport sitting **idle**,
        not a slow frame, so it clears the window instead of being averaged in.
        Without that, a viewport nobody is touching reports single-digit rates
        and the number means nothing.

        Returns
        -------
        float
            ``0.0`` until there are enough samples, which is what makes a still
            viewport show nothing rather than a stale rate.
        """
        import time  # noqa: PLC0415

        now = time.perf_counter()
        previous, self._last_frame_time = self._last_frame_time, now
        samples = self._frame_times
        if previous is None:
            return 0.0
        delta = now - previous
        if delta <= 0.0 or delta > _IDLE_GAP:
            samples.clear()
            return 0.0
        samples.append(delta)
        if len(samples) > _FPS_WINDOW:
            del samples[:-_FPS_WINDOW]
        if len(samples) < 3:
            return 0.0

        # Published a few times a second, not every frame -- and this is a
        # correctness fix, not a cosmetic one. The readout is part of the
        # chrome, so a value that changes every frame invalidates the chrome
        # cache every frame, and rebuilding the chrome is ~14 ms on a large
        # model. **Switching the counter on therefore destroyed the frame rate
        # it was reporting**, which is the worst possible behaviour for an
        # instrument: it does not merely perturb the measurement, it dominates
        # it, and the number it shows is the number it caused.
        #
        # Twice a second is also simply more readable. A rate redrawn sixty
        # times a second cannot be read at all.
        rate = len(samples) / sum(samples)
        if now - self._fps_published_at >= _FPS_REPORT_INTERVAL:
            self._fps_published_at = now
            self._fps_published = rate
        return self._fps_published

    def _chrome_quads(self) -> np.ndarray | None:
        """The panel, strip, menus and transport as GPU quads.

        Returns
        -------
        numpy.ndarray or None
            ``(n, 12)`` float32 for ``ui.wgsl``, or ``None`` when there is no
            panel to draw.

        Notes
        -----
        Built **every frame**, and the absence of a cache is the change. The
        panel used to be rasterised into a full-viewport image by a painter --
        *9.6 ms of a 21 ms frame* with a quarter of a million beads on screen --
        which was expensive enough that it could not be repainted when it
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

        from .gui_state import refresh_gui_state
        from .ui.quad_painter import QuadPainter

        refresh_gui_state(gui, self._controller)
        # `self._width`/`self._height` are **device** pixels: `_draw` resizes
        # the camera from `_physical_size()`. The panel must be laid out in
        # **logical** pixels and scaled back up as the quads are built, which is
        # exactly what the painter path did (`paint_chrome_into` took
        # `width / ratio`).
        #
        # Both halves matter, and getting either alone is worse than getting
        # neither. Laying out in device pixels draws the panel correctly and
        # hit-tests it in the wrong coordinates, so it looks fine and ignores
        # every click. Scaling that by the ratio as well puts it off the right
        # edge of the window entirely.
        ratio = self._ratio()
        # Read every frame rather than at construction: the settings panel
        # edits this like any other setting, and a chrome scale that only
        # applied at start-up would be the one setting with no live effect.
        gui.set_ui_scale(_chrome_scale())
        # Same reason as the scale above: a debug switch read once at start-up
        # would be the one setting the settings panel could not change live.
        gui.debug_overlays = _layout_flag("debug", False)
        gui.fps = self._measured_fps()
        gui.window_snap = _window_snap_enabled()
        # The chrome piece by piece, each a live display setting: all off is
        # a bare 3-D viewer, which is what an embedded page wants.
        gui.menubar_visible = _layout_flag("show_menubar")
        gui.toolbar_visible = _layout_flag("show_toolbar")
        gui.command_line.visible = _layout_flag("show_command_line")
        gui.status_visible = _layout_flag("show_status")
        gui.layout(int(self._width / ratio), int(self._height / ratio))

        # Rebuilt only when something it draws from has changed. The chrome is
        # immediate mode -- ~2,800 quads emitted from scratch -- and on a large
        # model that was most of the frame while the molecule itself was about
        # a millisecond. It changes on hover, focus and state; it does not
        # change while the camera moves, which is the only time frame rate is
        # being watched.
        #
        # The key is taken *after* `layout`, because layout is what turns a
        # size or a scale change into the rectangles the paint reads.
        key = (ratio, gui.chrome_fingerprint())
        cached = self._chrome_cache
        if cached is not None and cached[0] == key:
            return cached[1]

        painter = QuadPainter(scale=ratio, font_scale=gui.ui_scale)
        gui.paint(painter)
        vertices = painter.vertices()
        vertices = vertices if len(vertices) else None
        self._chrome_cache = (key, vertices)
        return vertices

    def _chrome_image(self) -> np.ndarray | None:
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

        None of them is present in an ordinary frame, so an ordinary frame
        rasterises **nothing** on the CPU and uploads **nothing** -- where
        before it uploaded a viewport-sized image whenever the panel's timer
        expired, and every single frame if the scene had labels.
        """
        if not self._labels and self._ray_image is None and self._select_rect is None:
            return None
        return self._composite_overlay()

    def _composite_overlay(self) -> np.ndarray | None:
        """Rasterise the three image-shaped overlays, if the host can.

        Returns
        -------
        numpy.ndarray or None
            ``(h, w, 4)`` uint8 premultiplied RGBA at device resolution, or
            ``None`` when there is nothing this host can draw.

        Notes
        -----
        The **labels** and the **selection box** genuinely need a painter --
        glyph rasterising and dashed strokes -- and a host with no toolkit has
        none, so they are still absent here.

        A **traced frame is not in that class**. It is already a finished image;
        putting it on screen is a scale and a blit, which NumPy does. Returning
        ``None`` for it too meant ``ray`` on the toolkit-free host traced the
        scene, wrote the PNG, reported success, and displayed nothing -- the
        image was stored on the renderer and no code path could ever draw it.
        """
        image = self._ray_image
        if image is None:
            return None
        rgba = _as_rgba_array(image)
        if rgba is None:
            return None

        width, height = max(int(self._width), 1), max(int(self._height), 1)
        out = np.zeros((height, width, 4), dtype=np.uint8)

        # `ray_image_rect` is in logical pixels -- the Qt path hands it to a
        # painter that is already scaled by the device ratio. This one writes
        # device pixels directly, so it does the scaling itself.
        ratio = float(self._ratio()) if callable(getattr(self, "_ratio", None)) else 1.0
        ratio = ratio if ratio > 0 else 1.0
        rect = self.ray_image_rect()
        # `Rect` spells its accessors Qt's way -- they are methods, not fields.
        rx, ry = int(rect.x() * ratio), int(rect.y() * ratio)
        rw, rh = int(rect.width() * ratio), int(rect.height() * ratio)
        if rw <= 0 or rh <= 0:
            return None

        # Aspect preserved and centred, exactly as `paint_ray_image` does it:
        # a traced frame stretched to the column is a different picture from
        # the one that was traced.
        src_h, src_w = rgba.shape[0], rgba.shape[1]
        scale = min(rw / src_w, rh / src_h)
        dst_w, dst_h = max(int(src_w * scale), 1), max(int(src_h * scale), 1)
        rows = np.minimum((np.arange(dst_h) / scale).astype(np.intp), src_h - 1)
        cols = np.minimum((np.arange(dst_w) / scale).astype(np.intp), src_w - 1)
        scaled = rgba[rows[:, None], cols[None, :]]

        x0 = rx + (rw - dst_w) // 2
        y0 = ry + (rh - dst_h) // 2
        # Clip rather than trust the arithmetic: a window smaller than the
        # traced image would otherwise raise from inside a paint pass.
        sx0, sy0 = max(x0, 0), max(y0, 0)
        sx1, sy1 = min(x0 + dst_w, width), min(y0 + dst_h, height)
        if sx1 <= sx0 or sy1 <= sy0:
            return None
        out[sy0:sy1, sx0:sx1] = scaled[sy0 - y0 : sy1 - y0, sx0 - x0 : sx1 - x0]
        return out

    def _label_size(self) -> float:
        """Point size for 3-D labels -- PyMOL's ``label_size``.

        Returns
        -------
        float
        """
        from ..config import _DISPLAY_CONFIG
        from .gui_state import DEFAULT_LABEL_SIZE

        try:
            cfg = _DISPLAY_CONFIG.get("label", {}) or {}
            return float(cfg.get("size", DEFAULT_LABEL_SIZE))
        except Exception:
            return DEFAULT_LABEL_SIZE

    # -- the traced frame ----------------------------------------------------

    def scene_pixel_size(self) -> tuple[int, int]:
        """The size ``ray`` traces at when given none.

        The *scene column*, not the whole surface: the panel owns a column and
        the sequence viewer a band, so tracing the full size traces a wider
        field than the viewport shows -- measured once at 59 % of the image width
        against the viewport's 70 %, and shifted right, because the viewport
        centres the scene in its column while the trace centred it in the image.
        PyMOL has the same rectangle and the same rule.

        Device pixels rather than logical ones, so a default trace and a
        screenshot of the same window come out the same size on a retina
        display, where they otherwise differ by a factor of two.

        Returns
        -------
        tuple of int
        """
        ratio = self._ratio()
        return (
            max(int(round(self.scene_width() * ratio)), 1),
            max(int(round(self.scene_height() * ratio)), 1),
        )

    def scene_rect(self) -> tuple[int, int, int, int]:
        """Where a traced frame is shown, as ``(x, y, width, height)``.

        Returns
        -------
        tuple of int
        """
        return (
            0,
            int(self.scene_origin_y()),
            int(self.scene_width()),
            int(max(self.scene_height(), 1)),
        )

    def ray_image_rect(self) -> Rect:
        """Where a traced frame is shown: the scene column, under the strip.

        Exposed rather than computed inline so the containment can be asserted
        exactly. A pixel probe cannot: the panel's background is semi-transparent
        and would darken an out-of-bounds image rather than replace it.

        Returns
        -------
        Rect
        """
        return Rect(*self.scene_rect())

    def show_ray_image(self, image) -> bool:
        """Display a traced frame over the scene, keeping the chrome.

        Over the *scene column only*, which is the whole point: a traced image
        stretched across the surface puts the picture where the chrome goes, and
        the panel is what tells you which object you are looking at.

        Parameters
        ----------
        image : object
            An image the host's overlay path can blit.

        Returns
        -------
        bool
            Whether an image was taken.
        """
        if image is None or (hasattr(image, "isNull") and image.isNull()):
            return False
        self._ray_image = image
        self.update()
        return True

    def clear_ray_image(self) -> bool:
        """Drop the traced frame and go back to the live view.

        Returns
        -------
        bool
            Whether there was one to drop.
        """
        if self._ray_image is None:
            return False
        self._ray_image = None
        self.update()
        return True

    def get_background_image(self):
        """The backdrop source the viewer last set, if any."""
        return self._background_source

    def set_background_image(self, source) -> None:
        """Record a backdrop behind the molecule.

        Parameters
        ----------
        source : str, numpy.ndarray or None
            A name from :data:`~.backdrop.BACKDROPS`, a path, an image already
            in hand, or ``None`` / ``"off"`` to clear it.

        Notes
        -----
        The source is *recorded* here and rasterised by the host, because
        turning a path into pixels is a toolkit's image reader. A host that has
        one overrides this; without one a named backdrop still works, since
        those are generated at paint time.
        """
        self._background_source = source
        self._background_image = None
        self.update()

    # -- the ground grid -----------------------------------------------------

    def _build_grid_draw_data(self, radius: float):
        """Build the ground grid as line geometry, or ``None`` if degenerate.

        The spacing is derived from the extent rather than taken as an absolute.
        ``grid.spacing`` is 1.0 in *scene* units while a protein's radius is a
        couple of hundred, so a fixed spacing draws ~415 lines each way: an
        aliased grey sheet that buries the molecule instead of a reference plane
        behind it.

        Parameters
        ----------
        radius : float
            The scene's radius.

        Returns
        -------
        PackedGeometry or None
        """
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

    # -- the frame -----------------------------------------------------------

    def _context_menu_target(self, x: float, y: float) -> str:
        """What a right-click in the scene should act on.

        The object under the cursor when there is one, so the menu addresses
        what was clicked; `sele` otherwise, which is what the object list's own
        `sele` row addresses and is never empty of meaning.

        Parameters
        ----------
        x, y : float
            Where the click landed, in logical pixels.

        Returns
        -------
        str
        """
        controller = self._controller
        if controller is None:
            return "sele"
        try:
            objects = controller.list_objects()
        except Exception:
            objects = []
        if not objects:
            return "sele"
        try:
            active = controller.get_active_object_id()
        except Exception:
            active = None
        for entry in objects:
            if str(entry.get("id")) == str(active):
                from ..object_menus import quote_selection_name

                return quote_selection_name(str(entry.get("name") or active))
        return "sele"

    def project_to_screen(self, points):
        """Project scene points to viewport pixels; see :class:`CameraState`.

        Inherited unchanged, and that is worth stating: :meth:`scene_width` and
        :meth:`scene_height` report *logical* pixels, so the shared projection
        already speaks the same units as a pointer event and a painter. Mixing
        in the surface's device pixels here is a factor of two on a retina
        display -- the difference between hitting an atom and hitting the one
        beside it.

        Parameters
        ----------
        points : numpy.ndarray
            ``(n, 3)`` positions in scene space.

        Returns
        -------
        tuple of numpy.ndarray
        """
        return CameraState.project_to_screen(self, points)

    def _resolved_rig(self):
        """The configured light rig with the viewer's overrides applied.

        ``set_lighting`` speaks ChimeraX's names (``key_light_intensity`` and
        friends) and the rig uses its own, so the mapping happens once, here.

        Returns
        -------
        LightRig
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

        Returns
        -------
        numpy.ndarray
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
            # The panel is quads now, and they arrive through `chrome`, not
            # through `overlay`. Omitting them here made every headless grab
            # come back with the molecule and no panel -- the same failure this
            # method's own docstring describes for labels, one port later.
            chrome=self._chrome_quads() if chrome else None,
        )

    def _frame_scene(self):
        """The packed scene this frame draws, grid included.

        Returns
        -------
        PackedScene
        """
        from .pack import PackedScene

        base = self._packed
        return PackedScene(
            objects=list(self._draw_data),
            center=base.center if base is not None else np.zeros(3, dtype=np.float32),
            radius=base.radius if base is not None else 1.0,
        )

    # -- pointer -------------------------------------------------------------

    def _action_for(self, button: int, modifiers: int) -> str:
        """What this button and these modifiers do, per the mode table.

        Asked of the same table the mouse-mode block on screen draws, so what
        the panel promises and what the mouse does cannot drift apart. Deriving
        it here instead is how the block came to advertise a subtract-box that
        panned the camera.

        Parameters
        ----------
        button : int
            One of :mod:`chimol.host.events`' ``*_BUTTON`` constants.
        modifiers : int
            A mask of its ``*_MODIFIER`` constants.

        Returns
        -------
        str
        """
        from ..mouse_modes import action_of

        try:
            return action_of(self._internal_gui.mouse_mode, button, modifiers)
        except Exception:
            return "none"

    def _start_box_drag(self, x: float, y: float, button: int, modifiers: int) -> bool:
        """Begin a selection box if this press is bound to one.

        Shared by every button, because which button carries a box is the mode
        table's business, not the handler's: ``+Box`` is shift-left, ``-Box`` is
        shift-middle in the three-button modes and shift-right in the
        two-button ones.

        Parameters
        ----------
        x, y : float
            Where the press landed.
        button : int
            The button pressed.
        modifiers : int
            The modifiers held.

        Returns
        -------
        bool
            Whether a box was started.
        """
        action = self._action_for(button, modifiers)
        if action not in self._BOX_ACTIONS:
            return False
        self._drag_selecting = True
        self._drag_start = (x, y)
        self._drag_modifiers = modifiers
        self._drag_action = action
        self._drag_button = button
        self._select_rect = Rect(x, y, 1.0, 1.0)
        self.update()
        return True

    def _end_box_drag(self, x: float, y: float, button: int, modifiers: int) -> None:
        """Apply the dragged box and clear it, whatever it ended up enclosing.

        Parameters
        ----------
        x, y : float
            Where the release landed.
        button : int
            The button released.
        modifiers : int
            The modifiers held at release.
        """
        rect = self._select_rect
        self._select_rect = None
        self._drag_selecting = False
        self._drag_start = None
        self._drag_button = NO_BUTTON
        self.update()
        if self._controller is None:
            self._drag_action = None
            return
        if rect is not None and rect.width() > 2 and rect.height() > 2:
            self._controller.handle_rect_selection(
                rect, self._drag_modifiers, self._drag_action
            )
        elif self._drag_action is not None:
            # A box that was never dragged is a **click**, and it has to act
            # like one: ctrl-shift-left is `Sele`, so the press claims it as a
            # rubber band, and a plain ctrl-shift *click* -- which is how anyone
            # coming from PyMOL selects a residue -- then falls through a
            # zero-size rectangle and does nothing at all.
            self._controller.handle_mouse_click(
                PointerEvent(x, y, button=button, modifiers=modifiers),
                self._drag_action,
            )
        self._drag_action = None

    def on_pointer_press(
        self,
        x: float,
        y: float,
        button: int,
        modifiers: int = NO_MODIFIER,
        double: bool = False,
    ) -> bool:
        """Route a press: the panel first, then the mode table.

        The panel is offered it *first*, as in qtgl: otherwise a click meant for
        a menu also starts rotating the molecule, and the model spins away under
        the menu that just opened.

        Parameters
        ----------
        x, y : float
            Where the press landed, in logical pixels.
        button : int
            One of the ``*_BUTTON`` constants.
        modifiers : int, optional
            A mask of the ``*_MODIFIER`` constants.
        double : bool, optional
            Whether this is the second press of a double click. The panel opens
            its menus on one (`DblClk Menu` in the mouse-mode block); dropping
            the flag leaves every menu in the panel unreachable while single
            clicks keep working, so the panel looks alive and inert.

        Returns
        -------
        bool
            Whether the press was consumed.
        """
        gui = self._internal_gui
        # About to move the camera or pick, so a traced still stops being true.
        # A press that misses every panel puts the overlays down first. Only
        # when nothing was dismissed does it reach the camera, so clicking away
        # from `help` closes it rather than closing it *and* spinning the view.
        if gui is not None and not gui.wants(float(x), float(y)):
            if gui.dismiss_overlays(float(x), float(y)):
                self.update()
                return True
        if gui is None or not gui.wants(float(x), float(y)):
            self.clear_ray_image()
        if gui is not None and gui.mouse_press(
            float(x),
            float(y),
            right=button == RIGHT_BUTTON,
            modifiers=modifiers,
            double=double,
        ):
            self._gui_grab = True
            self.update()
            return True

        # A right-click on the scene itself opens the object menus at the
        # cursor. The mouse-mode block has always promised this -- its
        # `SnglClk` row reads `R  Menu` -- while the five menus were reachable
        # only from the object list's buttons.
        if gui is not None and button == RIGHT_BUTTON:
            target = self._context_menu_target(x, y)
            if gui.open_context_menu(float(x), float(y), target):
                self._gui_grab = True
                self.update()
                return True

        if button == RIGHT_BUTTON:
            # The right button carries a box too -- `-Box` is shift-right in the
            # two-button modes -- so the table is asked before the press is
            # deferred, or that cell of the block names a gesture nothing starts.
            if self._start_box_drag(x, y, button, modifiers):
                return True
            # Defer: a right *drag* dollies; a right *click* is a click.
            self._last_pos = (x, y)
            self._press_pos = (x, y)
            self._press_mods = modifiers
            self._press_button = button
            return True

        if button in (LEFT_BUTTON, MIDDLE_BUTTON):
            action = self._action_for(button, modifiers)
            if action == "move":
                self._panning = True
                self._last_pos = (x, y)
                return True
            if self._start_box_drag(x, y, button, modifiers):
                return True
            # A non-box press is a candidate click, or the start of a drag that
            # rotates. PyMOL decides on *release*: a press that never dragged
            # fires the `single_*` cell, so the click action and the drag action
            # can differ.
            self._press_pos = (x, y)
            self._press_mods = modifiers
            self._press_button = button
            self._last_pos = (x, y)
            return True

        self._last_pos = (x, y)
        return False

    def on_pointer_move(
        self, x: float, y: float, buttons: int = NO_BUTTON, modifiers: int = NO_MODIFIER
    ) -> bool:
        """Drag the box, the panel, or the camera -- whatever the press began.

        Keyed on what the press decided rather than re-derived from the button:
        deriving it here is what once made ctrl-left rotate when the mode table
        said pan.

        Parameters
        ----------
        x, y : float
            The pointer's position, in logical pixels.
        buttons : int, optional
            Mask of the buttons currently held; zero for a hover.
        modifiers : int, optional
            A mask of the ``*_MODIFIER`` constants.

        Returns
        -------
        bool
            Whether the move was consumed.
        """
        gui = self._internal_gui
        if self._gui_grab:
            if gui is not None and gui.is_dragging() and gui.drag(float(x), float(y)):
                self.update()
            return True
        if gui is not None and not buttons:
            if gui.mouse_move(float(x), float(y)):
                self.update()
            if gui.wants(float(x), float(y)):
                return True
        elif gui is not None and gui.has_menu():
            # An open menu owns the pointer. Rotating the molecule under it is
            # never what a drag across a menu meant.
            return True

        if self._drag_selecting and self._drag_start is not None:
            self._select_rect = Rect.from_corners(
                self._drag_start[0], self._drag_start[1], x, y
            )
            self.update()
            return True

        if self._last_pos is None or not buttons:
            return False
        last_x, last_y = self._last_pos
        if self._panning:
            ratio = self._ratio()
            self.pan((x - last_x) * ratio, (y - last_y) * ratio)
        elif buttons & RIGHT_BUTTON:
            # Right drag dollies, as PyMOL's `cButModeTransZ` does.
            self._right_dragged = True
            self.dolly(WHEEL_STEP ** ((y - last_y) / 40.0))
        else:
            self.orbit((last_x, last_y), (x, y))
        self._last_pos = (x, y)
        self.update()
        return True

    def on_pointer_release(
        self, x: float, y: float, button: int, modifiers: int = NO_MODIFIER
    ) -> bool:
        """End the gesture, and turn a press that never moved into a click.

        Parameters
        ----------
        x, y : float
            Where the release landed, in logical pixels.
        button : int
            The button released.
        modifiers : int, optional
            A mask of the ``*_MODIFIER`` constants.

        Returns
        -------
        bool
            Whether the release was consumed.
        """
        if self._panning:
            self._panning = False
            self._last_pos = None
            self._press_pos = None
            return True

        if self._gui_grab:
            self._gui_grab = False
            if self._internal_gui is not None:
                self._internal_gui.release()
            self.update()
            return True

        if self._drag_selecting and button == self._drag_button:
            self._end_box_drag(x, y, button, modifiers)
            return True

        press, self._press_pos = self._press_pos, None
        self._last_pos = None
        if press is not None and self._controller is not None:
            if (
                abs(x - press[0]) <= self.CLICK_SLOP
                and abs(y - press[1]) <= self.CLICK_SLOP
            ):
                self._handle_click(x, y, button, modifiers)
        self._right_dragged = False
        return True

    def _handle_click(
        self, x: float, y: float, button: int, modifiers: int
    ) -> None:
        """Fire the mode table's *click* cell for the press that just ended.

        PyMOL keeps a separate row for clicks, so a press that never dragged can
        mean something other than the drag it would have been -- plain left
        drags (`Rota`) but clicks (`+/-`). Where that row says nothing, the
        modified cell the press resolved still applies: ctrl-middle is `PkAt`
        whether or not it moved.

        Parameters
        ----------
        x, y : float
            Where the click landed.
        button : int
            The button released.
        modifiers : int
            The modifiers held at release.
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
            self._controller.handle_mouse_click(
                PointerEvent(x, y, button=button, modifiers=modifiers), click
            )
        except Exception:  # pragma: no cover - a viewer that refuses the click
            return
        self.update()

    def on_wheel(
        self, x: float, y: float, steps: int, modifiers: int = NO_MODIFIER
    ) -> bool:
        """Dolly the camera, or move the clipping slab when a modifier is held.

        Parameters
        ----------
        x, y : float
            Where the pointer was, in logical pixels.
        steps : int
            Notches, positive away from the user. Never zero: a trackpad sends
            many small deltas rather than 120-unit notches, and truncating those
            to zero makes the gesture do nothing at all -- so a host rounds
            *away* from zero rather than passing 0 in.
        modifiers : int, optional
            A mask of the ``*_MODIFIER`` constants.

        Returns
        -------
        bool
            Whether the notch was consumed.
        """
        from ..host.events import CONTROL_MODIFIER, SHIFT_MODIFIER

        if not steps:
            return False
        gui = self._internal_gui
        if gui is not None:
            # Over an open menu the wheel scrolls the menu -- PyMOL's `CPopUp`
            # takes the scroll buttons. A menu longer than the window is the
            # ordinary case for the Action menu on a small viewport, and zooming
            # the molecule underneath it is never what was meant.
            if gui.has_menu():
                if gui.scroll_menu(x, y, steps):
                    self.update()
                return True
            # Over the info panel, the wheel scrolls the info panel.
            #
            # This looks redundant next to `scroll_menu`, which also tries the
            # info panel -- and that was the bug. `scroll_menu` is only reached
            # when `has_menu()` is true, so the info panel was scrollable
            # *only while a menu happened to be open*, which is never. Every
            # other notch fell through to `dolly()` below, so pointing at a
            # `help` listing longer than the panel and turning the wheel zoomed
            # the molecule behind it and left the text where it was.
            if gui.info_contains(x, y) and gui.info_max_scroll() > 0:
                # Consumed whether or not it moved: at the top or the bottom of
                # the listing the panel has nowhere to go, and letting the notch
                # fall through there zooms the molecule *behind* the text the
                # reader is looking at. The menu branch above takes the same
                # line for the same reason.
                if gui.scroll_info(x, y, steps):
                    self.update()
                return True
            # Over the sequence, the wheel scrolls the sequence.
            if gui.sequence_visible and gui.sequence_strip_contains(x, y):
                if gui.scroll_sequence(-steps * 5):
                    self.update()
                return True

        # The camera is about to move, so a traced still stops being true.
        self.clear_ray_image()
        if modifiers & (SHIFT_MODIFIER | CONTROL_MODIFIER):
            # Ctrl is PyMOL's `MvSZ`: the camera goes with the slab, so it stays
            # put against the molecule and the view dollies instead.
            if self.move_slab(steps, dolly=bool(modifiers & CONTROL_MODIFIER)):
                self.announce_clipping()
        else:
            self.dolly(WHEEL_STEP ** (-steps))
        self.update()
        return True

    def on_key_press(self, key: int, text: str = "", modifiers: int = NO_MODIFIER) -> bool:
        """Offer the key to the chrome, then to the viewer.

        The chrome goes first because it owns the in-viewport command line, and
        a prompt with a caret in it must get the ``r`` the user typed rather
        than the representation switching underneath them. It answers ``False``
        for every key it does not want, so the shortcuts are untouched until
        something is being typed.

        Parameters
        ----------
        key : int
            One of :mod:`chimol.host.keys`' ``KEY_*`` values, or ``0``.
        text : str, optional
            The character the key produced.
        modifiers : int, optional
            A mask of the ``*_MODIFIER`` constants.

        Returns
        -------
        bool
            Whether the key was consumed.
        """
        from ..host.events import CONTROL_MODIFIER, SHIFT_MODIFIER, KeyEvent

        gui = self._internal_gui
        if gui is not None:
            try:
                if gui.key_press(int(key), str(text or ""), int(modifiers)):
                    self.update()
                    return True
            except Exception:  # pragma: no cover - a chrome that refuses the key
                pass

        # Ctrl+Z and Ctrl+Shift+Z, *after* the chrome has had the key: while the
        # prompt has focus they are its own (a command being typed is text, and
        # taking Z out of it would be worse than having no shortcut at all).
        letter = str(text or "").lower()
        if letter == "z" and (int(modifiers) & CONTROL_MODIFIER):
            run = getattr(gui, "_run_command", None) if gui is not None else None
            if callable(run):
                run("redo" if int(modifiers) & SHIFT_MODIFIER else "undo")
                self.update()
                return True

        handler = getattr(self._controller, "handle_key_event", None)
        if callable(handler):
            try:
                if handler(KeyEvent(key, text, modifiers)):
                    self.update()
                    return True
            except Exception:  # pragma: no cover - viewer-side refusal
                pass
        return False
