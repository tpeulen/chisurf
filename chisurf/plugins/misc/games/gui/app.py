"""Native EMTK games hub with lazy, state-preserving game surfaces."""

from __future__ import annotations

import importlib

from emtk import i18n, im
from emtk.app import ImApp

from .registry import GAME_PANELS
from .translations import install_translations

install_translations()


def tr(text: str) -> str:
    return i18n.tr(text, context="Games")


class GamesHubApp(ImApp):
    """Keep each game alive while the player visits another panel."""

    def __init__(self) -> None:
        self.entries = GAME_PANELS
        self.selected = self.entries[0]["name"]
        self.children: dict[str, ImApp] = {}
        self.error = ""
        self.child_box = (180.0, 86.0, 880.0, 644.0)
        self._painter = None
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
        self.selected = name
        self.error = ""
        factory = entry["emtk"]
        if factory and name not in self.children:
            try:
                module, attr = factory.split(":", 1)
                self.children[name] = getattr(importlib.import_module(module), attr)()
            except Exception as exc:
                self.error = f"{tr('Game unavailable')}: {exc}"
        self.request_frame()
        return self.child

    def close(self):
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
        nav_width = min(self.NAV_WIDTH, max(150.0, width * .26))
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
                label = tr(panel["name"]) if panel["emtk"] else f"{tr(panel['name'])} ({tr('not available')})"
                if im.selectable(
                    label + "##game-" + panel["name"],
                    self.selected == panel["name"],
                    icon=panel.get("icon"),
                ):
                    self.select(panel["name"])
                im.set_item_tooltip(tr(panel["description"]))
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
            im.unindent(self.PAD)
        im.end()

        # -- the game fills the rest -------------------------------------- #
        self.child_box = (area_x, self.HEADER_H, area_w, max(1.0, height - self.HEADER_H))
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
        return self.child.key(key, text, modifiers) if self.child else super().key(key, text, modifiers)

    def key_release(self, key, text="", modifiers=0):
        release = getattr(self.child, "key_release", None)
        return release(key, text, modifiers) if callable(release) else False

    def focus_lost(self):
        """The host lost focus mid-press: the game must not keep a key held."""
        lost = getattr(self.child, "focus_lost", None)
        if callable(lost):
            lost()


def make_app():
    return GamesHubApp()
