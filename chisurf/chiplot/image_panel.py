"""The toolkit-free image viewer: :class:`ImagePanel`, an emtk control.

A picture (an image or a ``(t, y, x)`` stack) on chiplot's image view, with what
makes it an image *viewer*: a colour ramp with draggable levels beside it, a
frame slider under it while a stack is shown, playback, a picture placed on real
axes, symbols and labels over it, a paintable brush layer, region shapes and
click-to-pick. The whole viewer is one control (``draw``/``press``/``drag``/
``release``/``hover``/``scroll``): an emtk surface draws it directly, and a
legacy widget form hosts it with :func:`chisurf.gui.chiplot.host`.

Events are hooks (``connect``/``disconnect``/``emit``): :attr:`ImagePanel.clicked`
``(x, y)``, :attr:`ImagePanel.picked` ``(PickedSpot)``, :attr:`ImagePanel.frame_changed`
``(index)`` and :attr:`ImagePanel.playing_changed` ``(bool)``.

Playback needs a clock, which a control does not own: while :attr:`ImagePanel.playing`
is true whatever shows the panel calls :meth:`ImagePanel.advance` every
:attr:`ImagePanel.interval_ms` (a widget host does it with a timer), or
:meth:`ImagePanel.tick` with the time on every frame (an emtk surface that keeps
drawing while :meth:`ImagePanel.animating`).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import numpy as np

from chisurf.chiplot.backends import get_backend
from chisurf.chiplot.canvas import _Hook
from chisurf.chiplot.handles import Image, Roi, Scatter, Text
from chisurf.chiplot.style import colormap as _colormap
from chisurf.chiplot.style import to_brush, to_color, to_pen

__all__ = ["ImagePanel"]

#: emtk's text alignment flags (``emtk.painter``), spelled here so drawing needs no import.
_ALIGN_RIGHT_VCENTER = 0x02 | 0x80
_ALIGN_CENTER = 0x04 | 0x80


class ImagePanel:
    """Image viewer: picture, colour ramp with draggable levels, frame slider for a stack.

    Parameters
    ----------
    **backend_opts
        Passed to the backend image-view factory.

    Attributes
    ----------
    clicked, picked, frame_changed, playing_changed : hook
        ``connect(callback)`` / ``disconnect(callback)``; see the module docstring.
    """

    #: Height of the frame slider row, shown only while a stack is on screen.
    SLIDER_H = 22.0
    #: Width kept for the ``i/n`` frame label at the slider's right end.
    LABEL_W = 56.0
    #: What the frame slider says under the pointer.
    SLIDER_TIP = "Frame of the stack"

    def __init__(self, **backend_opts: Any) -> None:
        self._iv = get_backend().create_image_view(**backend_opts)
        self.clicked = _Hook()
        self.picked = _Hook()
        self.frame_changed = _Hook()
        self.playing_changed = _Hook()
        self._picking = False
        self._pick_fit = "gaussian"
        self._pick_window = 9
        self._pick_image = None
        self._last_image: np.ndarray | None = None
        self._extent: tuple[float, float, float, float] | None = None
        self._brush: dict | None = None
        self._playing = False
        self._play_loop = True
        self._fps = 10
        self._due: float | None = None
        self._host: Any = None
        self._refresh_target: Callable[[], None] | None = None
        #: Boxes of the last draw: picture, ramp, slider track (``None`` when absent).
        self._boxes: dict[str, tuple[float, float, float, float] | None] = {}
        self._captured: str | None = None
        self._hovered: str | None = None
        self._iv.on_click(lambda x, y: self.clicked.emit(x, y))
        self._iv.on_frame_changed(self._frame_moved)

    # -- the host ------------------------------------------------------------
    def attach_host(self, host: Any) -> None:
        """Let *host* show the panel (duck-typed: ``update()``, optional ``playing_changed(bool)``)."""
        self._host = host

    @property
    def host(self) -> Any:
        """The attached host, or ``None``."""
        return self._host

    def set_refresh_target(self, callback: Callable[[], None] | None) -> None:
        """Send repaint requests to *callback* (a surface drawing the panel)."""
        self._refresh_target = callback
        self._iv.set_refresh_target(callback)

    def refresh(self) -> None:
        """Ask whatever shows the panel to repaint."""
        if self._refresh_target is not None:
            self._refresh_target()
            return
        update = getattr(self._host, "update", None)
        if callable(update):
            update()

    def control(self) -> ImagePanel:
        """The control a surface draws: the panel itself."""
        return self

    # -- the picture -----------------------------------------------------------
    def set_image(self, data, *, auto_levels=True, axes=None) -> None:
        """Show a 2-D image or a 3-D ``(t, y, x)`` stack.

        Parameters
        ----------
        data : array-like
            2-D image or 3-D stack.
        auto_levels : bool
            Auto-scale the intensity range to the data.
        axes : dict, optional
            Dimension map for stacks, e.g. ``{"t": 0, "y": 1, "x": 2}``.
        """
        data = np.asarray(data)
        # Kept so picking has something to fit against without the caller
        # having to hand the same array over twice.
        self._last_image = data
        self._iv.set_image(data, auto_levels=auto_levels, axes=axes)
        if self.frame_count <= 1:
            self.stop()
        self.refresh()

    @property
    def frame_bar_visible(self) -> bool:
        """Whether the frame slider is shown (a stack is on screen)."""
        return self.frame_count > 1

    @property
    def frame_label(self) -> str:
        """The slider's ``i/n`` text (empty for a single image)."""
        count = self.frame_count
        return f"{self.frame + 1}/{count}" if count > 1 else ""

    @property
    def ramp(self):
        """The colour ramp (a control with draggable levels), once an image is shown."""
        return self._iv.colorbar()

    # -- frames and playback ---------------------------------------------------
    @property
    def frame_count(self) -> int:
        """Number of frames of the shown stack (``1`` for a single image)."""
        return int(self._iv.frame_count)

    @property
    def frame(self) -> int:
        """Index of the frame being shown."""
        return int(self._iv.frame)

    def set_frame(self, index: int) -> None:
        """Show frame *index* of the stack (wrapping); a no-op for one image."""
        self._iv.set_frame(index)

    def _frame_moved(self, index: int) -> None:
        self.frame_changed.emit(index)
        self.refresh()

    @property
    def playing(self) -> bool:
        """Whether the stack is being played."""
        return self._playing

    @property
    def fps(self) -> int:
        """Playback speed in frames per second."""
        return self._fps

    @property
    def interval_ms(self) -> int:
        """Milliseconds between two playback steps."""
        return int(1000 / self._fps)

    def _announce_playing(self, playing: bool) -> None:
        notify = getattr(self._host, "playing_changed", None)
        if callable(notify):
            notify(playing)
        self.playing_changed.emit(playing)

    def play(self, fps: int | None = None, *, loop: bool | None = None) -> None:
        """Step through the stack at *fps* frames per second.

        Parameters
        ----------
        fps : int, optional
            Frames per second; the last value is kept when omitted.
        loop : bool, optional
            Wrap round at the end (default) or stop on the last frame.
        """
        if self.frame_count <= 1:
            return
        if fps is not None:
            self._fps = max(int(fps), 1)
        if loop is not None:
            self._play_loop = bool(loop)
        self._playing = True
        self._due = None
        self._announce_playing(True)

    def set_fps(self, fps: int) -> None:
        """Change the playback speed, taking effect at once while playing."""
        self._fps = max(int(fps), 1)
        if self._playing:
            self._announce_playing(True)

    def set_loop(self, loop: bool) -> None:
        """Wrap round at the end of the stack (``True``) or stop on the last frame."""
        self._play_loop = bool(loop)

    def pause(self) -> None:
        """Stop playing, staying on the current frame."""
        was = self._playing
        self._playing = False
        if was:
            self._announce_playing(False)

    def stop(self) -> None:
        """Stop playing and return to the first frame."""
        self.pause()
        if self.frame_count > 1:
            self.set_frame(0)

    def advance(self) -> None:
        """One playback step: next frame, wrapping or stopping at the end."""
        nxt = self.frame + 1
        if nxt >= self.frame_count:
            if not self._play_loop:
                self.pause()
                return
            nxt = 0
        self.set_frame(nxt)

    def tick(self, now: float | None = None) -> None:
        """Advance as many steps as are due at *now* (seconds; default the monotonic clock)."""
        if not self._playing:
            return
        now = time.monotonic() if now is None else float(now)
        period = 1.0 / self._fps
        if self._due is None:
            self._due = now + period
            return
        while self._playing and now >= self._due:
            self.advance()
            self._due += period

    def animating(self) -> bool:
        """Whether the panel wants frames by itself (it is playing)."""
        return self._playing

    # -- placing the picture ---------------------------------------------------
    def set_extent(self, extent) -> None:
        """Put the picture on real axes ``(x0, x1, y0, y1)``; ``None`` = pixel indices."""
        if extent is None:
            self._extent = None
        else:
            x0, x1, y0, y1 = (float(v) for v in extent)
            self._extent = (x0, x1, y0, y1)
        self._iv.set_extent(self._extent)

    def set_labels(self, *, bottom: str | None = None, left: str | None = None) -> None:
        """Title the axes and show them (a bare picture has none)."""
        self._iv.set_axes_visible(True)
        self._iv.set_labels(bottom=bottom, left=left)

    def set_axes_visible(self, visible: bool) -> None:
        """Show or hide tick numbers and axis titles."""
        self._iv.set_axes_visible(bool(visible))

    def invert_y(self, invert: bool = True) -> None:
        """Row 0 at the top (``True``, a picture) or the bottom (a plot)."""
        self._iv.invert_y(invert)

    def set_aspect_locked(self, lock: bool = True) -> None:
        """Square pixels (``True``) or fill the panel."""
        self._iv.set_aspect_locked(lock)

    def auto_range(self) -> None:
        """Fit the view to the picture."""
        self._iv.auto_range()

    def view_range(self):
        """The visible ``((x0, x1), (y0, y1))`` in axis units."""
        return self._iv.view_range()

    def pixel_at(self, x: float, y: float) -> tuple[int, int] | None:
        """Convert axis coordinates to ``(row, column)`` of the shown picture (``None`` outside)."""
        image = self._last_image
        if image is None:
            return None
        ny, nx = image.shape[-2:]
        if self._extent is not None:
            x0, x1, y0, y1 = self._extent
            col = (x - x0) / (x1 - x0) * nx
            row = (y - y0) / (y1 - y0) * ny
        else:
            col, row = x, y
        row, col = int(np.floor(row)), int(np.floor(col))
        if 0 <= row < ny and 0 <= col < nx:
            return row, col
        return None

    # -- symbols and labels over the picture -----------------------------------
    def marks(
        self, x, y, *, symbol="o", size=7.0, pen=None, brush=None, width=1.0, z=None
    ) -> Scatter:
        """Draw a set of symbols over the picture, in axis coordinates.

        Parameters
        ----------
        x, y : array-like
            Positions (``x`` a column, ``y`` a row for an image without extent).
        symbol : str
            ``"o"``, ``"s"``, ``"t"``, ``"d"``, ``"+"`` or ``"x"``.
        size : float
            Symbol size in pixels.
        pen, brush : color-like, optional
            Outline and fill; ``None`` leaves the symbol hollow / flat.
        width : float
            Outline width in pixels.
        z : float, optional
            Stacking order among the marks.

        Returns
        -------
        handles.Scatter
        """
        style = {
            "symbol": symbol,
            "size": size,
            "pen": None if pen is None else to_pen(pen),
            "brush": None if brush is None else to_brush(brush),
            "width": width,
        }
        marks = self._iv.add_marks(np.asarray(x, dtype=float), np.asarray(y, dtype=float), **style)
        if z is not None:
            marks.z = float(z)
        return marks

    def label(self, text: str, x: float, y: float, *, color="w", anchor=(0.0, 0.0)) -> Text:
        """Write *text* at axis position ``(x, y)`` over the picture."""
        return self._iv.add_text(str(text), (x, y), color=to_color(color), anchor=anchor)

    # -- painting ----------------------------------------------------------------
    def enable_brush(self, kernel=None, *, on_stroke=None, color=(255, 255, 255)) -> None:
        """Make the picture paintable with a brush, on a layer of its own.

        The left drag stamps *kernel* onto a mask the size of the picture and
        shows it as a translucent layer; a drag that starts on a shape still
        moves the shape. Values accumulate (a stroke over painted pixels adds)
        and are floored at zero, so a negative kernel erases.

        Parameters
        ----------
        kernel : array-like or callable, optional
            2-D weights stamped at each pixel (centred on it), or a callable
            returning them, read at the start of every stroke. Default a single pixel.
        on_stroke : callable, optional
            ``on_stroke(mask, phase)`` after every stamp, ``phase`` one of
            ``"start"``, ``"move"`` or ``"end"``; ``mask`` is a copy.
        color : color-like
            Colour of the painted layer.
        """
        tint = to_color(color)
        lut = np.zeros((256, 4), dtype=np.uint8)
        lut[:, :3] = (tint.r, tint.g, tint.b)
        lut[:, 3] = np.linspace(0, 170, 256).astype(np.uint8)
        self._brush = {
            "kernel": kernel,
            "on_stroke": on_stroke,
            "lut": lut,
            "layer": None,
            "mask": None,
            "last": None,
            "active": None,
        }
        self._iv.set_paint_handler(self._paint)
        if self._last_image is not None:
            self.set_brush_mask(None)

    def disable_brush(self) -> None:
        """Remove the brush and its layer; the drag pans again."""
        if self._brush is None:
            return
        if self._brush["layer"] is not None:
            self._brush["layer"].remove()
        self._iv.set_paint_handler(None)
        self._brush = None

    def brush_mask(self) -> np.ndarray | None:
        """A copy of the painted mask, or ``None`` before an image is shown."""
        if self._brush is None or self._brush["mask"] is None:
            return None
        return self._brush["mask"].copy()

    def set_brush_mask(self, mask) -> None:
        """Replace the painted mask (``None`` clears it) and redraw the layer.

        A mask whose shape is not the picture's is dropped for an empty one:
        painting on a stale mask would stamp onto pixels that no longer exist.
        """
        brush = self._brush
        if brush is None or self._last_image is None:
            return
        shape = self._last_image.shape[-2:]
        if mask is None or np.shape(mask) != shape:
            mask = np.zeros(shape, dtype=float)
        brush["mask"] = np.array(mask, dtype=float)
        if brush["layer"] is None or brush["layer"].get_image().shape != shape:
            if brush["layer"] is not None:
                brush["layer"].remove()
            brush["layer"] = self._iv.add_overlay(brush["mask"], colormap=brush["lut"])
            brush["layer"].set_levels(0.0, 1.0)
        else:
            brush["layer"].set_image(brush["mask"])

    def _stamp(self, row: int, col: int) -> None:
        """Add the kernel to the mask, centred on ``(row, col)``, clipped to it."""
        brush = self._brush
        if brush is None:
            return
        kernel = brush["active"]
        mask = brush["mask"]
        kh, kw = kernel.shape
        top, left = row - kh // 2, col - kw // 2
        r0, c0 = max(top, 0), max(left, 0)
        r1, c1 = min(top + kh, mask.shape[0]), min(left + kw, mask.shape[1])
        if r1 <= r0 or c1 <= c0:
            return
        window = mask[r0:r1, c0:c1] + kernel[r0 - top : r1 - top, c0 - left : c1 - left]
        mask[r0:r1, c0:c1] = np.maximum(window, 0.0)

    def _paint(self, phase: str, x: float, y: float) -> None:
        """The backend's drag, in axis coordinates: stamp along the stroke."""
        brush = self._brush
        if brush is None or self._last_image is None:
            return
        if brush["mask"] is None or brush["mask"].shape != self._last_image.shape[-2:]:
            self.set_brush_mask(None)
        if phase == "start":
            source = brush["kernel"]
            kernel = source() if callable(source) else source
            kernel = np.ones((1, 1)) if kernel is None else np.atleast_2d(np.asarray(kernel, float))
            brush["active"] = kernel
            brush["last"] = None
        if phase != "end":
            pixel = self.pixel_at(x, y)
            if pixel is not None and brush["active"] is not None:
                last = brush["last"]
                if last is None or last == pixel:
                    steps = [pixel]
                else:
                    # A fast drag skips pixels: walk the straight line between
                    # the last stamp and this one so the stroke has no gaps.
                    n = max(abs(pixel[0] - last[0]), abs(pixel[1] - last[1]))
                    steps = [
                        (
                            int(round(last[0] + (pixel[0] - last[0]) * k / n)),
                            int(round(last[1] + (pixel[1] - last[1]) * k / n)),
                        )
                        for k in range(1, n + 1)
                    ]
                for row, col in steps:
                    self._stamp(row, col)
                brush["last"] = pixel
                brush["layer"].set_image(brush["mask"])
        if brush["on_stroke"] is not None:
            brush["on_stroke"](brush["mask"].copy(), phase)

    def on_hover(self, callback) -> None:
        """Call ``callback(x, y)`` as the pointer moves over the picture."""
        self._iv.on_hover(callback)

    def set_colormap(self, name, source="matplotlib") -> None:
        """Apply a named colormap (e.g. ``"viridis"``)."""
        self._iv.set_colormap(name, source)

    def clear(self) -> None:
        """Clear the image and overlays."""
        self.stop()
        self._iv.clear()
        self._last_image = None
        if self._brush is not None:
            self._brush["layer"] = None
            self._brush["mask"] = None
        self.refresh()

    def set_histogram_width(self, width) -> None:
        """Fix (int) or free (``None``) the colour ramp's width in pixels."""
        self._iv.set_histogram_width(width)

    def set_interactive(self, *, mouse=True, menu=True) -> None:
        """Toggle view pan/zoom (``mouse``) and the right-click menu."""
        self._iv.set_interactive(mouse=mouse, menu=menu)

    def set_auto_range_button(self, shown: bool = True) -> None:
        """Show (default) or never show the "A" auto-range button."""
        self._iv.set_auto_range_button(shown)

    def add_overlay(self, data, *, colormap=None) -> Image:
        """Overlay a second image (typically RGBA with transparency) on the view."""
        cmap = colormap
        if isinstance(cmap, str):
            cmap = _colormap(cmap)
        return self._iv.add_overlay(np.asarray(data), colormap=cmap)

    def add_roi(
        self,
        *,
        kind="rect",
        pos=(0.0, 0.0),
        size=(10.0, 10.0),
        pen="y",
        movable=True,
        rotatable=False,
        points=None,
        angle=0.0,
        resizable=False,
    ) -> Roi:
        """Add a region-of-interest shape over the image.

        Parameters
        ----------
        kind : str
            ``"rect"``, ``"circle"``, ``"ellipse"`` or ``"polygon"``.
        pos : tuple of float
            Lower-left corner in image coordinates.
        size : tuple of float
            ``(w, h)`` in image coordinates.
        pen : pen-like
            Outline style.
        movable : bool
            Whether the user can drag/resize it.
        rotatable : bool
            Accepted; emtk draws no rotation grip.
        points : sequence of (float, float), optional
            Vertices for ``kind="polygon"``.
        angle : float, optional
            Rotation of an ellipse, in **radians**, about its own centre.
        resizable : bool, optional
            Give an upright rectangle or ellipse corner grips that resize it.

        Returns
        -------
        handles.Roi
        """
        return self._iv.add_roi(
            kind=kind,
            pos=tuple(pos),
            size=tuple(size),
            pen=to_pen(pen),
            movable=movable,
            rotatable=rotatable,
            points=points,
            angle=np.degrees(float(angle)),
            resizable=resizable,
        )

    def add_region(self, region, *, pen="y", movable=False, name: str = "") -> Roi:
        """Draw a :class:`chisurf.core.roi.ROI` (rectangle, ellipse/circle, polygon) over the image.

        A region drawn from a measurement is a result, so it is not movable by
        default. A mask-backed region has no analytic outline and raises
        :class:`TypeError` naming the alternative (an overlay).
        """
        from chisurf.core.roi import EllipseROI, PolygonROI, RectangleROI

        if isinstance(region, RectangleROI):
            x0, y0, x1, y1 = region.bounds()
            return self.add_roi(
                kind="rect", pos=(x0, y0), size=(x1 - x0, y1 - y0), pen=pen, movable=movable
            )
        if isinstance(region, EllipseROI):
            # pos/size are the bounding box, so the radii double.
            return self.add_roi(
                kind="ellipse",
                pos=(region.cx - region.rx, region.cy - region.ry),
                size=(2.0 * region.rx, 2.0 * region.ry),
                pen=pen,
                movable=movable,
                angle=region.angle,
            )
        if isinstance(region, PolygonROI):
            return self.add_roi(
                kind="polygon", points=[tuple(v) for v in region.vertices], pen=pen, movable=movable
            )
        raise TypeError(
            f"{type(region).__name__} has no analytic outline to draw; "
            "show it with add_overlay(region.to_mask(shape)) instead"
        )

    def enable_picking(self, image_source=None, *, fit: str = "gaussian", window: int = 9) -> None:
        """Turn clicks into picked spots, emitted on :attr:`picked`.

        The click is a seed: with ``fit="gaussian"`` a 2-D Gaussian fitted in a
        *window*-pixel square around the brightest pixel near it decides where
        the spot is (:func:`chisurf.core.roi.fit_gaussian_spot`); a fit that
        does not converge is emitted with ``success`` false and a reason.
        ``fit="none"`` takes the click as it is.

        Parameters
        ----------
        image_source : callable, optional
            Returns the 2-D array to fit against; default the last :meth:`set_image`.
        fit : str, optional
            ``"gaussian"`` or ``"none"``.
        window : int, optional
            Side of the square the fit sees.
        """
        self._pick_fit = str(fit)
        self._pick_window = int(window)
        self._pick_image = image_source
        if not self._picking:
            self._picking = True
            self.clicked.connect(self._on_pick_click)

    def _on_pick_click(self, x: float, y: float) -> None:
        """Turn one click into a pick and emit it."""
        from chisurf.core.roi import PickedSpot, fit_gaussian_spot

        image = self._pick_image() if callable(self._pick_image) else self._last_image
        if image is None:
            return
        if self._pick_fit == "none":
            self.picked.emit(PickedSpot(y=float(y), x=float(x), success=True))
            return
        self.picked.emit(fit_gaussian_spot(np.asarray(image), y, x, window=self._pick_window))

    @property
    def native(self):
        """The backend image-view object (escape hatch; avoid in new code)."""
        return self._iv.native

    # -- the control ---------------------------------------------------------------
    def layout(self, x: float, y: float, w: float, h: float) -> None:
        """Split ``(x, y, w, h)`` into the picture, the ramp beside it and the slider under both."""
        slider_h = self.SLIDER_H if self.frame_bar_visible else 0.0
        bar = self.ramp
        ramp_w = 0.0
        if bar is not None and bar.visible:
            least, most = bar.width_range
            ramp_w = float(most) if w - most >= 2 * least else float(least)
        top_h = max(h - slider_h, 0.0)
        self._boxes = {
            "picture": (x, y, max(w - ramp_w, 0.0), top_h),
            "ramp": (x + w - ramp_w, y, ramp_w, top_h) if ramp_w > 0 else None,
            "slider": (x, y + top_h, w, slider_h) if slider_h > 0 else None,
        }

    def draw(self, painter, x: float, y: float, w: float, h: float) -> None:
        """Draw the picture, the colour ramp and (for a stack) the frame slider."""
        self.layout(x, y, w, h)
        canvas = self._iv.control()
        px, py, pw, ph = self._box("picture")
        painter.fill_rect(px, py, pw, ph, tuple(canvas._background[:3]))
        painter.push_clip(px, py, pw, ph)
        try:
            canvas.draw(painter, px, py, pw, ph)
        finally:
            painter.pop_clip()
        ramp_box = self._boxes["ramp"]
        if ramp_box is not None:
            painter.fill_rect(*ramp_box, tuple(self.ramp.background))
            self.ramp.draw(painter, *ramp_box)
        if self._boxes["slider"] is not None:
            self._draw_slider(painter, *self._boxes["slider"])

    def _track(self) -> tuple[float, float, float, float] | None:
        box = self._boxes.get("slider")
        if box is None:
            return None
        x, y, w, h = box
        return (x + 8.0, y, max(w - 16.0 - self.LABEL_W, 1.0), h)

    def _box(self, part: str) -> tuple[float, float, float, float]:
        """The laid-out box of *part*; only parts that are shown are routed here."""
        box = self._boxes.get(part)
        if box is None:
            raise RuntimeError(f"the image panel's {part} is not laid out")
        return box

    def _draw_slider(self, painter, x: float, y: float, w: float, h: float) -> None:
        painter.fill_rect(x, y, w, h, (30, 32, 38))
        track = self._track()
        if track is None:
            return
        tx, ty, tw, th = track
        mid = ty + th / 2.0
        painter.fill_rect(tx, mid - 2.0, tw, 4.0, (70, 74, 84))
        count = self.frame_count
        at = tx + (tw * self.frame / (count - 1) if count > 1 else 0.0)
        thumb = (
            (120, 160, 230)
            if self._captured == "slider" or self._hovered == "slider"
            else (100, 140, 210)
        )
        painter.fill_rect(at - 5.0, mid - 7.0, 10.0, 14.0, thumb)
        painter.text(
            x + w - self.LABEL_W,
            y,
            self.LABEL_W - 4.0,
            h,
            _ALIGN_RIGHT_VCENTER,
            self.frame_label,
            (220, 220, 220),
        )

    def _part_at(self, px: float, py: float) -> str | None:
        for part in ("slider", "ramp", "picture"):
            box = self._boxes.get(part)
            if (
                box is not None
                and box[0] <= px < box[0] + box[2]
                and box[1] <= py < box[1] + box[3]
            ):
                return part
        return None

    def _slide_to(self, px: float) -> None:
        track = self._track()
        if track is None:
            return
        tx, _ty, tw, _th = track
        count = self.frame_count
        if count <= 1:
            return
        index = int(round((min(max(px, tx), tx + tw) - tx) / tw * (count - 1)))
        if index != self.frame:
            self.set_frame(index)

    def press(self, px: float, py: float, *args: Any) -> None:
        """Route a press: the slider steps frames, the ramp drags a level, the picture its own."""
        self._captured = self._part_at(px, py)
        if self._captured == "slider":
            self._slide_to(px)
        elif self._captured == "ramp":
            self.ramp.press(px, py, *self._box("ramp"), *args[4:])
        elif self._captured == "picture":
            self._iv.control().press(px, py, *self._box("picture"), *args[4:])

    def drag(self, px: float, py: float, *_args: Any) -> None:
        """Continue the gesture the press started."""
        if self._captured == "slider":
            self._slide_to(px)
        elif self._captured == "ramp":
            self.ramp.drag(px, py, *self._box("ramp"))
        elif self._captured == "picture":
            self._iv.control().drag(px, py, *self._box("picture"))

    def release(self, *args: Any) -> None:
        """End the gesture."""
        if self._captured == "ramp" and self.ramp is not None:
            self.ramp.release(*args)
        elif self._captured == "picture":
            self._iv.control().release(*args)
        self._captured = None

    def hover(self, px: float, py: float, *_args: Any) -> None:
        """Report the pointer to the part under it."""
        self._hovered = self._part_at(px, py)
        if self._hovered == "picture":
            self._iv.control().hover(px, py, *self._box("picture"))

    def scroll(self, rows: float, *args: Any) -> None:
        """Zoom the picture when the pointer is over it."""
        if self._hovered == "picture":
            self._iv.control().scroll(rows, *args)

    def tooltip_at(self, px: float, py: float) -> str | None:
        """What the part under the pointer is: the slider names itself."""
        return self.SLIDER_TIP if self._part_at(px, py) == "slider" else None
