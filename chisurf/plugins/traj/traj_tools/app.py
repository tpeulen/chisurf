"""Native trajectory-tools workspace: the eight tools in a list on the left, the chosen one built lazily on the right.

The native counterpart of the Qt ``TrajectoryToolsTool`` dock workspace. The shared
:class:`~chisurf.plugins.calculator.hub.gui.app.CalculatorHubApp` keeps every opened tool alive with its state while the user
works in another one and forwards pointer, wheel, key and file drops to it; the catalogue is :mod:`.registry` (the Qt hub's
tool factories, each pointing at the child's native app). Here: the list, the status line the Qt window had
(``Active tool: X``, the drop message), Help and Guide.

The Qt tabs were closable (a closed tab could not be brought back); here a tool is always in the list.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace

from emtk import i18n, im

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.plugins.calculator.hub.gui.app import CalculatorHubApp

from .registry import TOOL_PANELS
from .strings import install_translations

install_translations()
HERE = Path(__file__).parent
_LIST_MAX_W = 180.0
_LIST_MIN_W = 130.0
_HEADER_H = 70.0


def tr(text: str) -> str:
    return i18n.tr(text, context="Trajectory Tools")


class TrajectoryToolsHubApp(CalculatorHubApp):
    """Keep each trajectory tool alive while the user works in another."""

    window_title = "Traj Tools"

    def __init__(self) -> None:
        self.panels = TOOL_PANELS
        entries = [SimpleNamespace(id=p["name"], label=p["name"], icon="", description=p["description"], emtk=p["emtk"])
                   for p in TOOL_PANELS]
        super().__init__(entries=entries)
        self.status = "Ready"
        self.help_window = EmTkHelpWindow(title="Trajectory tools - Help", resource=HERE / "gui/help.md", owner=self,
                                          on_start_guide=self.start_guide, size=(700.0, 480.0))
        self.tour = EmTkGuidedTour(steps=HERE / "gui/guide.json", get_target_rect=lambda name: self.item_rects.get(name),
                                   owner=self, wait_for_controls=True, on_step_change=self._tour_step)

    # -- selection ---------------------------------------------------------------------------------------------------- #
    @property
    def entries_by_name(self) -> dict:
        return {e.id: e for e in self.entries}

    def select(self, name: str):
        """Select a tool, building its app on first use; returns the app (``None`` when it could not be built)."""
        entry = self.entries_by_name.get(name)
        if entry is None:
            raise ValueError(f"Unknown tool: {name}")
        self.selected = name
        self.error = ""
        if name not in self.children:
            try:
                module, attr = entry.emtk.split(":", 1)
                child = getattr(importlib.import_module(module), attr)()
                setter = getattr(child, "set_frame_request_callback", None)
                if callable(setter):
                    setter(self.request_frame)
                self.children[name] = child
                saved = self._pending_settings.pop(name, None)
                if saved is not None and callable(getattr(child, "restore_settings", None)):
                    child.restore_settings(saved)
            except Exception as exc:  # noqa: BLE001 - surfaced in the header, as the Qt hub showed the child's error
                self.error = f"{tr('Tool unavailable')}: {exc}"
        self.status = f"Active tool: {name}"
        self.tour.notify_used("tool_list")
        self.tour.notify_used("entry:" + name)
        self.request_frame()
        return self.child

    def _tour_step(self, _index: int, step: dict) -> None:
        """The tour reached a card pointing at a tool of the list: show that tool."""
        name = str((step.get("target") or {}).get("name", ""))
        if name.startswith("entry:") and name[6:] in self.entries_by_name and not step.get("await"):
            self.select(name[6:])

    # -- frame -------------------------------------------------------------------------------------------------------- #
    def render(self):
        width, height = im.get_main_viewport().size
        left = min(_LIST_MAX_W, max(_LIST_MIN_W, width * 0.24))
        status_h = 24.0
        im.set_next_window_pos((0, 0), im.Cond.ALWAYS)
        im.set_next_window_size((left, height), im.Cond.ALWAYS)
        if im.begin(tr("Trajectory tools"), flags=im.WindowFlags.NO_RESIZE):
            im.text_disabled(tr("Available tools"))
            im.separator()
            first = last = None
            for entry in self.entries:
                if im.selectable(tr(entry.label), self.selected == entry.id):
                    self.select(entry.id)
                im.set_item_tooltip(tr(entry.description))
                rect = im.get_item_rect()
                first, last = first or rect, rect
                self.item_rects["entry:" + entry.id] = rect
            if first is not None:
                self.item_rects["tool_list"] = (first[0], first[1], first[2], last[1] + last[3] - first[1])
            im.separator()
            if im.button(tr("Guide")):
                self.start_guide()
            im.set_item_tooltip(tr("A short walk through preparing a trajectory."))
            self.item_rects["guide"] = im.get_item_rect()
            im.same_line()
            if im.button(tr("Help")):
                self.show_help()
            im.set_item_tooltip(tr("What the tools do and how a dropped file is used."))
            self.item_rects["help"] = im.get_item_rect()
        im.end()
        entry = self.entries_by_name[self.selected]
        wrap = max(width - left - 16.0, 50.0)
        shown = [tr(entry.label), tr(entry.description)]
        header_h = max(_HEADER_H - 20.0, 10.0 + sum(im.calc_text_size(t, wrap_width=wrap)[1] for t in shown))
        im.set_next_window_pos((left, 0), im.Cond.ALWAYS)
        im.set_next_window_size((width - left, header_h), im.Cond.ALWAYS)
        if im.begin("Tool description", flags=im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE):
            im.text_unformatted(tr(entry.label))
            im.text_wrapped(tr(entry.description))
            self.item_rects["description"] = im.get_item_rect()
        im.end()
        body_h = max(1.0, height - header_h - status_h)
        self.child_box = (left, header_h, max(1.0, width - left), body_h)
        if self.child is not None:
            self.draw_child(self._painter, self.child, *self.child_box, local_coordinates=True)
        else:
            im.set_next_window_pos((left + 16, header_h + 8), im.Cond.ALWAYS)
            im.set_next_window_size((max(1.0, width - left - 32), max(1.0, body_h - 16)), im.Cond.ALWAYS)
            if im.begin("Tool status", flags=im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE):
                im.heading(tr("Tool unavailable"), level=2)
                im.text_wrapped(self.error)
            im.end()
        im.set_next_window_pos((left, height - status_h), im.Cond.ALWAYS)
        im.set_next_window_size((width - left, status_h), im.Cond.ALWAYS)
        if im.begin("Status", flags=im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE):
            im.text_unformatted(self.status)
            self.item_rects["status"] = im.get_item_rect()
        im.end()
        self.help_window.draw((0.0, 0.0, width, height))
        self.tour.draw(width, height)

    # -- drops: the child takes what fits its fields; the status line says what happened ------------------------------- #
    def files_dropped(self, paths):
        """Hand a drop to the open tool (the Qt window routed it to the panel in front); say what happened."""
        paths = [str(p) for p in paths or []]
        child = self.child
        if child is None or not paths:
            return False
        taker = getattr(child, "on_paths_dropped", None)
        took = False
        if callable(taker):
            took = bool(taker(paths))
        else:
            for name in ("files_dropped", "on_files_dropped"):
                handler = getattr(child, name, None)
                if callable(handler):
                    took = bool(handler(paths))
                    break
        self.status = (f"{self.selected}: {Path(paths[0]).name}" if took else
                       f"{self.selected} takes no dropped file like this: drop onto one of its fields")
        self.request_frame()
        return True

    on_files_dropped = files_dropped
    on_paths_dropped = files_dropped

    # -- persistence -------------------------------------------------------------------------------------------------- #
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
        if not isinstance(settings, dict):
            return
        for name, child_state in (settings.get("open_tools") or {}).items():
            if name not in self.entries_by_name or not isinstance(child_state, dict):
                continue
            child = self.children.get(name)
            if child is not None and callable(getattr(child, "restore_settings", None)):
                child.restore_settings(child_state)
            else:
                self._pending_settings[name] = child_state
        active = str(settings.get("active_tool", ""))
        if active in self.entries_by_name:
            self.select(active)

    @property
    def _pending_state(self) -> dict:
        """The stream's name for the settings of tools not opened yet."""
        return self._pending_settings


def make_app():
    """Build the workspace (the manifest's ``entrypoints.emtk``)."""
    from chisurf.emtk.i18n import install

    install()
    return TrajectoryToolsHubApp()
