"""ChiMOL inside a region of an emtk window: the molecular viewer as a reusable view.

:class:`ChimolView` embeds chimol's offscreen renderer (its own chrome included: object list, mouse panel, command
prompt) where an emtk layout puts it, and hands it the pointer, wheel and keys that land on it. A card draws it like any
widget, ``view.draw()``, and talks to ``view.viewer`` with the same calls the Qt windows make on their embedded viewer
(``add_structure``, ``add_surface_overlay``, ``add_sphere``, ``add_measurement``, ``atomSelectionChanged``).

The whole-window host :mod:`chisurf.plugins.chimol.app` is the same embedding for a window that is nothing but the viewer.

Input is read from the emtk context each frame (the card's host forwards nothing): a press on the picture starts a drag
that chimol keeps until the release, wherever it ends; the wheel over the picture is chimol's; keys go to chimol while it
has the focus (the last press landed on it) and no emtk field has the keyboard. Nothing reaches chimol through a window
drawn over the view (a dialog, the guide's card).
"""

from __future__ import annotations

import logging
import os
from typing import Any

import numpy as np
from emtk import im
from emtk.events import (
    ALT_MODIFIER,
    CONTROL_MODIFIER,
    LEFT_BUTTON,
    META_MODIFIER,
    MIDDLE_BUTTON,
    RIGHT_BUTTON,
    SHIFT_MODIFIER,
)
from emtk.im_core import get_current_context

logger = logging.getLogger(__name__)

#: emtk's mouse index (``io.mouse_down[i]``) to the button code chimol's handlers take.
_BUTTONS = (LEFT_BUTTON, RIGHT_BUTTON, MIDDLE_BUTTON)


class ChimolView:
    """An embedded ChiMOL viewer, created on first draw.

    Parameters
    ----------
    min_size : tuple of int, optional
        The smallest size chimol renders at; a smaller region shows the frame scaled down. chimol lays out its sequence
        strip and panels for a desktop-size canvas and overprints below about 760x420.
    """

    def __init__(self, min_size: tuple[int, int] = (760, 420)) -> None:
        self.min_size = min_size
        self.app: Any = None
        #: Why chimol could not start (no WebGPU adapter, ...); empty while it works.
        self.error = ""
        self.frame: np.ndarray | None = None
        #: Where the picture was drawn in the last frame, ``(x, y, w, h)``.
        self.rect: tuple[float, float, float, float] | None = None
        self._render_size = min_size
        self._dragging = False
        self._focused = False

    # ── lifecycle ─────────────────────────────────────────────────────────

    def ensure(self) -> bool:
        """Start chimol once; ``False`` (with :attr:`error`) when it cannot run here."""
        if self.app is not None or self.error:
            return self.app is not None
        try:
            # Before chimol.core.viewer is imported: with ChiSurf's Qt loaded, "auto" binds a QWidget base, and
            # building one without a QApplication aborts. "none" is what chimol's toolkit-free host sets.
            os.environ.setdefault("CHIMOL_TOOLKIT", "none")
            from chimol.hosts.native.app import ChimolApp

            self.app = ChimolApp(size=self.min_size, backend="offscreen")
        except Exception as exc:  # noqa: BLE001 - shown in place of the view
            self.error = f"{type(exc).__name__}: {exc}"
            logger.warning("chimol view unavailable: %s", self.error)
            return False
        return True

    @property
    def viewer(self) -> Any:
        """chimol's :class:`~chimol.core.viewer.Viewer`, or ``None`` when it is not running."""
        return self.app.viewer if self.ensure() else None

    def sync_panel(self) -> None:
        """Refresh chimol's object list after objects were added or removed through the viewer API (chimol's own
        commands do this themselves)."""
        if self.app is not None:
            try:
                self.app.sync_panel()
            except Exception:  # noqa: BLE001 - the panel is chrome; the scene is drawn regardless
                logger.debug("chimol object list did not refresh", exc_info=True)

    def close(self) -> None:
        if self.app is not None:
            try:
                self.app.close()
            except Exception:  # noqa: BLE001 - closing must not raise
                logger.debug("chimol view close failed", exc_info=True)
        self.app = None

    # ── one frame ─────────────────────────────────────────────────────────

    def draw(self, size: tuple[float, float] = (-1.0, -1.0), enabled: bool = True) -> bool:
        """Draw the viewer at the cursor, *size* as ``im.image`` takes it (``-1`` = the room left).

        Returns ``False`` when chimol is unavailable (the caller shows :attr:`error` and its fallback).
        *enabled* ``False`` draws the picture but gives chimol no input (a modal question is open).
        """
        if not self.ensure():
            return False
        avail_w, avail_h = im.get_content_region_avail()
        w = avail_w if size[0] <= 0 else float(size[0])
        h = avail_h if size[1] <= 0 else float(size[1])
        w, h = max(w, 1.0), max(h, 1.0)
        # Below the minimum, render larger by one factor on both axes, so the scaled-down picture keeps its aspect.
        k = max(1.0, self.min_size[0] / w, self.min_size[1] / h)
        self._resize(int(round(w * k)), int(round(h * k)))
        frame = self.app.renderer.draw_frame()
        if frame is not None:
            self.frame = frame
        if self.frame is None:
            im.dummy(w, h)
        else:
            im.image(self.frame, size=(w, h))
        self.rect = tuple(im.get_item_rect())
        if enabled:
            self._input()
        return True

    def _resize(self, w: int, h: int) -> None:
        """Render at ``w x h``: the offscreen canvas first (it reports no size it was not given), then the renderer."""
        if (w, h) == self._render_size and self.frame is not None:
            return
        renderer = self.app.renderer
        set_logical = getattr(getattr(renderer, "_canvas", None), "set_logical_size", None)
        if callable(set_logical):
            try:
                set_logical(w, h)
            except Exception:  # noqa: BLE001 - a fixed-size canvas blits as before
                logger.debug("chimol canvas did not resize", exc_info=True)
        renderer.on_resize(w, h, 1.0)
        self._render_size = (w, h)

    # ── input ─────────────────────────────────────────────────────────────

    def _to_frame(self, x: float, y: float) -> tuple[float, float]:
        rx, ry, rw, rh = self.rect
        fw, fh = self._render_size
        return (x - rx) * fw / max(rw, 1.0), (y - ry) * fh / max(rh, 1.0)

    def over(self, x: float, y: float) -> bool:
        """Whether a pointer at (x, y) is on the picture and not under another window."""
        if self.rect is None:
            return False
        rx, ry, rw, rh = self.rect
        if not (rx <= x < rx + rw and ry <= y < ry + rh):
            return False
        ctx = get_current_context()
        cx, cy, cw, ch = ctx.clip_rect
        if not (cx <= x < cx + cw and cy <= y < cy + ch):
            return False
        return ctx.hovered_window in (None, ctx.current_window)

    def _modifiers(self, io) -> int:
        return (
            (SHIFT_MODIFIER if io.key_shift else 0)
            | (CONTROL_MODIFIER if io.key_ctrl else 0)
            | (ALT_MODIFIER if getattr(io, "key_alt", False) else 0)
            | (META_MODIFIER if getattr(io, "key_super", False) else 0)
        )

    def _input(self) -> None:
        ctx = get_current_context()
        io = ctx.io
        renderer = self.app.renderer
        mx, my = io.mouse_pos
        over = self.over(mx, my)
        fx, fy = self._to_frame(mx, my)
        mods = self._modifiers(io)
        pressed = False
        for i, code in enumerate(_BUTTONS):
            if io.mouse_clicked[i]:
                if over:
                    renderer.on_pointer_press(fx, fy, code, mods, double=bool(io.mouse_double_clicked[i]))
                    self._dragging = pressed = True
                    self._focused = True
                else:
                    self._focused = False
        if not pressed and (over or self._dragging) and io.mouse_pos != io.mouse_pos_prev:
            buttons = sum(code for i, code in enumerate(_BUTTONS) if io.mouse_down[i])
            renderer.on_pointer_move(fx, fy, buttons, mods)
        for i, code in enumerate(_BUTTONS):
            if io.mouse_released[i] and self._dragging:
                renderer.on_pointer_move(fx, fy, 0, mods)
                renderer.on_pointer_release(fx, fy, code, mods)
                self._dragging = any(io.mouse_down)
        if over and io.mouse_wheel:
            renderer.on_wheel(fx, fy, int(round(io.mouse_wheel)) or (1 if io.mouse_wheel > 0 else -1), mods)
            io.mouse_wheel = 0.0
        if self._focused and not io.want_capture_keyboard:
            for key, text, kmods in list(io.key_events):
                renderer.on_key_press(key, text, kmods)


__all__ = ["ChimolView"]
