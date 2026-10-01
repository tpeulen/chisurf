"""Native calculator hub with lazy, state-preserving child applications."""

import importlib

from emtk import im
from emtk.app import ImApp

from ..core.registry import default_calculators

FACTORIES = {
    "fret_calculator": "chisurf.plugins.calculator.fret_calculator.gui.app:make_app",
    "fret_line": "chisurf.plugins.fret_line.gui.app:make_app",
    "fcs_calculator": "chisurf.plugins.fcs.fcs_calculator.gui.app:make_app",
    "rics_precision": "chisurf.plugins.calculator.rics_precision.gui.app:make_app",
    "phasor": "chisurf.plugins.calculator.phasor_calculator.gui.app:make_app",
    "kappa2_dist": "chisurf.plugins.calculator.kappa2_dist.gui.app:make_app",
    "f_test": "chisurf.plugins.core.f_test.gui.app:make_app",
    "fcs_saturation": "chisurf.plugins.calculator.fcs_saturation_calc.gui.app:make_app",
    "psf_calculator": "chisurf.plugins.calculator.psf_calculator.gui.app:make_app",
}


class CalculatorHubApp(ImApp):
    def __init__(self, entries=None):
        self.entries = default_calculators() if entries is None else entries
        self.children = {}
        self.selected = self.entries[0].id if self.entries else None
        self.error = ""
        self.child_box = (220.0, 70.0, 700.0, 550.0)
        self._painter = None
        super().__init__(self.render, continuous=True)

    def select(self, id):
        if id not in {entry.id for entry in self.entries}:
            raise ValueError("Unknown calculator: " + id)
        self.selected = id
        self.error = ""
        if id not in self.children:
            try:
                module, attr = FACTORIES[id].split(":")
                self.children[id] = getattr(importlib.import_module(module), attr)()
            except Exception as exc:
                self.error = f"Native calculator unavailable: {exc}"
        return self.children.get(id)

    def close(self):
        for child in self.children.values():
            close = getattr(child, "close", None)
            if callable(close):
                close()
        self.children.clear()

    @property
    def native_layouts(self):
        layouts = {}
        for id, child in self.children.items():
            for name, manager in getattr(child, "native_layouts", {}).items():
                layouts[id + "/" + name] = manager
            if hasattr(child, "docks"):
                layouts[id] = child.docks
        return layouts

    @property
    def child(self):
        return self.children.get(self.selected)

    def draw(self, painter, x, y, w, h):
        self._painter = painter
        if self.selected and self.child is None and not self.error:
            self.select(self.selected)
        super().draw(painter, x, y, w, h)
        self._painter = None

    def render(self):
        vp = im.get_main_viewport()
        width, height = vp.size
        left = min(240.0, width * 0.25)
        im.set_next_window_pos((0, 0), im.Cond.ALWAYS)
        im.set_next_window_size((left, height), im.Cond.ALWAYS)
        if im.begin("Calculators", flags=im.WindowFlags.NO_RESIZE):
            for entry in self.entries:
                if im.selectable(entry.icon + " " + entry.label, self.selected == entry.id):
                    self.select(entry.id)
                im.set_item_tooltip(entry.description)
        im.end()
        im.set_next_window_pos((left, 0), im.Cond.ALWAYS)
        im.set_next_window_size((width - left, 70), im.Cond.ALWAYS)
        if im.begin(
            "Calculator description", flags=im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE
        ):
            entry = next((e for e in self.entries if e.id == self.selected), None)
            if entry:
                im.text_unformatted(entry.label)
                im.text_wrapped(entry.description)
            if self.error:
                im.text_wrapped(self.error)
        im.end()
        self.child_box = (left, 70.0, max(1.0, width - left), max(1.0, height - 70.0))
        if self.child is not None:
            self.draw_child(self._painter, self.child, *self.child_box, local_coordinates=True)

    def _inside(self, x, y):
        bx, by, bw, bh = self.child_box
        return bx <= x < bx + bw and by <= y < by + bh

    def pointer_press(self, x, y, button, modifiers=0, clicks=1):
        super().pointer_press(x, y, button, modifiers, clicks)
        if self.child and self._inside(x, y):
            self.child.pointer_press(
                x - self.child_box[0], y - self.child_box[1], button, modifiers, clicks
            )

    def pointer_release(self, x, y, button, modifiers=0):
        super().pointer_release(x, y, button, modifiers)
        if self.child:
            self.child.pointer_release(
                x - self.child_box[0], y - self.child_box[1], button, modifiers
            )

    def pointer_move(self, x, y, buttons=0, modifiers=0):
        super().pointer_move(x, y, buttons, modifiers)
        if self.child:
            self.child.pointer_move(
                x - self.child_box[0], y - self.child_box[1], buttons, modifiers
            )

    def wheel(self, x, y, steps, modifiers=0):
        super().wheel(x, y, steps, modifiers)
        if self.child and self._inside(x, y):
            self.child.wheel(x - self.child_box[0], y - self.child_box[1], steps, modifiers)

    def key(self, key, text="", modifiers=0):
        return (
            self.child.key(key, text, modifiers)
            if self.child
            else super().key(key, text, modifiers)
        )


def make_app(**kwargs):
    from chisurf.emtk.i18n import install

    install()
    return CalculatorHubApp(entries=kwargs.get("entries"))
