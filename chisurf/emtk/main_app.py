"""The ChiSurf main window as one emtk surface (opt-in: ``python -m chisurf --emtk-shell``).

The Qt shell (``chisurf/gui/main.py``) stays the default while this surface grows to parity, one slice at a time;
the parity ledger and the slice order are in the OKF concept ``okf/subsystems/qt-retirement.md``.

What this slice provides:

* a **menu bar** built from the plugin manifests: ``display_name`` is the menu path (``"Spectroscopy:Correlation:FCS"``
  sits under *Spectroscopy*, group *Correlation*), ``menu_hidden`` plugins are left out, exactly as the Qt plugin
  menus read it;
* a **Tools** dock listing the same entries with a filter;
* every opened plugin as a **dock window** of one :class:`emtk.docking.DockManager` (tabs in the centre region by
  default; it can be floated, re-docked, split and closed like any dock). The plugin's own ``entrypoints.emtk`` app is
  made on a worker thread (:class:`~chisurf.emtk.background_build.BackgroundBuild`) and drawn into its window with
  :meth:`emtk.app.ImApp.draw_child`; pointer, wheel, key and file-drop events go to the plugin under the pointer;
* a **Log** dock showing the ``chisurf`` log records.

Plugins whose manifest declares only a Qt ``gui`` or an ``action`` entrypoint are not offered here yet.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

from emtk import im
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.i18n import tr

from chisurf.emtk.background_build import BackgroundBuild, draw_opening

#: Settings id of the shell's own layout and preferences (``<settings>/emtk/emtk_shell.*.json``).
SHELL_ID = "emtk_shell"
#: Height of the menu bar strip.
MENU_BAR = 30.0
#: Prefix of a hosted plugin's dock window key.
PLUGIN_KEY = "plugin."
#: How many log lines the Log dock keeps.
LOG_LINES = 500

_log = logging.getLogger("chisurf.emtk.shell")


@dataclass(frozen=True)
class MenuEntry:
    """One plugin the shell can open: its id and its menu path from ``display_name``."""

    plugin_id: str
    path: tuple[str, ...]
    description: str = ""
    experimental: bool = False
    deprecated: bool = False

    @property
    def label(self) -> str:
        """The item text: the last path segment."""
        return self.path[-1]

    @property
    def menu(self) -> str:
        """The top-level menu."""
        return self.path[0] if len(self.path) > 1 else tr("Plugins")

    @property
    def group(self) -> str:
        """The group inside the menu (the middle segments), ``""`` for none."""
        return " › ".join(self.path[1:-1])


def menu_entries(catalog: dict[str, dict] | None = None) -> list[MenuEntry]:
    """The visible native plugins of *catalog* (default: the shipped manifests), sorted by menu path.

    Parameters
    ----------
    catalog : dict, optional
        Manifests by plugin id, as :func:`chisurf.emtk.plugins.manifests` returns them.

    Returns
    -------
    list of MenuEntry
        Plugins with an ``entrypoints.emtk`` factory that are not ``menu_hidden``.
    """
    if catalog is None:
        from chisurf.emtk.plugins import manifests

        catalog = manifests()
    entries = []
    for plugin_id, data in catalog.items():
        if data.get("menu_hidden") or not (data.get("entrypoints") or {}).get("emtk"):
            continue
        name = str(data.get("display_name") or plugin_id)
        path = tuple(part.strip() for part in name.split(":") if part.strip()) or (plugin_id,)
        entries.append(
            MenuEntry(
                plugin_id,
                path,
                str(data.get("description") or "").strip().split("\n\n")[0],
                bool(data.get("experimental")),
                bool(data.get("deprecated")),
            )
        )
    return sorted(entries, key=lambda entry: tuple(part.casefold() for part in entry.path))


@dataclass
class HostedPlugin:
    """A plugin opened in the shell: its app once built, or the error that stopped it."""

    entry: MenuEntry
    app: Any = None
    error: str = ""
    build: BackgroundBuild | None = None
    #: The content box it was drawn into on the last frame (canvas coordinates), ``None`` when not shown.
    box: tuple[float, float, float, float] | None = None
    extra: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        """The dock window key."""
        return PLUGIN_KEY + self.entry.plugin_id


class _LogBuffer(logging.Handler):
    """Keep the last log records' text for the Log dock."""

    def __init__(self, lines: int = LOG_LINES) -> None:
        super().__init__(level=logging.INFO)
        self.lines: deque[str] = deque(maxlen=lines)
        self.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.lines.append(self.format(record))
        except Exception:  # noqa: BLE001 - a log handler must never raise into the caller
            self.handleError(record)


def _default_loader(plugin_id: str) -> Any:
    from chisurf.emtk.plugins import load_plugin

    return load_plugin(plugin_id)


class EmtkShellApp(ImApp):
    """The ChiSurf main window: menu bar, Tools / Log docks and every opened plugin as a dock window.

    Parameters
    ----------
    catalog : dict, optional
        Plugin manifests by id; the shipped ones by default.
    loader : callable, optional
        ``loader(plugin_id) -> app``; :func:`chisurf.emtk.plugins.load_plugin` by default (which binds the plugin's
        saved preferences and layouts). Runs on a worker thread.
    """

    def __init__(
        self,
        catalog: dict[str, dict] | None = None,
        loader: Callable[[str], Any] | None = None,
    ) -> None:
        self.entries = menu_entries(catalog)
        self.by_id = {entry.plugin_id: entry for entry in self.entries}
        self.loader = loader or _default_loader
        self.window_size = (1400, 900)
        self.item_rects: dict[str, tuple] = {}
        self.hosted: dict[str, HostedPlugin] = {}
        self.filter = ""
        self.status = tr("Ready")
        self._painter = None
        self._menu_open = False
        #: Plugin id holding the pointer since a press on it (gets the drag and the release).
        self._capture: str | None = None
        #: Plugin id that was pressed last (gets the keys).
        self._focus: str | None = None
        self.docks = DockManager(
            Split("h", 0.2, Region("left"), Split("v", 0.8, Region("center"), Region("bottom"))),
            name="shell",
        )
        self.docks.add_window("tools", tr("Tools"), self._draw_tools, dock="left", closable=False)
        self.docks.add_window("start", tr("Start"), self._draw_start, dock="center")
        self.docks.add_window("log", tr("Log"), self._draw_log, dock="bottom")
        self.log = _LogBuffer()
        logging.getLogger("chisurf").addHandler(self.log)
        _log.setLevel(logging.INFO)
        super().__init__(self.render)

    # ── plugins ───────────────────────────────────────────────────────────

    def open_plugin(self, plugin_id: str) -> HostedPlugin:
        """Open *plugin_id* as a dock window (or bring its window to front); the app is made on a worker thread."""
        if plugin_id in self.hosted:
            self.docks.show(self.hosted[plugin_id].key)
            self.docks.focus(self.hosted[plugin_id].key)
            return self.hosted[plugin_id]
        entry = self.by_id.get(plugin_id)
        if entry is None:
            raise KeyError(f"No native plugin {plugin_id!r} in the shell menus")
        hosted = HostedPlugin(entry)
        hosted.build = BackgroundBuild(wake=self.request_frame)
        loader = self.loader
        hosted.build.start(
            {plugin_id: lambda: loader(plugin_id)}, name=f"chisurf-shell-{plugin_id}"
        )
        self.hosted[plugin_id] = hosted
        self.docks.add_window(
            hosted.key,
            tr(entry.label),
            lambda box, pid=plugin_id: self._draw_plugin(pid, box),
            dock="center",
            scrollable=False,
            padding=0.0,
            min_size=(240.0, 160.0),
            tooltip=tr(entry.description),
        )
        self.docks.focus(hosted.key)
        self.status = tr("Opening {name}…").format(name=tr(entry.label))
        _log.info("open %s", plugin_id)
        return hosted

    def close_plugin(self, plugin_id: str) -> None:
        """Close the plugin's app and drop its window."""
        hosted = self.hosted.pop(plugin_id, None)
        if hosted is None:
            return
        if hosted.build is not None:
            results = hosted.build.collect(wait=True) or {}
            made, _error = results.get(plugin_id, (None, None))
            hosted.app = hosted.app or made
        close = getattr(hosted.app, "close", None)
        if callable(close):
            try:
                close()
            except Exception:  # noqa: BLE001 - one plugin failing to close must not take the shell down
                _log.exception("closing %s failed", plugin_id)
        self.docks.remove_window(hosted.key)
        if self._focus == plugin_id:
            self._focus = None
        if self._capture == plugin_id:
            self._capture = None

    def _collect_builds(self) -> None:
        for plugin_id, hosted in self.hosted.items():
            if hosted.build is None:
                continue
            results = hosted.build.collect()
            if results is None:
                continue
            hosted.build = None
            made, error = results.get(plugin_id, (None, None))
            if error is not None:
                hosted.error = f"{type(error).__name__}: {error}"
                _log.error("opening %s failed: %s", plugin_id, hosted.error)
                self.status = tr("{name} could not be opened.").format(name=tr(hosted.entry.label))
            else:
                hosted.app = made
                if hasattr(made, "set_frame_request_callback"):
                    made.set_frame_request_callback(self.request_frame)
                self.status = tr("{name} opened.").format(name=tr(hosted.entry.label))

    def _closed_by_user(self) -> None:
        """A plugin window closed with its ``×`` closes the plugin; one whose app asked to close closes too."""
        for plugin_id, hosted in list(self.hosted.items()):
            window = self.docks.window(hosted.key)
            if (window is not None and not window.visible) or getattr(
                hosted.app, "close_requested", False
            ):
                self.close_plugin(plugin_id)

    # ── one frame ─────────────────────────────────────────────────────────

    def draw(self, painter, x, y, w, h):
        self._painter = painter
        self._collect_builds()
        for hosted in self.hosted.values():
            hosted.box = None
        try:
            super().draw(painter, x, y, w, h)
        finally:
            self._painter = None
        self._closed_by_user()

    def render(self) -> None:
        width, height = im.get_main_viewport().size
        self._draw_menu_bar(width)
        self.docks.draw((0.0, MENU_BAR, width, max(1.0, height - MENU_BAR)))

    def _draw_menu_bar(self, width: float) -> None:
        im.set_next_window_pos((0.0, 0.0), im.Cond.ALWAYS)
        im.set_next_window_size((width, MENU_BAR), im.Cond.ALWAYS)
        self._menu_open = False
        flags = im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE
        if im.begin("shell menu bar", flags=flags):
            im.begin_menu_bar()
            menus: dict[str, list[MenuEntry]] = {}
            for entry in self.entries:
                menus.setdefault(entry.menu, []).append(entry)
            for menu, entries in menus.items():
                if im.begin_menu(tr(menu)):
                    self._menu_open = True
                    group = None
                    for entry in entries:
                        if entry.group != group and entry.group:
                            # A disabled row is the section caption; ``separator_text`` became a
                            # popup row only in emtk adee696, and this shell runs on older pins too.
                            im.menu_item(tr(entry.group), enabled=False)
                        group = entry.group
                        if im.menu_item(tr(entry.label), selected=entry.plugin_id in self.hosted):
                            self.open_plugin(entry.plugin_id)
                    im.end_menu()
                self.item_rects["menu." + menu] = im.get_item_rect()
            if im.begin_menu(tr("Window")):
                self._menu_open = True
                for key, title in (("tools", "Tools"), ("start", "Start"), ("log", "Log")):
                    if im.menu_item(tr(title), selected=self.docks.is_visible(key)):
                        self.docks.toggle(key)
                if im.menu_item(tr("Reset layout")):
                    self.docks.reset()
                im.end_menu()
            self.item_rects["menu.Window"] = im.get_item_rect()
            im.end_menu_bar()
        im.end()

    # ── docks ─────────────────────────────────────────────────────────────

    def _draw_tools(self, box) -> None:
        changed, value = im.input_text_with_hint("##tool filter", self.filter, tr("Filter tools"))
        if changed:
            self.filter = value
        self.item_rects["tools.filter"] = im.get_item_rect()
        needle = self.filter.casefold().strip()
        menu = None
        for entry in self.entries:
            text = " ".join(entry.path).casefold()
            if needle and needle not in text and needle not in entry.plugin_id:
                continue
            if entry.menu != menu:
                im.separator_text(tr(entry.menu))
                menu = entry.menu
            label = tr(entry.label) if not entry.group else f"{tr(entry.group)} › {tr(entry.label)}"
            if entry.experimental:
                label = "⚠ " + label
            if im.selectable(f"{label}##{entry.plugin_id}", entry.plugin_id in self.hosted):
                self.open_plugin(entry.plugin_id)
            self.item_rects["tools." + entry.plugin_id] = im.get_item_rect()
            if entry.description:
                im.set_item_tooltip(tr(entry.description))

    def _draw_start(self, box) -> None:
        im.text_unformatted(tr("ChiSurf"))
        im.text_wrapped(
            tr(
                "Open a tool from the menu bar or the Tools panel. Every tool opens as a window that "
                "can be docked, tabbed, floated or closed."
            )
        )
        im.spacing()
        im.text_disabled(self.status)
        self.item_rects["status"] = im.get_item_rect()

    def _draw_log(self, box) -> None:
        for line in list(self.log.lines)[-200:]:
            im.text_unformatted(line)

    def _draw_plugin(self, plugin_id: str, box) -> None:
        hosted = self.hosted.get(plugin_id)
        if hosted is None:
            return
        x, y, w, h = (float(v) for v in box)
        hosted.box = (x, y, max(1.0, w), max(1.0, h))
        if hosted.app is not None:
            painter = im.get_current_context().p
            self.draw_child(painter, hosted.app, *hosted.box, local_coordinates=True)
        elif hosted.error:
            im.text_wrapped(tr("The tool could not be opened."))
            im.text_wrapped(hosted.error)
            if im.button(tr("Retry") + f"##{plugin_id}"):
                self.close_plugin(plugin_id)
                self.open_plugin(plugin_id)
        else:
            draw_opening(tr(hosted.entry.label), hosted.box, f"shell opening {plugin_id}")

    # ── input: the plugin under the pointer gets it ───────────────────────

    def _plugin_at(self, x: float, y: float) -> str | None:
        """The plugin whose drawn content is on top at (x, y): floating windows front to back, then docked tabs."""
        if self._menu_open:
            return None
        order = list(reversed(self.docks.floating()))
        order += [self.docks.active_tab(region) for region in self.docks.regions]
        for key in order:
            if not key or not self.docks.is_shown(key):
                continue
            frame = self.docks.window(key).frame
            if frame is None or not (
                frame[0] <= x < frame[0] + frame[2] and frame[1] <= y < frame[1] + frame[3]
            ):
                continue
            if not key.startswith(PLUGIN_KEY):
                return None
            hosted = self.hosted.get(key[len(PLUGIN_KEY) :])
            if hosted is None or hosted.app is None or hosted.box is None:
                return None
            bx, by, bw, bh = hosted.box
            inside = bx <= x < bx + bw and by <= y < by + bh
            return hosted.entry.plugin_id if inside else None
        return None

    def _child(self, plugin_id: str | None):
        hosted = self.hosted.get(plugin_id) if plugin_id else None
        if hosted is None or hosted.app is None or hosted.box is None:
            return None, (0.0, 0.0)
        return hosted.app, hosted.box[:2]

    def pointer_press(self, x, y, button, modifiers=0, clicks=1):
        target = self._plugin_at(x, y)
        self._capture = target
        if target is not None:
            self._focus = target
        elif not self._menu_open:
            self._focus = None
        super().pointer_press(x, y, button, modifiers, clicks)
        child, (ox, oy) = self._child(target)
        if child is not None:
            child.pointer_press(x - ox, y - oy, button, modifiers, clicks)

    def pointer_release(self, x, y, button, modifiers=0):
        super().pointer_release(x, y, button, modifiers)
        child, (ox, oy) = self._child(self._capture)
        if child is not None:
            child.pointer_release(x - ox, y - oy, button, modifiers)
        self._capture = None

    def pointer_move(self, x, y, buttons=0, modifiers=0):
        super().pointer_move(x, y, buttons, modifiers)
        target = self._capture or self._plugin_at(x, y)
        child, (ox, oy) = self._child(target)
        if child is not None:
            child.pointer_move(x - ox, y - oy, buttons, modifiers)

    def wheel(self, x, y, steps, modifiers=0):
        child, (ox, oy) = self._child(self._plugin_at(x, y))
        if child is not None:
            child.wheel(x - ox, y - oy, steps, modifiers)
        else:
            super().wheel(x, y, steps, modifiers)

    def scroll(self, rows):
        child, _origin = self._child(self._focus)
        if child is not None:
            return child.scroll(rows)
        return super().scroll(rows)

    def key(self, key, text="", modifiers=0):
        child, _origin = self._child(self._focus)
        if child is not None:
            return child.key(key, text, modifiers)
        return super().key(key, text, modifiers)

    def on_files_dropped(self, paths) -> bool:
        """Hand dropped files to the focused plugin when it takes them."""
        child, _origin = self._child(self._focus)
        if child is None:
            return False
        for name in ("on_paths_dropped", "on_files_dropped", "files_dropped"):
            handler = getattr(child, name, None)
            if callable(handler):
                return handler(paths) is not False
        return False

    def animating(self) -> bool:
        busy = any(hosted.build is not None for hosted in self.hosted.values())
        children = any(
            hosted.app is not None and hosted.app.animating() for hosted in self.hosted.values()
        )
        return super().animating() or busy or children

    def next_frame_in(self):
        delays = [super().next_frame_in()]
        delays += [
            hosted.app.next_frame_in() for hosted in self.hosted.values() if hosted.app is not None
        ]
        return min((delay for delay in delays if delay is not None), default=None)

    # ── persistence ───────────────────────────────────────────────────────

    def export_settings(self) -> dict:
        """The plugins open in the shell, restored on the next start."""
        return {"open": list(self.hosted)}

    def restore_settings(self, state: dict) -> None:
        """Reopen the plugins that were open (each built on its worker thread)."""
        for plugin_id in (state or {}).get("open", []):
            if plugin_id in self.by_id:
                self.open_plugin(plugin_id)

    def close(self) -> None:
        """Close every hosted plugin and detach the log handler."""
        for plugin_id in list(self.hosted):
            self.close_plugin(plugin_id)
        logging.getLogger("chisurf").removeHandler(self.log)


def make_app(persist: bool = True) -> EmtkShellApp:
    """The shell app; with *persist* its dock layout, size and open plugins are kept between runs."""
    app = EmtkShellApp()
    if persist:
        from chisurf.emtk.state import attach_native_state

        attach_native_state(SHELL_ID, app)
    return app


def main(argv: list[str] | None = None) -> int:
    """Open the emtk shell in a native window (``python -m chisurf --emtk-shell``)."""
    from chisurf.emtk.i18n import install

    install(None)
    from emtk.native import main as run_native

    return int(
        run_native(["--app", "chisurf.emtk.main_app:make_app", "--title", "ChiSurf", *(argv or [])])
        or 0
    )


__all__ = ["EmtkShellApp", "HostedPlugin", "MenuEntry", "main", "make_app", "menu_entries"]
