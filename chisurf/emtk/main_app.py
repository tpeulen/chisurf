"""The ChiSurf main window as one emtk surface (the default: ``python -m chisurf``).

The Qt shell (``chisurf/gui/main.py``, ``python -m chisurf --qt``) is kept as the reference this surface is measured
against until it reaches parity; the parity ledger is in the OKF concept ``okf/subsystems/qt-retirement.md``.

What this slice provides:

* a **menu bar** built from the plugin manifests: ``display_name`` is the menu path (``"Spectroscopy:Correlation:FCS"``
  sits under *Spectroscopy*, group *Correlation*), ``menu_hidden`` plugins are left out, exactly as the Qt plugin
  menus read it;
* the **ribbon** under it (:mod:`chisurf.emtk.shell_ribbon`): the Qt ribbon's tabs, groups and buttons from the same
  manifests, the *File* and *Main* tabs' session groups, a search field, folding, and the help and language buttons;
* a **Tools** dock listing the same entries as a tree with a filter; every plugin row, menu item and ribbon button
  shows the plugin's manifest icon;
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

A plugin whose manifest declares only an ``action`` entrypoint (*Menu Switch*) is a command, not a window: its
menu item, ribbon button and Tools row run the action with the shell as its main window
(:func:`chisurf.core.plugin.registry.execute_plugin_action`). Plugins with only a Qt ``gui`` entrypoint are not
offered here.
"""

from __future__ import annotations

import collections
import logging
import time
from dataclasses import dataclass, field
from functools import partial
from typing import Any, Callable, Sequence

from emtk import accents, im, overlays
from emtk.app import ImApp
from emtk.docking import MIN_TILE, DockManager, Region, Split, tile_grid
from emtk.i18n import mark, tr

from chisurf.emtk.background_build import BackgroundBuild, draw_opening
from chisurf.emtk.shell_ribbon import ACTION_ICONS
from chisurf.emtk.shell_session import MenuAction, ShellProject

#: Settings id of the shell's own layout and preferences (``<settings>/emtk/emtk_shell.*.json``).
SHELL_ID = "emtk_shell"
#: Height of the menu bar strip.
MENU_BAR = 20.0
#: The region tools open in (tabbed docks beside the workspace in the central region).
TOOL_REGION = "center"
#: Prefix of a hosted plugin's dock window key.
PLUGIN_KEY = "plugin."
_log = logging.getLogger("chisurf.emtk.shell")
#: The shell open in this process (a weak reference), for :func:`host_in_shell`.
_ACTIVE_SHELL: Any = None


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
    #: The manifest's pictogram.
    icon: str = ""
    #: A command-line tool: listed only in experimental mode, as the Qt ribbon does.
    cli_only: bool = False
    #: A command (an ``entrypoints.action``), run instead of opened as a window.
    action: bool = False
    #: The manifest's ``single_instance``: opening it again shows the open one (settings, help).
    single_instance: bool = False

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
        Plugins with an ``entrypoints.emtk`` factory or only an ``entrypoints.action`` (a command), that are not
        ``menu_hidden``.
    """
    if catalog is None:
        from chisurf.emtk.plugins import manifests

        catalog = manifests()
    entries = []
    for plugin_id, data in catalog.items():
        entrypoints = data.get("entrypoints") or {}
        is_action = bool(entrypoints.get("action")) and not entrypoints.get("emtk")
        if data.get("menu_hidden") or not (entrypoints.get("emtk") or is_action):
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
                str(data.get("icon") or ""),
                bool(data.get("cli_only")),
                is_action,
                bool(data.get("single_instance")),
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
    #: Called once the app is built (:func:`host_in_shell`: a page to show, a file to open).
    on_ready: list = field(default_factory=list)
    #: The content box it was drawn into on the last frame (canvas coordinates), ``None`` when not shown.
    box: tuple[float, float, float, float] | None = None
    extra: dict = field(default_factory=dict)
    #: Which opening of the tool this is: 1 for the first, 2 for "ndX #2", ...
    instance: int = 1

    @property
    def instance_id(self) -> str:
        """The key of :attr:`EmtkShellApp.hosted`: the plugin id, then ``<id>#2``, ``<id>#3``..."""
        pid = self.entry.plugin_id
        return pid if self.instance == 1 else f"{pid}#{self.instance}"

    @property
    def key(self) -> str:
        """The dock window key."""
        return PLUGIN_KEY + self.instance_id

    def title(self) -> str:
        """The tab text in the current language: the label, numbered from the second opening on."""
        label = tr(self.entry.label)
        return label if self.instance == 1 else f"{label} #{self.instance}"


def _ribbon_preference() -> bool:
    """The user's ``gui.use_ribbon_interface`` (shown unless they switched it off)."""
    try:
        from chisurf.core.settings import cs_settings
    except Exception:  # noqa: BLE001 - unreadable settings: the shipped default
        return True
    return bool((cs_settings.get("gui") or {}).get("use_ribbon_interface", True))


def _apply_modal_blur_preference() -> None:
    """The user's ``gui.modal_blur`` (on unless switched off) onto emtk's backdrop."""
    from emtk.backdrop import set_modal_blur

    try:
        from chisurf.core.settings import cs_settings
    except Exception:  # noqa: BLE001 - unreadable settings: the shipped default
        set_modal_blur(True)
        return
    set_modal_blur(bool((cs_settings.get("gui") or {}).get("modal_blur", True)))


def _is_focused(docks: DockManager, key: str) -> bool:
    """Whether *key* is the focused dock window (a *Window* menu entry's check mark)."""
    return bool(docks.focused == key)


def _default_loader(plugin_id: str) -> Any:
    from chisurf.emtk.plugins import load_plugin

    return load_plugin(plugin_id)


class ShellDockManager(DockManager):
    """The shell's outer dock manager, delegating workspace document operations to workspace_docks."""

    def __init__(self, *args, app: Any, **kwargs):
        super().__init__(*args, **kwargs)
        self._app = app

    @property
    def focused(self) -> str | None:
        if hasattr(self._app, "workspace_docks") and getattr(self, "_focused", None) == "workspace":
            return self._app.workspace_docks.focused or "workspace"
        return getattr(self, "_focused", None)

    @focused.setter
    def focused(self, val: str | None) -> None:
        self._focused = val

    @property
    def _workspace_buttons(self) -> dict:
        if hasattr(self._app, "workspace_docks"):
            return getattr(self._app.workspace_docks, "_workspace_buttons", {})
        return {}

    def in_workspace(self, key: str) -> bool:
        if hasattr(self._app, "workspace_docks"):
            return bool(self._app.workspace_docks.in_workspace(key))
        return False

    def workspace_children(self) -> list[str]:
        if hasattr(self._app, "workspace_docks"):
            return list(self._app.workspace_docks.workspace_children())
        return []

    def tile_workspace(self, keys=None) -> None:
        self._app.tile_windows()

    def tab_workspace(self, keys=None) -> None:
        self._app.tab_windows()

    def cascade_workspace(self, keys=None) -> None:
        self._app.cascade_windows()

    def cycle_workspace(self, step: int = 1) -> str | None:
        if hasattr(self._app, "workspace_docks"):
            return self._app.workspace_docks.cycle_workspace(step)
        return None

    def floating_bounds(self, minimized: bool = False):
        if hasattr(self._app, "workspace_docks"):
            return self._app.workspace_docks.floating_bounds(minimized=minimized)
        return super().floating_bounds(minimized=minimized)

    def window(self, key: str):
        w = super().window(key)
        if w is not None:
            return w
        if hasattr(self._app, "workspace_docks"):
            return self._app.workspace_docks.window(key)
        return None

    def minimize(self, key: str):
        if hasattr(self._app, "workspace_docks") and key in self._app.workspace_docks.windows:
            return self._app.workspace_docks.minimize(key)
        return super().minimize(key)

    def add_window(self, key: str, *args, **kwargs):
        if kwargs.get("workspace"):
            res = self._app.workspace_docks.add_window(key, *args, **kwargs)
            self.show("workspace")
            self.focus("workspace")
            return res
        return super().add_window(key, *args, **kwargs)

    def remove_window(self, key: str) -> bool:
        if hasattr(self._app, "workspace_docks") and key in self._app.workspace_docks.windows:
            return self._app.workspace_docks.remove_window(key)
        return super().remove_window(key)

    def is_shown(self, key: str) -> bool:
        if hasattr(self._app, "workspace_docks") and key in self._app.workspace_docks.windows:
            return super().is_shown("workspace") and self._app.workspace_docks.is_shown(key)
        return super().is_shown(key)

    def is_visible(self, key: str) -> bool:
        if hasattr(self._app, "workspace_docks") and key in self._app.workspace_docks.windows:
            return self._app.workspace_docks.is_visible(key)
        return super().is_visible(key)

    def hide(self, key: str):
        if hasattr(self._app, "workspace_docks") and key in self._app.workspace_docks.windows:
            return self._app.workspace_docks.hide(key)
        return super().hide(key)

    def show(self, key: str):
        if hasattr(self._app, "workspace_docks") and key in self._app.workspace_docks.windows:
            super().show("workspace")
            return self._app.workspace_docks.show(key)
        return super().show(key)

    def focus(self, key: str):
        if hasattr(self._app, "workspace_docks") and key in self._app.workspace_docks.windows:
            super().show("workspace")
            super().focus("workspace")
            return self._app.workspace_docks.focus(key)
        return super().focus(key)

    def undock(self, key: str, box=None):
        if hasattr(self._app, "workspace_docks") and key in self._app.workspace_docks.windows:
            super().show("workspace")
            super().focus("workspace")
            return self._app.workspace_docks.undock(key, box=box)
        return super().undock(key, box=box)

    def region_of(self, key: str):
        if hasattr(self._app, "workspace_docks") and key in self._app.workspace_docks.windows:
            return self._app.workspace_docks.region_of(key)
        return super().region_of(key)

    def floating(self):
        floats = list(super().floating())
        if hasattr(self._app, "workspace_docks"):
            floats.extend(self._app.workspace_docks.floating())
        return floats

    def state(self) -> dict:
        data = super().state()
        if hasattr(self._app, "workspace_docks"):
            data["_workspace"] = self._app.workspace_docks.state()
        return data

    def restore(self, state: dict) -> None:
        if hasattr(self._app, "workspace_docks") and isinstance(state, dict) and "_workspace" in state:
            self._app.workspace_docks.restore(state["_workspace"])
        super().restore(state)

    def _sync_order(self, ctx, names: list[str], before: set) -> None:
        wanted = set(names)
        by_name = {w.name: w for w in ctx.windows if w.name in wanted}
        ws_prefix = (
            f"##{self._app.workspace_docks.name}."
            if hasattr(self._app, "workspace_docks")
            else None
        )
        ws_windows = [w for w in ctx.windows if ws_prefix and w.name.startswith(ws_prefix)]
        mine = []
        for n in names:
            if n in by_name:
                mine.append(by_name[n])
                if n == f"##{self.name}.region.center":
                    mine.extend(ws_windows)
        def is_ws(w) -> bool:
            return bool(ws_prefix and w.name.startswith(ws_prefix))

        earlier = [w for w in ctx.windows if w.name not in wanted and not is_ws(w) and id(w) in before]
        later = [w for w in ctx.windows if w.name not in wanted and not is_ws(w) and id(w) not in before]
        ctx.windows[:] = earlier + mine + later


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
    splash : SplashState, optional
        The boot splash's state; the session's startup stages are reported to it
        (:mod:`chisurf.emtk.splash`).
    post_show : bool or callable, optional
        Run the ``post_show`` startup stages (the update check;
        :mod:`chisurf.emtk.post_show`) once the session is adopted. ``True`` runs the declared
        stages, a callable ``runner(on_stage) -> metadata`` stands in for them (tests); off by
        default, so a test's shell never asks the update server.
    settings_sink : callable, optional
        ``settings_sink(state)`` hears :meth:`export_settings` whenever the persisted shape changes
        (a plugin opened or closed). The desktop persists through :func:`attach_native_state`
        instead and passes nothing; the web page sinks into ``localStorage``
        (:func:`chisurf.web.make_app`).
    """

    def __init__(
        self,
        catalog: dict[str, dict] | None = None,
        loader: Callable[[str], Any] | None = None,
        session_factory: Callable[..., Any] | None = None,
        console_history: Any = None,
        console_session_file: Any = None,
        splash: Any = None,
        post_show: Any = False,
        settings_sink: Callable[[dict], None] | None = None,
    ) -> None:
        from chisurf.emtk.frame_modules import import_frame_modules

        # Before the session, a plugin or the update check imports on a worker (chisurf._import_gate),
        # with what the shell's own first frames import lazily (measured: they waited on these).
        import_frame_modules()
        import chisurf.emtk.child_contract
        import chisurf.emtk.help_guide
        import chisurf.emtk.i18n
        import chisurf.emtk.shared_i18n  # noqa: F401
        if catalog is None:
            from chisurf.emtk.plugins import manifests

            catalog = manifests()
        #: The manifests the shell was made from (an action entry runs from its manifest).
        self.catalog = catalog
        #: The boot splash's state (:class:`chisurf.emtk.splash.SplashState`): the session reports
        #: its startup stages to it. ``None`` when the shell opens without a splash.
        self.splash = splash
        #: Frames drawn so far: the splash closes once the main window has drawn one.
        self.frames_drawn = 0
        self.entries = menu_entries(catalog)
        self.by_id = {entry.plugin_id: entry for entry in self.entries}
        from chisurf.emtk.shell_ribbon import ShellRibbon, menu_tree

        #: ``{menu: {caption: [MenuEntry]}}``: the plugin menus and the Tools tree, in ribbon order.
        self.menus = menu_tree(self.entries)
        from chisurf.emtk.task_colors import plugin_categories

        #: ``{plugin_id: category}``: the colour of each tool's kind of task (:mod:`chisurf.emtk.task_colors`).
        self.task_categories = plugin_categories(self.entries)
        self.ribbon = ShellRibbon(self)
        self._ribbon_enabled = _ribbon_preference()
        _apply_modal_blur_preference()
        #: The canvas size of the last frame (what *Screenshot* copies).
        self._canvas = (1400, 900)
        self._screenshot_pending = False
        self.loader = loader or _default_loader
        #: ``settings_sink(export_settings())`` on a persisted-shape change; ``None`` on the desktop.
        self._settings_sink = settings_sink
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
        #: Key -> the child that took its press: its release goes there, wherever the focus is by then.
        self._key_owners: dict[int, Any] = {}
        #: The children drawn in the last frame: child id -> (dock window key, app, box).
        self._drawn: dict[str, tuple[str, Any, tuple[float, float, float, float]]] = {}
        self.docks = ShellDockManager(
            Split(
                "h",
                # A third, as wide as the Qt window's left dock (474 of 1440 px): narrower, the
                # model editor's parameter tables drop Lo / Hi / Bounds for width (collapse_order).
                0.33,
                Split("v", 0.5, Region("left"), Region("left_lower")),
                # The workspace is where the fits live (its dock window is in center); the
                # tools are docks, tabbed beside Workspace by default in center, and dock anywhere else.
                Split(
                    "v",
                    0.8,
                    Region("center"),
                    Region("bottom"),
                ),
            ),
            app=self,
            name="shell",
        )
        self.workspace_docks = DockManager(
            Region("center", workspace=True),
            name="workspace",
        )
        # The machine and versions, faint behind the fit windows (emtk >= 0.1.15).
        self.workspace_docks.workspace_background = self._draw_workspace_background
        # ``core``: the shell's own docks, which "Close all panels" / "Close other panels" leave
        # open -- only the hosted tools (and what the user opened) go.
        # Not scrollable itself: the tool list scrolls under its filter (_draw_tools).
        self.docks.add_window(
            "tools",
            mark("Tools"),
            self._draw_tools,
            dock="left",
            closable=False,
            core=True,
            scrollable=False,
        )
        self.docks.add_window(
            "workspace",
            mark("Workspace"),
            self._draw_workspace_dock,
            dock="center",
            closable=False,
            core=True,
            scrollable=False,
            padding=0.0,
        )
        # Start fills the empty workspace (it says where the fits go), so it is one of its documents.
        self.workspace_docks.add_window(
            "start", mark("Start"), self._draw_start, dock="center", core=True, workspace=True
        )
        self.docks.add_window(
            "log", mark("Log"), self._draw_log, dock="bottom", scrollable=False, core=True
        )
        self.docks.add_window(
            "console",
            mark("Console"),
            self._draw_console,
            dock="bottom",
            scrollable=False,
            core=True,
        )
        _log.setLevel(logging.INFO)
        super().__init__(self.render)
        import weakref

        global _ACTIVE_SHELL
        _ACTIVE_SHELL = weakref.ref(self)
        from chisurf.core.plugin.handoff import install_host

        # Plugins hand payloads to each other through the shell (:meth:`hand_off`).
        install_host(self)
        from chisurf.emtk.status_strip import StatusStrip

        #: The line along the bottom: message, *Ready*, the operation under way
        #: (:mod:`chisurf.emtk.status_strip`, the Qt main window's status bar).
        self.status_strip = StatusStrip(wake=self.request_frame)
        self.status_strip.install()
        #: The startup stage under way while the session starts (its ``label`` / ``progress``).
        self._stage: dict = {}
        #: The strip's handles of the shell's own operations: ``kind -> (identity, task)``.
        self._strip_tasks: dict[str, tuple[Any, Any]] = {}
        from chisurf.emtk.fit_docks import ANALYSIS_KEY, PLOT_KEY, DataDocks

        self.data = DataDocks(self, session_factory)
        self.project = ShellProject(self)
        from chisurf.emtk.post_show import PostShow

        #: The ``post_show`` startup stages (``None``: not run by this shell).
        self.post_show = (
            PostShow(self, runner=post_show if callable(post_show) else None)
            if post_show
            else None
        )
        from chisurf.emtk.shell_log import ShellLog

        #: The Log dock: the log, the server's calls and the undo history (:mod:`chisurf.emtk.shell_log`).
        self.log = ShellLog(self.project)
        self.log.install()
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
        from chisurf.emtk.macro_recorder import MacroRecorder

        #: Records what the user does (dispatched actions) as editable code.
        self.macro_recorder = MacroRecorder()
        self._console_names: dict[str, Any] = {"gui": self}
        self._push_console_namespace()
        self.console.install()
        from chisurf.plugins.core.terminal.app import make_console_app

        def _console_pane_factory():
            # Another Python pane of the Console dock: the names the first one has (cs, np, os,
            # gui, api), kept in step by _push_console_namespace.
            return ShellConsole(
                dict(self._console_names),
                history_path=console_history,
                session_file=console_session_file,
                wake=self.request_frame,
                record_command=self.project.note_command,
            )

        self.console_terminal = make_console_app(
            console_factory=_console_pane_factory,
            initial_console=self.console,
        )
        for key in (ANALYSIS_KEY, PLOT_KEY):
            self.docks.dock(key, "left_lower")
        self.docks.focus(ANALYSIS_KEY)
        self.docks.focus("tools")
        self.docks.focus("console")
        self._focus = "console"
        self.docks.focus("workspace")
        self._watermark_folded = False
        try:
            from chisurf.core.system_info import process_usage

            self._usage_at, self._usage = time.monotonic(), process_usage()
            if self._usage is not None:
                self._usage_history: list[tuple[float, float]] = [self._usage]
        except Exception:
            pass
        # Last: the session's worker imports while it starts, so nothing of the shell may still be
        # importing on this thread when it begins (see :meth:`DataDocks.start`).
        self.data.start()

    # ── plugins ───────────────────────────────────────────────────────────

    def open_plugin(
        self, plugin_id: str, focus: bool = True, new: bool = False
    ) -> HostedPlugin | None:
        """Open *plugin_id* as a dock window (or bring its window to front); the app is made on a worker thread.

        A command plugin (``entrypoints.action``) is run instead and opens nothing (``None``). Without
        *focus* the window takes the place the saved layout gives it (minimized stays minimized).
        With *new* (the menus, the tool list and the ribbon) a tool that is open already opens again
        as "<name> #2", "#3", ... unless its manifest says ``single_instance``. *plugin_id* may name
        one opening (``ndxplorer#2``), as :meth:`export_settings` lists them.
        """
        base, _, number = plugin_id.partition("#")
        instance = int(number) if number.isdigit() and int(number) > 1 else 1
        entry = self.by_id.get(base)
        if entry is not None and entry.action:
            self.run_plugin_action(base)
            return None
        open_ = self.instances(base)
        if number:
            existing = self.hosted.get(plugin_id if instance > 1 else base)
        elif open_ and (not new or (entry is not None and entry.single_instance)):
            existing = next((h for h in open_ if h.key == self.docks.focused), open_[0])
        else:
            existing = None
            taken = {h.instance for h in open_}
            instance = next(n for n in range(1, len(taken) + 2) if n not in taken)
        if existing is not None:
            self.docks.show(existing.key)
            self.docks.focus(existing.key)
            if focus:
                self._focus = existing.key
            return existing
        if entry is None:
            raise KeyError(f"No native plugin {base!r} in the shell menus")
        hosted = HostedPlugin(entry, instance=instance)
        plugin_id = hosted.instance_id
        # A tool the user has placed before (docked or floated, this run or a saved layout)
        # goes back there; only a tool never placed gets a first place chosen (_place_wide_tool).
        remembers = getattr(self.docks, "remembers", None)  # emtk >= 0.1.14
        hosted.extra["placed"] = bool(callable(remembers) and remembers(hosted.key))
        hosted.build = BackgroundBuild(wake=self.request_frame)
        loader = self.loader
        hosted.build.start(
            {plugin_id: lambda: loader(entry.plugin_id)}, name=f"chisurf-shell-{plugin_id}"
        )
        self.hosted[plugin_id] = hosted
        self.docks.add_window(
            hosted.key,
            # The source text, not tr(): the tab translates it each frame, so a language
            # switched while the tool is open retitles it (a stored translation would not).
            mark(entry.label) if instance == 1 else hosted.title(),
            lambda box, pid=plugin_id: self._draw_plugin(pid, box),
            dock=self._tool_region(),
            scrollable=False,
            padding=0.0,
            min_size=(240.0, 160.0),
            tooltip=mark(entry.description),
        )
        if focus:
            self.docks.focus(hosted.key)
            self._focus = hosted.key
        self.status = tr("Opening {name}…").format(name=hosted.title())
        _log.info("open %s", plugin_id)
        self._emit_settings_change()
        return hosted

    def _emit_settings_change(self) -> None:
        """Hand :meth:`export_settings` to the ``settings_sink``, once, with failures said.

        The persisted shape changed (a plugin opened or closed); a sink that saves must hear it.
        A sink that fails must not take the open/close down with it.
        """
        sink = getattr(self, "_settings_sink", None)
        if sink is None:
            return
        try:
            sink(self.export_settings())
        except Exception:  # noqa: BLE001 - saving must not break opening
            _log.exception("the settings sink failed")

    def instances(self, plugin_id: str) -> list[HostedPlugin]:
        """Every opening of *plugin_id* in the shell, first opened first."""
        return sorted(
            (h for h in self.hosted.values() if h.entry.plugin_id == plugin_id),
            key=lambda h: h.instance,
        )

    def accepts(self, plugin_id: str, kind: str) -> Any:
        """The ``accepts`` declaration of *kind* when the shell offers *plugin_id*, else ``None``.

        The hand-off contract (:mod:`chisurf.core.plugin.handoff`): only a payload kind the target's
        manifest declares may be handed to it.
        """
        from chisurf.core.plugin.handoff import accepted

        entry = self.by_id.get(plugin_id)
        if entry is None or entry.action:
            return None
        return accepted(plugin_id, kind, self.catalog.get(plugin_id))

    def hand_off(
        self,
        plugin_id: str,
        kind: str,
        payload: dict,
        on_delivered: Callable[[Any], Any] | None = None,
        new: bool = False,
    ) -> HostedPlugin:
        """Open *plugin_id* as a dock and give its app *payload* once the app is built.

        With *new* it is a new dock of the tool ("ndX #2"), as the menus open one.

        The payload goes to the receive hook the target declares for *kind*
        (:func:`chisurf.core.plugin.handoff.deliver`), on the draw thread, after the build finishes
        -- at once when the tool is already open. A tool already open keeps its dock and gets the
        new payload (tools are docks, one per tool). A hook that fails is said in the status line
        and logged. After the hook took the payload, ``on_delivered(app)`` gets the target's app
        (the requester's way to reach what it opened); a failure there is said the same way.

        Raises
        ------
        chisurf.core.plugin.handoff.HandoffError
            The shell does not offer *plugin_id*, it does not declare *kind*, or *payload* lacks a
            required key; nothing is opened then.
        """
        from chisurf.core.plugin.handoff import HandoffError, check_payload, deliver

        spec = self.accepts(plugin_id, kind)
        if spec is None:
            if plugin_id not in self.by_id:
                raise HandoffError(f"{plugin_id} is not a tool of this window")
            raise HandoffError(f"{plugin_id} does not accept a {kind} payload")
        check_payload(spec, payload)
        hosted = self.open_plugin(plugin_id, new=new)
        assert hosted is not None  # accepts() refused command plugins

        def receive() -> None:
            app = hosted.app
            app = getattr(app, "_control", app)  # the plugin's own app, not the child wrapper
            try:
                deliver(app, spec, payload)
                if on_delivered is not None:
                    on_delivered(app)
            except Exception as exc:  # noqa: BLE001 - said, never raised into the frame
                _log.exception("handing %s to %s failed", kind, plugin_id)
                self.status = tr("{name} could not take it: {error}").format(
                    name=tr(hosted.entry.label), error=exc
                )
                hosted.extra["handoff_error"] = f"{type(exc).__name__}: {exc}"
                return
            hosted.extra.pop("handoff_error", None)
            hosted.extra.setdefault("handoffs", []).append(kind)
            self.request_frame()

        hosted.on_ready.append(receive)
        if hosted.app is not None and hosted.build is None:
            self._run_ready(hosted)
        self.request_frame()
        return hosted

    def _place_wide_tool(self, hosted: HostedPlugin) -> None:
        """Deprecated: tools always land docked in their region without auto-floating."""
        hosted.extra["placed"] = True

    def _tool_region(self) -> str:
        """The region a tool opens in: the central dock region beside Workspace."""
        return "center"

    def run_plugin_action(self, plugin_id: str) -> dict:
        """Run the command plugin *plugin_id* with this window as its main window; a failure is said."""
        from chisurf.core.api.context import PluginContext
        from chisurf.core.plugin.manifest import PluginManifest
        from chisurf.core.plugin.registry import execute_plugin_action

        entry = self.by_id[plugin_id]
        result = execute_plugin_action(
            PluginManifest.from_dict(self.catalog[plugin_id]), PluginContext(main_window=self)
        )
        if result.get("ok"):
            self.status = tr("{name} done.").format(name=tr(entry.label))
            _log.info("ran %s", plugin_id)
        else:
            error = str(result.get("error") or "")
            self.status = tr("{name} failed.").format(name=tr(entry.label))
            self.project.dialogs.message(tr(entry.label), error or tr("The command did not run."))
        self.request_frame()
        return result

    # ── Menu Switch ───────────────────────────────────────────────────────

    @property
    def ribbon_enabled(self) -> bool:
        """Whether the ribbon is shown under the menu bar (*Menu Switch* turns it off and on)."""
        return self._ribbon_enabled

    def toggle_ribbon_interface(self, enabled: bool | None = None) -> None:
        """Show (*enabled*) or hide the ribbon, or swap; the choice is the user's ``gui.use_ribbon_interface``.

        The menu bar stays either way: every session command is in it, and the ribbon's tabs are
        the same plugin menus. The preference is the one the Qt window reads, so both start alike.
        """
        from chisurf.core.settings.settings_utils import set_use_ribbon_interface

        self._ribbon_enabled = (not self._ribbon_enabled) if enabled is None else bool(enabled)
        if not set_use_ribbon_interface(self._ribbon_enabled):
            _log.warning("the ribbon preference could not be saved")
        self.request_frame()

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
        self._emit_settings_change()

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
                self.status = tr("{name} could not be opened.").format(name=hosted.title())
            else:
                from chisurf.emtk.child_contract import as_child

                hosted.app = made = as_child(made)
                if hasattr(made, "set_frame_request_callback"):
                    made.set_frame_request_callback(self.request_frame)
                self.status = tr("{name} opened.").format(name=hosted.title())
                self._run_ready(hosted)

    def _run_ready(self, hosted: HostedPlugin) -> None:
        """Run what waited for *hosted*'s app (:func:`host_in_shell`), once."""
        waiting, hosted.on_ready = hosted.on_ready, []
        for then in waiting:
            try:
                then()
            except Exception:  # noqa: BLE001 - a page that cannot be shown must not stop the frame
                _log.exception("after opening %s", hosted.entry.plugin_id)

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
        if self.post_show is not None:
            if self.data.session is not None:
                self.post_show.start()
            self.post_show.poll()
        self.project.poll()
        # Every Python pane, not only the one in view: a cell running in a pane tabbed under
        # another may be waiting for the window (ShellConsole.call_on_frame).
        for console in self._python_consoles():
            console.poll()
        self._push_console_namespace()
        # Drawn again this frame if the workspace is shown; a rectangle left from a frame it
        # was tabbed under would take presses meant for the tool in front.
        self._watermark_last = self.item_rects.pop("system_info", None)
        self._poll_hidden_tools()
        for hosted in self.hosted.values():
            hosted.box = None
            if hosted.instance > 1:
                # "ndX #2" has no catalogue entry: the window carries the translated label with its
                # number, set again every frame so a language switch retitles it.
                window = self.docks.window(hosted.key)
                if window is not None:
                    window.title = hosted.title()
        self._drawn = {}
        self._canvas = (int(w), int(h))
        frame_start = time.perf_counter()
        try:
            super().draw(painter, x, y, w, h)
        finally:
            self._painter = None
        self.frames_drawn += 1
        now_ts = time.perf_counter()
        self._frame_ms = (now_ts - frame_start) * 1000.0

        last_ts = getattr(self, "_last_frame_ts", None)
        if last_ts is not None and now_ts > last_ts:
            dt = now_ts - last_ts
            if dt <= 0.25:  # active frame delta (idle gaps > 250ms are not frame times)
                history = getattr(self, "_frame_durations", None)
                if history is None:
                    self._frame_durations = collections.deque(maxlen=30)
                    history = self._frame_durations
                history.append(dt)
                self._fps = len(history) / sum(history) if sum(history) > 0 else 0.0
        self._last_frame_ts = now_ts

        if self._screenshot_pending:
            self._screenshot_pending = False
            self._copy_screenshot()
        self._closed_by_user()
        self.project.guard_fit_windows()
        self.data.closed_by_user()
        self.data.focused_window()
        self.feed_status_strip()

    def render(self) -> None:
        width, height = im.get_main_viewport().size
        self._draw_menu_bar(width)
        top = MENU_BAR + self._draw_ribbon(width)
        self._colour_docks()
        from chisurf.emtk.status_strip import HEIGHT as STRIP
        from chisurf.emtk.status_strip import draw_strip

        self.docks.draw((0.0, top, width, max(1.0, height - top - STRIP)))
        draw_strip(self.status_strip, width, height)
        self.item_rects.update(self.status_strip.item_rects)
        self.data.draw_file_dialog((0.0, 0.0, width, height))
        self.console.draw_overlays((0.0, 0.0, width, height))
        self.project.draw((0.0, 0.0, width, height))

    def host_child(self, window_key: str, child_id: str, app: Any, box) -> None:
        """Draw *app* into *box* (canvas coordinates) of dock window *window_key*; input over it goes to it.

        Called from a dock's draw callback. *child_id* names the child for focus and capture (a plugin's or a fit
        window's dock key, ``reader.<n>`` for a reader's settings). The child's section headers and title bars
        take a muted tint of the dock's task colour.
        """
        x, y, w, h = (float(v) for v in box)
        box = (x, y, max(1.0, w), max(1.0, h))
        painter = im.get_current_context().p
        window = self.docks.window(window_key)
        with accents.region(window.accent if window is not None else None):
            self.draw_child(painter, app, *box, local_coordinates=True)
        self._drawn[child_id] = (window_key, app, box)

    def _colour_docks(self) -> None:
        """Give every dock window the colour of its kind of task (:mod:`chisurf.emtk.task_colors`); emtk draws it.

        A plugin's dock takes its plugin's category, the data / fit docks *fitting*, Log and Console *console*;
        the rest is core chrome in the neutral grey (also its section headers and selected rows, which the theme
        would draw in a blue that reads as *Documentation*). Done each frame, so fit windows opened since are
        coloured too; emtk picks the theme variant when it draws.
        """
        from chisurf.emtk.task_colors import accent, dock_category, neutral

        for key, window in self.docks.windows.items():
            category = dock_category(key, self.task_categories)
            window.accent = accent(category) or neutral()
            window.header_tint = True
        if hasattr(self, "workspace_docks"):
            for key, window in self.workspace_docks.windows.items():
                category = dock_category(key, self.task_categories)
                window.accent = accent(category) or neutral()
                window.header_tint = True

    def _draw_ribbon(self, width: float) -> float:
        """The ribbon under the menu bar; returns its height (none while *Menu Switch* hid it)."""
        if not self._ribbon_enabled:
            return 0.0
        height = self.ribbon.height()
        im.set_next_window_pos((0.0, MENU_BAR), im.Cond.ALWAYS)
        im.set_next_window_size((width, height), im.Cond.ALWAYS)
        flags = im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE
        if im.begin("shell ribbon", flags=flags):
            self.ribbon.draw((0.0, MENU_BAR, width, height))
            self._menu_open = self._menu_open or self.ribbon.menu_open()
        im.end()
        return height

    def _draw_menu_bar(self, width: float) -> None:
        im.set_next_window_pos((0.0, 0.0), im.Cond.ALWAYS)
        im.set_next_window_size((width, MENU_BAR), im.Cond.ALWAYS)
        self._menu_open = False
        flags = im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE | im.WindowFlags.MENU_BAR
        if im.begin("shell menu bar", flags=flags):
            im.begin_menu_bar()
            plugins = {tr(menu): groups for menu, groups in self.menus.items()}
            session = self.session_menus()
            # File first, then the plugin menus, then View, Macro and Settings, and Help last; a
            # plugin menu with a session menu's title (the File tools under "File") joins that menu.
            help_menu = tr("Help")
            order = [session[0]] + [
                (menu, []) for menu in plugins if menu not in dict(session) and menu != help_menu
            ]
            order += session[1:]
            if help_menu in plugins:
                order.append((help_menu, []))
            for menu, actions in order:
                opened = im.begin_menu(menu)
                self.item_rects["menu." + menu] = im.get_item_rect()
                if opened:
                    self._menu_open = True
                    self._draw_actions(actions)
                    self._draw_plugin_entries(plugins.get(menu, {}), separate=bool(actions))
                    im.end_menu()
            im.end_menu_bar()
        im.end()

    def _draw_actions(self, actions: Sequence[MenuAction]) -> None:
        """The items of a session menu: group captions, shortcut texts, check marks."""
        group = None
        for action in actions:
            if action.children:
                if action.group != group:
                    if action.group:
                        im.separator_text(action.group)
                    elif group:
                        im.separator()
                group = action.group
                if im.begin_menu(action.label, enabled=action.enabled()):
                    self._draw_actions(action.children)
                    im.end_menu()
                self.item_rects[f"menu.{action.key}"] = im.get_item_rect()
                if action.description:
                    im.set_item_tooltip(action.description)
                continue

            if action.group != group:
                # A group is a captioned section (Qt's submenus: Project, Fits, Recent Projects, Docks).
                if action.group:
                    im.separator_text(action.group)
                elif group:
                    im.separator()
            group = action.group
            selected = bool(action.checked()) if action.checked is not None else False
            icon = ACTION_ICONS.get(action.key) or (
                ACTION_ICONS["recent"] if action.key.startswith("recent.") else None
            )
            if im.menu_item(
                action.label,
                action.shortcut,
                selected=selected,
                enabled=action.enabled(),
                icon=icon,
            ):
                self._menu_open = False
                action.run()
            self.item_rects[f"menu.{action.key}"] = im.get_item_rect()
            if action.description:
                im.set_item_tooltip(action.description)

    def _draw_plugin_entries(
        self, groups: dict[str, list[MenuEntry]], separate: bool = False
    ) -> None:
        """The plugins of one menu, each group a captioned section, each row with the plugin's icon."""
        from chisurf.emtk.shell_ribbon import entry_label

        for caption, entries in groups.items():
            if caption:
                im.separator_text(tr(caption))
            elif separate:
                im.separator()
            separate = True
            for entry in entries:
                if im.menu_item(
                    entry_label(entry),
                    selected=bool(self.instances(entry.plugin_id)),
                    icon=entry.icon or None,
                ):
                    self.open_plugin(entry.plugin_id, new=True)

    # ── session menus ─────────────────────────────────────────────────────

    def _theme_actions(self) -> list[MenuAction]:
        """Settings: one checked entry per available style (switch now and keep for next start)."""
        import pathlib

        from emtk import theme

        from chisurf.core.settings import cs_settings
        from chisurf.core.settings import theme as stored_theme

        def choose(name: str) -> None:
            st_list = [self.style] if getattr(self, "style", None) is not None else []
            stored_theme.choose(name, styles=st_list)
            self.request_frame()

        def style_display_label(name: str) -> str:
            stem = pathlib.Path(name).stem
            special = {
                "dark_blue": tr("Dark Blue"),
                "dark": tr("Dark"),
                "light": tr("Light"),
                "dark_green": tr("Dark Green"),
                "dark_orange": tr("Dark Orange"),
                "dark_violet": tr("Dark Violet"),
                "dark_blue_flat": tr("Dark Blue Flat"),
            }
            if stem in special:
                return special[stem]
            return stem.replace("_", " ").title()

        def is_checked(name: str) -> bool:
            stem = pathlib.Path(name).stem
            curr_theme = theme.current_theme()
            if curr_theme == stem or curr_theme == name:
                return True
            curr_sheet = str((cs_settings.get("gui") or {}).get("style_sheet") or "")
            if curr_sheet == name or curr_sheet == stem or pathlib.Path(curr_sheet).stem == stem:
                return True
            return False

        def toggle_blur() -> None:
            from emtk.backdrop import modal_blur, set_modal_blur

            from chisurf.core.settings.settings_utils import set_modal_blur as save_blur

            set_modal_blur(not modal_blur())
            if not save_blur(modal_blur()):
                _log.warning("the blur preference could not be saved")
            self.request_frame()

        def blur_on() -> bool:
            from emtk.backdrop import modal_blur

            return modal_blur()

        blur = MenuAction(
            "style_modal_blur",
            tr("Blur behind dialogs"),
            toggle_blur,
            "",
            "",
            tr("While a dialog is open, everything behind it is blurred, so the dialog is "
               "the only thing in focus. Kept for the next start."),
            checked=blur_on,
        )
        # The shell's session menus are flat: one checked entry per theme
        # (emtk's palette sets — "dark", "light"), no submenu layer.
        return [
            MenuAction(
                f"style_{pathlib.Path(name).stem}",
                style_display_label(name),
                partial(choose, name),
                "",
                "",
                name,
                checked=partial(is_checked, name),
            )
            for name in stored_theme.available_styles()
        ] + [blur]

    def session_menus(self) -> list[tuple[str, list[MenuAction]]]:
        """*File*, *View* and *Settings* as ``(title, [MenuAction])``; the shortcut table is read from them."""
        project, data = self.project, self.data
        has_session = lambda: project.channel is not None  # noqa: E731
        has_fits = lambda: bool(data.datasets.fits)  # noqa: E731
        file_menu = [
            MenuAction(
                "add_dataset",
                tr("Add dataset"),
                data.read.load,
                "Ctrl+N",
                description=tr("Read the file in Read data with the selected file type."),
                enabled=lambda: data.session is not None,
            ),
            MenuAction(
                "save_project",
                tr("Save Project"),
                project.save,
                "Ctrl+S",
                tr("Project"),
                tr("Save the project to its file, or choose one."),
                has_session,
            ),
            MenuAction(
                "export_project",
                tr("Export Project…"),
                project.save_as,
                "Ctrl+Shift+S",
                tr("Project"),
                tr("Save the project under a new .cs.pto file (save as)."),
                has_session,
            ),
            MenuAction(
                "open_project",
                tr("Open Project…"),
                project.open_project,
                "",
                tr("Project"),
                tr("Replace the session with a saved project."),
                has_session,
            ),
            MenuAction(
                "import_project",
                tr("Import Project…"),
                project.import_project,
                "",
                tr("Project"),
                tr("Open a .cs.pto, or import a copy into the database."),
                has_session,
            ),
            MenuAction(
                "load_fit",
                tr("Load Fit"),
                project.load_fit,
                "",
                tr("Fits"),
                tr("Add the fit of a .fit.cs.pto file (written by Current Fit) to the session."),
                has_session,
            ),
            MenuAction(
                "save_fit",
                tr("Current Fit"),
                project.save_current_fit,
                "Ctrl+Alt+S",
                tr("Fits"),
                tr("Write the current fit's curves, its fit file and a Word report into a folder."),
                lambda: bool(data.current_uid),
            ),
            MenuAction(
                "save_all_fits",
                tr("All Fits"),
                project.save_all_fits,
                "",
                tr("Fits"),
                tr("Write every fit into a folder of its own, and all reports into all_fits.docx."),
                has_fits,
            ),
            MenuAction(
                "close_fit",
                tr("Close Fit"),
                project.close_fit,
                "",
                tr("Fits"),
                tr("Remove the current fit (asks first)."),
                lambda: bool(data.current_uid),
            ),
            MenuAction(
                "close_all_fits",
                tr("Close all fits"),
                project.close_all_fits,
                "",
                tr("Fits"),
                tr("Remove every fit from the session."),
                has_fits,
            ),
            MenuAction(
                "close_project",
                tr("Close Project"),
                project.close_project,
                "",
                "",
                tr("Start an empty session (asks to save unsaved work)."),
                has_session,
            ),
            MenuAction(
                "reinitialize",
                tr("Reinitialize"),
                lambda: project.close_project(reinitialize=True),
                "Ctrl+R",
                "",
                tr("Clear all data and start again (asks to save unsaved work)."),
                has_session,
            ),
        ]
        recent = [
            MenuAction(
                f"recent.{index}",
                f"{index + 1} {path}",
                partial(project.open_recent, path),
                "",
                tr("Recent Projects"),
                enabled=has_session,
            )
            for index, path in enumerate(project.recent)
        ] or [
            MenuAction(
                "recent.none",
                tr("No recent projects"),
                lambda: None,
                "",
                tr("Recent Projects"),
                enabled=lambda: False,
            )
        ]
        file_menu += recent
        file_menu += [
            MenuAction(
                "clear_recent",
                tr("Clear Recent Projects"),
                project.clear_recent,
                "",
                tr("Recent Projects"),
                enabled=lambda: bool(project.recent),
            ),
            MenuAction(
                "quit",
                tr("Quit"),
                project.request_quit,
                "Ctrl+Q",
                "",
                tr("Close ChiSurf (asks to save unsaved work)."),
            ),
        ]
        docks = [
            ("data.read", tr("Read data")),
            ("data.sets", tr("Datasets")),
            ("fit.analysis", tr("Analysis")),
            ("fit.plot", tr("Plot settings")),
            ("tools", tr("Tools")),
            ("start", tr("Start")),
            ("log", tr("Log")),
            ("console", tr("Console")),
        ]
        view_menu = [
            MenuAction(
                f"dock.{key}",
                title,
                partial(self.docks.toggle, key),
                "",
                tr("Docks"),
                checked=partial(self.docks.is_visible, key),
            )
            for key, title in docks
        ]
        view_menu += self.workspace_actions() + [
            MenuAction(
                "reset_layout",
                tr("Reset layout"),
                self.docks.reset,
                "",
                "",
                tr("Put every dock back where it started."),
            ),
            MenuAction(
                "undo",
                tr("Undo"),
                project.undo,
                "Ctrl+Z",
                "",
                tr("Go back one change of the science."),
                project.can_undo,
            ),
            MenuAction(
                "redo",
                tr("Redo"),
                project.redo,
                "Ctrl+Y",
                "",
                tr("Go forward one change of the science."),
                project.can_redo,
            ),
        ]
        settings_menu = [
            MenuAction(
                "settings_edit",
                tr("Edit"),
                project.edit_settings,
                "",
                "",
                tr("Open the settings editor."),
                lambda: "setup" in self.by_id,
            ),
            *self._theme_actions(),
            MenuAction(
                "fret_rda_axis",
                tr("FRET RDA axis…"),
                project.rda_axis,
                "",
                "",
                tr("The distance grid FRET models use."),
            ),
            MenuAction(
                "data_loading",
                tr("Data loading…"),
                project.data_loading,
                "",
                "",
                tr("Staging of files on slow storage, and the plot point budget."),
            ),
            MenuAction(
                "reset_local_settings",
                tr("Reset local settings"),
                project.reset_local_settings,
                "",
                "",
                tr("Return your settings folder to the shipped defaults."),
            ),
            MenuAction(
                "clear_logging_files", tr("Clear logging files"), project.clear_logging_files
            ),
            MenuAction("clear_user_styles", tr("Clear user styles"), project.clear_user_styles),
            MenuAction("clear_user_plugins", tr("Clear user plugins"), project.clear_user_plugins),
        ]
        macro_menu = [
            MenuAction(
                "record",
                tr("Record"),
                self.toggle_macro_recording,
                "",
                "",
                tr("Record what you click and type; click again to stop -- the macro opens in the console's editor as code."),
                checked=lambda: self.console.recording,
            ),
            MenuAction(
                "run_macro",
                tr("Run Macro…"),
                self.run_macro,
                "",
                "",
                tr("Run a saved macro (.cm.py) in the console's namespace."),
            ),
            MenuAction(
                "copy_macro",
                tr("Last recording → editor"),
                self.edit_last_macro,
                "",
                "",
                tr(
                    "Put the last recording (clicks as cs_dispatch calls, plus the console) "
                    "into the console's editor to edit and run."
                ),
                enabled=lambda: bool(self.macro_recorder.entries or self.console.macro.strip()),
            ),
        ]
        return [
            (tr("File"), file_menu),
            (tr("View"), view_menu),
            (tr("Macro"), macro_menu),
            (tr("Settings"), settings_menu),
        ]

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
            # A connection of the console's own: its cells call from the console's worker thread,
            # and the docks' connection is theirs (the client serialises its own calls).
            api = getattr(session, "api", None)
            if (
                getattr(session, "server", None) is not None
                and getattr(session.server, "cmd_port", None) is not None
            ):
                # A connection of the console's own: its cells call from the console's worker thread,
                # and the docks' connection is theirs (the client serialises its own calls).
                from chisurf.emtk.shell_session import ProjectChannel

                try:
                    self._console_channel = ProjectChannel(session)
                    api = self._console_channel.api
                except Exception:  # noqa: BLE001 - the console still runs Python without ``api``
                    _log.exception("connecting the console to the session failed")
            # else: a port-less server (the web page's in-process host) keeps
            # the session's own API -- local mode, no sockets to connect.
            names["api"] = api
        self._console_names = names
        for console in self._python_consoles():
            console.push(names)
        self._console_session = session

    def _python_consoles(self) -> list:
        """The window's console and every other Python pane the Console dock has open."""
        consoles = [self.console]
        terminal = getattr(self, "console_terminal", None)
        if terminal is not None:
            for pane in terminal.workspace.panes.values():
                if pane.kind == "python" and pane.console is not self.console:
                    consoles.append(pane.console)
        return consoles

    def _close_console_channel(self) -> None:
        channel, self._console_channel = getattr(self, "_console_channel", None), None
        if channel is not None:
            channel.close()

    def _macro_script(self) -> str:
        """Everything recorded: the user's actions as code, then the console's code."""
        recorder = self.macro_recorder
        action_part = recorder.script
        console_part = self.console.macro.strip()
        parts = []
        if action_part:
            parts.append(action_part.rstrip("\n"))
        if console_part:
            parts.append("# -- code run in the console " + "-" * 33 + "\n\n" + console_part)
        return "\n\n".join(parts).rstrip() + "\n" if parts else ""

    def toggle_macro_recording(self) -> None:
        """*Macro ▸ Record*: record what the user clicks and types; the second click stops,
        puts the macro in the console's editor and offers to save it."""
        console = self.console
        if not console.recording:
            console.start_recording()
            self.macro_recorder.clear()
            dispatcher = getattr(__import__("chisurf"), "action_dispatcher", None)
            if dispatcher is not None:
                self.macro_recorder.attach(dispatcher)
            self.docks.show("console")
            self.docks.focus("console")
            self._focus = "console"
            console.focus_input()
            self.status = tr("Recording macro… (clicks and console)")
            return
        console.stop_recording()
        self.macro_recorder.detach()
        self.status = tr("Ready")
        script = self._macro_script()
        if not script.strip():
            self.project.dialogs.message(tr("Record macro"), tr("Nothing was recorded."))
            return
        # The macro is code for the user to edit: it lands in the console's editor,
        # ready to change and run -- and can be saved as a .cm.py on top.
        self.docks.show("console")
        self.docks.focus("console")
        console.focus_input()
        console.set_input(script)
        from chisurf.emtk.console import MACRO_FILTER

        self.project.open_file_dialog(
            tr("Save macro"),
            "save",
            self._save_recorded_macro,
            filters=MACRO_FILTER,
            filename="macro.cm.py",
        )

    def _save_recorded_macro(self, filename: str) -> None:
        """Write what the last recording produced (actions and console) to *filename*."""
        import chisurf.core.fio as io

        script = self._macro_script()
        with io.zipped.open_maybe_zipped(filename=str(filename), mode="w") as handle:
            handle.write(script)
        self.status = tr(f"Macro saved: {filename}")

    def edit_last_macro(self) -> None:
        """*Macro ▸ Last recording → editor*: the last recording as editable code."""
        script = self._macro_script()
        if not script.strip():
            self.project.dialogs.message(tr("Record macro"), tr("Nothing was recorded."))
            return
        self.docks.show("console")
        self.docks.focus("console")
        self.console.focus_input()
        self.console.set_input(script)

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

        def _collect(actions):
            for action in actions:
                parsed = parse_shortcut(action.shortcut)
                if parsed is not None:
                    table[parsed] = action
                if getattr(action, "children", None):
                    _collect(action.children)

        for _menu, actions in self.session_menus():
            _collect(actions)
        return table

    def workspace_actions(self) -> list[MenuAction]:
        """The View menu's *Workspace* group: arrange the fit windows, cycle them, pick one.

        The workspace (the centre, :class:`emtk.docking.Region` ``workspace=True``) is where the
        fits live: their windows (and Start) are its documents. Tools, help and the code editor
        are docks, never workspace windows, so these commands leave them alone. The workspace's
        own tool bar and right-click menu carry the same commands.
        """
        docks = self.workspace_docks
        group = tr("Workspace")
        has_windows = lambda: bool(docks.workspace_children())  # noqa: E731
        actions = [
            MenuAction(
                "tile_windows",
                tr("Tile Windows"),
                self.tile_windows,
                "",
                group,
                tr("Show every fit window side by side."),
                has_windows,
            ),
            MenuAction(
                "tab_windows",
                tr("Tab Windows"),
                self.tab_windows,
                "",
                group,
                tr("Show the fit windows as tabs."),
                has_windows,
            ),
            MenuAction(
                "cascade_windows",
                tr("Cascade Windows"),
                self.cascade_windows,
                "",
                group,
                tr("Float the fit windows, each a little below the last."),
                has_windows,
            ),
            MenuAction(
                "next_window",
                tr("Next Window"),
                self.next_window,
                "",
                group,
                tr("Bring the next fit window to the front (Ctrl+Tab)."),
                has_windows,
            ),
        ]
        for key in docks.workspace_children():
            window = docks.window(key)
            if window is None:
                continue
            label = tr(window.title)
            if window.minimized:
                label = tr("{title} (minimized)").format(title=label)
            actions.append(
                MenuAction(
                    f"window.{key}",
                    label,
                    partial(self._focus_workspace_window, key),
                    "",
                    group,
                    tr("Bring this window to the front."),
                    checked=partial(_is_focused, docks, key),
                )
            )
        return actions

    def _focus_workspace_window(self, key: str) -> None:
        self.docks.show("workspace")
        self.docks.focus("workspace")
        self.workspace_docks.focus(key)
        self.request_frame()

    def next_window(self) -> None:
        self.docks.show("workspace")
        self.docks.focus("workspace")
        self.workspace_docks.cycle_workspace(1)
        self.request_frame()

    def tile_windows(self) -> None:
        """*Tile Windows*: the workspace's windows in a near-square grid of usable tiles.

        :meth:`emtk.docking.DockManager.tile_workspace`: no tile is below :data:`MIN_TILE`; what
        the workspace cannot hold is minimized to its strip, a click away.
        """
        self.docks.show("workspace")
        self.docks.focus("workspace")
        self.workspace_docks.tile_workspace()
        self.request_frame()

    def tab_windows(self) -> None:
        """*Tab Windows*: every window of the workspace a tab of it."""
        self.docks.show("workspace")
        self.docks.focus("workspace")
        self.workspace_docks.tab_workspace()
        self.request_frame()

    def cascade_windows(self) -> None:
        """*Cascade Windows*: the workspace's windows float, each a little below the last."""
        self.docks.show("workspace")
        self.docks.focus("workspace")
        self.workspace_docks.cascade_workspace()
        self.request_frame()

    def window_actions(self) -> list[MenuAction]:
        """The Main tab's own window actions that no menu carries (*Screenshot*)."""
        return [
            MenuAction(
                "screenshot",
                tr("Screenshot"),
                self.request_screenshot,
                "",
                "",
                tr("Copy a picture of the window to the clipboard."),
            ),
        ]

    def request_screenshot(self) -> None:
        """*Screenshot*: copy the window to the clipboard once the frame that asked has ended."""
        self._screenshot_pending = True
        self.request_frame()

    def _copy_screenshot(self) -> None:
        from emtk.clipboard import copy_image
        from emtk.export import png_bytes

        try:
            copy_image(png_bytes(self, size=self._canvas, frames=1))
        except Exception:  # noqa: BLE001 - a failed grab is reported, the shell keeps running
            _log.exception("the screenshot failed")
            self.status = tr("Screenshot failed: the window could not be grabbed.")
            return
        self.status = tr("Screenshot copied to clipboard.")

    def close_request(self) -> bool:
        """The window's close button: close only after the unsaved-changes question (asked once)."""
        return self.project.request_quit()

    # ── docks ─────────────────────────────────────────────────────────────

    def _draw_tools(self, box) -> None:
        """The Tools tree: one section per menu, its groups as captions, each tool with its icon.

        Each tool carries a bar of its task colour and each caption is written in it; a menu whose tools
        are all one kind (Help, Structure) has its header tinted with that colour, the others neutral.
        The filter stays at the top while the tree scrolls under it.
        """
        changed, value = im.begin_filtered_list("tools", self.filter, tr("Filter tools"))
        try:
            if changed:
                self.filter = value
            self.item_rects["tools.filter"] = im.get_item_rect()
            self._draw_tool_list()
        finally:
            self.item_rects["tools.list"] = im.end_filtered_list()

    def _draw_tool_list(self) -> None:
        """The rows of the Tools panel that match its filter (inside its scrolling list)."""
        from chisurf.emtk.shell_ribbon import entry_label, entry_tooltip
        from chisurf.emtk.task_colors import accent, neutral

        def colour_of(entries) -> Any:
            kinds = {self.task_categories.get(e.plugin_id) for e in entries}
            return accent(kinds.pop()) if len(kinds) == 1 else None

        words = self.filter.casefold().split()

        def matches(entry: MenuEntry) -> bool:
            text = " ".join([*entry.path, *map(tr, entry.path), entry.plugin_id]).casefold()
            return all(word in text for word in words)

        shown = 0
        for menu, groups in self.menus.items():
            found = {
                caption: [e for e in entries if matches(e)] for caption, entries in groups.items()
            }
            found = {caption: entries for caption, entries in found.items() if entries}
            if not found:
                continue
            menu_accent = colour_of([e for items in groups.values() for e in items]) or neutral()
            with accents.headers(menu_accent):
                # A filter opens every section that has a match; otherwise the user's clicks own it.
                is_open = im.collapsing_header(f"{tr(menu)}##tools.{menu}", True if words else 32)
            self.item_rects[f"tools.menu.{menu}"] = im.get_item_rect()
            if not is_open:
                continue
            for caption, entries in found.items():
                im.indent(10.0)
                if caption:
                    accents.caption(tr(caption), colour_of(groups[caption]))
                    self.item_rects[f"tools.group.{menu}.{caption}"] = im.get_item_rect()
                    im.indent(10.0)
                for entry in entries:
                    shown += 1
                    label = entry_label(entry)
                    if im.selectable(
                        f"{label}##{entry.plugin_id}",
                        bool(self.instances(entry.plugin_id)),
                        icon=entry.icon or None,
                    ):
                        self.open_plugin(entry.plugin_id, new=True)
                    self.item_rects["tools." + entry.plugin_id] = im.get_item_rect()
                    accents.mark_item(accent(self.task_categories.get(entry.plugin_id)))
                    im.set_item_tooltip(entry_tooltip(entry))
                if caption:
                    im.unindent(10.0)
                im.unindent(10.0)
        if words and not shown:
            im.text_disabled(tr("No tool matches the filter."))

    def _draw_workspace_dock(self, box) -> None:
        self.workspace_docks.draw(box)

    def _draw_start(self, box) -> None:
        # The watermark sits in the workspace's top-right corner (_draw_workspace_background):
        # the Start text keeps clear of it.
        watermark = self.item_rects.get("system_info") or getattr(self, "_watermark_last", None)
        reserve = float(watermark[2]) + 24.0 if watermark else 0.0
        width = max(200.0, float(box[2]) - reserve)
        im.begin_child("##start text", (width, max(1.0, float(box[3]))), scrollable=False)
        try:
            self._draw_start_text()
        finally:
            im.end_child()

    def _draw_start_text(self) -> None:
        im.text_unformatted(tr("ChiSurf"))
        im.text_wrapped(
            tr(
                "Open a tool from the menu bar or the Tools panel: it opens as a dock beside the "
                "workspace, which can be moved, tabbed, floated or closed. The fits open here, as "
                "windows of the workspace."
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

    #: The watermark's samples of CPU and memory use (one a second), as the Qt sparklines kept.
    WATERMARK_SAMPLES = 60

    def _draw_workspace_background(self, rect) -> None:
        """The system-info watermark, faint in the workspace's top-right corner, under the fits.

        Where the Qt window painted it over its MDI area (``system_info_watermark.py``): a
        translucent panel 10 px from the corner with the CPU and memory sparklines and the
        machine, version and environment lines. Draw-list only: it takes no input.
        """
        import time

        from emtk.style import is_dark

        import chisurf
        from chisurf.core import info as _info_mod
        from chisurf.core.system_info import machine_info, process_usage, system_info_lines

        if getattr(self, "_system_lines", None) is None:
            self._system_lines = system_info_lines()
            self._usage_at = 0.0
            self._usage = None
            self._usage_history = []
        now = time.monotonic()
        if now - getattr(self, "_usage_at", 0.0) >= 1.0 or getattr(self, "_usage", None) is None:
            self._usage_at = now
            self._usage = process_usage()
            if self._usage is not None:
                history = getattr(self, "_usage_history", [])
                self._usage_history = (history + [self._usage])[-self.WATERMARK_SAMPLES :]

        fps = getattr(self, "_fps", 0.0)
        frame_ms = getattr(self, "_frame_ms", 0.0)
        try:
            cs_ver = getattr(_info_mod, "__version__", None) or getattr(chisurf, "__version__", "?")
        except Exception:
            cs_ver = "?"

        # Under the workspace's tab strip too (where its floating windows may go), not on it.
        x, y, w, h = (float(v) for v in self.docks.floating_bounds())
        style = im.get_style()
        dark = is_dark(style.color(im.Col.WINDOW_BG))
        panel = (0, 0, 0, 96) if dark else (0, 0, 0, 24)
        ink = (255, 255, 255, 120) if dark else (0, 0, 0, 120)
        track_fill = (255, 255, 255, 18) if dark else (0, 0, 0, 15)
        track_border = (255, 255, 255, 42) if dark else (0, 0, 0, 35)
        colours = (
            (100, 180, 220, 245),  # CPU: bright cyan/blue
            (100, 200, 100, 245),  # Mem: bright green
        )
        im.push_font_scale(0.85)
        try:
            line_h = max(im.get_text_line_height(), 13.0)
            pad = 6.0
            spark_w = 80.0
            folded = getattr(self, "_watermark_folded", False)

            if folded:
                cpu_s = f"CPU {self._usage[0]:.0f}%" if self._usage is not None else "CPU --"
                mem_s = f"Mem {self._usage[1]:.0f} MB" if self._usage is not None else "Mem --"
                fps_s = f"{fps:.0f} fps" if fps > 0.0 else "-- fps"
                badge_text = f"▶ ChiSurf {cs_ver} · {fps_s} · {cpu_s} · {mem_s}"
                text_w = im.calc_text_size(badge_text)[0]
                box_w = text_w + 2 * pad
                box_h = line_h + 2 * pad
                if box_w > w - 20.0 or box_h > h - 20.0:
                    return
                bx, by = x + w - box_w - 10.0, y + 10.0
                draw = im.get_window_draw_list()
                draw.add_rect_filled((bx, by), (bx + box_w, by + box_h), panel, 3.0)
                draw.add_text((bx + pad, by + pad), ink, badge_text)
                self.item_rects["system_info"] = (bx, by, box_w, box_h)
                self._watermark_pressed((bx, by, box_w, box_h))
                return

            rows: list[tuple[str, int]] = []  # (text, sparkline index or -1)
            fps_hdr = f" ({fps:.1f} fps · {frame_ms:.1f} ms)" if fps > 0.0 else ""
            rows.append((f"▼ ChiSurf {cs_ver}{fps_hdr}", -1))
            if self._usage is not None:
                cpu, mem = self._usage
                rows.append((tr("CPU: {cpu:.0f}%").format(cpu=cpu), 0))
                rows.append((tr("Mem: {mem:.0f} MB").format(mem=mem), 1))
            mach = machine_info()
            if mach:
                rows.append((f"Machine: {mach}", -1))
            rows += [(line, -1) for line in self._system_lines]
            text_w = max((im.calc_text_size(t)[0] for t, _ in rows), default=0.0)
            box_w = text_w + spark_w + 3 * pad
            box_h = len(rows) * line_h + 2 * pad
            if box_w > w - 20.0 or box_h > h - 20.0:
                return  # no room: a watermark never covers what it sits under
            bx, by = x + w - box_w - 10.0, y + 10.0
            draw = im.get_window_draw_list()
            draw.add_rect_filled((bx, by), (bx + box_w, by + box_h), panel, 3.0)
            for row, (text, spark) in enumerate(rows):
                ty = by + pad + row * line_h
                tx = bx + pad + (spark_w + pad if spark >= 0 else 0.0)
                draw.add_text((tx, ty), ink, text)
                if spark >= 0:
                    history = [sample[spark] for sample in getattr(self, "_usage_history", [])]
                    gx = bx + pad
                    gy = ty + 1.0
                    gh = max(4.0, line_h - 3.0)
                    draw.add_rect_filled((gx, gy), (gx + spark_w, gy + gh), track_fill, 2.0)
                    draw.add_rect((gx, gy), (gx + spark_w, gy + gh), track_border, 2.0)
                    if history:
                        top = max(100.0, max(history)) if spark == 0 else max(max(history) * 1.15, 50.0)
                        step = spark_w / max(self.WATERMARK_SAMPLES - 1, 1)
                        if len(history) < 2:
                            y_val = gy + gh - 1.0 - (history[0] / top) * (gh - 2.0)
                            points = [(gx + 1.0, y_val), (gx + spark_w - 1.0, y_val)]
                        else:
                            x0 = gx + spark_w - step * (len(history) - 1)
                            points = [
                                (x0 + i * step, gy + gh - 1.0 - (v / top) * (gh - 2.0))
                                for i, v in enumerate(history)
                            ]
                            if x0 > gx + 1.0:
                                points.insert(0, (gx + 1.0, points[0][1]))
                        draw.add_polyline(points, colours[spark], 0, 1.5)
            self.item_rects["system_info"] = (bx, by, box_w, box_h)
            self._watermark_pressed((bx, by, box_w, box_h))
        finally:
            im.pop_font_scale()

    def _watermark_pressed(self, rect) -> None:
        """Fold or unfold the watermark when a press lands on it, and on nothing drawn over it.

        The watermark lies under everything in the workspace, so a press is its own only when
        the workspace window it is drawn into is the window under the pointer: a fit window
        floating over it, a menu or popup opened over it (the workspace's window list), a dock
        or a tool in front all come later in the display list and take the press. Hit-tested
        in :meth:`pointer_press` against its rectangle alone, it once ate every click in its
        corner -- a tool's filter row, the window list's rows.
        """
        if not (im.is_mouse_clicked(0) and im.is_window_hovered()):
            return
        if self._plugin_at(*im.get_mouse_pos()) is not None:
            return  # a hosted tool is drawn over the workspace here
        wx, wy, ww, wh = rect
        mx, my = im.get_mouse_pos()
        if wx <= mx <= wx + ww and wy <= my <= wy + wh:
            self._watermark_folded = not getattr(self, "_watermark_folded", False)
            self.request_frame()

    def _draw_console(self, box) -> None:
        self.host_child("console", "console", self.console_terminal, box)
        bx, by = box[:2]
        for k, rect in list(self.console.item_rects.items()):
            if len(rect) == 4 and rect[1] < by:
                rx, ry, rw, rh = rect
                offset_rect = (rx + bx, ry + by, rw, rh)
                self.console.item_rects[k] = offset_rect
                self.item_rects[k] = offset_rect
        for k, (cx, cy, cw, ch) in list(self.console.control.boxes.items()):
            if cy < by:
                self.console.control.boxes[k] = (cx + bx, cy + by, cw, ch)
        if self.console.control.image_boxes:
            new_img_boxes = []
            for ix, iy, iw, ih, img in self.console.control.image_boxes:
                if iy < by:
                    new_img_boxes.append((ix + bx, iy + by, iw, ih, img))
                else:
                    new_img_boxes.append((ix, iy, iw, ih, img))
            self.console.control.image_boxes = new_img_boxes

    def _draw_log(self, box) -> None:
        self.log.draw(box)

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
            if key == "workspace" and hasattr(self, "workspace_docks"):
                ws_order = list(reversed(self.workspace_docks.floating()))
                ws_order += [self.workspace_docks.active_tab(r) for r in self.workspace_docks.regions]
                for ws_key in ws_order:
                    if not ws_key or not self.workspace_docks.is_shown(ws_key):
                        continue
                    ws_win = self.workspace_docks.window(ws_key)
                    ws_frame = ws_win.frame if ws_win else None
                    if ws_frame is None or not (
                        ws_frame[0] <= x < ws_frame[0] + ws_frame[2]
                        and ws_frame[1] <= y < ws_frame[1] + ws_frame[3]
                    ):
                        continue
                    for child_id, (window_key, _app, box) in self._drawn.items():
                        bx, by, bw, bh = box
                        if window_key == ws_key and bx <= x < bx + bw and by <= y < by + bh:
                            return child_id
                    return None
                return None
            for child_id, (window_key, _app, box) in self._drawn.items():
                bx, by, bw, bh = box
                if window_key == key and bx <= x < bx + bw and by <= y < by + bh:
                    return child_id
            return None
        return None

    def _hidden_busy(self, hosted: HostedPlugin) -> bool:
        if hosted.app is None or hosted.key in self._drawn or not callable(getattr(hosted.app, "poll", None)):
            return False
        try:
            return bool(hosted.app.animating())
        except Exception:  # noqa: BLE001 - a tool that cannot say is not kept awake
            return False

    def _poll_hidden_tools(self) -> None:
        """Let every tool not drawn last frame collect its finished background work.

        The shell draws only the tools in front; a tool's code otherwise runs only while
        it is drawn, so a file opened in a tool tabbed behind another did not finish
        loading until that tab was shown. A tool declaring ``poll()`` gets it instead.
        """
        drawn = getattr(self, "_drawn", {})
        for hosted in list(self.hosted.values()):
            poll = getattr(hosted.app, "poll", None) if hosted.app is not None else None
            if callable(poll) and hosted.key not in drawn:
                try:
                    poll()
                except Exception:  # noqa: BLE001 - one tool failing must not stop the frame
                    _log.exception("polling %s failed", hosted.instance_id)

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
        # The watermark (the workspace's background) folds in the frame, not here: only the
        # frame knows what is drawn over it (_watermark_pressed).
        self._capture = target
        # A press outside a child never reaches it, so it cannot see the press that closes its context menu
        # or list; it is told here. Otherwise the menu stays up and holds the child's input until a click
        # inside it closes the menu instead of landing where it was aimed.
        for child_id, (_window_key, child, _box) in self._drawn.items():
            if child_id != target:
                overlays.dismiss(getattr(child, "storage", None))
        if target is not None:
            self._focus = target
        elif not self._menu_open:
            self._focus = None
        super().pointer_press(x, y, button, modifiers, clicks)
        child, (ox, oy) = self._child(target)
        from emtk.native import input_trace

        input_trace.debug("shell press (%.1f, %.1f) -> %s at (%.1f, %.1f)", x, y, target,
                          x - ox, y - oy)
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
        for child_id, (_window_key, other_child, _box) in self._drawn.items():
            if child_id != target and other_child is not None and getattr(other_child, "io", None) is not None:
                if other_child.io.mouse_pos != (-1.0, -1.0):
                    other_child.pointer_move(-1.0, -1.0, 0, 0)
                    self.request_frame()
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
        from emtk.keys import KEY_ESCAPE

        if self.project.modal or (self._menu_open and key == KEY_ESCAPE):
            return super().key(key, text, modifiers)
        if hasattr(self, "workspace_docks") and self.workspace_docks.handle_key(key, modifiers):
            self.docks.show("workspace")
            self.docks.focus("workspace")
            self.request_frame()
            return True
        if self.docks.handle_key(key, modifiers):
            self.request_frame()
            return True  # Ctrl+Tab cycles the workspace's windows, whoever has the keys
        focus_id = self._focus or (self.docks.focused if self.docks.focused in self._drawn else None)
        child, _origin = self._child(focus_id)
        if self._shortcut(key, modifiers, child):
            return True
        if child is not None:
            self._key_owners[int(key)] = child
            return child.key(key, text, modifiers)
        return super().key(key, text, modifiers)

    def key_release(self, key, text="", modifiers=0):
        """A key came up: tell the child that took its press, as the native and Qt hosts tell a tool.

        Without it a game docked here never saw a key go up -- the key stayed held, so Tetris
        auto-repeated the move and Pong's paddle kept going after release. The press's owner gets
        it even when the focus moved on meanwhile; a release with no recorded press goes to the
        focused child.
        """
        child = self._key_owners.pop(int(key), None)
        if child is None:
            focus_id = self._focus or (self.docks.focused if self.docks.focused in self._drawn else None)
            child, _origin = self._child(focus_id)
        release = getattr(child, "key_release", None) if child is not None else None
        if callable(release):
            return release(key, text, modifiers)
        return False

    def focus_lost(self):
        """The window lost the keyboard (the Qt host says so; no releases follow): release held keys."""
        owners, self._key_owners = self._key_owners, {}
        for key, child in owners.items():
            release = getattr(child, "key_release", None)
            if callable(release):
                try:
                    release(key, "", 0)
                except Exception:  # noqa: BLE001 - one tool failing must not keep the others' keys held
                    _log.exception("releasing a key in %r failed", child)

    def compose(self, text, cursor=None):
        """The input method's composition goes where the keys go: the focused child, else the shell."""
        if not self.project.modal:
            focus_id = self._focus or (self.docks.focused if self.docks.focused in self._drawn else None)
            child, _origin = self._child(focus_id)
            if child is not None and callable(getattr(child, "compose", None)):
                return child.compose(text, cursor)
        return super().compose(text, cursor)

    def ime_caret(self):
        """The caret of the focused text, in the shell's coordinates (a child's is offset by its box)."""
        focus_id = self._focus or (self.docks.focused if self.docks.focused in self._drawn else None)
        child, (ox, oy) = self._child(focus_id)
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
        if (
            (child is None or child is getattr(self, "console_terminal", None))
            and self.console.control.has_focus
            and self.console.claims(key, modifiers)
        ):
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
        """Hand dropped files to the child under the pointer when it takes them, else read them as data.

        The drop goes where it was dropped, not to the child that has the keys: the platform
        delivers the drop position as a pointer move first (:meth:`emtk.native.CanvasEvents.files_dropped`).
        """
        child, _origin = self._child(self._plugin_at(*self.io.mouse_pos))
        if child is not None:
            for name in ("on_paths_dropped", "on_files_dropped", "files_dropped"):
                handler = getattr(child, name, None)
                if callable(handler) and handler(paths) is not False:
                    return True
        return self.data.drop([str(path) for path in paths or ()])

    # ── status strip ──────────────────────────────────────────────────────

    def stage_started(self, payload: dict) -> None:
        """A startup stage began (the session's worker thread): the splash and the strip show it."""
        self._stage = dict(payload or {})
        if self.splash is not None:
            self.splash.stage_started(payload)
        self.request_frame()

    def begin_task(self, message: str, maximum: int = 0, cancel=None):
        """Show an operation on the status strip (the progress-host contract of the Qt status bar)."""
        return self.status_strip.begin_task(message, maximum, cancel=cancel)

    def feed_status_strip(self) -> None:
        """Once per frame: the status lines and the operations under way go onto the strip.

        The message follows the shell's, the data docks' and the project's status lines (newest
        change wins; log records arrive by themselves). The operations: the session's startup
        stages, an API call on the data docks' worker (size unknown) and a sampling job on the
        server (its percentage, ✕ asks the server to stop).
        """
        strip = self.status_strip
        strip.follow("shell", self.status)
        strip.follow("data", self.data.status)
        strip.follow("project", self.project.status)
        data = self.data
        stage = self._stage if data.starting else {}
        job = data.job
        sampling = data.sampling_job
        post_show = self.post_show
        late = post_show.stage if post_show is not None and post_show.running else {}
        wanted = {
            "startup": (id(data), stage.get("label") or tr("Starting the session…"), 100)
            if data.starting
            else None,
            "call": (id(job), job.label, 0) if job is not None else None,
            "sampling": (sampling, tr("Sampling…"), 100) if sampling else None,
            "post_show": (id(post_show), tr(late["label"]), 100) if late.get("label") else None,
        }
        for kind, want in wanted.items():
            held = self._strip_tasks.get(kind)
            if want is None:
                if held is not None:
                    held[1].close()
                    del self._strip_tasks[kind]
                continue
            identity, text, maximum = want
            if held is None or held[0] != identity:
                if held is not None:
                    held[1].close()
                cancel = self._cancel_sampling if kind == "sampling" else None
                held = (identity, strip.begin_task(text, maximum, cancel=cancel))
                self._strip_tasks[kind] = held
            task = held[1]
            task.setLabelText(text)
            if kind == "startup":
                task.setValue(int(stage.get("progress") or 0))
            elif kind == "sampling":
                task.setValue(int(data.sampling_progress))
            elif kind == "post_show":
                task.setValue(int(late.get("progress") or 0))

    def _cancel_sampling(self) -> None:
        """✕ on a sampling job: ask the server to stop it."""
        data = self.data
        if data.session is not None and data.sampling_job:
            try:
                data.session.api.cancel_sampling(data.sampling_job)
            except Exception as exc:  # noqa: BLE001 - the strip says it
                self.status_strip.show_message(tr("Cancel failed: {error}").format(error=exc))

    def animating(self) -> bool:
        busy = any(hosted.build is not None for hosted in self.hosted.values()) or self.data.busy
        busy = busy or self.status_strip.animating()
        busy = busy or self.project.busy
        children = any(app.animating() for _key, app, _box in self._drawn.values())
        # A tool behind another tab still finishing work (a file loading) keeps the shell
        # waking, so _poll_hidden_tools can land it.
        children = children or any(self._hidden_busy(hosted) for hosted in self.hosted.values())
        # The watermark's sparklines refresh once a second through next_frame_in; asking for
        # every frame instead kept an idle window drawing ~60 frames a second for good.
        return super().animating() or busy or children

    def next_frame_in(self):
        delays = [super().next_frame_in(), self.project.next_frame_in()]
        delays += [app.next_frame_in() for _key, app, _box in self._drawn.values()]
        now = time.monotonic()
        usage_age = now - getattr(self, "_usage_at", 0.0)
        delays.append(max(0.05, 1.0 - usage_age))
        return min((delay for delay in delays if delay is not None), default=None)

    # ── persistence ───────────────────────────────────────────────────────

    @property
    def native_layouts(self) -> dict[str, DockManager]:
        return {"shell": self.docks, "workspace": self.workspace_docks}

    def export_settings(self) -> dict:
        """The plugins open in the shell and the ribbon's pin (with a pinned ribbon's fold and tab)."""
        return {"open": list(self.hosted), "ribbon": self.ribbon.ribbon.state()}

    def restore_settings(self, state: dict) -> None:
        """Reopen the plugins that were open (each built on its worker thread); put the ribbon back as pinned."""
        self.ribbon.ribbon.restore((state or {}).get("ribbon"))
        for plugin_id in (state or {}).get("open", []):
            if str(plugin_id).partition("#")[0] in self.by_id:  # "ndxplorer#2" reopens as #2
                self.open_plugin(plugin_id, focus=False)

    def close(self) -> None:
        """Close every hosted plugin, the fit windows and the session, and detach the log handler.

        Once: a host that closes its window after the shell was closed (a test's offscreen canvas collected at
        interpreter exit) must not tear the console down a second time.
        """
        if getattr(self, "_shell_closed", False):
            return
        self._shell_closed = True
        global _ACTIVE_SHELL
        if _ACTIVE_SHELL is not None and _ACTIVE_SHELL() is self:
            _ACTIVE_SHELL = None
        from chisurf.core.plugin.handoff import uninstall_host

        uninstall_host(self)
        for plugin_id in list(self.hosted):
            self.close_plugin(plugin_id)
        self.console.close()
        if hasattr(self, "console_terminal"):
            self.console_terminal.close()
        self._close_console_channel()
        self.project.close()
        self.data.close()
        self.log.close()
        self.status_strip.close()


def host_in_shell(plugin_id: str, then: Callable[[], Any] | None = None) -> bool:
    """Open *plugin_id* as a dock of the shell open in this process; ``then()`` once it is built.

    The help browser and the code editor used to open as a second process with its own OS window, which
    went behind the main window on the next click into it. With the shell open they are its docks
    instead (tools are docks, never windows of the workspace). Returns ``False`` when no shell is open (or it does not offer the plugin), and the caller
    goes on as before.
    """
    shell = _ACTIVE_SHELL() if _ACTIVE_SHELL is not None else None
    if shell is None or getattr(shell, "_shell_closed", False) or plugin_id not in shell.by_id:
        return False
    hosted = shell.open_plugin(plugin_id)
    if hosted is None:
        return False
    if then is not None:
        hosted.on_ready.append(then)
        if hosted.app is not None and hosted.build is None:
            shell._run_ready(hosted)
    shell.request_frame()
    return True


def make_app(persist: bool = True, splash: Any = None) -> EmtkShellApp:
    """The shell app with its session; with *persist* its dock layout, size and open plugins are kept.

    *splash* (:class:`chisurf.emtk.splash.SplashState`) hears the session's startup stages.
    """
    from chisurf.emtk.session import start_session

    # The update check runs for the real window (persisted), not a figure's.
    app = EmtkShellApp(session_factory=start_session, splash=splash, post_show=persist)
    if persist:
        from chisurf.emtk.state import attach_native_state

        attach_native_state(SHELL_ID, app)
    return app


def make_headless_app() -> EmtkShellApp:
    """The shell for a headless frame (``--screenshot``, an offscreen canvas): nothing persisted.

    A screenshot must not read the user's layout (the picture would depend on it) nor write it
    back (it would replace the user's own), and it does not ask the update server.
    """
    return make_app(persist=False)


def main(argv: list[str] | None = None) -> int:
    """Open the emtk shell (``python -m chisurf``): the splash window first, the main window when ready.

    ``--screenshot PATH`` (and ``--backend offscreen``) render one frame of the shell offscreen
    through :func:`emtk.native.main`, without a splash; ``--size WxH`` sets the main window's size.
    """
    from chisurf.core.settings import theme as stored_theme
    from chisurf.core.settings.fonts import apply_stored
    from chisurf.emtk.i18n import install

    install(None)
    # The font settings (Settings ▸ Fonts) before the first window draws: sizes, faces, zoom.
    apply_stored()
    # The colour theme (Settings ▸ Theme), likewise before the first frame.
    stored_theme.apply_stored()
    args = list(argv or [])
    headless = "--screenshot" in args or any(
        arg == "offscreen" or arg.endswith("=offscreen") for arg in args
    )
    if headless or not _interactive_display():
        from emtk.native import main as run_native

        return int(
            run_native(
                ["--app", "chisurf.emtk.main_app:make_headless_app", "--title", "ChiSurf", *args]
            )
            or 0
        )
    size = None
    if "--size" in args and args.index("--size") + 1 < len(args):
        width, _, height = args[args.index("--size") + 1].partition("x")
        size = (int(width), int(height or width))
    from chisurf.emtk.splash import run_with_splash

    return run_with_splash(make_app, title="ChiSurf", size=size)


def _interactive_display() -> bool:
    """Whether a desktop window can open (an interactive rendercanvas backend is importable)."""
    import os

    if os.environ.get("EMTK_CANVAS", "").strip() == "offscreen":
        return False
    from emtk.native import canvas_module

    return canvas_module().__name__.rsplit(".", 1)[-1] != "offscreen"


__all__ = [
    "EmtkShellApp",
    "HostedPlugin",
    "MIN_TILE",
    "MenuEntry",
    "host_in_shell",
    "main",
    "make_app",
    "make_headless_app",
    "menu_entries",
    "tile_grid",
]
