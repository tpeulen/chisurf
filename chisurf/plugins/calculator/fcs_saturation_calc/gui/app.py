"""Native multi-state FCS saturation calculator, retaining original numerical model."""

import json
from pathlib import Path

import numpy as np
from emtk import im, implot
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.plugins.calculator.inputs import bounded_float
from chisurf.plugins.calculator.native_form import fields, parameter_field, plain

from .model import SaturationModel


class SaturationApp(ImApp):
    def __init__(self, model=None):
        self.model = model or SaturationModel()
        self.result_tab = 0
        self.dialog = None
        self.dialog_mode = ""
        self.error = ""
        self.item_rects = {}
        self.sections = json.loads(Path(__file__).with_name("view.json").read_text())["sections"][
            0
        ]["sections"]
        for section in self.sections[0]["sections"]:
            if section.get("attr") == "power_mW":
                section["minimum"] = 0.0  # The guide and zero-power physical baseline require it.
        self.help_window = EmTkHelpWindow(
            title="FCS saturation — Help", resource=Path(__file__).with_name("help.md"), owner=self
        )
        self.tour = EmTkGuidedTour(
            steps=Path(__file__).with_name("guide.json"),
            get_target_rect=lambda k: self.item_rects.get(k),
            owner=self,
            wait_for_controls=True,
        )
        self.docks = DockManager(Split("h", 0.38, Region("controls"), Region("plots")))
        self.docks.add_window(
            "controls", "Photophysics and kinetics", self.controls, dock="controls", closable=False
        )
        self.docks.add_window(
            "plots", "FCS predictions", self.results, dock="plots", closable=False
        )
        super().__init__(self.render, continuous=False)

    def controls(self, box):
        m = self.model
        for label, tip, action in [
            (
                "Compute",
                "Recompute FCS curves, apparent diffusion fits, profiles and power sweeps.",
                m._on_compute,
            ),
            (
                "Load scheme",
                "Load an arbitrary photophysical scheme from JSON.",
                lambda: self.choose("open"),
            ),
            (
                "Save scheme",
                "Export all transition rates, state labels and brightness as JSON.",
                lambda: self.choose("save"),
            ),
            (
                "Load session",
                "Restore the previously saved session including optics and display settings.",
                m.load_user_settings,
            ),
            (
                "Save session",
                "Save the current optics, kinetics and display settings for future sessions.",
                m.save_user_settings,
            ),
            (
                "Help",
                "Explain saturation physics and interpreting the fit residuals.",
                self.help_window.show,
            ),
            ("Guide", "Start a guided tour of the saturation calculator.", self.tour.start),
        ]:
            if im.button(label):
                try:
                    action()
                    self.tour.notify_used(label)
                except Exception as exc:
                    self.error = str(exc)
            im.set_item_tooltip(tip)
            self.item_rects[label.lower().replace(" ", "_")] = im.get_item_rect()
        im.separator()
        fields(m, self.sections[:1], m._on_changed, self.item_rects, self.tour.notify_used)
        sat = m.saturation
        for title, group, maximum in [
            ("Dark transition rates", sat.dark, 1e9),
            ("Excitation cross-sections", sat.exc, 1.0),
        ]:
            if im.collapsing_header(title, im.TreeNodeFlags.DEFAULT_OPEN):
                im.set_item_tooltip(
                    "Edit directed transitions; dark rates use the selected time unit, cross-sections are relative to peak excitation."
                )
                for name, parameter in group.rates_by_name().items():
                    im.begin_disabled(group is sat.dark and name.startswith("k1_"))
                    edited, value = bounded_float(
                        name, float(parameter.value), minimum=0.0, maximum=maximum, step=0.01
                    )
                    im.set_item_tooltip(
                        f"{name}: {getattr(parameter, 'description', title)}. Enter zero to remove this transition. Ground-state dark excitation is read-only; use the excitation cross-section instead."
                    )
                    im.end_disabled()
                    if edited:
                        parameter.value = value
                        m._on_changed()
        if im.collapsing_header("State brightness", im.TreeNodeFlags.DEFAULT_OPEN):
            im.set_item_tooltip(
                "Relative fluorescence emitted by each state; dark states have brightness zero."
            )
            for i, parameter in enumerate(sat.brightness._brightness):
                if parameter_field(parameter, sat.state_labels[i] + " brightness"):
                    m._on_changed()
        if im.collapsing_header("Optics and measurement", im.TreeNodeFlags.DEFAULT_OPEN):
            im.set_item_tooltip(
                "Beam dimensions, extinction, diffusion, concentration and detection parameters."
            )
            sat.find_parameters()
            for parameter in sat._parameters:
                if parameter in getattr(sat, "_relaxation_outputs", []):
                    im.text_unformatted(f"{parameter.name}: {parameter.value:g}")
                    continue
                if parameter_field(parameter):
                    self.tour.notify_used("state_scheme")
                    m._on_changed()
        if self.error:
            im.text_wrapped(self.error)

    def choose(self, mode):
        self.dialog_mode = mode
        self.dialog = FileDialog(
            "Photophysical scheme",
            mode=mode,
            filename="scheme.json" if mode == "save" else "",
            filters="JSON (*.json)",
        )

    def plot(self, section, height=-1):
        if implot.begin_plot(section.get("title", section["source"]), (-1, height)):
            implot.setup_axes(section.get("x_label", ""), section.get("y_label", ""))
            if section.get("log_x"):
                implot.setup_axis_scale(implot.AXIS_X1, implot.SCALE_LOG10)
            if section.get("log_y"):
                implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
            implot.setup_legend()
            for series in getattr(self.model, section["source"]):
                implot.set_next_line_style(
                    weight=series.get("width", 1.5), dash=(4, 3) if series.get("dash") else None
                )
                implot.plot_line(series.get("name", "Prediction"), series["x"], series["y"])
            implot.end_plot()
            im.set_item_tooltip(
                plain(
                    section.get("description")
                    or f"{section.get('title')}: prediction using the current kinetics and optical parameters."
                )
            )

    def diagram(self):
        sat = self.model.saturation
        n = sat.n_states
        angle = np.linspace(0, 2 * np.pi, n, endpoint=False)
        x, y = np.cos(angle), np.sin(angle)
        if implot.begin_plot("State scheme", (-1, -1)):
            implot.setup_axes("", "")
            implot.setup_axes_limits(-1.5, 1.5, -1.5, 1.5, implot.COND_ALWAYS)
            for group_name, group in [("dark", sat.dark), ("excitation", sat.exc)]:
                matrix = np.asarray(group.rate_matrix())
                for target, source in zip(*np.nonzero(matrix)):
                    if source != target:
                        name = f"{sat.state_labels[source]} → {sat.state_labels[target]} ({group_name}: {matrix[target, source]:g})"
                        implot.plot_line(name, [x[source], x[target]], [y[source], y[target]])
            implot.plot_scatter("States", x, y)
            for i, label in enumerate(sat.state_labels):
                implot.plot_text(label, float(x[i]), float(y[i]), (0, -15))
            implot.end_plot()
            self.item_rects["state_scheme"] = im.get_item_rect()
            im.set_item_tooltip(
                "Directed transitions are listed in the legend as source → target; ground, excited and dark state labels come from the active scheme."
            )

    def results(self, box):
        panels = self.sections[1:]
        if im.begin_tab_bar("saturation_views"):
            for index, section in enumerate(panels):
                label = section.get("title", "Results")
                if im.begin_tab_item(label):
                    self.result_tab = index
                    im.end_tab_item()
                self.item_rects[label] = im.get_item_rect()
                im.set_item_tooltip(
                    f"Inspect {label.lower()} for the current photophysical scheme."
                )
            im.end_tab_bar()
        section = panels[self.result_tab]
        if section.get("title") == "State diagram":
            self.diagram()
        fields(
            self.model,
            section.get("sections", []),
            self.model._on_changed,
            self.item_rects,
            self.tour.notify_used,
        )
        n_plots = sum(child.get("type") == "plot" for child in section.get("sections", []))
        plot_height = max(100.0, im.get_content_region_avail()[1] / max(1, n_plots) - 8.0)
        for child in section.get("sections", []):
            if child.get("type") == "plot":
                self.plot(child, plot_height)
            elif child.get("type") == "info":
                im.text_wrapped(plain(self.model.info_text()))

    def render(self):
        vp = im.get_main_viewport()
        self.docks.draw((0, 0, *vp.size))
        if self.dialog:
            if im.begin("Scheme file"):
                result = self.dialog.draw()
                if result:
                    try:
                        if self.dialog_mode == "open":
                            self.model.load_scheme_from_file(result[0])
                            self.model._scheme_preset = "Custom"
                        else:
                            self.model.save_scheme_to_file(result[0])
                        self.dialog = None
                    except Exception as exc:
                        self.error = str(exc)
                elif result is False:
                    self.dialog = None
            im.end()
        if self.help_window.open:
            self.help_window.draw((0, 0, *vp.size))
        if self.tour.active:
            self.tour.draw(*vp.size)


def make_app(**kwargs):
    from chisurf.emtk.i18n import install

    install()
    return SaturationApp(SaturationModel(restore=kwargs.get("restore", True)))
