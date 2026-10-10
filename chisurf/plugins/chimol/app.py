"""EMTK host for the ChiMOL molecular viewer.

ChiMOL ships its own toolkit-free desktop host (:mod:`chimol.hosts.native`)
rendering through wgpu. This adapter embeds that viewer in ChiSurf's native
plugin chrome: the chimol renderer draws offscreen, each frame is read back to
a numpy image and blitted through :func:`emtk.im.image`, and pointer, wheel
and keyboard events are forwarded to chimol's viewport canvas — the same
handlers its own window drives, so orbit/pan/zoom behave identically.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from emtk import im
from emtk.app import ImApp
from emtk.im_core import get_current_context

from chisurf.emtk.background_build import BackgroundBuild
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.plugins.emtk_layout import action_button, window_size
from emtk.i18n import tr

if TYPE_CHECKING:
    from chimol.hosts.native.app import ChimolApp

HERE = Path(__file__).parent

class ChimolHostApp(ImApp):
    """Run ChiMOL inside an EMTK surface."""

    #: Height of the status strip kept below the viewport.
    STATUS_H = 26.0
    #: Height of chimol's command prompt at the bottom of its own frame, in
    #: frame pixels (the guide points at it; it is drawn by chimol, not here).
    PROMPT_H = 18.0

    def __init__(self, size: tuple[int, int] = (900, 620)):
        spec = json.loads((HERE / "window.view.json").read_text(encoding="utf-8"))
        self.window_size = window_size(spec, (1200, 800))
        self._chimol_size = size
        #: The viewer once it is running; :attr:`_chimol` is the same, after joining a start under way.
        self._chimol_app: ChimolApp | None = None
        self._error = ""
        #: Starting chimol (wgpu adapter, ~50 render pipelines, the first frame) costs over a second; the first
        #: draw starts it on a worker thread and the window says "Starting" until it lands.
        self._starter = BackgroundBuild(wake=self.request_frame)
        self._frame: np.ndarray | None = None
        self._surface = size
        self._viewport_h = float(size[1])
        self._objects_seen: int | None = None
        self._drag_from: tuple[float, float] | None = None
        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        self.help_window = EmTkHelpWindow(
            title="ChiMOL — Help", resource=HERE / "help.md", owner=self
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            owner=self,
            wait_for_controls=True,
            get_target_rect=self.item_rects.get,
        )
        super().__init__(self.render)

    # ── chimol lifecycle (lazy: keep plugin import toolkit- and wgpu-free) ──
    @property
    def _chimol(self) -> ChimolApp | None:
        """The running viewer (a start under way is finished first); ``None`` before the first draw or on error."""
        self._adopt_start(wait=True)
        return self._chimol_app

    @_chimol.setter
    def _chimol(self, value) -> None:
        self._chimol_app = value

    @property
    def _chimol_error(self) -> str:
        self._adopt_start(wait=True)
        return self._error

    @_chimol_error.setter
    def _chimol_error(self, value: str) -> None:
        self._error = value

    @property
    def starting(self) -> bool:
        """Whether chimol is being started on the worker thread."""
        return self._starter.busy

    def _start(self, surface: tuple[int, int] | None = None):
        """Construct chimol (and, with *surface*, render its first frame there): ``(app, frame)``. Runs on the
        start thread or, from :meth:`_ensure_chimol`, on the caller's."""
        # The choice has to precede chimol.core.viewer's import: with the
        # default "auto" and ChiSurf's Qt already loaded, Viewer binds a
        # QWidget base and building one without a QApplication aborts.
        # "none" is exactly what chimol's own toolkit-free host sets.
        os.environ.setdefault("CHIMOL_TOOLKIT", "none")
        from chimol.hosts.native.app import ChimolApp

        app = ChimolApp(size=self._chimol_size, backend="offscreen")
        frame = None
        if surface is not None:
            # The first frame compiles the render pipelines: pay that here too, not on the UI thread.
            self._resize(app, *surface)
            frame = app.renderer.draw_frame()
        return app, frame

    def _adopt_start(self, wait: bool = False) -> None:
        """Take over a finished start (with *wait*, finish it first)."""
        done = self._starter.collect(wait=wait)
        if not done:
            return
        made, exc = done["chimol"]
        if exc is not None:
            self._error = f"{type(exc).__name__}: {exc}"
            return
        self._chimol_app, frame = made
        if frame is not None:
            self._frame = frame
        self._subscribe()

    def _ensure_chimol(self) -> bool:
        """Start chimol now if it is not running (joins a start under way); whether it runs."""
        self._adopt_start(wait=True)
        if self._chimol_app is not None or self._error:
            return self._chimol_app is not None
        try:
            self._chimol_app, _frame = self._start()
        except Exception as exc:  # noqa: BLE001 - surface the load error inline
            self._error = f"{type(exc).__name__}: {exc}"
            return False
        self._subscribe()
        return True

    def _subscribe(self) -> None:
        # A movie started from the console, a macro or a script runs no input
        # event, and chimol's own wake (`update()` -> `request_draw`) knocks on
        # the rendercanvas loop -- which is not running inside this embed. The
        # clock (Playback.pump) only turns inside a frame we draw, and the
        # animating() chain below only *keeps* a chain going, never starts one.
        # A command that ran is the one honest signal that the picture is now
        # stale: wake the host (emtk.request_frame -> ControlHost.update) so
        # one paint happens, and that paint's animating() check takes over.
        try:
            self._command_sub = self._chimol_app.viewer.bus.subscribe(
                "command.executed",
                self._on_command_executed,
                owner="chisurf-emtk-host",
            )
        except Exception:  # noqa: BLE001 - a viewer without its bus still draws
            self._command_sub = None

    def _running(self) -> bool:
        """Whether chimol takes input now; input during its start is dropped rather than blocking the UI."""
        self._adopt_start()
        return self._chimol_app is not None

    def _on_command_executed(self, _line=None) -> None:
        self.tour.notify_used("command_line")
        self.request_frame()

    # ── frame pump ──────────────────────────────────────────────────────
    def draw(self, painter, x, y, w, h):
        # chimol's viewport lays out its sequence strip and panels for a
        # desktop-size canvas; below ~760 px its text overprints. Render at
        # the clamped size and let the blit scale to the actual width.
        self._surface = (
            max(760, int(w)),
            max(420, int(h - self.STATUS_H)),
        )
        self._adopt_start()
        if self._chimol_app is None and not self._error and not self.starting:
            surface = self._surface
            self._starter.start({"chimol": lambda: self._start(surface)}, name="chisurf-chimol-start")
        elif self._chimol_app is not None:
            self._resize(self._chimol_app, *self._surface)
            frame = self._chimol_app.renderer.draw_frame()
            if frame is not None:
                self._frame = frame
        super().draw(painter, x, y, w, h)

    def _resize_chimol(self, w, h) -> None:
        if self._chimol_app is not None:
            self._resize(self._chimol_app, w, h)

    @staticmethod
    def _resize(chimol, w, h) -> None:
        renderer = chimol.renderer
        canvas = renderer._canvas
        try:
            logical = canvas.get_logical_size()
        except Exception:  # noqa: BLE001 - a canvas that cannot say is at its size
            logical = None
        if logical is not None and (int(w), int(h)) == (int(logical[0]), int(logical[1])):
            return
        # The canvas itself must grow first: rendercanvas only reports a new
        # size after `set_logical_size` (its own resize events come from the
        # window manager, and an offscreen canvas has no window manager).
        # Telling the renderer alone (`on_resize`) resizes nothing -- its
        # canvas answered 900x620 for the rest of the session and the blit
        # stretched the stale frame over the grown widget.
        set_logical = getattr(canvas, "set_logical_size", None)
        if callable(set_logical):
            try:
                set_logical(int(w), int(h))
            except Exception:  # noqa: BLE001 - a fixed-size canvas blits as before
                pass
        renderer.on_resize(int(w), int(h), 1.0)

    def animating(self) -> bool:
        # The host's repaint contract (emtk.qt_host.ControlHost.paintEvent):
        # while `animating()` is True the widget asks for its next frame
        # itself, and each frame ChimolHostApp.draw runs pumps the movie
        # (`canvas.frame()` -> `Playback.pump`) -- that is the whole clock an
        # embedded chimol has. Without this the movie ran only while the
        # pointer kept producing events, because those were the only frames.
        if self.starting:
            return True
        if self._chimol_app is not None:
            playback = getattr(self._chimol_app.viewer, "playback", None)
            if playback is not None and getattr(playback, "running", False):
                return True
        return super().animating()

    def render(self):
        width, height = im.get_main_viewport().size
        box = (0, 0, width, height)
        im.begin("ChiMOL", box)
        if self._error:
            im.heading("ChiMOL unavailable", level=2)
            im.text_wrapped(self._error)
            im.end()
            return
        # Reserve a status strip: chimol's own viewport draws its command bar
        # at the bottom of its frame, so overlaying text there collides.
        viewport_h = max(1.0, height - self.STATUS_H)
        self._viewport_h = viewport_h
        if self._frame is not None:
            im.image(self._frame, size=(width, viewport_h))
        else:
            # Keep the viewport's room, so the status strip sits where it will once the picture arrives.
            x, y = im.get_cursor_screen_pos()
            im.text_disabled(tr("Starting ChiMOL…") if self.starting else tr("Rendering…"))
            im.set_cursor_screen_pos((x, y))
            im.dummy(width, viewport_h)
        vx, vy, vw, vh = im.get_item_rect()
        self.item_rects["viewport"] = (vx, vy, vw, vh)
        self.item_rects["structure"] = (vx, vy, vw, vh)
        prompt_h = self.PROMPT_H * vh / max(1.0, float(self._surface[1]))
        self.item_rects["command_line"] = (vx, vy + vh - prompt_h, vw, prompt_h)
        objects = self._object_count()
        if self._objects_seen is not None and objects > self._objects_seen:
            self.tour.notify_used("structure")
        self._objects_seen = objects
        im.text(f"ChiMOL · {objects} object(s)")
        self.item_rects["status"] = im.get_item_rect()
        self._toolbar(width)
        im.end()
        self.help_window.draw(box)
        self.tour.draw(width, height)

    def _toolbar(self, width: float) -> None:
        """Help and Guide, right-aligned in the status strip."""
        im.same_line(max(0.0, width - 130.0))
        if action_button("help"):
            self.help_window.show()
        self.item_rects["help"] = im.get_item_rect()
        im.same_line()
        if action_button("guide"):
            self.tour.start()
        self.item_rects["guide"] = im.get_item_rect()

    def _object_count(self) -> int:
        if self._chimol_app is None:  # drawn every frame: never waits for a start under way
            return 0
        # What the object list shows: `viewer.objects` also holds the empty
        # placeholder a fresh viewer starts with, which read as "1 object(s)"
        # before anything was loaded.
        try:
            return len(self._chimol_app.viewer.list_objects())
        except Exception:  # noqa: BLE001 - status is best-effort
            return 0

    # ── input forwarding (same handlers chimol's own window drives) ─────
    def _inside(self, x, y) -> bool:
        """Whether a pointer event at (x, y) belongs to chimol.

        Not when it lands on the status strip (Help / Guide), on an emtk
        control hovered in the last frame (the tour card's buttons, the help
        window), or on a window other than the viewer's own (the help window).
        Otherwise a click on Next also picked the atom underneath it.
        """
        if y >= self._viewport_h:
            return False
        try:
            ctx = get_current_context()
        except Exception:  # noqa: BLE001 - before the first frame: chimol's
            return True
        if ctx.hovered_id is not None:
            return False
        window = ctx.find_hovered_window(float(x), float(y))
        return window is None or getattr(window, "name", "ChiMOL") == "ChiMOL"

    def pointer_press(self, x, y, button, modifiers=0, clicks=1):
        super().pointer_press(x, y, button, modifiers, clicks)
        if self._inside(x, y) and self._running():
            self._drag_from = (float(x), float(y))
            self._chimol.renderer.on_pointer_press(x, y, button, modifiers, double=clicks > 1)

    def pointer_move(self, x, y, buttons=0, modifiers=0):
        super().pointer_move(x, y, buttons, modifiers)
        if (self._drag_from is not None or self._inside(x, y)) and self._running():
            self._chimol.renderer.on_pointer_move(x, y, buttons, modifiers)
            if buttons and self._drag_from is not None:
                dx, dy = x - self._drag_from[0], y - self._drag_from[1]
                if dx * dx + dy * dy > 25.0:
                    self.tour.notify_used("viewport")

    def pointer_release(self, x, y, button, modifiers=0):
        super().pointer_release(x, y, button, modifiers)
        # A drag that began on the viewer ends there, wherever it is released.
        if (self._drag_from is not None or self._inside(x, y)) and self._running():
            self._chimol.renderer.on_pointer_release(x, y, button, modifiers)
        self._drag_from = None

    def wheel(self, x, y, steps, modifiers=0):
        super().wheel(x, y, steps, modifiers)
        if self._inside(x, y) and self._running():
            self._chimol.renderer.on_wheel(x, y, steps, modifiers)

    def key(self, key, text="", modifiers=0):
        consumed = super().key(key, text, modifiers)
        if self._running():
            # chimol keys on the typed character (emtk.keys' values pass through
            # its on_key_press as DOM text + modifiers).
            return self._chimol.renderer.on_key_press(key, text, modifiers) or consumed
        return consumed

    # ── persistence ─────────────────────────────────────────────────────
    def export_settings(self) -> dict:
        """Nothing of the host's own to remember.

        The Qt window remembered nothing either (``settings_key`` is null):
        chimol keeps its window layout and display configuration itself
        (``enable_persistence``, the display config), the same on every host.
        """
        return {}

    def restore_settings(self, settings) -> None:
        """Accept and ignore a saved dict (see :meth:`export_settings`)."""
        return None

    def close(self):
        self.help_window.close()
        self.tour.stop()
        if self._chimol is not None:
            sub = getattr(self, "_command_sub", None)
            if sub is not None:
                try:
                    self._chimol.viewer.bus.unsubscribe(sub)
                except Exception:  # noqa: BLE001 - teardown is best-effort
                    pass
                self._command_sub = None
            close = getattr(self._chimol.renderer, "close", None)
            if callable(close):
                close()
            self._chimol = None


def make_app() -> ChimolHostApp:
    return ChimolHostApp()
