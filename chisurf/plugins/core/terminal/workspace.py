"""The terminal workspace: tmux-style panes on an emtk dock manager.

One :class:`emtk.docking.DockManager` is the workspace; each terminal session
is one of its windows. That alone gives the cmux/tmux behaviour ChiSurf's
single console lacked:

* **tabs** -- several panes docked in the same region show as tabs;
* **split panes** -- :meth:`new_pane` tabs beside the active pane,
  :meth:`split_active` calls the dock manager's ``split_region`` first, so the
  new pane lands in a region of its own (side by side for ``"right"``, stacked
  for ``"down"``), draggable into any other region or out to float;
* **floating** -- a pane dragged out of its region floats, and can be docked
  back anywhere (all of it is the dock manager's own dragging machinery).

The workspace owns the panes' lifecycle: it numbers them in creation order,
focuses the new pane, kills its session on close, prunes empty regions, and
cycles focus. Sessions are made by *session_factory* (a real PTY in the app;
a fake in tests), so the layout logic is testable without processes.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any, Callable

from emtk.docking import DockManager, Region

from .control import TerminalControl

__all__ = ["Pane", "TerminalWorkspace"]

_SPLITS = {"right": "right", "down": "bottom"}

#: How a pane's session is made: a real PTY (``"shell"``) or the built-in
#: Python console engine (``"python"``) behind the same seam.
KINDS = ("shell", "python")


@dataclass
class Pane:
    """One terminal pane: its session/console, its control, its dock window key."""

    key: str
    title: str
    session: Any
    control: Any
    kind: str = "shell"
    #: Bumped when the pane's dock window is closed by hand (the ×).
    closed_by_user: bool = field(default=False)

    @property
    def console(self) -> Any:
        """The ShellConsole instance when this is a python pane, else None."""
        return self.session if self.kind == "python" else None


def default_console_factory(
    wake: Callable[[], None] | None = None,
    namespace: dict | None = None,
    history_path: Any = None,
    session_file: Any = None,
):
    """Build a ShellConsole seeded with the active shell's namespace (gui + api)."""
    from chisurf.emtk.console import ShellConsole
    from chisurf.emtk.main_app import _ACTIVE_SHELL

    user_ns: dict[str, Any] = {}
    try:
        import chisurf

        user_ns["cs"] = chisurf
    except Exception:
        pass
    try:
        import numpy as np

        user_ns["np"] = np
    except Exception:
        pass
    import os

    user_ns["os"] = os

    shell = _ACTIVE_SHELL() if _ACTIVE_SHELL is not None else None
    if shell is not None:
        user_ns["gui"] = shell
        session = getattr(shell, "data", None) and getattr(shell.data, "session", None)
        if session is not None:
            api = getattr(session, "api", None)
            if getattr(session, "server", None) is not None:
                from chisurf.emtk.shell_session import ProjectChannel

                try:
                    chan = ProjectChannel(session)
                    api = chan.api
                except Exception:
                    pass
            user_ns["api"] = api
    if "api" not in user_ns:
        try:
            from chisurf.core.api import ChiSurfAPI

            api = ChiSurfAPI.instance(create=False)
            if api is not None:
                user_ns["api"] = api
        except Exception:
            pass
    if namespace:
        user_ns.update(namespace)

    return ShellConsole(
        user_ns,
        history_path=history_path,
        session_file=session_file,
        wake=wake,
    )


class TerminalWorkspace:
    """The panes, their layout and their focus.

    Parameters
    ----------
    session_factory : callable
        ``session_factory() -> session``; the engine seam the control draws
        (a real :func:`~chisurf.plugins.core.terminal.session.spawn` in the
        app, a fake in tests).
    console_factory : callable, optional
        ``console_factory() -> ShellConsole``; builds a Python console pane.
    max_scrollback : int
        Lines of history a pane keeps.
    wake : callable, optional
        Wakes the host app when frame updates are requested.
    namespace : dict, optional
        Variables to seed into new console panes.
    """

    def __init__(
        self,
        session_factory: Callable[[], Any],
        console_factory: Callable[[], Any] | None = None,
        max_scrollback: int = 2000,
        wake: Callable[[], None] | None = None,
        namespace: dict | None = None,
        initial_console: Any = None,
    ) -> None:
        self.session_factory = session_factory
        self.wake = wake
        self.namespace = namespace
        self.initial_console = initial_console
        self.console_factory = console_factory or self._default_console_factory
        self.max_scrollback = max_scrollback
        root = Region("root", keep=False)
        root._dynamic = True
        self.docks = DockManager(root, name="terminal")
        #: The panes, in creation order (their titles number them).
        self.panes: dict[str, Pane] = {}
        self._counter = itertools.count(1)
        self._active_key: str | None = None

    def _default_console_factory(self):
        return default_console_factory(wake=self.wake, namespace=self.namespace)

    # ── pane lifecycle ────────────────────────────────────────────────────

    def new_pane(self, kind: str | None = None) -> Pane:
        """Open a pane: a tab after the active pane's tab.

        *kind* is ``"shell"`` (a PTY, the default) or ``"python"`` (the
        built-in console engine behind the same seam). When omitted, it
        inherits the kind of the active pane.
        """
        if kind is None:
            active = self.active
            kind = active.kind if active is not None else "shell"
        return self._make_pane(kind, dock=self._focus_region())

    def split_active(self, zone: str, kind: str | None = None) -> Pane:
        """Split the active pane's region *zone*-wards ('right' or 'down')."""
        if zone not in _SPLITS:
            raise ValueError(f"split zone must be 'right' or 'down', not {zone!r}")
        if kind is None:
            active = self.active
            kind = active.kind if active is not None else "shell"
        region = self._focus_region()
        if region is None:
            return self.new_pane(kind)
        target_node = self.docks.regions.get(region)
        if target_node is not None:
            target_node.keep = False
            target_node._dynamic = True
        new_region = self.docks.split_region(region, _SPLITS[zone])
        return self._make_pane(kind, dock=new_region)

    def _make_pane(self, kind: str, dock: str | None) -> Pane:
        number = next(self._counter)
        key = f"term.{number}"
        if kind == "python":
            if self.initial_console is not None and not self.panes:
                console = self.initial_console
            else:
                console = self.console_factory()
            control = console.control
            session = console
            console.focus_input()
        else:
            session = self.session_factory()
            control = TerminalControl(session)
        pane = Pane(key=key, title=str(number), session=session, control=control, kind=kind)
        self.panes[key] = pane
        self.docks.add_window(
            key,
            ("🐍 " if kind == "python" else "▮ ") + str(number),
            self._draw_pane(key),
            dock=dock,
            closable=True,
            scrollable=False,
            padding=0.0,
            min_size=(200.0, 120.0),
        )
        self.docks.focus(key)
        self.active_key = key
        if self.wake is not None:
            self.wake()
        return pane

    def _draw_pane(self, key: str) -> Callable:
        def draw(box) -> None:
            from emtk import im

            pane = self.panes.get(key)
            if pane is None:
                return
            if pane.kind == "python":
                pane.console.draw(box, control_id=f"##{key}", show_toolbar=False)
            else:
                im.host_control(f"##{key}", pane.control, size=None)

        return draw

    # ── focus ─────────────────────────────────────────────────────────────

    @property
    def active_key(self) -> str | None:
        focused = self.docks.focused
        if focused and focused in self.panes:
            return focused
        # The tab on top of the home region of the fallback key, else the
        # stored fallback -- read WITHOUT re-entering this property (the
        # region lookup must not recurse through active_key again).
        active = self._active_key
        region = self.docks.region_of(active) if active else None
        if not region or region not in self.docks.tabs:
            region = next(iter(self.docks.tabs), None)
        if region is not None:
            tab = self.docks.active_tab(region)
            if tab and tab in self.panes:
                return tab
        return active

    @active_key.setter
    def active_key(self, key: str | None) -> None:
        self._active_key = key
        if key in self.panes:
            self.docks.focus(key)
            pane = self.panes[key]
            if pane.kind == "python":
                pane.console.focus_input()

    @property
    def active(self) -> Pane | None:
        return self.panes.get(self.active_key)

    def focus(self, key: str) -> None:
        """Focus a pane (its tab on top, or its floating window raised)."""
        if key in self.panes:
            self.docks.focus(key)
            self.active_key = key
            pane = self.panes[key]
            if pane.kind == "python":
                pane.console.focus_input()
            if self.wake is not None:
                self.wake()

    def cycle(self, step: int = 1) -> str | None:
        """Focus the next pane (``step=-1``: the previous)."""
        keys = list(self.panes)
        if not keys:
            return None
        current = self.active_key
        index = keys.index(current) if current in keys else (-1 if step > 0 else 0)
        key = keys[(index + (1 if step > 0 else -1)) % len(keys)]
        self.focus(key)
        return key

    def _focus_region(self) -> str | None:
        active = self.active_key
        if active is not None:
            region = self.docks.region_of(active)
            if region and region in self.docks.regions:
                return region
        return next(iter(self.docks.regions), "root")

    # ── closing ───────────────────────────────────────────────────────────

    def close(self, key: str) -> None:
        """Close a pane: kill its session, drop its window, prune the layout."""
        pane = self.panes.pop(key, None)
        if pane is None:
            return
        if pane.kind == "python":
            pane.console.close()
        else:
            pane.control.close()
        self.docks.remove_window(key)
        self.docks.prune_empty()
        if not self.panes:
            root = Region("root", keep=False)
            root._dynamic = True
            self.docks.layout = root
            self.docks._reindex()
            self._active_key = None
        elif self._active_key == key:
            self._active_key = None
            remaining = list(self.panes)
            if remaining:
                self.focus(remaining[-1])
        if self.wake is not None:
            self.wake()

    def close_all(self) -> None:
        for key in list(self.panes):
            self.close(key)

    # ── the frame contract ────────────────────────────────────────────────

    def animating(self) -> bool:
        """Whether any pane has undrawn output: the host keeps drawing frames."""
        return any(
            pane.control.animating()
            for pane in self.panes.values()
            if hasattr(pane.control, "animating")
        )

    def next_frame_in(self) -> float | None:
        delays = [
            pane.control.next_frame_in()
            for pane in self.panes.values()
            if hasattr(pane.control, "next_frame_in")
        ]
        delays = [d for d in delays if d is not None]
        return min(delays, default=None)

    def poll_closed_windows(self) -> bool:
        """Adopt panes whose dock window the user closed with its ``×``.

        Returns whether anything changed (the caller draws another frame).
        """
        changed = False
        for key, pane in list(self.panes.items()):
            window = self.docks.window(key)
            if window is not None and not window.visible:
                self.close(key)
                changed = True
        return changed
