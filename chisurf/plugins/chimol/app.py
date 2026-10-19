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
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from emtk import im
from emtk.app import ImApp
from emtk.i18n import tr
from emtk.im_core import get_current_context

from chisurf.emtk.background_build import BackgroundBuild
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.plugins.emtk_layout import action_button, action_caption, window_size

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

    def __init__(
        self,
        size: tuple[int, int] = (900, 620),
        commands: tuple[str, ...] = (),
        guide_command: str = "",
        help_resource: Path | None = None,
        ask_display_defaults: bool = False,
    ):
        #: Ask once, when the viewer is up, whether to take the display defaults this chimol ships with
        #: (chimol's in-viewport question; only when the user's settings differ and they did not opt out).
        #: The user's window (:func:`make_app`) asks; a test or a capture building the app directly does not.
        self._ask_display_defaults = bool(ask_display_defaults)
        #: chimol commands run once the viewer is up: a launcher opens one of chimol's own panels this way
        #: (Structure › FRET › FPS JSON Editor runs ``fps_circle , , Positions``).
        self._startup_commands = tuple(commands)
        #: The chimol command the Guide button runs instead of the viewer tour below, for a launcher that opens
        #: one of chimol's own tools (the FPS JSON Editor runs ``tour fps_editor``). Empty: the general tour.
        self._guide_command = str(guide_command)
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
        # The ``?`` page: the launcher's own (the FPS JSON Editor explains the labelling plan), else the viewer's.
        self.help_window = EmTkHelpWindow(
            title=tr("ChiMOL — Help"), resource=Path(help_resource or HERE / "help.md"), owner=self
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
        # ChimolApp builds chimol's viewer, which is never a toolkit widget.
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
        self._run_startup_commands()

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
        self._run_startup_commands()
        return True

    def _run_startup_commands(self) -> None:
        """Run the commands this window was opened with, once, on the viewer that just started.

        Then, once, the display-defaults question (``ask_display_defaults``).
        """
        if self._ask_display_defaults:
            self._ask_display_defaults = False
            offer = getattr(self._chimol_app, "offer_display_defaults", None)
            if callable(offer):
                try:
                    offer()
                except Exception:  # noqa: BLE001 - the question is a courtesy; the viewer runs
                    logging.getLogger(__name__).debug(
                        "could not offer the display defaults", exc_info=True
                    )
        commands, self._startup_commands = self._startup_commands, ()
        app = self._chimol_app
        for line in commands:
            try:
                if app is None:
                    break
                app.cmd.do(line)
            except Exception:  # noqa: BLE001 - the viewer stays usable; the failure is logged
                logging.getLogger(__name__).exception("chimol startup command failed: %s", line)

    def _subscribe(self) -> None:
        # A movie started from the console, a macro or a script runs no input
        # event, and chimol's own wake (`update()` -> `request_draw`) knocks on
        # the rendercanvas loop -- which is not running inside this embed. The
        # clock (Playback.pump) only turns inside a frame we draw, and the
        # animating() chain below only *keeps* a chain going, never starts one.
        # A command that ran is the one honest signal that the picture is now
        # stale: wake the host (emtk.request_frame -> ControlHost.update) so
        # one paint happens, and that paint's animating() check takes over.
        app = self._chimol_app
        if app is None:
            return
        try:
            self._command_sub = app.viewer.bus.subscribe(
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
            self._starter.start(
                {"chimol": lambda: self._start(surface)}, name="chisurf-chimol-start"
            )
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
        # The canvas grows first and the projection follows; chimol owns that
        # order (`CanvasView.resize`), so this host only says the size.
        chimol.renderer.resize(int(w), int(h))

    def animating(self) -> bool:
        # The host's repaint contract:
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
            im.heading(tr("ChiMOL unavailable"), level=2)
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
            self.tour.notify_used("example")
        self._objects_seen = objects
        im.text(tr("ChiMOL · {count} object(s)").format(count=objects))
        self.item_rects["status"] = im.get_item_rect()
        self._toolbar(width)
        im.end()
        self.help_window.draw(box)
        self.tour.draw(width, height)

    def _toolbar(self, width: float) -> None:
        """Load example, Help and Guide, right-aligned in the status strip.

        Measured from the translated captions: a fixed offset pushed
        "Anleitung" past the window edge in German.
        """
        style = im.get_style()
        keys = ("example", "help", "guide")
        needed = (
            sum(
                im.calc_text_size(action_caption(key))[0] + 2.0 * style.frame_padding[0]
                for key in keys
            )
            + style.item_spacing[0] * (len(keys) - 1)
            + 2.0 * style.item_spacing[0]
        )
        im.same_line(max(0.0, width - needed))
        if action_button("example"):
            self.load_example()
        self.item_rects["example"] = im.get_item_rect()
        im.same_line()
        if action_button("help"):
            self.help_window.show()
        self.item_rects["help"] = im.get_item_rect()
        im.same_line()
        if action_button("guide"):
            self.start_guide()
        self.item_rects["guide"] = im.get_item_rect()

    def start_guide(self) -> None:
        """Start the tour this window is for: its launcher's chimol tour, else the viewer's general one."""
        if self._guide_command and self._ensure_chimol() and self._chimol_app is not None:
            try:
                self._chimol_app.cmd.do(self._guide_command)
            except Exception:  # noqa: BLE001 - fall back to the general tour rather than a dead button
                logging.getLogger(__name__).exception("chimol guide command failed: %s", self._guide_command)
            else:
                self.request_frame()
                return
        self.tour.start()

    def load_example(self) -> bool:
        """Load the bundled T4 lysozyme (148l) into the viewer; whether a command ran."""
        if not self._ensure_chimol() or self._chimol_app is None:  # joins a start under way: a press is never dropped
            return False
        from chimol.plugins.demos.catalog import DEMO_DIR  # noqa: PLC0415

        try:
            path = DEMO_DIR / "148l.pdb"
            self._chimol_app.cmd.do(f'load "{path}"')
        except Exception as exc:  # noqa: BLE001 - a missing example is reported, not fatal
            self._error = f"{type(exc).__name__}: {exc}"
            return False
        self.request_frame()
        return True

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

    def _to_frame(self, x, y) -> tuple[float, float]:
        """Map a pointer position on the host onto chimol's frame.

        Below 760 x 446 the frame is rendered at the clamped size and the blit
        scales it into the window, so the host's coordinates are not chimol's:
        unmapped, a click in a narrow window picked the atom at the unscaled
        position and a drag rotated about the wrong point.
        """
        vx, vy, vw, vh = self.item_rects.get("viewport", (0.0, 0.0, *self._surface))
        sw, sh = self._surface
        return (
            (float(x) - vx) * sw / max(float(vw), 1.0),
            (float(y) - vy) * sh / max(float(vh), 1.0),
        )

    def pointer_press(self, x, y, button, modifiers=0, clicks=1):
        super().pointer_press(x, y, button, modifiers, clicks)
        if self._inside(x, y) and self._running():
            self._drag_from = (float(x), float(y))
            self._chimol.renderer.on_pointer_press(
                *self._to_frame(x, y), button, modifiers, double=clicks > 1
            )

    def pointer_move(self, x, y, buttons=0, modifiers=0):
        super().pointer_move(x, y, buttons, modifiers)
        if (self._drag_from is not None or self._inside(x, y)) and self._running():
            self._chimol.renderer.on_pointer_move(*self._to_frame(x, y), buttons, modifiers)
            if buttons and self._drag_from is not None:
                dx, dy = x - self._drag_from[0], y - self._drag_from[1]
                if dx * dx + dy * dy > 25.0:
                    self.tour.notify_used("viewport")

    def pointer_release(self, x, y, button, modifiers=0):
        super().pointer_release(x, y, button, modifiers)
        # A drag that began on the viewer ends there, wherever it is released.
        if (self._drag_from is not None or self._inside(x, y)) and self._running():
            self._chimol.renderer.on_pointer_release(*self._to_frame(x, y), button, modifiers)
        self._drag_from = None

    def wheel(self, x, y, steps, modifiers=0):
        super().wheel(x, y, steps, modifiers)
        if self._inside(x, y) and self._running():
            self._chimol.renderer.on_wheel(*self._to_frame(x, y), steps, modifiers)

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


def make_app(
    commands: tuple[str, ...] = (), guide_command: str = "", help_resource: Path | None = None
) -> ChimolHostApp:
    """The embedded viewer, speaking ChiSurf's language.

    :func:`chisurf.emtk.i18n.install` selects ChiSurf's configured language in
    :mod:`emtk.i18n`; chimol looks its own strings up there (domain
    ``"chimol"``), so the viewer's menus, toolbar, panels and feedback follow
    the host without being told twice -- and a live language switch in ChiSurf
    reaches the viewer on its next frame.
    """
    from chisurf.emtk.i18n import install

    install()
    return ChimolHostApp(
        commands=commands,
        guide_command=guide_command,
        help_resource=help_resource,
        ask_display_defaults=True,
    )
