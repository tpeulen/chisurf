"""Native lifetime hub: the five decay-analysis tools in a list on the left, the chosen one built lazily on the right."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from emtk import im
from emtk.i18n import get_locale

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.emtk.plugin_icons import entry_icon
from chisurf.emtk.plugins import load_plugin, manifests
from chisurf.plugins.calculator.hub.gui.app import CalculatorHubApp

#: (plugin id, list label, icon (empty: the plugin's own manifest icon), description, tour alias)
PANELS = [
    ("irf_estimator", "1. IRF Estimation", "", "Estimate instrument response functions from fluorescence decays.", "IRF Estimation"),
    ("maxent_decay", "2. MaxEnt MEM", "", "Run maximum entropy lifetime and FRET-distance analysis.", "MaxEnt MEM"),
    ("lltf", "3. Lazy Lifetime Analysis", "", "Analyze TCSPC decays with the LLTF workflow.", "Lazy Lifetime"),
    ("microtime_histogram", "4. Histogram-Microtime", "", "Build TTTR microtime histograms.", "Histogram-Microtime"),
    ("vv_vh_g_factor", "5. VV/VH G-Factor", "", "Calculate detector G-factors from VV/VH decays.", "G-Factor"),
    (
        "vv_vh_anisotropy",
        "6. VV/VH Anisotropy",
        "",
        "Compute and plot the anisotropy decay r(t) of a VV/VH file with a g-factor, backgrounds and a fractional VH shift.",
        "VV/VH Anisotropy",
    ),
    (
        "synthetic_decay",
        "Synthetic Decay",
        "",
        "Generate synthetic TCSPC decays from lifetimes, with optional IRF convolution and Poisson shot noise.",
        "Synthetic Decay",
    ),
]
LIST_MAX_W = 300.0
EXPERIMENTAL_COLOUR = (230, 80, 80, 255)


class LifetimeAnalysisApp(CalculatorHubApp):
    def __init__(self):
        entries = [
            SimpleNamespace(
                id=id,
                label=label,
                icon=icon or entry_icon({}, id),
                description=description,
                alias=alias,
            )
            for id, label, icon, description, alias in PANELS
        ]
        super().__init__(entries=entries)
        self.continuous = False
        self.item_rects = {}
        self.search = ""
        self.metadata = manifests()
        self.status = "Ready"
        self.help_window = EmTkHelpWindow(
            title="Lifetime Analysis: Help", resource=Path(__file__).with_name("help.md"), owner=self
        )
        self.tour = EmTkGuidedTour(
            steps=Path(__file__).with_name("guide.json"),
            get_target_rect=lambda key: self.item_rects.get(key),
            owner=self,
            wait_for_controls=True,
            on_step_change=self.reveal_step,
        )

    # -- selection ------------------------------------------------------------------------------ #
    def select(self, id, notify=True):
        if id not in {entry.id for entry in self.entries}:
            raise ValueError("Unknown lifetime tool: " + id)
        self.selected = id
        self.error = ""
        if id not in self.children:
            try:
                child = load_plugin(id, locale=get_locale(), persist=getattr(self, "_native_state_bound", False))
                setter = getattr(child, "set_frame_request_callback", None)
                if callable(setter):
                    setter(self.request_frame)
                self.children[id] = child
                saved = self._pending_settings.pop(id, None)
                if saved is not None and callable(getattr(child, "restore_settings", None)):
                    child.restore_settings(saved)
            except Exception as exc:  # noqa: BLE001
                self.error = f"Native tool could not open: {exc}"
        if notify:
            entry = next(entry for entry in self.entries if entry.id == id)
            self.tour.notify_used(entry.alias)
        entry = next(entry for entry in self.entries if entry.id == id)
        self.status = self.error or f"{entry.label}: ready."
        return self.children.get(id)

    def step(self, direction):
        """Back / Next through the tools in their dependency order."""
        ids = [entry.id for entry in self.entries]
        index = min(max(ids.index(self.selected) + direction, 0), len(ids) - 1)
        self.select(ids[index])

    def reveal_step(self, index, step):
        key = EmTkGuidedTour._target_key(step.get("target"))
        entry = next((entry for entry in self.entries if entry.alias == key), None)
        if entry is not None and not step.get("await"):
            self.select(entry.id, notify=False)

    def experimental_message(self, id):
        metadata = self.metadata.get(id, {})
        if metadata.get("experimental"):
            return metadata.get("experimental_message") or "This workflow is experimental."
        return ""

    def visible_entries(self):
        needle = self.search.casefold()
        return [e for e in self.entries if needle in (e.label + " " + e.description).casefold()]

    # -- frame ----------------------------------------------------------------------------------- #
    def render(self):
        vp = im.get_main_viewport()
        width, height = vp.size
        left = min(LIST_MAX_W, max(215.0, width * 0.24)) + im.selectable_icon_width()
        self.item_rects.clear()
        im.set_next_window_pos((0, 0), im.Cond.ALWAYS)
        im.set_next_window_size((left, height), im.Cond.ALWAYS)
        if im.begin("Decay Analysis", flags=im.WindowFlags.NO_RESIZE):
            im.set_next_item_width(-1)
            _, self.search = im.input_text("##search_tools", self.search, hint="Search...")
            im.set_item_tooltip("Filter the decay-analysis tools by their name or purpose.")
            self.item_rects["search"] = im.get_item_rect()
            first = last = None
            for entry in self.visible_entries():
                mark = " *" if self.experimental_message(entry.id) else ""
                if im.selectable(entry.label + mark, selected=self.selected == entry.id, icon=entry.icon):
                    self.select(entry.id)
                im.set_item_tooltip(entry.description + (" (marked * : experimental, see the banner)" if mark else ""))
                rect = im.get_item_rect()
                self.item_rects[entry.alias] = rect
                first, last = first or rect, rect
            if not self.visible_entries():
                im.text_wrapped("No tool matches the search.")
            im.separator()
            ids = [e.id for e in self.entries]
            at = ids.index(self.selected) if self.selected in ids else 0
            im.begin_disabled(at == 0)
            if im.button("Back"):
                self.step(-1)
            im.end_disabled()
            im.set_item_tooltip("Go to the previous tool in the order the analyses depend on each other.")
            self.item_rects["back"] = im.get_item_rect()
            im.same_line()
            im.begin_disabled(at == len(ids) - 1)
            if im.button("Next"):
                self.step(1)
            im.end_disabled()
            im.set_item_tooltip("Go to the next tool in the order the analyses depend on each other.")
            self.item_rects["next"] = im.get_item_rect()
            if im.button("Help"):
                self.help_window.show()
            im.set_item_tooltip("Explain the complementary lifetime-analysis workflows.")
            self.item_rects["help"] = im.get_item_rect()
            im.same_line()
            if im.button("Guide"):
                self.tour.start()
            im.set_item_tooltip("Walk through the real analysis panels and their purpose.")
            self.item_rects["guide"] = im.get_item_rect()
            im.separator()
            im.text_wrapped(self.status)
        im.end()
        entry = next((e for e in self.entries if e.id == self.selected), None)
        wrap = max(width - left - 16.0, 50.0)
        warning = self.experimental_message(entry.id) if entry else ""
        shown = [entry.label if entry else "", entry.description if entry else "Select a tool on the left.", warning, self.error]
        header_h = max(60.0, 12.0 + sum(im.calc_text_size(t, wrap_width=wrap)[1] + 4.0 for t in shown if t))
        im.set_next_window_pos((left, 0), im.Cond.ALWAYS)
        im.set_next_window_size((width - left, header_h), im.Cond.ALWAYS)
        if im.begin("Lifetime tool description", flags=im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE):
            if entry:
                im.text_unformatted(entry.label)
                im.text_wrapped(entry.description)
            if warning:
                im.text_colored(EXPERIMENTAL_COLOUR, warning)
                im.set_item_tooltip("This tool declares itself experimental in its manifest.")
            if self.error:
                im.text_wrapped(self.error)
            self.item_rects["description"] = im.get_item_rect()
        im.end()
        self.child_box = (left, header_h, max(1.0, width - left), max(1.0, height - header_h))
        if self.child is not None:
            self.draw_child(self._painter, self.child, *self.child_box, local_coordinates=True)
        self.help_window.draw((0.0, 0.0, width, height))
        self.tour.draw(width, height)

    # -- persistence: the selection and the embedded tools' own settings ---------------------------- #
    def export_settings(self):
        children = {}
        for id, child in self.children.items():
            export = getattr(child, "export_settings", None)
            if callable(export):
                children[id] = export()
        return {"selected": self.selected, "children": children}

    def restore_settings(self, settings):
        if not isinstance(settings, dict):
            return
        valid = {entry.id for entry in self.entries}
        for id, value in (settings.get("children") or {}).items():
            if id not in valid or not isinstance(value, dict):
                continue
            child = self.children.get(id)
            if child is not None and callable(getattr(child, "restore_settings", None)):
                child.restore_settings(value)
            else:
                self._pending_settings[id] = value
        if settings.get("selected") in valid:
            self.selected = settings["selected"]

    def animating(self):
        return super().animating() or (self.child is not None and self.child.animating())

    def next_frame_in(self):
        values = [super().next_frame_in()]
        if self.child is not None:
            values.append(self.child.next_frame_in())
        return min((value for value in values if value is not None), default=None)


def make_app():
    return LifetimeAnalysisApp()
