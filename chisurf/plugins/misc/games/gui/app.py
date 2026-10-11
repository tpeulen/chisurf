"""Native EMTK games hub with lazy, state-preserving game surfaces."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

from emtk import i18n, im
from emtk.app import ImApp

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.plugins.emtk_layout import action_button, window_size

from .registry import GAME_PANELS
from .translations import install_translations

install_translations()


def tr(text: str) -> str:
    return i18n.tr(text, context="Games")


class GamesHubApp(ImApp):
    """Keep each game alive while the player visits another panel."""

    def __init__(self) -> None:
        spec = json.loads(Path(__file__).with_name("app.view.json").read_text(encoding="utf-8"))
        self.window_size = window_size(spec, (1200, 800))
        self.entries = GAME_PANELS
        self.selected = self.entries[0]["name"]
        self.children: dict[str, ImApp] = {}
        self.error = ""
        self.child_box = (180.0, 86.0, 880.0, 644.0)
        self._painter = None
        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        gui_dir = Path(__file__).parent
        self.tour = EmTkGuidedTour(
            gui_dir / "guide.json",
            get_target_rect=self.item_rects.get,
            owner=self,
            wait_for_controls=True,
        )
        self.help_window = EmTkHelpWindow(
            title="Games - Help",
            resource=gui_dir / "help.md",
            owner=self,
            on_start_guide=self.tour.start,
        )
        super().__init__(self.render)
        # The game shown on first open must exist at once: it used to be built only when its list
        # entry was clicked, so the first game took no keys and drew nothing until then.
        self.select(self.selected)

    @property
    def child(self):
        return self.children.get(self.selected)

    def select(self, name: str):
        entry = next((item for item in self.entries if item["name"] == name), None)
        if entry is None:
            raise ValueError(f"Unknown game: {name}")
        if self.child is not None and callable(getattr(self.child, "focus_lost", None)):
            self.child.focus_lost()
        self.selected = name
        self.error = ""
        factory = entry["emtk"]
        if factory and name not in self.children:
            try:
                module, attr = factory.split(":", 1)
                self.children[name] = getattr(importlib.import_module(module), attr)()
            except Exception as exc:
                self.error = f"{tr('Game unavailable')}: {exc}"
        if self.child is not None and callable(getattr(self.child, "focus_lost", None)):
            self.child.focus_lost()
        gained = getattr(self.child, "focus_gained", None)
        if callable(gained):
            gained()  # the hub has the focus: a game whose Sound switch is on may speak again
        self.request_frame()
        return self.child

    def close(self):
        self.tour.stop()
        for child in self.children.values():
            close = getattr(child, "close", None)
            if callable(close):
                close()
        self.children.clear()

    def animating(self):
        return super().animating() or bool(self.child and self.child.animating())

    def next_frame_in(self):
        values = [super().next_frame_in()]
        if self.child is not None:
            values.append(self.child.next_frame_in())
        return min((value for value in values if value is not None), default=None)

    def draw(self, painter, x, y, w, h):
        self._painter = painter
        try:
            if self.child is None and not self.error:
                self.select(self.selected)
            super().draw(painter, x, y, w, h)
        finally:
            self._painter = None

    #: Width of the game list, and height of the header above the game.
    NAV_WIDTH = 190.0
    HEADER_H = 80.0
    PAD = 10.0

    def render(self):
        width, height = im.get_main_viewport().size
        nav_width = min(self.NAV_WIDTH, max(150.0, width * 0.26))
        entry = next(item for item in self.entries if item["name"] == self.selected)
        flags = im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE

        # -- the game list: one row per game, its blurb under it ------------- #
        im.set_next_window_pos((0, 0), im.Cond.ALWAYS)
        im.set_next_window_size((nav_width, height), im.Cond.ALWAYS)
        if im.begin("##games-list", flags=flags):
            im.indent(self.PAD)
            im.dummy(0.0, self.PAD)
            im.heading(tr("Games"), level=2)
            im.separator()
            for panel in self.entries:
                im.dummy(0.0, 4.0)
                label = (
                    tr(panel["name"])
                    if panel["emtk"]
                    else f"{tr(panel['name'])} ({tr('not available')})"
                )
                if im.selectable(
                    label + "##game-" + panel["name"],
                    self.selected == panel["name"],
                    icon=panel.get("icon"),
                ):
                    self.select(panel["name"])
                    self.tour.notify_used("game_" + panel["name"])
                self.remember("game_" + panel["name"])
                im.set_item_tooltip(tr(panel["description"]))
            im.dummy(0.0, 4.0)
            im.separator()
            if action_button("guide"):
                self.tour.start()
            self.remember("guide")
            im.same_line()
            if action_button("help"):
                self.help_window.show()
            self.remember("help")
            im.unindent(self.PAD)
        im.end()

        # -- the header: what is selected and how it is played --------------- #
        area_x, area_w = nav_width, max(1.0, width - nav_width)
        im.set_next_window_pos((area_x, 0), im.Cond.ALWAYS)
        im.set_next_window_size((area_w, self.HEADER_H), im.Cond.ALWAYS)
        if im.begin("##game-header", flags=flags):
            im.indent(self.PAD)
            im.dummy(0.0, self.PAD / 2)
            im.heading(tr(entry["name"]), level=2)
            im.text(tr(entry["description"]))
            if entry.get("keys"):
                im.text_disabled(tr("Keys: ") + tr(entry["keys"]))
            self.remember("game_header", (area_x, 0.0, area_w, self.HEADER_H))
            im.unindent(self.PAD)
        im.end()

        # -- the game fills the rest -------------------------------------- #
        self.child_box = (area_x, self.HEADER_H, area_w, max(1.0, height - self.HEADER_H))
        self.item_rects["game_area"] = self.child_box
        if self.child is not None:
            self.draw_child(self._painter, self.child, *self.child_box, local_coordinates=True)
        else:
            im.set_next_window_pos((area_x, self.HEADER_H), im.Cond.ALWAYS)
            im.set_next_window_size((area_w, max(1.0, height - self.HEADER_H)), im.Cond.ALWAYS)
            if im.begin("##game-status", flags=flags):
                im.dummy(0.0, self.PAD)
                im.indent(self.PAD)
                im.heading(tr("Game unavailable"), level=2)
                im.text_wrapped(self.error or tr("This game has no native version yet."))
                im.unindent(self.PAD)
            im.end()
        self.help_window.draw((0.0, 0.0, width, height))
        self.tour.draw(width, height)

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
        if self.child and self.child.key(key, text, modifiers):
            return True
        from emtk import keys as k

        if not modifiers:
            if key in {k.KEY_1, k.KEY_2, k.KEY_3, k.KEY_4, k.KEY_5}:
                idx = key - k.KEY_1
                if 0 <= idx < len(self.entries):
                    self.select(self.entries[idx]["name"])
                    return True
            if key == k.KEY_TAB:
                cur_idx = next(
                    (i for i, item in enumerate(self.entries) if item["name"] == self.selected), 0
                )
                next_idx = (cur_idx + 1) % len(self.entries)
                self.select(self.entries[next_idx]["name"])
                return True
        return super().key(key, text, modifiers)

    def key_release(self, key, text="", modifiers=0):
        release = getattr(self.child, "key_release", None)
        if callable(release) and release(key, text, modifiers):
            return True
        from emtk import keys as k

        if not modifiers and (key in {k.KEY_1, k.KEY_2, k.KEY_3, k.KEY_4, k.KEY_5, k.KEY_TAB}):
            return True
        return False

    def focus_lost(self):
        """The host lost focus mid-press: the game must not keep a key held."""
        lost = getattr(self.child, "focus_lost", None)
        if callable(lost):
            lost()

    def focus_gained(self):
        """The host window is back in front: the child may unmute."""
        gained = getattr(self.child, "focus_gained", None)
        if callable(gained):
            gained()


def make_app():
    return GamesHubApp()
