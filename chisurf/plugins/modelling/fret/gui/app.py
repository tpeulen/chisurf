"""The native FRET docking app: the docking window and the pair selection window of the plugin.

Both are this plugin's own cards (:mod:`.docking_card`, :mod:`.pair_selection_app`). They live in one window with a
short list of the two tools on the left; each tool is made the first time it is selected (the one shown when the
window opens on a worker thread, behind an "Opening" placeholder) and keeps its state while the other one is shown.
"""

from __future__ import annotations

import importlib
import json
from collections.abc import Hashable
from pathlib import Path
from typing import Any

from emtk import im
from emtk.app import ImApp
from emtk.i18n import mark, tr

from chisurf.emtk.background_build import BackgroundBuild, draw_opening
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.emtk.plugin_icons import entry_icon
from chisurf.plugins.emtk_layout import action_button, window_size

HERE = Path(__file__).resolve().parent

ENTRIES = [
    {
        "name": mark("Docking & Screening"),
        "description": mark(
            "FRET-restrained rigid-body docking, refinement and structure-library screening (IMP + IMP.bff)."
        ),
        "emtk": "chisurf.plugins.modelling.fret.gui.docking_card:make_app",
    },
    {
        "name": mark("Pair Selection"),
        "description": mark(
            "Choose the most informative FRET pairs to tell the conformations of a trajectory apart."
        ),
        "emtk": "chisurf.plugins.modelling.fret.gui.pair_selection_app:make_app",
    },
]

#: Width of the tool list: wide enough for "Docking & Screening" with its icon at the default font.
NAV_WIDTH = 190.0
#: Height of the strip naming the selected tool.
HEADER = 86.0


class FretApp(ImApp):
    """Docking & Screening and Pair Selection in one window."""

    TITLE = mark("FRET")

    def __init__(self) -> None:
        self.window_size = window_size(
            json.loads((HERE / "resources" / "window.view.json").read_text(encoding="utf-8")),
            (1100, 720),
        )
        self.entries = ENTRIES
        self.selected = self.entries[0]["name"]
        self.children: dict[str, ImApp] = {}
        self._pending_state: dict[str, dict] = {}
        self.error = ""
        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        self.child_box = (NAV_WIDTH, HEADER, 950.0, 634.0)
        self._painter = None
        self._builder = BackgroundBuild(wake=self.request_frame)
        self._prebuilt: dict[Hashable, tuple[Any, BaseException | None]] = {}
        self.tour = EmTkGuidedTour(
            HERE / "guide.json",
            get_target_rect=self.item_rects.get,
            owner=self,
            wait_for_controls=True,
        )
        self.help_window = EmTkHelpWindow(
            title=f"{self.TITLE} - Help",
            resource=HERE / "help.md",
            owner=self,
            on_start_guide=self.tour.start,
        )
        super().__init__(self.render)

    @property
    def child(self):
        return self.children.get(self.selected)

    def _entry(self, name: str) -> dict | None:
        return next((item for item in self.entries if item["name"] == name), None)

    def select(self, name: str):
        """Show the tool *name*, making it on first use (a failure is shown in its place)."""
        entry = self._entry(name)
        if entry is None:
            raise ValueError(f"Unknown tool: {name}")
        self.selected = name
        self.error = ""
        if name not in self.children:
            if self._builder.building(name):
                self._prebuilt.update(self._builder.collect(wait=True) or {})
            try:
                made, exc = self._prebuilt.pop(name, (None, None))
                if exc is not None:
                    raise exc
                self.children[name] = made if made is not None else self._make(entry["emtk"])
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
                if self.selected in self._prebuilt:
                    self.select(self.selected)
                elif not self._builder.busy:
                    factory = self._entry(self.selected)["emtk"]
                    self._builder.start(
                        {self.selected: lambda f=factory: self._make(f)}, name="chisurf-fret"
                    )
            super().draw(painter, x, y, w, h)
        finally:
            self._painter = None

    # ── render ──────────────────────────────────────────────────────────
    def render(self):
        width, height = im.get_main_viewport().size
        entry = self._entry(self.selected)
        im.set_next_window_pos((0, 0), im.Cond.ALWAYS)
        im.set_next_window_size((NAV_WIDTH, height), im.Cond.ALWAYS)
        if im.begin(tr(self.TITLE), flags=im.WindowFlags.NO_RESIZE):
            for panel in self.entries:
                if im.selectable(
                    tr(panel["name"]),
                    self.selected == panel["name"],
                    icon=entry_icon(panel, panel["emtk"]),
                ):
                    self.select(panel["name"])
                    self.tour.notify_used(f"nav_{panel['name']}")
                self.remember(f"nav_{panel['name']}")
                im.set_item_tooltip(tr(panel["description"]))
        im.end()

        im.set_next_window_pos((NAV_WIDTH, 0), im.Cond.ALWAYS)
        im.set_next_window_size((max(1.0, width - NAV_WIDTH), HEADER), im.Cond.ALWAYS)
        if im.begin(
            "Tool description", flags=im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE
        ):
            im.heading(tr(entry["name"]), level=2)
            im.push_text_wrap_pos()
            im.text_wrapped(tr(entry["description"]))
            im.pop_text_wrap_pos()
            if action_button("guide"):
                self.tour.start()
            self.remember("guide")
            im.same_line()
            if action_button("help"):
                self.help_window.show()
            self.remember("help")
        im.end()

        self.child_box = (NAV_WIDTH, HEADER, max(1.0, width - NAV_WIDTH), max(1.0, height - HEADER))
        self.item_rects["tool_area"] = self.child_box
        if self.child is not None:
            self.draw_child(self._painter, self.child, *self.child_box, local_coordinates=True)
        elif self._builder.busy:
            draw_opening(tr(self.selected), self.child_box, "FRET tool opening")
        else:
            im.set_next_window_pos((NAV_WIDTH + 16, HEADER + 16), im.Cond.ALWAYS)
            im.set_next_window_size(
                (max(1.0, width - NAV_WIDTH - 32), max(1.0, height - HEADER - 32)), im.Cond.ALWAYS
            )
            if im.begin(
                "Tool status", flags=im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE
            ):
                im.heading(tr("Tool unavailable"), level=2)
                im.text_wrapped(self.error)
                self.remember("tool_error")
            im.end()
        self.help_window.draw((0.0, 0.0, width, height))
        self.tour.draw(width, height)

    # ── input forwarding into the visible tool ──────────────────────────
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
        for name, child_state in (settings.get("open_tools") or {}).items():
            child = self.children.get(name)
            restore = getattr(child, "restore_settings", None) if child is not None else None
            if callable(restore):
                restore(child_state)
            elif child is None:
                self._pending_state[name] = child_state
        active = str(settings.get("active_tool", ""))
        if self._entry(active) is not None:
            self.select(active)


def make_app() -> FretApp:
    """The FRET docking plugin's native app."""
    from chisurf.emtk.i18n import install

    install()
    return FretApp()


__all__ = ["ENTRIES", "FretApp", "make_app"]


def _paths(payload: dict, key: str) -> list[str]:
    from chisurf.core.plugin.workspace_input import read_address

    values = payload.get(key) or []
    values = values if isinstance(values, list) else [values]
    return [str(read_address(str(v))) for v in values if v]


def _tool(app, index: int):
    """The card a hand-off goes to: the plugin window's card *index* (opened if needed), or *app*
    itself when the card draws the Input section (it is the card)."""
    if not hasattr(app, "select"):
        return app
    child = app.select(ENTRIES[index]["name"])
    if child is None:
        raise ValueError(app.error or f"{ENTRIES[index]['name']} is not available")
    return child


def _kind(address: str) -> str:
    """The workspace kind of *address*'s file (``structure``, ``trajectory``, ``setup``, ...)."""
    from chisurf.core.fio.classify import classify

    return classify(address)


def receive_structures(app, payload: dict) -> bool:
    """Hand-off receiver (``structures``): workspace structures become the next rigid bodies of
    Docking & Screening."""
    paths = _paths(payload, "structures")
    if not paths:
        raise ValueError("no structure picked")
    _tool(app, 0)._add_pdb(paths)
    return True


def receive_docking_setup(app, payload: dict) -> bool:
    """Hand-off receiver (``docking_setup``): a docking project loads into Docking & Screening, an
    FPS labelling plan (fps.json) becomes its distances."""
    import json

    paths = _paths(payload, "setup")
    if not paths:
        raise ValueError("no setup picked")
    card = _tool(app, 0)
    try:
        with open(paths[0], encoding="utf-8") as handle:
            keys = set(json.load(handle))
    except (OSError, ValueError, TypeError):
        keys = set()
    if "fret_docking_project_version" in keys:
        card._load_project(paths[0])
    else:
        card._set_fps(paths[0])
    return True


def receive_topology(app, payload: dict) -> bool:
    """Hand-off receiver (``topology``): a workspace structure becomes Pair Selection's topology."""
    paths = _paths(payload, "topology")
    if not paths:
        raise ValueError("no structure picked")
    _tool(app, 1).set_path("topology", paths[0])
    return True


def receive_pair_inputs(app, payload: dict) -> bool:
    """Hand-off receiver (``pair_inputs``): Pair Selection's files from the workspace, by kind -- a
    trajectory is the trajectory, a structure its topology (or the trajectory itself when no
    trajectory is picked or set), a setup row the FPS plan."""
    paths = _paths(payload, "files")
    if not paths:
        raise ValueError("nothing picked")
    card = _tool(app, 1)
    kinds = {path: _kind(path) for path in paths}
    trajectories = [p for p in paths if kinds[p] == "trajectory"]
    structures = [p for p in paths if kinds[p] == "structure"]
    setups = [p for p in paths if kinds[p] not in ("trajectory", "structure")]
    if trajectories:
        card.set_path("trajectory", trajectories[0])
    if structures:
        has_trajectory = bool(trajectories or getattr(card.session, "trajectory", ""))
        card.set_path("topology" if has_trajectory else "trajectory", structures[0])
    if setups:
        card.set_path("fps_json", setups[0])
    return True

