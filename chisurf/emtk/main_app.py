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
* a **Log** dock showing the ``chisurf`` log records;
* the **Read data**, **Datasets**, **Analysis** and **Plot settings** docks and one dock window per fit
  (:mod:`chisurf.emtk.fit_docks`), working through :class:`chisurf.core.api.ChiSurfAPI` against an in-process
  server whose events arrive through a Qt-free subscriber (:mod:`chisurf.emtk.session`). A file dropped onto the
  shell, with no tool taking it, is read with the selected file type.
* the **session menus** -- *File* (datasets, project files, fits, recent projects, quit), *View* (docks, window
  arrangements, undo and redo), *Macro* (record, run) and *Settings* -- with the Qt shell's shortcuts, the project
  dialogs, the unsaved-changes guard on close and the autosave (:mod:`chisurf.emtk.shell_session`);
* the **Console** dock: ChiSurf's Python console on emtk's TextEditor (:mod:`chisurf.emtk.console`), which is
  also where ``chisurf.run(...)`` runs while the shell is open.

Anything drawn inside a dock by an app of its own (a plugin, a fit window, a reader's settings) is a *child*: it is
drawn with :meth:`emtk.app.ImApp.draw_child` through :meth:`EmtkShellApp.host_child`, and the pointer, wheel, keys
and dropped files go to the child under the pointer (keys to the one pressed last).

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
from chisurf.emtk.shell_session import MenuAction, ShellProject

#: Settings id of the shell's own layout and preferences (``<settings>/emtk/emtk_shell.*.json``).
SHELL_ID = "emtk_shell"
#: Height of the menu bar strip.
MENU_BAR = 30.0
#: Prefix of a hosted plugin's dock window key.
PLUGIN_KEY = "plugin."
#: How many log lines the Log dock keeps.
LOG_LINES = 500

_log = logging.getLogger("chisurf.emtk.shell")


def parse_shortcut(text: str) -> tuple[int, int] | None:
    """``"Ctrl+Shift+S"`` as ``(key, modifiers)`` of :mod:`emtk.keys` / :mod:`emtk.events`.

    ``Ctrl`` is Command on a Mac (emtk swaps them, as Qt does).
    """
    from emtk.events import ALT_MODIFIER, CONTROL_MODIFIER, SHIFT_MODIFIER

    if not text:
        return None
    *mods, key = [part.strip() for part in text.split("+")]
    bits = {"ctrl": CONTROL_MODIFIER, "shift": SHIFT_MODIFIER, "alt": ALT_MODIFIER}
    modifiers = 0
    for mod in mods:
        modifiers |= bits[mod.lower()]
    return (ord(key.lower()) if len(key) == 1 else 0), modifiers


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
    session_factory : callable, optional
        ``session_factory(wake=...) -> ShellSession`` (:func:`chisurf.emtk.session.start_session`), run on a
        worker thread; without one the data and fit docks say there is no session.
    console_history, console_session_file : path or bool, optional
        The console's input-history file and session log (:class:`~chisurf.emtk.console.ShellConsole`);
        ``None`` uses the settings folder, ``False`` keeps none (tests).
    """

    def __init__(
        self,
        catalog: dict[str, dict] | None = None,
        loader: Callable[[str], Any] | None = None,
        session_factory: Callable[..., Any] | None = None,
        console_history: Any = None,
        console_session_file: Any = None,
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
        #: Child holding the pointer since a press on it (gets the drag and the release).
        self._capture: str | None = None
        #: Child that was pressed last (gets the keys).
        self._focus: str | None = None
        #: The children drawn in the last frame: child id -> (dock window key, app, box).
        self._drawn: dict[str, tuple[str, Any, tuple[float, float, float, float]]] = {}
        self.docks = DockManager(
            Split(
                "h",
                0.27,
                Split("v", 0.5, Region("left"), Region("left_lower")),
                Split("v", 0.8, Region("center"), Region("bottom")),
            ),
            name="shell",
        )
        self.docks.add_window("tools", tr("Tools"), self._draw_tools, dock="left", closable=False)
        self.docks.add_window("start", tr("Start"), self._draw_start, dock="center")
        self.docks.add_window("log", tr("Log"), self._draw_log, dock="bottom")
        self.docks.add_window("console", tr("Console"), self._draw_console, dock="bottom",
                              scrollable=False)
        self.log = _LogBuffer()
        logging.getLogger("chisurf").addHandler(self.log)
        _log.setLevel(logging.INFO)
        super().__init__(self.render)
        from chisurf.emtk.fit_docks import ANALYSIS_KEY, PLOT_KEY, DataDocks

        self.data = DataDocks(self, session_factory)
        self.project = ShellProject(self)
        from chisurf.emtk.console import ShellConsole

        self.console = ShellConsole(
            {"gui": self},
            history_path=console_history,
            session_file=console_session_file,
            wake=self.request_frame,
            record_command=self.project.note_command,
        )
        self._console_session: Any = None
        self._console_channel: Any = None
        self._push_console_namespace()
        self.console.install()
        for key in (ANALYSIS_KEY, PLOT_KEY):
            self.docks.dock(key, "left_lower")
        self.docks.focus(ANALYSIS_KEY)
        self.docks.focus("tools")
        self.docks.focus("console")

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
        self._drawn.pop(hosted.key, None)
        if self._focus == hosted.key:
            self._focus = None
        if self._capture == hosted.key:
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
        self.data.poll()
        self.project.poll()
        self.console.poll()
        self._push_console_namespace()
        for hosted in self.hosted.values():
            hosted.box = None
        self._drawn = {}
        try:
            super().draw(painter, x, y, w, h)
        finally:
            self._painter = None
        self._closed_by_user()
        self.project.guard_fit_windows()
        self.data.closed_by_user()
        self.data.focused_window()

    def render(self) -> None:
        width, height = im.get_main_viewport().size
        self._draw_menu_bar(width)
        self.docks.draw((0.0, MENU_BAR, width, max(1.0, height - MENU_BAR)))
        self.data.draw_file_dialog((0.0, 0.0, width, height))
        self.console.draw_overlays((0.0, 0.0, width, height))
        self.project.draw((0.0, 0.0, width, height))

    def host_child(self, window_key: str, child_id: str, app: Any, box) -> None:
        """Draw *app* into *box* (canvas coordinates) of dock window *window_key*; input over it goes to it.

        Called from a dock's draw callback. *child_id* names the child for focus and capture (a plugin's or a fit
        window's dock key, ``reader.<n>`` for a reader's settings).
        """
        x, y, w, h = (float(v) for v in box)
        box = (x, y, max(1.0, w), max(1.0, h))
        painter = im.get_current_context().p
        self.draw_child(painter, app, *box, local_coordinates=True)
        self._drawn[child_id] = (window_key, app, box)

    def _draw_menu_bar(self, width: float) -> None:
        im.set_next_window_pos((0.0, 0.0), im.Cond.ALWAYS)
        im.set_next_window_size((width, MENU_BAR), im.Cond.ALWAYS)
        self._menu_open = False
        flags = im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE
        if im.begin("shell menu bar", flags=flags):
            im.begin_menu_bar()
            plugins: dict[str, list[MenuEntry]] = {}
            for entry in self.entries:
                plugins.setdefault(tr(entry.menu), []).append(entry)
            session = self.session_menus()
            # File first, then the plugin menus, then View and Settings, as the Qt menu bar; a plugin
            # menu with a session menu's title (the File tools under "File") joins that menu.
            order = [session[0]] + [(menu, []) for menu in plugins if menu not in dict(session)]
            order += session[1:]
            for menu, actions in order:
                if im.begin_menu(menu):
                    self._menu_open = True
                    self._draw_actions(actions)
                    self._draw_plugin_entries(plugins.get(menu, []))
                    im.end_menu()
                self.item_rects["menu." + menu] = im.get_item_rect()
            im.end_menu_bar()
        im.end()

    def _draw_actions(self, actions: list[MenuAction]) -> None:
        """The items of a session menu: group captions, shortcut texts, check marks."""
        group = None
        for action in actions:
            if action.group != group:
                # A group is a captioned section (Qt's submenus: Project, Fits, Recent Projects, Docks).
                if action.group:
                    im.separator_text(action.group)
                elif group:
                    im.separator()
            group = action.group
            selected = bool(action.checked()) if action.checked is not None else False
            if im.menu_item(action.label, action.shortcut, selected=selected, enabled=action.enabled()):
                action.run()
            self.item_rects[f"menu.{action.key}"] = im.get_item_rect()
            if action.description:
                im.set_item_tooltip(action.description)

    def _draw_plugin_entries(self, entries: list[MenuEntry]) -> None:
        """The plugins of one menu, grouped under disabled caption rows."""
        group = None
        for entry in entries:
            if entry.group != group and entry.group:
                # A disabled row is the section caption; ``separator_text`` became a
                # popup row only in emtk adee696, and this shell runs on older pins too.
                im.menu_item(tr(entry.group), enabled=False)
            group = entry.group
            if im.menu_item(tr(entry.label), selected=entry.plugin_id in self.hosted):
                self.open_plugin(entry.plugin_id)

    # ── session menus ─────────────────────────────────────────────────────

    def session_menus(self) -> list[tuple[str, list[MenuAction]]]:
        """*File*, *View* and *Settings* as ``(title, [MenuAction])``; the shortcut table is read from them."""
        project, data = self.project, self.data
        has_session = lambda: project.channel is not None  # noqa: E731
        has_fits = lambda: bool(data.datasets.fits)  # noqa: E731
        file_menu = [
            MenuAction("add_dataset", tr("Add dataset"), data.read.load, "Ctrl+N",
                       description=tr("Read the file in Read data with the selected file type."),
                       enabled=lambda: data.session is not None),
            MenuAction("save_project", tr("Save Project"), project.save, "Ctrl+S", tr("Project"),
                       tr("Save the project to its file, or choose one."), has_session),
            MenuAction("export_project", tr("Export Project…"), project.save_as, "Ctrl+Shift+S",
                       tr("Project"), tr("Save the project under a new .cs.pto file (save as)."),
                       has_session),
            MenuAction("open_project", tr("Open Project…"), project.open_project, "", tr("Project"),
                       tr("Replace the session with a saved project."), has_session),
            MenuAction("import_project", tr("Import Project…"), project.import_project, "",
                       tr("Project"), tr("Open a .cs.pto, or import a copy into the database."),
                       has_session),
            MenuAction("close_fit", tr("Close Fit"), project.close_fit, "", tr("Fits"),
                       tr("Remove the current fit (asks first)."),
                       lambda: bool(data.current_uid)),
            MenuAction("close_all_fits", tr("Close all fits"), project.close_all_fits, "", tr("Fits"),
                       tr("Remove every fit from the session."), has_fits),
            MenuAction("close_project", tr("Close Project"), project.close_project, "", "",
                       tr("Start an empty session (asks to save unsaved work)."), has_session),
            MenuAction("reinitialize", tr("Reinitialize"),
                       lambda: project.close_project(reinitialize=True), "Ctrl+R", "",
                       tr("Clear all data and start again (asks to save unsaved work)."), has_session),
        ]
        recent = [
            MenuAction(f"recent.{index}", f"{index + 1} {path}",
                       lambda p=path: project.open_recent(p), "", tr("Recent Projects"),
                       enabled=has_session)
            for index, path in enumerate(project.recent)
        ] or [MenuAction("recent.none", tr("No recent projects"), lambda: None, "",
                         tr("Recent Projects"), enabled=lambda: False)]
        file_menu += recent
        file_menu += [
            MenuAction("clear_recent", tr("Clear Recent Projects"), project.clear_recent, "",
                       tr("Recent Projects"), enabled=lambda: bool(project.recent)),
            MenuAction("quit", tr("Quit"), project.request_quit, "Ctrl+Q", "",
                       tr("Close ChiSurf (asks to save unsaved work).")),
        ]
        docks = [
            ("data.read", tr("Read data")), ("data.sets", tr("Datasets")),
            ("fit.analysis", tr("Analysis")), ("fit.plot", tr("Plot settings")), ("tools", tr("Tools")),
            ("start", tr("Start")), ("log", tr("Log")), ("console", tr("Console")),
        ]
        view_menu = [
            MenuAction(f"dock.{key}", title, lambda k=key: self.docks.toggle(k), "", tr("Docks"),
                       checked=lambda k=key: self.docks.is_visible(k))
            for key, title in docks
        ]
        view_menu += [
            MenuAction("tile_windows", tr("Tile Windows"), self.tile_fit_windows, "", "",
                       tr("Show every fit window side by side."), has_fits),
            MenuAction("tab_windows", tr("Tab Windows"), self.tab_fit_windows, "", "",
                       tr("Show the fit windows as tabs."), has_fits),
            MenuAction("cascade_windows", tr("Cascade Fit Windows"), self.cascade_fit_windows, "", "",
                       tr("Float the fit windows, each a little below the last."), has_fits),
            MenuAction("reset_layout", tr("Reset layout"), self.docks.reset, "", "",
                       tr("Put every dock back where it started.")),
            MenuAction("undo", tr("Undo"), project.undo, "Ctrl+Z", "",
                       tr("Go back one change of the science."), project.can_undo),
            MenuAction("redo", tr("Redo"), project.redo, "Ctrl+Y", "",
                       tr("Go forward one change of the science."), project.can_redo),
        ]
        settings_menu = [
            MenuAction("settings_edit", tr("Edit"), project.edit_settings, "", "",
                       tr("Open the settings editor."), lambda: "setup" in self.by_id),
            MenuAction("fret_rda_axis", tr("FRET RDA axis…"), project.rda_axis, "", "",
                       tr("The distance grid FRET models use.")),
            MenuAction("data_loading", tr("Data loading…"), project.data_loading, "", "",
                       tr("Staging of files on slow storage, and the plot point budget.")),
            MenuAction("reset_local_settings", tr("Reset local settings"),
                       project.reset_local_settings, "", "",
                       tr("Return your settings folder to the shipped defaults.")),
            MenuAction("clear_logging_files", tr("Clear logging files"),
                       project.clear_logging_files),
            MenuAction("clear_user_styles", tr("Clear user styles"), project.clear_user_styles),
            MenuAction("clear_user_plugins", tr("Clear user plugins"), project.clear_user_plugins),
        ]
        macro_menu = [
            MenuAction("record", tr("Record"), self.toggle_macro_recording, "", "",
                       tr("Record what runs in the console; click again to stop and save it as a macro."),
                       checked=lambda: self.console.recording),
            MenuAction("run_macro", tr("Run Macro…"), self.run_macro, "", "",
                       tr("Run a saved macro (.cm.py) in the console's namespace.")),
        ]
        return [(tr("File"), file_menu), (tr("View"), view_menu), (tr("Macro"), macro_menu),
                (tr("Settings"), settings_menu)]

    # ── console and macros ────────────────────────────────────────────────

    def _push_console_namespace(self) -> None:
        """Give the console ``api`` once the session is up (and again after it was replaced)."""
        import os

        import numpy as np

        import chisurf

        session = getattr(self.data, "session", None)
        if session is self._console_session and self._console_session is not None:
            return
        names = {"cs": chisurf, "np": np, "os": os, "gui": self}
        self._close_console_channel()
        if session is not None:
            # A connection of the console's own: it calls on the frame thread, and a ZMQ socket
            # must not cross threads (the docks' calls run on workers).
            api = getattr(session, "api", None)
            if getattr(session, "server", None) is not None:
                from chisurf.emtk.shell_session import ProjectChannel

                try:
                    self._console_channel = ProjectChannel(session)
                    api = self._console_channel.api
                except Exception:  # noqa: BLE001 - the console still runs Python without ``api``
                    _log.exception("connecting the console to the session failed")
            names["api"] = api
        self.console.push(names)
        self._console_session = session

    def _close_console_channel(self) -> None:
        channel, self._console_channel = getattr(self, "_console_channel", None), None
        if channel is not None:
            channel.close()

    def toggle_macro_recording(self) -> None:
        """*Macro ▸ Record*: start recording the console; the second click stops and offers to save."""
        console = self.console
        if not console.recording:
            console.start_recording()
            self.docks.show("console")
            self.docks.focus("console")
            console.focus_input()
            self.status = tr("Recording macro…")
            return
        console.stop_recording()
        self.status = tr("Ready")
        if not console.macro.strip():
            self.project.dialogs.message(tr("Record macro"), tr("Nothing was recorded."))
            return
        from chisurf.emtk.console import MACRO_FILTER

        self.project.open_file_dialog(
            tr("Save macro"), "save", console.save_macro, filters=MACRO_FILTER, filename="macro.cm.py"
        )

    def run_macro(self) -> None:
        """*Macro ▸ Run Macro…*: choose a macro file and run it in the console."""
        from chisurf.emtk.console import MACRO_FILTER

        def run(path: str) -> None:
            self.docks.show("console")
            self.docks.focus("console")
            self.console.focus_input()
            self.console.run_file(path)

        self.project.open_file_dialog(tr("Run Macro"), "open", run, filters=MACRO_FILTER)

    def shortcuts(self) -> dict[tuple[int, int], MenuAction]:
        """``(key, modifiers) -> action`` of every session menu item with a shortcut."""
        table = {}
        for _menu, actions in self.session_menus():
            for action in actions:
                parsed = parse_shortcut(action.shortcut)
                if parsed is not None:
                    table[parsed] = action
        return table

    def _fit_window_keys(self) -> list[str]:
        return [window.key for window in self.data.windows.values()]

    def tab_fit_windows(self) -> None:
        """*Tab Windows*: every fit window a tab of the centre."""
        for key in self._fit_window_keys():
            self.docks.dock(key, "center")
            self.docks.show(key)

    def tile_fit_windows(self) -> None:
        """*Tile Windows*: the fit windows side by side, each in a region of its own."""
        keys = self._fit_window_keys()
        self.tab_fit_windows()
        region = "center"
        for index, key in enumerate(keys[1:], start=1):
            zone = "right" if index % 2 else "bottom"
            region = self.docks.split_region(region, zone, ratio=1.0 / (len(keys) - index + 1))
            self.docks.dock(key, region)

    def cascade_fit_windows(self) -> None:
        """*Cascade Fit Windows*: the fit windows float, each offset from the last."""
        width, height = self.window_size
        for index, key in enumerate(self._fit_window_keys()):
            offset = 40.0 + 28.0 * index
            self.docks.undock(key, (offset + 280.0, offset + MENU_BAR, width * 0.5, height * 0.5))
            self.docks.raise_window(key)

    def close_request(self) -> bool:
        """The window's close button: close only after the unsaved-changes question (asked once)."""
        return self.project.request_quit()

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
            im.set_item_tooltip(
                tr(entry.description) if entry.description else tr("Open {name}").format(name=label)
            )

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
        document = self.project.document
        where = str(document.path) if document.path else tr("not saved yet")
        im.text_disabled(tr("Project: {name} ({where})").format(name=document.name, where=where))
        self.item_rects["project"] = im.get_item_rect()
        if self.project.status:
            im.text_disabled(self.project.status)
            self.item_rects["project.status"] = im.get_item_rect()

    def _draw_console(self, box) -> None:
        self.console.draw(box)

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
            self.host_child(hosted.key, hosted.key, hosted.app, hosted.box)
        elif hosted.error:
            im.text_wrapped(tr("The tool could not be opened."))
            im.text_wrapped(hosted.error)
            retry = im.button(tr("Retry") + f"##{plugin_id}")
            im.set_item_tooltip(tr("Close the tool and open it again."))
            if retry:
                self.close_plugin(plugin_id)
                self.open_plugin(plugin_id)
        else:
            draw_opening(tr(hosted.entry.label), hosted.box, f"shell opening {plugin_id}")

    # ── input: the child under the pointer gets it ────────────────────────

    def _plugin_at(self, x: float, y: float) -> str | None:
        """The child whose drawn content is on top at (x, y): floating windows front to back, then docked tabs."""
        if self._menu_open or self.data.modal_open or self.project.modal:
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
            for child_id, (window_key, _app, box) in self._drawn.items():
                bx, by, bw, bh = box
                if window_key == key and bx <= x < bx + bw and by <= y < by + bh:
                    return child_id
            return None
        return None

    def _child(self, child_id: str | None):
        drawn = self._drawn.get(child_id) if child_id else None
        if drawn is None:
            return None, (0.0, 0.0)
        _window_key, app, box = drawn
        return app, box[:2]

    def pointer_press(self, x, y, button, modifiers=0, clicks=1):
        if self.project.modal and not self.project.contains(x, y):
            return  # a question is open: a press beside it does nothing (it is modal)
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
        if self.project.modal:
            return super().key(key, text, modifiers)
        child, _origin = self._child(self._focus)
        if self._shortcut(key, modifiers, child):
            return True
        if child is not None:
            return child.key(key, text, modifiers)
        return super().key(key, text, modifiers)

    def compose(self, text, cursor=None):
        """The input method's composition goes where the keys go: the focused child, else the shell."""
        if not self.project.modal:
            child, _origin = self._child(self._focus)
            if child is not None and callable(getattr(child, "compose", None)):
                return child.compose(text, cursor)
        return super().compose(text, cursor)

    def ime_caret(self):
        """The caret of the focused text, in the shell's coordinates (a child's is offset by its box)."""
        child, (ox, oy) = self._child(self._focus)
        caret = getattr(child, "ime_caret", None) if child is not None else None
        caret = caret() if callable(caret) else caret
        if caret is not None:
            return (caret[0] + ox, caret[1] + oy, caret[2])
        return super().ime_caret()

    def _shortcut(self, key, modifiers, child) -> bool:
        """Run the session menu item bound to this key, as Qt's application-wide shortcuts do.

        Undo and redo are left to a text field that has the keyboard (its own undo), in the
        shell or in the focused child.
        """
        from emtk.events import ALT_MODIFIER, CONTROL_MODIFIER, SHIFT_MODIFIER

        mods = int(modifiers) & (CONTROL_MODIFIER | SHIFT_MODIFIER | ALT_MODIFIER)
        if child is None and self.console.control.has_focus and self.console.claims(key, modifiers):
            return False  # Ctrl+R searches the console's history there, as in the Qt console
        letter = int(key)
        if 65 <= letter <= 90:
            letter += 32
        action = self.shortcuts().get((letter, mods))
        if action is None or not action.enabled():
            return False
        if action.key in ("undo", "redo"):
            typing = getattr(child, "io", self.io) if child is not None else self.io
            if getattr(typing, "want_capture_keyboard", False):
                return False
        action.run()
        self.request_frame()
        return True

    def on_files_dropped(self, paths) -> bool:
        """Hand dropped files to the focused child when it takes them, else read them as data."""
        child, _origin = self._child(self._focus)
        if child is not None:
            for name in ("on_paths_dropped", "on_files_dropped", "files_dropped"):
                handler = getattr(child, name, None)
                if callable(handler) and handler(paths) is not False:
                    return True
        return self.data.drop([str(path) for path in paths or ()])

    def animating(self) -> bool:
        busy = any(hosted.build is not None for hosted in self.hosted.values()) or self.data.busy
        busy = busy or self.project.busy
        children = any(app.animating() for _key, app, _box in self._drawn.values())
        return super().animating() or busy or children

    def next_frame_in(self):
        delays = [super().next_frame_in(), self.project.next_frame_in()]
        delays += [app.next_frame_in() for _key, app, _box in self._drawn.values()]
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
        """Close every hosted plugin, the fit windows and the session, and detach the log handler."""
        for plugin_id in list(self.hosted):
            self.close_plugin(plugin_id)
        self.console.close()
        self._close_console_channel()
        self.project.close()
        self.data.close()
        logging.getLogger("chisurf").removeHandler(self.log)


def make_app(persist: bool = True) -> EmtkShellApp:
    """The shell app with its session; with *persist* its dock layout, size and open plugins are kept."""
    from chisurf.emtk.session import start_session

    app = EmtkShellApp(session_factory=start_session)
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
