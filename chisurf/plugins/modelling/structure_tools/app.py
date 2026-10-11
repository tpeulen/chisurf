"""Native EMTK structure-modelling workspace.

The native counterpart of the Qt ``StructureToolsTool`` navigation hub: a nav
sidebar of the structure tools (with the Qt hub's search box and its Back and
Next steppers) and lazy, state-preserving child apps, in the same mechanics as
the trajectory-tools and games hubs. Every tool has a native app: the FPS JSON
editor, docking and QuEst are the cards in ``cards/``.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

from emtk import i18n, im
from emtk.app import ImApp

from chisurf.emtk.background_build import BackgroundBuild, draw_opening
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.emtk.plugin_icons import entry_icon
from chisurf.plugins.emtk_layout import action_button, window_size

from .registry import STRUCTURE_TOOL_PANELS
from .strings import install_translations

install_translations()


def tr(text: str) -> str:
    return i18n.tr(text, context="Structure Tools")


class StructureToolsHubApp(ImApp):
    """Keep each structure tool alive while the user works in another.

    A plugin that hosts a few of the tools (or tools of its own) in the same window subclasses this and sets
    :attr:`ENTRIES` (``name``, ``group``, ``description``, ``emtk`` factory ``"module:attr"`` per tool), :attr:`TITLE`
    and, for a short list, :attr:`COMPACT` (no search box, no Back / Next).
    """

    ENTRIES = STRUCTURE_TOOL_PANELS
    TITLE = "Structure Tools"
    COMPACT = False
    #: The width of the list in a compact hub (the names are short, the tool gets the room).
    NAV_WIDTH = 150.0
    #: ``guide.json`` / ``help.md`` of the hub itself; ``None`` leaves the hub without Guide and Help buttons.
    GUIDE_FILE: Path | None = None
    HELP_FILE: Path | None = None

    def __init__(self) -> None:
        primary = json.loads((Path(__file__).parent / "gui/window.view.json").read_text())
        self.window_size = window_size(primary, (1100, 720))
        self.entries = self.ENTRIES
        self.selected = self.entries[0]["name"]
        self.children: dict[str, ImApp] = {}
        self._pending_state: dict[str, dict] = {}
        self.error = ""
        self.search = ""
        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        self.child_box = (180.0, 86.0, 880.0, 644.0)
        self._painter = None
        #: The tool shown when the hub opens is made on a worker thread, behind an "Opening" placeholder.
        self._builder = BackgroundBuild(wake=self.request_frame)
        self._prebuilt: dict[str, tuple] = {}
        if self.GUIDE_FILE is not None:
            self.tour = EmTkGuidedTour(
                self.GUIDE_FILE,
                get_target_rect=self.item_rects.get,
                owner=self,
                wait_for_controls=True,
            )
            self.help_window = EmTkHelpWindow(
                title=f"{self.TITLE} - Help",
                resource=self.HELP_FILE,
                owner=self,
                on_start_guide=self.tour.start,
            )
        super().__init__(self.render)

    @property
    def child(self):
        return self.children.get(self.selected)

    def select(self, name: str):
        entry = next((item for item in self.entries if item["name"] == name), None)
        if entry is None:
            raise ValueError(f"Unknown tool: {name}")
        self.selected = name
        self.error = ""
        factory = entry["emtk"]
        if not factory:
            self.error = f"{tr('Tool unavailable')}: no native app"
        elif name not in self.children:
            if self._builder.building(name):
                self._prebuilt.update(self._builder.collect(wait=True) or {})
            try:
                made, exc = self._prebuilt.pop(name, (None, None))
                if exc is not None:
                    raise exc
                self.children[name] = made if made is not None else self._make(factory)
            except Exception as exc:  # noqa: BLE001 - surface child load errors inline
                self.error = f"{tr('Tool unavailable')}: {exc}"
            else:
                saved = self._pending_state.pop(name, None)
                restore = getattr(self.children[name], "restore_settings", None)
                if saved and callable(restore):
                    restore(saved)
        self.request_frame()
        return self.child

    @staticmethod
    def _make(factory: str):
        """Import and construct a tool's app (may run on the build thread)."""
        module, attr = factory.split(":", 1)
        return getattr(importlib.import_module(module), attr)()

    def close(self):
        self._prebuilt.clear()
        self._builder.collect(wait=True)
        if self.GUIDE_FILE is not None:
            self.tour.stop()
        for child in self.children.values():
            close = getattr(child, "close", None)
            if callable(close):
                close()
        self.children.clear()

    def animating(self):
        return (
            super().animating() or self._builder.busy or bool(self.child and self.child.animating())
        )

    def next_frame_in(self):
        values = [super().next_frame_in()]
        if self.child is not None:
            values.append(self.child.next_frame_in())
        return min((value for value in values if value is not None), default=None)

    def draw(self, painter, x, y, w, h):
        self._painter = painter
        try:
            if self.child is None and not self.error:
                self._prebuilt.update(self._builder.collect() or {})
                entry = next(item for item in self.entries if item["name"] == self.selected)
                if self.selected in self._prebuilt or not entry["emtk"]:
                    self.select(self.selected)
                elif not self._builder.busy:
                    self._builder.start(
                        {self.selected: lambda f=entry["emtk"]: self._make(f)},
                        name="chisurf-structure-tools",
                    )
            super().draw(painter, x, y, w, h)
        finally:
            self._painter = None

    def visible_entries(self) -> list[dict]:
        """The tools the search box lets through (all of them while it is empty)."""
        needle = self.search.strip().lower()
        if not needle:
            return list(self.entries)
        return [
            e
            for e in self.entries
            if needle in e["name"].lower() or needle in e["description"].lower()
        ]

    def step(self, direction: int):
        """The Back / Next buttons: the neighbouring tool of the list (the ends stay where they are)."""
        names = [e["name"] for e in self.entries]
        index = max(0, min(len(names) - 1, names.index(self.selected) + direction))
        return self.select(names[index])

    # ── render ──────────────────────────────────────────────────────────
    def render(self):
        width, height = im.get_main_viewport().size
        # Wide enough that the longest entry plus its "soon" marker stays
        # inside the sidebar at narrow host widths.
        nav_width = self.NAV_WIDTH if self.COMPACT else min(200.0, max(190.0, width * 0.26))
        entry = next(item for item in self.entries if item["name"] == self.selected)
        im.set_next_window_pos((0, 0), im.Cond.ALWAYS)
        im.set_next_window_size((nav_width, height), im.Cond.ALWAYS)
        if im.begin(tr(self.TITLE), flags=im.WindowFlags.NO_RESIZE):
            if not self.COMPACT:
                im.set_next_item_width(-1)
                changed, value = im.input_text("##toolsearch", self.search, hint=tr("Search..."))
                if changed:
                    self.search = value
                self.remember("tool_search")
                im.set_item_tooltip(
                    tr("Type to list only the tools whose name or description matches.")
                )
                im.separator()
            shown = self.visible_entries()
            last_group = None
            for panel in shown:
                group = panel.get("group")
                if last_group is not None and group != last_group and not self.search.strip():
                    im.separator()
                last_group = group
                label = tr(panel["name"])
                if im.selectable(
                    label, self.selected == panel["name"], icon=entry_icon(panel, panel.get("emtk"))
                ):
                    self.select(panel["name"])
                    if self.GUIDE_FILE is not None:
                        self.tour.notify_used(f"nav_{panel['name']}")
                self.remember(f"nav_{panel['name']}")
                im.set_item_tooltip(tr(panel["description"]))
            if not shown:
                im.text_disabled(tr("No tool matches."))
            if not self.COMPACT:
                im.separator()
                if im.button(tr("Back")):
                    self.step(-1)
                im.set_item_tooltip(tr("Go to the previous tool of the list."))
                self.remember("back")
                im.same_line()
                if im.button(tr("Next")):
                    self.step(1)
                im.set_item_tooltip(tr("Go to the next tool of the list."))
                self.remember("next")
        im.end()

        im.set_next_window_pos((nav_width, 0), im.Cond.ALWAYS)
        im.set_next_window_size((max(1.0, width - nav_width), 86), im.Cond.ALWAYS)
        if im.begin(
            "Tool description", flags=im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE
        ):
            im.heading(tr(entry["name"]), level=2)
            im.push_text_wrap_pos()
            im.text_wrapped(tr(entry["description"]))
            im.pop_text_wrap_pos()
            if self.GUIDE_FILE is not None:
                if action_button("guide"):
                    self.tour.start()
                self.remember("guide")
                im.same_line()
                if action_button("help"):
                    self.help_window.show()
                self.remember("help")
        im.end()

        self.child_box = (nav_width, 86.0, max(1.0, width - nav_width), max(1.0, height - 86.0))
        self.item_rects["tool_area"] = self.child_box
        if self.child is not None:
            self.draw_child(self._painter, self.child, *self.child_box, local_coordinates=True)
        elif self._builder.busy:
            draw_opening(tr(self.selected), self.child_box, "Structure tool opening")
        else:
            im.set_next_window_pos((nav_width + 16, 102), im.Cond.ALWAYS)
            im.set_next_window_size(
                (max(1.0, width - nav_width - 32), max(1.0, height - 118)), im.Cond.ALWAYS
            )
            if im.begin(
                "Tool status", flags=im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE
            ):
                im.heading(tr("Tool unavailable"), level=2)
                im.text_wrapped(self.error)
                self.remember("tool_error")
            im.end()
        if self.GUIDE_FILE is not None:
            self.help_window.draw((0.0, 0.0, width, height))
            self.tour.draw(width, height)

    # ── input forwarding into the visible child ─────────────────────────
    def _inside_child(self, x, y):
        bx, by, bw, bh = self.child_box
        return bx <= x < bx + bw and by <= y < by + bh

    def _child_xy(self, x, y):
        return x - self.child_box[0], y - self.child_box[1]

    def pointer_press(self, x, y, button, modifiers=0, clicks=1):
        super().pointer_press(x, y, button, modifiers, clicks)
        if self.child and self._inside_child(x, y):
            self.child.pointer_press(*self._child_xy(x, y), button, modifiers, clicks)

    def pointer_release(self, x, y, button, modifiers=0):
        super().pointer_release(x, y, button, modifiers)
        if self.child:
            self.child.pointer_release(*self._child_xy(x, y), button, modifiers)

    def pointer_move(self, x, y, buttons=0, modifiers=0):
        super().pointer_move(x, y, buttons, modifiers)
        if self.child:
            self.child.pointer_move(*self._child_xy(x, y), buttons, modifiers)

    def wheel(self, x, y, steps, modifiers=0):
        super().wheel(x, y, steps, modifiers)
        if self.child and self._inside_child(x, y):
            self.child.wheel(*self._child_xy(x, y), steps, modifiers)

    def on_files_dropped(self, paths):
        """A drop goes to the visible tool (the hub itself takes no files)."""
        handler = getattr(self.child, "on_files_dropped", None)
        return bool(handler(paths)) if callable(handler) else False

    def key(self, key, text="", modifiers=0):
        return (
            self.child.key(key, text, modifiers)
            if self.child
            else super().key(key, text, modifiers)
        )

    def key_release(self, key, text="", modifiers=0):
        handler = getattr(self.child, "key_release", None)
        return bool(handler(key, text, modifiers)) if callable(handler) else False

    # ── persistence ─────────────────────────────────────────────────────
    def export_settings(self) -> dict:
        state: dict = {"active_tool": self.selected}
        children = {}
        for name, child in self.children.items():
            export = getattr(child, "export_settings", None)
            if callable(export):
                children[name] = export()
        if children:
            state["open_tools"] = children
        return state

    def restore_settings(self, settings: dict) -> None:
        active = str(settings.get("active_tool", ""))
        for name, child_state in (settings.get("open_tools") or {}).items():
            child = self.children.get(name)
            if child is not None:
                restore = getattr(child, "restore_settings", None)
                if callable(restore):
                    restore(child_state)
            else:
                self._pending_state[name] = child_state
        if active:
            self.select(active)


class StructureToolsApp(StructureToolsHubApp):
    """The Structure Tools workspace, with its own Guide and Help."""

    GUIDE_FILE = Path(__file__).parent / "gui" / "guide.json"
    HELP_FILE = Path(__file__).parent / "gui" / "help.md"


def make_app():
    return StructureToolsApp()
