"""The emtk shell's ribbon, plugin menus and Tools tree: one layout, read from the plugin manifests.

A plugin's manifest ``display_name`` is its address (``"Tab:Group:Name"``) and its ``icon`` its
pictogram. :func:`plugin_tree` places every native plugin the shell offers with the same rules
the Qt ribbon uses (:mod:`chisurf.core.plugin.ribbon_layout`: tab order, the authored group
order, ``plugin_order``, ``disabled_plugins``), so the ribbon, the menu bar and the Tools dock
list the same tools in the same order under the same captions, each with its manifest icon.

:class:`ShellRibbon` is the ribbon itself (:class:`emtk.ribbon.Ribbon`): the plugin tabs, plus
the Qt ribbon's built-in groups drawn from the shell's own session actions -- *File* (Recent,
Project, Fits, Application) and *Main* (Window) -- and in its corner the help button and the
language switch. Its pin (in the tab row) keeps the fold and the tab between sessions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from emtk.i18n import mark, tr
from emtk.ribbon import Ribbon, RibbonButton, RibbonGroup, RibbonTab

from chisurf.core.plugin.maturity import maturity_markers, maturity_warnings
from chisurf.core.plugin.ribbon_layout import ordered_tabs, plugin_layout
from chisurf.plugins.emtk_layout import ACTIONS

__all__ = [
    "ACTION_ICONS",
    "FILE_GROUPS",
    "WINDOW_ACTIONS",
    "ShellRibbon",
    "menu_tree",
    "plugin_tree",
]

#: The File tab's session groups, as the Qt ribbon's ``ribbon_file.FILE_ACTION_GROUPS``, by the
#: shell's session action keys (``EmtkShellApp.session_menus``). *Recent* comes first and is
#: built from the recent projects.
FILE_GROUPS = (
    (
        mark("Project"),
        ("open_project", "save_project", "export_project", "import_project", "close_project"),
    ),
    (mark("Fits"), ("load_fit", "save_fit", "save_all_fits", "close_fit", "close_all_fits")),
    (mark("Application"), ("quit", "reinitialize")),
)
#: The captions the ribbon gives its built-in tabs and groups (the plugins' come from their manifests).
BUILT_IN_CAPTIONS = (mark("Main"), mark("Recent"), mark("Window"))
#: The Main tab's *Window* group: the Qt toolbar's window actions.
WINDOW_ACTIONS = ("add_dataset", "tile_windows", "tab_windows", "reset_layout", "screenshot")

#: The pictogram of every session action, in the ribbon and in the menus. The actions every
#: window shares take their icon from the one vocabulary (:data:`chisurf.plugins.emtk_layout.ACTIONS`).
ACTION_ICONS = {
    "add_dataset": "➕",
    "open_project": ACTIONS["open"].icon,
    "save_project": ACTIONS["save"].icon,
    "export_project": ACTIONS["export"].icon,
    "import_project": "📥",
    "close_project": ACTIONS["close"].icon,
    "load_fit": ACTIONS["open"].icon,
    "save_fit": ACTIONS["save"].icon,
    "save_all_fits": "🗃️",
    "close_fit": "❎",
    "close_all_fits": "🧹",
    "reinitialize": ACTIONS["restart"].icon,
    "quit": "🚪",
    "clear_recent": "🧹",
    "recent": "🕘",
    "tile_windows": "🪟",
    "tab_windows": "🗂️",
    "cascade_windows": "📚",
    "reset_layout": ACTIONS["reset"].icon,
    "screenshot": "📸",
    "undo": "↩️",
    "redo": "↪️",
    "record": "⏺️",
    "run_macro": ACTIONS["run"].icon,
    "settings_edit": "⚙️",
    "fret_rda_axis": "📏",
    "data_loading": "🚚",
    "reset_local_settings": ACTIONS["reset"].icon,
    "clear_logging_files": "🧹",
    "clear_user_styles": "🧹",
    "clear_user_plugins": "🧹",
    "styles": "🎨",
}


def _settings() -> tuple[dict, bool]:
    """``(plugins settings, experimental)`` of the user's settings; the shipped defaults when unreadable."""
    try:
        from chisurf.core.settings import cs_settings
    except Exception:  # noqa: BLE001 - the shell still lists its tools with the default order
        return {}, False
    return (cs_settings.get("plugins") or {}), bool(cs_settings.get("enable_experimental", False))


def plugin_tree(
    entries, settings: dict | None = None, experimental: bool | None = None
) -> dict[str, dict[str, list]]:
    """``{tab: {group: [MenuEntry]}}`` in ribbon order -- the Qt ribbon's placement of *entries*.

    Parameters
    ----------
    entries : iterable of MenuEntry
        The shell's plugins (:func:`chisurf.emtk.main_app.menu_entries`).
    settings, experimental : optional
        The ``plugins`` settings (``plugin_order``, ``disabled_plugins``) and experimental mode;
        the user's by default.
    """
    if settings is None or experimental is None:
        user, mode = _settings()
        settings = user if settings is None else settings
        experimental = mode if experimental is None else experimental
    records = [
        {
            "plugin_name": ":".join(entry.path),
            "module_name": entry.plugin_id,
            "cli_only": entry.cli_only,
            "entry": entry,
        }
        for entry in entries
    ]
    layout = plugin_layout(records, settings, experimental)
    return {
        tab: {group: [record["entry"] for record in records] for group, records in groups.items()}
        for tab, groups in layout.items()
    }


def menu_tree(
    entries, settings: dict | None = None, experimental: bool | None = None
) -> dict[str, dict[str, list]]:
    """``{menu: {caption: [MenuEntry]}}`` for the menu bar and the Tools dock.

    The ribbon's tabs are the menus, except that its *Main* tab's *Help* group is a *Help* menu
    of its own, which comes last. A group named after its tab has no caption (``""``).
    """
    tree: dict[str, dict[str, list]] = {}
    for tab, groups in plugin_tree(entries, settings, experimental).items():
        for group, items in groups.items():
            menu = "Help" if (tab, group) == ("Main", "Help") else tab
            caption = "" if group == menu else group
            tree.setdefault(menu, {}).setdefault(caption, []).extend(items)
    order = [menu for menu in ordered_tabs(tree) if menu != "Help"] + (
        ["Help"] if "Help" in tree else []
    )
    return {menu: tree[menu] for menu in order}


def entry_label(entry) -> str:
    """The entry's caption with its maturity markers (``Decay Analysis ⚠️``), translated."""
    from emtk.im_widgets import icon_text

    markers = maturity_markers({"experimental": entry.experimental, "deprecated": entry.deprecated})
    # In running text a marker loses its emoji presentation selector, which would draw as a box.
    return " ".join([tr(entry.label), *map(icon_text, markers)])


def entry_tooltip(entry) -> str:
    """The entry's description, after its maturity warnings."""
    meta = {"experimental": entry.experimental, "deprecated": entry.deprecated}
    lines = maturity_warnings(meta, tr(entry.label))
    if entry.description:
        lines.append(tr(entry.description))
    return "\n".join(lines) or tr("Open {name}").format(name=tr(entry.label))


class ShellRibbon:
    """The shell's ribbon: tabs from :func:`plugin_tree` plus the session groups of *File* and *Main*.

    Parameters
    ----------
    shell : EmtkShellApp
        Opens plugins (``open_plugin``) and provides the session actions (``session_menus``).
    """

    def __init__(self, shell: Any) -> None:
        self.shell = shell
        #: With the pin: pinned keeps the fold and the tab as the user left them, also at the
        #: next start (the shell saves :meth:`emtk.ribbon.Ribbon.state`); unpinned folds after each pick.
        self.ribbon = Ribbon(name="ribbon", pin=True)
        self._plugins = plugin_tree(shell.entries)

    # -- the model ---------------------------------------------------------- #
    def _actions(self) -> dict[str, Any]:
        actions: dict[str, Any] = {}

        def _collect(items):
            for action in items:
                actions[action.key] = action
                if getattr(action, "children", None):
                    _collect(action.children)

        for _menu, items in self.shell.session_menus():
            _collect(items)
        actions.update({action.key: action for action in self.shell.window_actions()})
        return actions

    @staticmethod
    def _action_button(action, large: bool = False) -> RibbonButton:
        return RibbonButton(
            "action." + action.key,
            action.label,
            ACTION_ICONS.get(action.key, ""),
            tooltip=action.description or action.label,
            large=large,
            enabled=action.enabled,
            on_press=action.run,
        )

    def _plugin_button(self, entry, large: bool, accent=None) -> RibbonButton:
        plugin_id = entry.plugin_id
        return RibbonButton(
            "plugin." + plugin_id,
            entry_label(entry),
            entry.icon,
            tooltip=entry_tooltip(entry),
            large=large,
            on_press=lambda: self.shell.open_plugin(plugin_id, new=True),
            accent=accent,
        )

    def _recent_group(self, actions) -> RibbonGroup:
        project = self.shell.project
        buttons = [
            RibbonButton(
                f"recent.{index}",
                Path(path).name or path,
                ACTION_ICONS["recent"],
                tooltip=str(path),
                on_press=lambda p=path: project.open_recent(p),
                enabled=lambda: project.channel is not None,
            )
            for index, path in enumerate(project.recent[:9])
        ]
        if buttons:
            buttons.append(
                RibbonButton(
                    "action.clear_recent",
                    mark("Clear List"),
                    ACTION_ICONS["clear_recent"],
                    tooltip=mark("Clear recent projects list"),
                    on_press=project.clear_recent,
                )
            )
        else:
            buttons = [
                RibbonButton(
                    "recent.none", mark("No recent projects"), ACTION_ICONS["recent"], enabled=False
                )
            ]
        return RibbonGroup("Recent", buttons)

    def tabs(self) -> list[RibbonTab]:
        """The ribbon's tabs now (the session groups' enabled states and recent projects are live).

        Each group wears the colour of its kind of task (:mod:`chisurf.emtk.task_colors`) on its
        caption and underline; a tool of another kind than its group's (Wizards among the
        Calculators) carries a bar of its own colour.
        """
        from chisurf.emtk.task_colors import accent, group_category

        categories = getattr(self.shell, "task_categories", {})
        actions = self._actions()
        built: dict[str, list[RibbonGroup]] = {
            "File": [self._recent_group(actions)]
            + [
                RibbonGroup(
                    title, [self._action_button(actions[key]) for key in keys if key in actions]
                )
                for title, keys in FILE_GROUPS
            ],
            "Main": [
                RibbonGroup(
                    "Window",
                    [self._action_button(actions[key]) for key in WINDOW_ACTIONS if key in actions],
                )
            ],
        }
        for tab, groups in self._plugins.items():
            for group, entries in groups.items():
                large = len(entries) == 1
                kind = group_category(tab, group)
                buttons = []
                for entry in entries:
                    own = categories.get(entry.plugin_id, kind)
                    buttons.append(
                        self._plugin_button(entry, large, accent(own) if own != kind else None)
                    )
                built.setdefault(tab, []).append(RibbonGroup(group, buttons))
        for tab, tab_groups in built.items():
            for ribbon_group in tab_groups:
                ribbon_group.accent = ribbon_group.accent or accent(
                    group_category(tab, ribbon_group.title)
                )
        return [RibbonTab(tab, built[tab]) for tab in ordered_tabs(built)]

    # -- drawing ------------------------------------------------------------ #
    def menu_open(self) -> bool:
        """Whether a menu of the ribbon (a collapsed group, the overflow, the languages) is open."""
        from emtk import im

        return self.ribbon.menu_open or im.is_popup_open("##ribbon languages")

    def height(self) -> float:
        """The height the ribbon needs now."""
        return self.ribbon.height()

    def draw(self, box) -> str | None:
        """Draw into *box*; the pressed button's action has run when this returns its key."""
        self.ribbon.tabs = self.tabs()
        if not self.ribbon.current:
            self.ribbon.current = (
                "Spectroscopy" if any(t.title == "Spectroscopy" for t in self.ribbon.tabs) else ""
            )
        pressed = self.ribbon.draw(box, corner=self._draw_corner)
        self.shell.item_rects.update(self.ribbon.item_rects)
        return pressed

    def _draw_corner(self, right: float, top: float, height: float) -> float:
        """The help button and the language switch, right-aligned at *right*."""
        from emtk import i18n as toolkit_i18n
        from emtk import im

        from chisurf.emtk.i18n import LANGUAGE_DISPLAY_NAMES, SUPPORTED_LOCALES, choose_language
        from chisurf.plugins.emtk_layout import action_button, icon_label

        current = toolkit_i18n.get_locale().split("-")[0].split("_")[0]
        language = f"🌍 {current.upper()}"
        padding = im.get_style().frame_padding[0] * 2.0
        width_language = im.calc_text_size(language)[0] + padding
        width_help = (
            im.calc_text_size(icon_label(ACTIONS["help"].icon, tr(ACTIONS["help"].label)))[0]
            + padding
        )
        x = right - width_language - width_help - 4.0
        im.set_cursor_screen_pos((x, top))
        # The shared Help action (one icon, label and tooltip in every window); it opens the documentation.
        if (
            action_button("help", id="ribbon help", size=(width_help, height))
            and "help" in self.shell.by_id
        ):
            self.shell.open_plugin("help")
        self.shell.item_rects["ribbon.help"] = im.get_item_rect()
        im.set_cursor_screen_pos((x + width_help + 4.0, top))
        if im.button(language + "##ribbon language", (width_language, height)):
            rect = im.get_item_rect()
            from emtk.im_core import get_current_context

            get_current_context().open_context_popup(
                "##ribbon languages", (rect[0], rect[1] + rect[3])
            )
        name = LANGUAGE_DISPLAY_NAMES.get(current, current)
        im.set_item_tooltip(tr("Language: {name}").format(name=name))
        self.shell.item_rects["ribbon.language"] = im.get_item_rect()
        if im.begin_popup("##ribbon languages"):
            for code in SUPPORTED_LOCALES:
                label = LANGUAGE_DISPLAY_NAMES.get(code, code)
                if im.menu_item(f"{label} ({code})", selected=code == current):
                    choose_language(code)
            im.end_popup()
        return width_language + width_help + 8.0
