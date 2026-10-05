"""EMTK File tools hub: a navigation list of six file tools, each the child's own emtk app.

Child routes come from the children's manifests (``panels.json`` names them by
their Qt entrypoint; :func:`native_factory` reads the matching ``emtk``
entrypoint), so the hub never imports a Qt route. The selected child draws in
the right-hand box and receives the pointer, wheel, keys and drops that land
there. Frames are requested only while the child (or the hub's own tour/help)
needs them.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

from emtk import im
from emtk.app import ImApp

from chisurf.core.support.i18n import tr
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget
from chisurf.emtk.plugin_icons import entry_icon

SPEC = json.loads(Path(__file__).with_name("panels.json").read_text())
SPLITTER_FIELDS = (
    "input_format",
    "output_format",
    "photons_per_file_k",
    "microtime_binning",
    "split_files",
    "reset_macro_times",
    "keep_original",
    "batch_use_parent",
    "input_file",
    "output_folder",
    "batch_files",
)


def native_factory(panel):
    """Resolve only the native declaration; never import the legacy Qt route."""
    parts = panel["entrypoint"].split(":")[0].split(".")
    root = Path(__file__).resolve().parents[3]
    # A route may name a plugin package itself (BID), or its gui module.
    relative = parts[2 : parts.index("gui")] if "gui" in parts else parts[2:]
    manifest = root.joinpath(*relative, "manifest.json")
    data = json.loads(manifest.read_text())
    return data.get("entrypoints", {}).get("emtk")


def caption(panel) -> str:
    """The panel's name; its pictogram is drawn in the row's icon slot."""
    return tr(panel["name"])


class FileToolsApp(TourTarget, ImApp):
    """The File tools hub."""

    def __init__(self, panels=None, resolver=native_factory):
        self.panels = list(SPEC["panels"] if panels is None else panels)
        self.resolver = resolver
        self.children = {}
        self.errors = {}
        self.selected = self.panels[0]["role"]
        self.filter = ""
        self.child_box = (240.0, 90.0, 960.0, 710.0)
        self._painter = None
        self._child_focus = False
        self.item_rects = {}
        self.help = EmTkHelpWindow(
            title="File tools — Help", resource=Path(__file__).with_name("help.md"), owner=self,
            on_start_guide=self.start_guide,
        )
        self.tour = EmTkGuidedTour(Path(__file__).with_name("guide.json"), owner=self,
                                   get_target_rect=self.item_rects.get, wait_for_controls=True)
        super().__init__(self.render, continuous=False)

    def start_guide(self):
        self.tour.start()

    def animating(self):
        child = self.child
        return bool(child is not None and child.animating()) or super().animating()

    def next_frame_in(self):
        values = [super().next_frame_in()]
        if self.child is not None:
            values.append(self.child.next_frame_in())
        return min((value for value in values if value is not None), default=None)

    @property
    def child(self):
        return self.children.get(self.selected)

    def select(self, role):
        panel = next((p for p in self.panels if p["role"] == role), None)
        if panel is None:
            raise ValueError("Unknown file tool: " + role)
        self.selected = role
        self.tour.notify_used("nav_" + role)
        if role not in self.children:
            self.errors.pop(role, None)
            try:
                spec = self.resolver(panel)
                if not spec:
                    self.errors[role] = (
                        "Native panel pending. This route remains visible; its Qt workflow has not yet been ported."
                    )
                else:
                    module, name = spec.split(":", 1)
                    child = getattr(importlib.import_module(module), name)()
                    child.set_frame_request_callback(self.request_frame)
                    self.children[role] = child
            except Exception as exc:
                self.errors[role] = "Cannot open native panel: " + str(exc)
        return self.child

    @property
    def native_layouts(self):
        result = {}
        for role, child in self.children.items():
            if hasattr(child, "docks"):
                result[role] = child.docks
            for name in ("splitter_gui", "time_window_gui"):
                gui = getattr(child, name, None)
                if gui is not None and hasattr(gui, "docks"):
                    result[role] = gui.docks
            for name, layout in getattr(child, "native_layouts", {}).items():
                result[role + "/" + name] = layout
        return result

    def draw(self, painter, x, y, w, h):
        self._painter = painter
        if self.child is None and self.selected not in self.errors:
            self.select(self.selected)
        try:
            super().draw(painter, x, y, w, h)
        finally:
            self._painter = None

    def render(self):
        width, height = im.get_main_viewport().size
        left = min(250.0, width * 0.27)
        flags = im.WindowFlags.NO_RESIZE | im.WindowFlags.NO_MOVE
        im.set_next_window_pos((0, 0), im.Cond.ALWAYS)
        im.set_next_window_size((left, height), im.Cond.ALWAYS)
        if im.begin(tr("File tools"), flags=flags):
            if im.button(tr("Guide")):
                self.tour.start()
            im.set_item_tooltip(
                tr(
                    "Walk through choosing a converter, inspecting a container and correcting metadata."
                )
            )
            self.remember("guide")
            im.same_line()
            if im.button(tr("Help")):
                self.help.show()
            im.set_item_tooltip(tr("Read the file-tools help and the workflows of all six tools."))
            self.remember("help")
            im.set_next_item_width(-1)
            _, self.filter = im.input_text("##File tool search", self.filter, hint=tr("Filter tools…"))
            im.set_item_tooltip(tr("Filter tools by name or description."))
            self.remember("search")
            for panel in self.panels:
                if (
                    self.filter.casefold()
                    not in (tr(panel["name"]) + " " + tr(panel["description"])).casefold()
                ):
                    continue
                if im.selectable(
                    caption(panel),
                    self.selected == panel["role"],
                    icon=entry_icon(panel, panel["entrypoint"]),
                ):
                    self.select(panel["role"])
                im.set_item_tooltip(tr(panel["description"]))
                self.remember("nav_" + panel["role"])
        im.end()
        im.set_next_window_pos((left, 0), im.Cond.ALWAYS)
        im.set_next_window_size((width - left, 90), im.Cond.ALWAYS)
        if im.begin("##File tool description", flags=flags | im.WindowFlags.NO_TITLE_BAR):
            panel = next(p for p in self.panels if p["role"] == self.selected)
            im.text_unformatted(caption(panel))
            im.text_wrapped(tr(panel["description"]))
        self.remember("description", (left, 0.0, width - left, 90.0))
        im.end()
        self.child_box = (left, 90.0, width - left, max(1.0, height - 90.0))
        self.remember("panel", self.child_box)
        if self.child is not None:
            self.draw_child(self._painter, self.child, *self.child_box, local_coordinates=True)
        else:
            im.set_next_window_pos((left, 90), im.Cond.ALWAYS)
            im.set_next_window_size((width - left, height - 90), im.Cond.ALWAYS)
            if im.begin("##Pending file tool", flags=flags | im.WindowFlags.NO_TITLE_BAR):
                im.text_wrapped(tr(self.errors.get(self.selected, "")))
                im.text_wrapped(panel["entrypoint"])
                if im.button(tr("Retry")):
                    self.select(self.selected)
                im.set_item_tooltip(
                    tr(
                        "Check the child manifest again after the native port or dependency becomes available."
                    )
                )
            im.end()
        self.help.draw((0, 0, width, height))
        self.tour.draw(width, height)

    def _inside(self, x, y):
        bx, by, bw, bh = self.child_box
        return bx <= x < bx + bw and by <= y < by + bh

    def pointer_press(self, x, y, button, modifiers=0, clicks=1):
        self._child_focus = self._inside(x, y) and not self.help.open and not self.tour.active
        super().pointer_press(x, y, button, modifiers, clicks)
        if self.child and self._child_focus:
            self.child.pointer_press(
                x - self.child_box[0], y - self.child_box[1], button, modifiers, clicks
            )

    def pointer_release(self, x, y, button, modifiers=0):
        super().pointer_release(x, y, button, modifiers)
        if self.child and self._child_focus:
            self.child.pointer_release(
                x - self.child_box[0], y - self.child_box[1], button, modifiers
            )

    def pointer_move(self, x, y, buttons=0, modifiers=0):
        super().pointer_move(x, y, buttons, modifiers)
        if self.child and not self.help.open and not self.tour.active:
            self.child.pointer_move(x - self.child_box[0], y - self.child_box[1], buttons, modifiers)

    def wheel(self, x, y, steps, modifiers=0):
        # Wheel routing: the old scroll(x, y, dx, dy) override rejected the
        # host's scroll(rows) call outright (TypeError on the first tick).
        super().wheel(x, y, steps, modifiers)
        if self.child and self._inside(x, y) and not self.help.open and not self.tour.active:
            self.child.wheel(x - self.child_box[0], y - self.child_box[1], steps, modifiers)

    def key(self, key, text="", modifiers=0):
        if self.child and self._child_focus and not self.help.open and not self.tour.active:
            return self.child.key(key, text, modifiers)
        return super().key(key, text, modifiers)

    def files_dropped(self, paths):
        if self.child is not None and not self.help.open and not self.tour.active:
            for owner in (self.child, getattr(self.child, "tool", None)):
                for name in ("files_dropped", "on_paths_dropped"):
                    handler = getattr(owner, name, None)
                    if callable(handler):
                        handler(paths)
                        return True
            if self.selected == "split_convert" and paths:
                self.child.tool.load_input(paths[0])
                return True
        return False

    on_paths_dropped = files_dropped

    def export_settings(self):
        children = {}
        for role, child in self.children.items():
            exporter = getattr(child, "export_settings", None) or getattr(
                child, "export_state", None
            )
            if callable(exporter):
                children[role] = exporter()
            elif role == "split_convert":
                children[role] = {
                    name: getattr(child.tool._model, name) for name in SPLITTER_FIELDS
                }
            elif role == "tttr_time_windows":
                children[role] = {
                    "selected_files": [str(p) for p in child.tool._file_paths],
                    "time_window_ms": child.tool.time_window_ms,
                    "output_dir": child.tool.output_dir_text,
                }
        return {"selected": self.selected, "filter": self.filter, "children": children}

    def restore_settings(self, state):
        roles = {p["role"] for p in self.panels}
        for role, data in state.get("children", {}).items():
            if role in roles:
                child = self.select(role)
                restore = getattr(child, "restore_settings", None) or getattr(
                    child, "restore_state", None
                )
                if callable(restore):
                    restore(data)
                elif child is not None and role == "split_convert":
                    for name in SPLITTER_FIELDS:
                        if name in data:
                            setattr(child.tool._model, name, data[name])
                    if data.get("input_file") and Path(data["input_file"]).is_file():
                        child.tool.load_input(data["input_file"])
                elif child is not None and role == "tttr_time_windows":
                    child.tool.time_window_ms = float(data.get("time_window_ms", 10.0))
                    child.tool.output_dir_text = str(data.get("output_dir") or "")
                    child.tool.add_paths(data.get("selected_files", []))
        self.filter = str(state.get("filter", ""))
        self.select(
            state.get("selected") if state.get("selected") in roles else self.panels[0]["role"]
        )

    def close(self):
        for child in self.children.values():
            child.close()
        self.children.clear()


def make_app(**kwargs):
    from emtk.i18n import add_translations

    from chisurf.emtk.i18n import install

    install()
    catalogs = json.loads(Path(__file__).with_name("translations.json").read_text())
    for language, mapping in catalogs.items():
        add_translations(language, mapping, context="chisurf")
    return FileToolsApp(**kwargs)
