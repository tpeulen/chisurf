"""Native calculator hub: the list of calculators on the left, the selected one built lazily and embedded on the right.

The catalogue is Qt-free data (:mod:`..core.registry`). Each calculator is its own emtk app, constructed on its first
selection and kept (with its state) afterwards -- the one shown when the hub opens is made on a worker thread
(:mod:`chisurf.emtk.background_build`) behind an "Opening" placeholder, so the hub's first frame does not import it; the hub forwards pointer, wheel, key and file-drop events to it and
asks for a frame whenever the embedded app does.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

from emtk import im, keys
from emtk.app import ImApp
from emtk.i18n import tr

from chisurf.emtk.background_build import BackgroundBuild, draw_opening
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.emtk.plugin_icons import entry_icon
from chisurf.plugins.emtk_layout import action_button, window_size

from ..core.registry import default_calculators

HERE = Path(__file__).parent

#: Registry id -> the child's ``make_app`` factory.
FACTORIES = {
    "fret_calculator": "chisurf.plugins.calculator.fret_calculator.gui.app:make_app",
    "fret_line": "chisurf.plugins.fret_line.gui.app:make_app",
    "rics_precision": "chisurf.plugins.calculator.rics_precision.gui.app:make_app",
    "phasor": "chisurf.plugins.calculator.phasor_calculator.gui.app:make_app",
    "kappa2_dist": "chisurf.plugins.calculator.kappa2_dist.gui.app:make_app",
    "f_test": "chisurf.plugins.core.f_test.gui.app:make_app",
    "fcs_saturation": "chisurf.plugins.calculator.fcs_saturation_calc.gui.app:make_app",
    "psf_calculator": "chisurf.plugins.calculator.psf_calculator.gui.app:make_app",
}

_LIST_MAX_W = 240.0
_HEADER_H = 70.0


class CalculatorHubApp(ImApp):
    """Two panels: the calculator list, and the chosen calculator under its description."""

    def __init__(self, entries=None):
        self.window_size = window_size(
            json.loads((HERE / "hub.view.json").read_text(encoding="utf-8")), (1100, 720)
        )
        self.entries = default_calculators() if entries is None else entries
        self.children = {}
        self.selected = self.entries[0].id if self.entries else None
        self.error = ""
        self.child_box = (220.0, _HEADER_H, 700.0, 550.0)
        self.item_rects: dict[str, tuple] = {}
        self._painter = None
        self._pending_settings: dict[str, dict] = {}
        self._builder = BackgroundBuild(wake=self.request_frame)
        self.help_window = EmTkHelpWindow(
            title="Calculators - Help",
            resource=HERE / "help.md",
            owner=self,
            on_start_guide=self.start_guide,
            size=(700.0, 480.0),
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            get_target_rect=lambda name: self.item_rects.get(name),
            owner=self,
            wait_for_controls=True,
        )
        super().__init__(self.render, continuous=False)

    # -- selection and children ----------------------------------------------------------------- #
    def make_child(self, id):
        """Construct the app of entry *id* (may run on a worker thread: no hub state, no drawing)."""
        module, attr = FACTORIES[id].split(":")
        return getattr(importlib.import_module(module), attr)()

    def load_error(self, id, exc):
        """The header text for an entry whose app could not be made."""
        entry = next(e for e in self.entries if e.id == id)
        return f"Could not load '{entry.label}': {exc}"

    def adopt_child(self, id, child):
        """Wire a made app into the hub (UI thread): its frame requests, its saved settings."""
        setter = getattr(child, "set_frame_request_callback", None)
        if callable(setter):
            setter(self.request_frame)  # a worker thread of the child wakes the hub's host
        self.children[id] = child
        saved = self._pending_settings.pop(id, None)
        if saved is not None and callable(getattr(child, "restore_settings", None)):
            child.restore_settings(saved)

    def ensure_child(self, id):
        """The app of *id*, made now if it was not (joins a background build of it); ``None`` on failure."""
        if self._builder.building(id):
            self._collect_build(wait=True)
        if id not in self.children:
            try:
                self.adopt_child(id, self.make_child(id))
            except Exception as exc:  # noqa: BLE001 - shown in the header, as the Qt hub showed it in the page
                self.error = self.load_error(id, exc)
        return self.children.get(id)

    def _collect_build(self, wait=False):
        """Adopt a finished background build; whether the selected entry landed (or failed) with it."""
        built = self._builder.collect(wait=wait)
        if built is None:
            return False
        for id, (child, exc) in built.items():
            if id in self.children:
                continue
            if exc is None:
                try:
                    self.adopt_child(id, child)
                    continue
                except Exception as adopt_exc:  # noqa: BLE001
                    exc = adopt_exc
            if id == self.selected:
                self.error = self.load_error(id, exc)
        return self.selected in built

    @property
    def building(self):
        """Whether the shown entry's app is being made in the background."""
        return self._builder.busy

    def select(self, id):
        """Select a calculator, building its app on first use; returns the app (``None`` when it could not be built)."""
        if id not in {entry.id for entry in self.entries}:
            raise ValueError("Unknown calculator: " + id)
        self.selected = id
        self.error = ""
        return self.ensure_child(id)

    def _first_frame_build(self):
        """Per frame: adopt a finished build (then select it, for the subclass's bookkeeping); start one for a selected
        entry that has no app yet. Returns whether a build is under way."""
        if self._collect_build() and self.selected in self.children:
            self.select(self.selected)
        if self.selected and self.child is None and not self.error and not self.building:
            self._builder.start(
                {self.selected: lambda id=self.selected: self.make_child(id)},
                name=f"chisurf-hub-{self.selected}",
            )
        return self.building

    def draw_opening(self):
        """The "Opening" placeholder in the tool area, while the shown entry is made."""
        if self.building and self.child is None:
            entry = next((e for e in self.entries if e.id == self.selected), None)
            draw_opening(
                entry.label if entry else str(self.selected), self.child_box, "Hub opening"
            )

    def close(self):
        self._collect_build(wait=True)
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

    def start_guide(self):
        self.tour.start()

    def show_help(self):
        self.help_window.show()

    # -- frames --------------------------------------------------------------------------------- #
    def animating(self):
        return (
            super().animating()
            or self.building
            or bool(self.child is not None and self.child.animating())
        )

    def next_frame_in(self):
        own, child = (
            super().next_frame_in(),
            (self.child.next_frame_in() if self.child is not None else None),
        )
        due = [t for t in (own, child) if t is not None]
        return min(due) if due else None

    def draw(self, painter, x, y, w, h):
        self._painter = painter
        self._first_frame_build()
        super().draw(painter, x, y, w, h)
        self._painter = None

    def render(self):
        vp = im.get_main_viewport()
        width, height = vp.size
        left = min(_LIST_MAX_W, width * 0.25)
        im.set_next_window_pos((0, 0), im.Cond.ALWAYS)
        im.set_next_window_size((left, height), im.Cond.ALWAYS)
        if im.begin("Calculators", flags=im.WindowFlags.NO_RESIZE):
            first = last = None
            for entry in self.entries:
                if im.selectable(
                    entry.label,
                    self.selected == entry.id,
                    icon=entry_icon(entry, getattr(entry, "widget", None)),
                ):
                    self.select(entry.id)
                    self.tour.notify_used("calculators_list")
                im.set_item_tooltip(entry.description)
                rect = im.get_item_rect()
                first, last = first or rect, rect
                self.item_rects["entry:" + entry.id] = rect
            if first is not None:
                self.item_rects["calculators_list"] = (
                    first[0],
                    first[1],
                    first[2],
                    last[1] + last[3] - first[1],
                )
            im.separator()
            if action_button("guide"):
                self.start_guide()
            self.item_rects["guide"] = im.get_item_rect()
            im.same_line()
            if action_button("help"):
                self.show_help()
            self.item_rects["help"] = im.get_item_rect()
        im.end()
        entry = next((e for e in self.entries if e.id == self.selected), None)
        # the header grows with a long description or an error (a narrow window wraps them to several lines)
        wrap = max(width - left - 16.0, 50.0)
        shown = [
            entry.label if entry else "",
            entry.description if entry else "Select a calculator on the left to get started.",
            self.error,
        ]
        header_h = max(
            _HEADER_H, 10.0 + sum(im.calc_text_size(t, wrap_width=wrap)[1] for t in shown if t)
        )
        im.set_next_window_pos((left, 0), im.Cond.ALWAYS)
        im.set_next_window_size((width - left, header_h), im.Cond.ALWAYS)
        if im.begin(
            "Calculator description", flags=im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE
        ):
            if entry:
                im.text_unformatted(entry.label)
                im.text_wrapped(entry.description)
            else:
                im.text_wrapped(tr("Select a calculator on the left to get started."))
            if self.error:
                im.text_wrapped(self.error)
            self.item_rects["description"] = im.get_item_rect()
        im.end()
        self.child_box = (left, header_h, max(1.0, width - left), max(1.0, height - header_h))
        if self.child is not None:
            self.draw_child(self._painter, self.child, *self.child_box, local_coordinates=True)
        self.draw_opening()
        self.help_window.draw((0.0, 0.0, width, height))
        self.tour.draw(width, height)

    # -- events: the embedded calculator gets the pointer inside its box, every key, the wheel and file drops ------- #
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
        own = super().key(
            key, text, modifiers
        )  # the hub's own windows (help, tour) read Escape from its io
        taken = self.child.key(key, text, modifiers) if self.child else own
        if not taken and key in (keys.KEY_UP, keys.KEY_DOWN):
            # the Qt list answered the arrow keys: step the selection when no embedded field wants them
            ids = [entry.id for entry in self.entries]
            if self.selected in ids:
                step = -1 if key == keys.KEY_UP else 1
                self.select(ids[min(max(ids.index(self.selected) + step, 0), len(ids) - 1)])
                self.request_frame()
                return True
        return taken

    def files_dropped(self, paths):
        """Hand a dropped file to the embedded calculator (the Qt hub's children took their own drops)."""
        for name in ("files_dropped", "on_files_dropped", "on_paths_dropped"):
            handler = getattr(self.child, name, None) if self.child is not None else None
            if callable(handler):
                result = handler(list(paths))
                return True if result is None else bool(result)
        return False

    on_files_dropped = files_dropped
    on_paths_dropped = files_dropped

    # -- persistence: the selection and the embedded calculators' settings ------------------------------------- #
    def export_settings(self):
        """The selected calculator and, of the calculators built so far, their own settings."""
        children = {}
        for id, child in self.children.items():
            export = getattr(child, "export_settings", None)
            if callable(export):
                children[id] = export()
        return {"selected": self.selected, "children": children}

    def restore_settings(self, settings):
        """Restore :meth:`export_settings`; an unknown calculator or malformed entry is ignored."""
        if not isinstance(settings, dict):
            return
        saved = settings.get("children")
        if isinstance(saved, dict):
            for id, value in saved.items():
                if id not in FACTORIES or not isinstance(value, dict):
                    continue
                child = self.children.get(id)
                if child is not None and callable(getattr(child, "restore_settings", None)):
                    child.restore_settings(value)
                else:
                    self._pending_settings[id] = value
        selected = settings.get("selected")
        if selected in {entry.id for entry in self.entries}:
            self.select(selected)


__all__ = ["CalculatorHubApp", "FACTORIES"]


def make_app(**kwargs):
    from chisurf.emtk.i18n import install

    install()
    return CalculatorHubApp(entries=kwargs.get("entries"))
