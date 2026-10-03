"""Qt-free, manifest-driven TTTR toolbox with persistent native children."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

from emtk import im
from emtk.app import ImApp
from emtk.i18n import tr

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow

RESOURCES = Path(__file__).parent
#: Height of the window naming the selected tool.
HEADER = 62.0


def load_panels():
    return json.loads((RESOURCES / "panels.json").read_text(encoding="utf-8"))["panels"]


def manifest_path(panel):
    module = panel["entrypoint"].split(":", 1)[0].split(".gui.", 1)[0]
    # Resolve from the known package layout without importing the legacy GUI.
    return Path(__file__).resolve().parents[5].joinpath(*module.split("."), "manifest.json")


def resolve_factory(panel):
    path = manifest_path(panel)
    data = json.loads(path.read_text(encoding="utf-8"))
    spec = data.get("entrypoints", {}).get("emtk")
    if not spec:
        return None, ""
    module, attribute = spec.split(":", 1)
    return getattr(importlib.import_module(module), attribute), spec


class TttrToolboxApp(ImApp):
    def __init__(self, panels=None, resolver=resolve_factory):
        self.panels = list(load_panels() if panels is None else panels)
        self.tools = [panel for panel in self.panels if not panel.get("separator")]
        self.selected = self.tools[0]["role"] if self.tools else None
        self.children = {}
        self.routes = {}
        self.errors = {}
        self.filter = ""
        self.status = "Ready"
        self.item_rects = {}
        self.resolver = resolver
        self.child_box = (230.0, HEADER, 970.0, 688.0)
        self._painter = None
        self._child_focus = False
        self._child_capture = False
        self.help = EmTkHelpWindow(
            title="TTTR Tools — Help", resource=RESOURCES / "help.md", owner=self
        )
        self.child_help = None
        self.tour = EmTkGuidedTour(
            RESOURCES / "guide.json",
            owner=self,
            on_step_change=self._tour_step,
            get_target_rect=self._target_rect,
            wait_for_controls=True,
        )
        super().__init__(self.render, continuous=False)

    @property
    def child(self):
        return self.children.get(self.selected)

    @property
    def panel(self):
        return next((panel for panel in self.tools if panel["role"] == self.selected), None)

    @property
    def native_layouts(self):
        layouts = {}
        for role, child in self.children.items():
            if hasattr(child, "docks"):
                layouts[role] = child.docks
            for name, manager in getattr(child, "native_layouts", {}).items():
                layouts[role + "/" + name] = manager
        return layouts

    def select(self, role, retry=False, by_user=True):
        panel = next((p for p in self.tools if p["role"] == role), None)
        if panel is None:
            raise ValueError("Unknown TTTR panel: " + str(role))
        self.selected = role
        self._child_focus = False
        self._child_capture = False
        if retry:
            self.errors.pop(role, None)
        if role not in self.children and role not in self.errors:
            try:
                factory, spec = self.resolver(panel)
                self.routes[role] = spec
                if factory is None:
                    self.errors[role] = "This tool has no native EMTK factory yet."
                else:
                    self.children[role] = factory()
            except Exception as exc:
                self.errors[role] = str(exc)
        if by_user:
            self.tour.notify_used(panel["name"])
        if by_user and self.tour.active:  # a step names its panel by a part of the name ("Count Rate")
            key = self.tour._target_key(self.tour.steps[self.tour.step_idx].get("target"))
            if key and key.casefold() in panel["name"].casefold():
                self.tour.notify_used(key)
        self.child_help = None
        self.status = "Ready"
        self.wants_frame = True
        return self.child

    def step(self, delta):
        """Back / Next: the neighbouring tool in the list (the Qt stepper's navigation; no sub-tool has a run step)."""
        roles = [p["role"] for p in self.tools]
        index = roles.index(self.selected) + delta if self.selected in roles else 0
        if 0 <= index < len(roles):
            self.select(roles[index])

    def _target_rect(self, key):
        """Where the tour finds a step's target: a navigation row (named by part of its tool's name) or a control."""
        if key in self.item_rects:
            return self.item_rects[key]
        panel = next((p for p in self.tools if key and key.casefold() in p["name"].casefold()), None)
        return self.item_rects.get("nav." + panel["role"]) if panel else None

    def _tour_step(self, index, step):
        target = step.get("target", {}).get("panel", "")
        panel = next(
            (p for p in self.tools if target and target.casefold() in p["name"].casefold()), None
        )
        if panel and not step.get("await"):  # an awaited step waits for the user to pick the row
            self.select(panel["role"], by_user=False)

    def matching_panels(self):
        query = self.filter.casefold()
        return [
            p
            for p in self.tools
            if query in (tr(p["name"]) + " " + tr(p["description"]) + " " + p["role"]).casefold()
        ]

    def show_child_help(self):
        panel = self.panel
        if panel is None:
            return
        path = manifest_path(panel).parent / "gui" / "help.md"
        self.child_help = EmTkHelpWindow(
            title=panel["name"] + " — Help",
            resource=path if path.is_file() else None,
            text="" if path.is_file() else panel["description"],
            owner=self,
        )
        self.child_help.show()

    def draw(self, painter, x, y, w, h):
        self._painter = painter
        if (
            self.selected
            and self.selected not in self.children
            and self.selected not in self.errors
        ):
            self.select(self.selected)
        try:
            super().draw(painter, x, y, w, h)
        finally:
            self._painter = None

    def render(self):
        width, height = im.get_main_viewport().size
        left = min(230.0, width * 0.26)
        im.set_next_window_pos((0, 0), im.Cond.ALWAYS)
        im.set_next_window_size((left, height), im.Cond.ALWAYS)
        if im.begin("TTTR Tools", flags=im.WindowFlags.NO_RESIZE):
            if im.button("Help"):
                self.help.show()
            im.set_item_tooltip("Read the TTTR toolbox reference and photon-clock guidance.")
            self.item_rects["help"] = im.get_item_rect()
            im.same_line()
            if im.button("Guide"):
                self.tour.start()
            im.set_item_tooltip("Walk through the original TTTR tools and their workflows.")
            self.item_rects["guide"] = im.get_item_rect()
            _, self.filter = im.input_text("##Find TTTR tools", self.filter, hint=tr("Search…"))
            im.set_item_tooltip("Find tools by name, description or route.")
            self.item_rects["search"] = im.get_item_rect()
            matching = {p["role"] for p in self.matching_panels()}
            for panel in self.panels:
                if panel.get("separator"):
                    if not self.filter:
                        im.separator()
                    continue
                if panel["role"] not in matching:
                    continue
                if im.selectable(
                    tr(panel["name"]) + "##" + panel["role"],  # (the panels' pictograms are not in emtk's font)
                    self.selected == panel["role"],
                    size=(left - 8, 28),
                ):
                    self.select(panel["role"])
                im.set_item_tooltip(panel["description"])
                self.item_rects["nav." + panel["role"]] = im.get_item_rect()
            if not matching:
                im.text_wrapped(tr("No matching tools."))
        im.end()
        im.set_next_window_pos((left, 0), im.Cond.ALWAYS)
        im.set_next_window_size((width - left, HEADER), im.Cond.ALWAYS)
        if im.begin(
            "TTTR destination", flags=im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE
        ):
            if self.panel:
                im.text_unformatted(tr(self.panel["name"]))
                im.same_line()
                if im.button("Tool help"):
                    self.show_child_help()
                im.set_item_tooltip("Read help for the selected TTTR tool.")
                self.item_rects["tool_help"] = im.get_item_rect()
                im.text_wrapped(tr(self.panel["description"]))
                im.set_item_tooltip(
                    self.routes.get(self.selected) or "Native route not yet available."
                )
        im.end()
        bar = 30.0
        self.child_box = (left, HEADER, max(1.0, width - left), max(1.0, height - HEADER - bar))
        im.set_next_window_pos((left, height - bar), im.Cond.ALWAYS)
        im.set_next_window_size((width - left, bar), im.Cond.ALWAYS)
        if im.begin("TTTR status", flags=im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE):
            roles = [p["role"] for p in self.tools]
            index = roles.index(self.selected) if self.selected in roles else 0
            im.text_unformatted(tr(self.status))
            im.same_line(max(120.0, width - left - 190.0))
            im.begin_disabled(index <= 0)
            if im.button(tr("Back")):
                self.step(-1)
            self.item_rects["back"] = im.get_item_rect()
            im.set_item_tooltip(tr("Go to the previous tool in the list."))
            im.end_disabled()
            im.same_line()
            im.begin_disabled(index >= len(roles) - 1)
            if im.button(tr("Next")):
                self.step(1)
            self.item_rects["next"] = im.get_item_rect()
            im.set_item_tooltip(tr("Go to the next tool in the list."))
            im.end_disabled()
        im.end()
        if self.child:
            self.draw_child(self._painter, self.child, *self.child_box, local_coordinates=True)
        elif self.selected in self.errors:
            im.set_next_window_pos((left, HEADER), im.Cond.ALWAYS)
            im.set_next_window_size((width - left, height - HEADER - bar), im.Cond.ALWAYS)
            if im.begin("TTTR tool unavailable", flags=im.WindowFlags.NO_RESIZE):
                im.text_wrapped(tr("The selected tool could not be opened."))
                im.text_wrapped(tr(self.errors[self.selected]))
                if im.button("Retry"):
                    self.select(self.selected, retry=True)
                self.item_rects["retry"] = im.get_item_rect()
                im.set_item_tooltip(
                    "Resolve this tool's current manifest again and retry its native factory."
                )
            im.end()
        self.help.draw((0, 0, width, height))
        if self.child_help:
            self.child_help.draw((0, 0, width, height))
        self.tour.draw(width, height)

    def _overlay_open(self):
        return self.help.open or self.tour.active or bool(self.child_help and self.child_help.open)

    def _inside(self, x, y):
        bx, by, bw, bh = self.child_box
        return bx <= x < bx + bw and by <= y < by + bh

    def pointer_press(self, x, y, button, modifiers=0, clicks=1):
        self._child_focus = self._inside(x, y) and not self._overlay_open()
        self._child_capture = self._child_focus
        super().pointer_press(x, y, button, modifiers, clicks)
        if self.child and self._child_capture:
            self.child.pointer_press(
                x - self.child_box[0], y - self.child_box[1], button, modifiers, clicks
            )

    def pointer_release(self, x, y, button, modifiers=0):
        super().pointer_release(x, y, button, modifiers)
        if self.child and self._child_capture:
            self.child.pointer_release(
                x - self.child_box[0], y - self.child_box[1], button, modifiers
            )
        self._child_capture = False

    def pointer_move(self, x, y, buttons=0, modifiers=0):
        super().pointer_move(x, y, buttons, modifiers)
        if self.child:
            self.child.pointer_move(
                x - self.child_box[0], y - self.child_box[1], buttons, modifiers
            )

    def wheel(self, x, y, steps, modifiers=0):
        if self.child and self._inside(x, y) and not self._overlay_open():
            self.child.wheel(x - self.child_box[0], y - self.child_box[1], steps, modifiers)
        else:
            super().wheel(x, y, steps, modifiers)

    def scroll(self, rows):
        if self.child and self._child_focus and not self._overlay_open():
            return self.child.scroll(rows)
        return super().scroll(rows)

    def key(self, key, text="", modifiers=0):
        if self.child and self._child_focus and not self._overlay_open():
            return self.child.key(key, text, modifiers)
        return super().key(key, text, modifiers)

    def animating(self):
        return super().animating() or bool(self.child and self.child.animating())

    def next_frame_in(self):
        delays = [super().next_frame_in()]
        if self.child:
            delays.append(self.child.next_frame_in())
        return min((d for d in delays if d is not None), default=None)

    def on_files_dropped(self, paths):
        if not self.child or self._overlay_open():
            return False
        handler = getattr(self.child, "on_paths_dropped", None)
        if not callable(handler):
            handler = getattr(self.child, "on_files_dropped", None)
        if not callable(handler):
            return False
        result = handler(paths)
        return result is not False

    def on_paths_dropped(self, paths):
        return self.on_files_dropped(paths)

    def export_settings(self):
        children = {}
        for role, child in self.children.items():
            export = getattr(child, "export_settings", None) or getattr(child, "get_state", None)
            if callable(export):
                children[role] = export()
        return {"selected": self.selected, "children": children}

    def restore_settings(self, state):
        roles = {p["role"] for p in self.tools}
        for role, data in state.get("children", {}).items():
            if role in roles:
                child = self.select(role)
                restore = getattr(child, "restore_settings", None) or getattr(
                    child, "set_state", None
                )
                if callable(restore):
                    restore(data)
        selected = state.get("selected")
        if selected in roles:
            self.select(selected)

    def close(self):
        for child in self.children.values():
            close = getattr(child, "close", None)
            if callable(close):
                close()
        self.children.clear()


def make_app(**kwargs):
    from chisurf.emtk.i18n import install

    install()
    from .translations import install_translations

    install_translations()
    return TttrToolboxApp(
        panels=kwargs.get("panels"), resolver=kwargs.get("resolver", resolve_factory)
    )
