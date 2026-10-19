"""The Terminal plugin's app: a toolbar of pane actions over the panes.

The app is the plugin's emtk entrypoint (``entrypoints.emtk`` in the
manifest): the shell opens it like any core plugin -- a dock window in the
centre region, listed in the menus, the ribbon and the Tools tree. Inside, it
is the tmux picture: a row of pane actions above the
:class:`~chisurf.plugins.core.terminal.workspace.TerminalWorkspace`'s panes
(tabs and splits and floating windows, all the dock manager's own).

The chords are the cmux/tmux ones: Ctrl/Cmd+T a new pane, Ctrl/Cmd+W close,
Ctrl+Tab the next pane. Sessions come from *session_factory* -- the real PTY
spawner in the shipped plugin (:func:`_default_session_factory`), a fake in
tests. A pane whose process exits stays (its screen keeps the output; the
control says *process exited*); a ``New`` brings the next one.

Windows (no ``pty`` module) gets a message instead of a session.
"""

from __future__ import annotations

import os
import pathlib
import shlex
import sys
from typing import Any, Callable

from emtk import im
from emtk.app import ImApp
from emtk.events import CONTROL_MODIFIER, SHIFT_MODIFIER
from emtk.i18n import tr
from emtk.keys import KEY_T, KEY_TAB, KEY_W, letter_of

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.plugins.emtk_layout import action_button

from .workspace import TerminalWorkspace

__all__ = ["TerminalApp", "make_app"]


def _default_session_factory():
    """A PTY session running the user's shell (POSIX)."""
    from .session import spawn  # POSIX only; the factory is not called on Windows

    shell = os.environ.get("SHELL") or "/bin/sh"
    argv = shlex.split(os.environ.get("CHISURF_TERMINAL_SHELL") or "") or [shell, "-i"]
    return spawn(argv)


def _pty_available() -> bool:
    try:
        import pty  # noqa: F401

        return True
    except ImportError:
        return False


class TerminalApp(ImApp):
    """The Terminal plugin: pane actions over the tmux-style workspace.

    Parameters
    ----------
    session_factory : callable, optional
        ``session_factory() -> session``; the shipped one spawns a PTY.
    """

    def __init__(
        self,
        session_factory: Callable[[], Any] | None = None,
        console_factory: Callable[[], Any] | None = None,
        first_kind: str = "shell",
        namespace: dict | None = None,
        initial_console: Any = None,
    ) -> None:
        self.window_size = (760, 480)
        self.session_factory = session_factory or _default_session_factory
        self.console_factory = console_factory
        self.default_kind = first_kind
        self.available = _pty_available()
        factory = self.session_factory if self.available else _no_session
        self.workspace = TerminalWorkspace(
            factory,
            console_factory=console_factory,
            wake=self.request_frame,
            namespace=namespace,
            initial_console=initial_console,
        )
        self.status = ""
        self._last_focus: str | None = None
        #: Named rectangles of the last frame's toolbar items (tests, tours).
        self.item_rects: dict[str, tuple] = {}
        self.native_layouts: dict = {}
        gui_dir = pathlib.Path(__file__).parent
        self.tour = EmTkGuidedTour(
            gui_dir / "guide.json",
            get_target_rect=self.item_rects.get,
            owner=self,
            wait_for_controls=True,
        )
        self.help_window = EmTkHelpWindow(
            title="Terminal - Help",
            resource=gui_dir / "help.md",
            owner=self,
            on_start_guide=self.tour.start,
        )
        super().__init__(gui=self._render, continuous=False)
        if first_kind == "python" or (self.available and first_kind == "shell"):
            self.workspace.new_pane(first_kind)
        self.request_frame()

    def set_frame_request_callback(self, callback) -> None:
        super().set_frame_request_callback(callback)
        if callback is not None:
            callback()

    # ── pane actions ──────────────────────────────────────────────────────

    def new_pane(self, kind: str | None = None):
        if kind is None:
            active = self.workspace.active
            kind = active.kind if active is not None else self.default_kind
        if kind == "python":
            pane = self.workspace.new_pane("python")  # works without a PTY
            self.request_frame()
            return pane
        if not self.available:
            self.status = tr("Terminal sessions need a POSIX pseudo-terminal.")
            self.request_frame()
            return None
        pane = self.workspace.new_pane("shell")
        self.request_frame()
        return pane

    def split_pane(self, zone: str, kind: str | None = None):
        if kind is None:
            active = self.workspace.active
            kind = active.kind if active is not None else self.default_kind
        if kind != "python" and not self.available:
            return None
        pane = self.workspace.split_active(zone, kind)
        self.request_frame()
        return pane

    def close_pane(self):
        active = self.workspace.active_key
        if active is not None:
            self.workspace.close(active)
            self.request_frame()

    def cycle_pane(self, step: int = 1):
        self.workspace.cycle(step)
        self.request_frame()

    # ── the frame contract ────────────────────────────────────────────────

    def animating(self) -> bool:
        return super().animating() or self.workspace.animating()

    def next_frame_in(self):
        if self.workspace.animating():
            return 0.016
        delay = super().next_frame_in()
        ws_delay = self.workspace.next_frame_in()
        delays = [d for d in (delay, ws_delay) if d is not None]
        if getattr(self, "_frame_request_callback", None) is None:
            # A manual embedding can pump output without mouse motion.
            return min(delays, default=0.1)
        return min(delays, default=None)

    def key(self, key, text="", modifiers=0):
        """The cmux chords: Ctrl/Cmd+T new, +W close, Tab/+Shift the next pane."""
        if modifiers & CONTROL_MODIFIER:
            if key == KEY_T or letter_of(key, text) == "t":
                self.new_pane()
                return True
            if key == KEY_W or letter_of(key, text) == "w":
                self.close_pane()
                return True
            if key == KEY_TAB:
                self.cycle_pane(-1 if modifiers & SHIFT_MODIFIER else 1)
                return True
        handled = super().key(key, text, modifiers)
        if handled:
            return True
        active = self.workspace.active
        if active is not None and callable(getattr(active.control, "key", None)):
            res = active.control.key(key, text, modifiers)
            if res:
                self.request_frame()
            return res
        return False

    # ── drawing ───────────────────────────────────────────────────────────

    def _render(self) -> None:
        self._draw_body()
        vp = im.get_main_viewport()
        self.help_window.draw((0.0, 0.0, vp.size[0], vp.size[1]))
        self.tour.draw(*vp.size)

    def _draw_body(self) -> None:
        viewport = im.get_main_viewport()
        width, height = viewport.size
        self._toolbar(width)
        box = (0.0, self._toolbar_h, width, max(1.0, height - self._toolbar_h))
        if not self.workspace.panes:
            if not self.available:
                self._draw_unavailable(box)
            else:
                self._draw_empty(box)
            return
        if self.workspace.poll_closed_windows():
            self.request_frame()
        for pane in self.workspace.panes.values():
            if pane.kind == "python" and hasattr(pane.console, "poll"):
                pane.console.poll()
        active = self.workspace.active_key
        if active != self._last_focus:
            # The focus moved by a tab click: keep active_key in step.
            self._last_focus = active
            active_pane = self.workspace.panes.get(active) if active is not None else None
            if active_pane and active_pane.kind == "python":
                active_pane.console.focus_input()
        self.workspace.docks.draw(box)
        for pane in self.workspace.panes.values():
            if pane.kind == "python" and hasattr(pane.console, "draw_overlays"):
                pane.console.draw_overlays(box)

    def _toolbar(self, width: float) -> None:
        self._toolbar_h = im.get_frame_height() + 6.0
        im.begin(
            "##terminal toolbar",
            (0.0, 0.0, width, self._toolbar_h),
            im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE,
        )
        if im.small_button(tr("New") + "##term_new"):
            self.new_pane()
            self.tour.notify_used("new")
        self.item_rects["new"] = im.get_item_rect()
        im.set_item_tooltip(tr("Open a new pane") + " (Ctrl+T)")
        im.same_line()
        if self.default_kind == "python":
            if im.small_button(tr("Terminal") + "##term_shell"):
                self.new_pane("shell")
            self.item_rects["shell"] = im.get_item_rect()
            im.set_item_tooltip(tr("Open a terminal CLI pane"))
            im.same_line()
            if im.small_button(tr("Python") + "##term_python"):
                self.new_pane("python")
            self.item_rects["python"] = im.get_item_rect()
            im.set_item_tooltip(tr("Open a Python console pane (the built-in console engine)"))
        else:
            if im.small_button(tr("Python") + "##term_python"):
                self.new_pane("python")
            self.item_rects["python"] = im.get_item_rect()
            im.set_item_tooltip(tr("Open a Python console pane (the built-in console engine)"))
        im.same_line()
        if im.small_button(tr("Split ⇥") + "##term_split_h"):
            self.split_pane("right")
            self.tour.notify_used("split_right")
        self.item_rects["split_right"] = im.get_item_rect()
        im.set_item_tooltip(tr("Split the active pane side by side"))
        im.same_line()
        if im.small_button(tr("Split ⇣") + "##term_split_v"):
            self.split_pane("down")
            self.tour.notify_used("split_down")
        self.item_rects["split_down"] = im.get_item_rect()
        im.set_item_tooltip(tr("Split the active pane stacked"))
        im.same_line()
        if im.small_button(tr("Close") + "##term_close"):
            self.close_pane()
            self.tour.notify_used("close")
        self.item_rects["close"] = im.get_item_rect()
        im.set_item_tooltip(tr("Close the active pane") + " (Ctrl+W)")
        im.same_line()
        if action_button("guide"):
            self.tour.start()
        self.item_rects["guide"] = im.get_item_rect()
        im.same_line()
        if action_button("help"):
            self.help_window.show()
        self.item_rects["help"] = im.get_item_rect()
        if self.status:
            im.same_line()
            im.text(tr(self.status))
        im.end()

    def _draw_unavailable(self, box) -> None:
        im.begin("##terminal unavailable", box, im.WindowFlags.NO_TITLE_BAR)
        im.text_wrapped(
            tr(
                "Terminal sessions need a POSIX pseudo-terminal; "
                "this platform has none."
            )
        )
        im.end()

    def _draw_empty(self, box) -> None:
        im.begin("##terminal empty", box, im.WindowFlags.NO_TITLE_BAR)
        im.text_disabled(tr("No open terminal panes. Click 'New' or 'Python' above."))
        im.end()

    # ── lifecycle ─────────────────────────────────────────────────────────

    def close(self) -> None:
        self.workspace.close_all()


def _no_session():
    """Never called: the factory the unavailable app builds panes with."""
    raise RuntimeError("no PTY on this platform")


def make_app(*, console_factory: Any = None, namespace: Any = None):
    """The plugin's emtk entrypoint factory."""
    from chisurf.emtk.i18n import install

    install()
    return TerminalApp(console_factory=console_factory, namespace=namespace)


def make_console_app(
    *,
    console_factory: Any = None,
    namespace: Any = None,
    initial_console: Any = None,
):
    """The Python-console entrypoint: the same app, a Python pane first.

    The built-in console as a terminal pane: the tmux panes (tabs, splits,
    floating) around ChiSurf's own console engine.
    """
    from chisurf.emtk.i18n import install

    install()
    return TerminalApp(
        first_kind="python",
        console_factory=console_factory,
        namespace=namespace,
        initial_console=initial_console,
    )
