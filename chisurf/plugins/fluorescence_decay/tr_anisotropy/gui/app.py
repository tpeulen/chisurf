"""Native six-step anisotropy workflow with pure linked-fit construction."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from emtk import im, implot
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog
from emtk.view_form import FormState, draw_form

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, _clean_html_text
from chisurf.plugins.calculator.inputs import bounded_float, bounded_int

from .model import NativeAnisotropyModel


def spectrum_spec(label, source, selected, update, add, remove, prefix, value_label):
    return {
        "sections": [
            {
                "type": "table",
                "title": label,
                "source": source,
                "selected_attr": selected,
                "editable": True,
                "update_call": update,
                "height": 180,
                "description": f"Edit {label.lower()} amplitude/value pairs.",
                "columns": [
                    {
                        "key": "amplitude",
                        "label": "Amplitude",
                        "description": "Relative lifetime amplitude or absolute anisotropy contribution.",
                    },
                    {
                        "key": "value",
                        "label": value_label,
                        "description": "Lifetime or rotational correlation time in nanoseconds.",
                    },
                ],
            },
            {
                "type": "value",
                "attr": prefix + "_amplitude",
                "label": "New amplitude",
                "kind": "float",
                "minimum": 0.0,
                "maximum": 1e6,
                "description": "Amplitude of the component to add.",
            },
            {
                "type": "value",
                "attr": prefix + "_value",
                "label": value_label,
                "kind": "float",
                "minimum": 0.0,
                "maximum": 1e6,
                "description": "Time of the component to add, in nanoseconds.",
            },
            {
                "type": "button_row",
                "buttons": [
                    {
                        "label": "Add component",
                        "action": add,
                        "description": "Append the entered amplitude/time pair.",
                    },
                    {
                        "label": "Remove selected",
                        "action": remove,
                        "description": "Remove the selected component, or the last one when none is selected.",
                    },
                ],
            },
        ]
    }


class AnisotropyApp(ImApp):
    def __init__(self, model=None):
        self.model = model or NativeAnisotropyModel()
        self.steps = json.loads(
            (Path(__file__).parent.parent / "anisotropy.view.json").read_text()
        )["sections"][0]["steps"]
        self.step_index = 0
        self.item_rects = {}
        self.forms = [FormState(), FormState()]
        self.spectrum_specs = [
            spectrum_spec(
                "Lifetime spectrum",
                "spectrum_source",
                "selected_lifetime_row",
                "edit_lifetime",
                "add_lifetime",
                "remove_lifetime",
                "new_lifetime",
                "Lifetime (ns)",
            ),
            spectrum_spec(
                "Rotation spectrum",
                "rotation_source",
                "selected_rotation_row",
                "edit_rotation",
                "add_rotation",
                "remove_rotation",
                "new_rotation",
                "Correlation time (ns)",
            ),
        ]
        self.dialog = None
        self.file_window = None
        self.file_action = ""
        self.help_window = EmTkHelpWindow(
            title="Time-resolved anisotropy — Help",
            resource=Path(__file__).with_name("help.md"),
            owner=self,
        )
        self.tour = EmTkGuidedTour(
            steps=Path(__file__).with_name("guide.json"),
            get_target_rect=lambda key: self.item_rects.get(key),
            owner=self,
            wait_for_controls=True,
            on_step_change=self.reveal_step,
        )
        self.docks = DockManager(Split("h", 0.20, Region("navigation"), Region("step")))
        self.docks.add_window(
            "navigation", "Anisotropy workflow", self.navigation, dock="navigation", closable=False
        )
        self.docks.add_window("step", "Workflow step", self.content, dock="step", closable=False)
        super().__init__(self.render, continuous=False)

    def restore_settings(self, settings):
        self.model.restore_preferences(settings)
        self.step_index = max(0, min(int(settings.get("step_index", 0)), len(self.steps) - 1))

    def export_settings(self):
        return {**self.model.export_preferences(), "step_index": self.step_index}

    def select_step(self, index):
        self.step_index = max(0, min(int(index), len(self.steps) - 1))
        self.tour.notify_used(self.steps[self.step_index]["title"])

    def reveal_step(self, index, step):
        key = EmTkGuidedTour._target_key(step.get("target"))
        targets = {
            "data_vv_path": 1,
            "Normalize IRF": 2,
            "g_factor": 3,
            "Components": 4,
            "Finish": 5,
        }
        if key in targets:
            self.step_index = targets[key]
        elif index == 0:
            self.step_index = 0

    def error(self, action):
        try:
            return action()
        except Exception as exc:
            self.model.status = f"Error: {exc}"
            return None

    def choose(self, action):
        self.file_action = action
        mode = "save" if action in ("save_spectra", "export_irfs") else "open"
        title = (
            "Save spectra"
            if action == "save_spectra"
            else "Load spectra"
            if action == "load_spectra"
            else "Export corrected IRFs"
            if action == "export_irfs"
            else "Select polarized decay"
        )
        filename = (
            "anisotropy.spk.json"
            if action == "save_spectra"
            else "corrected_irfs.dat"
            if action == "export_irfs"
            else ""
        )
        filters = (
            "Spectra (*.spk.json *.json);;All files (*)"
            if "spectra" in action
            else "TCSPC data (*.dat *.txt *.csv *.npy *.thd *.pqres);;All files (*)"
        )
        self.dialog = FileDialog(title, mode=mode, filename=filename, filters=filters)
        self.file_window = DialogWindow(title, size=(760, 540))

    def navigation(self, box):
        for index, step in enumerate(self.steps):
            if im.selectable(
                f"{step.get('icon', '')} {step['title']}##anisotropy{index}",
                selected=self.step_index == index,
            ):
                self.select_step(index)
            im.set_item_tooltip(step.get("subtitle", step["title"]))
            self.item_rects[step["title"]] = im.get_item_rect()
        if im.button("Back"):
            self.select_step(self.step_index - 1)
        im.set_item_tooltip("Return to the previous workflow step.")
        im.same_line()
        ready = (self.step_index != 1 or self.model.data_ready) and (
            self.step_index != 4 or self.model.components_ready
        )
        im.begin_disabled(not ready or self.step_index == len(self.steps) - 1)
        if im.button("Next"):
            self.select_step(self.step_index + 1)
        im.set_item_tooltip(
            "Continue to the next step; required files or components must be present."
        )
        im.end_disabled()
        if im.button("Help"):
            self.help_window.show()
        im.set_item_tooltip(
            "Explain polarized decays, background correction and parameter linking."
        )
        im.same_line()
        if im.button("Guide"):
            self.tour.start()
        im.set_item_tooltip("Follow a guided tour through the real wizard controls.")
        im.text_wrapped(self.model.status)

    def data_step(self):
        m = self.model
        _, m.stacked_files = im.checkbox("Two stacked VV/VH files", m.stacked_files)
        im.set_item_tooltip(
            "Each IRF/data file contains both polarization channels; otherwise choose four separate files."
        )
        fields = [
            ("irf_vv_path", "IRF VV/VH" if m.stacked_files else "IRF VV"),
            ("data_vv_path", "Data VV/VH" if m.stacked_files else "Data VV"),
        ]
        if not m.stacked_files:
            fields = [
                ("irf_vv_path", "IRF VV"),
                ("irf_vh_path", "IRF VH"),
                ("data_vv_path", "Data VV"),
                ("data_vh_path", "Data VH"),
            ]
        for attr, label in fields:
            changed, value = im.input_text(label, getattr(m, attr))
            im.set_item_tooltip(f"Path to the {label} curve; paste a path or use Browse.")
            self.item_rects[attr] = im.get_item_rect()
            if changed:
                setattr(m, attr, value)
                if m.files_ready():
                    self.tour.notify_used("data_vv_path")
            if im.button(f"Browse {label}##{attr}"):
                self.choose(attr)
            im.set_item_tooltip(f"Choose the {label} file from disk.")
        if not m.stacked_files:
            _, m.first_column_is_time = im.checkbox(
                "First column is time (ns)", m.first_column_is_time
            )
            im.set_item_tooltip(
                "Keep a measured time axis unchanged; otherwise treat the first column as channel indices."
            )
        _, m.bin_width = bounded_float("Bin width (ns)", m.bin_width, minimum=1e-6, maximum=100.0)
        im.set_item_tooltip(
            "Time per histogram channel for channel-index or stacked files; time-axis columns are preserved."
        )
        _, m.rep_rate = bounded_float(
            "Repetition rate (MHz)", m.rep_rate, minimum=0.001, maximum=1e4
        )
        im.set_item_tooltip("Excitation repetition rate used to initialize the lifetime fits.")
        _, m.skiprows = bounded_int("Header rows", m.skiprows, minimum=0, maximum=100000)
        im.set_item_tooltip("Number of header rows to skip while reading text decays.")
        _, m.use_header = im.checkbox("Use file header", m.use_header)
        im.set_item_tooltip("Read available channel/calibration information from the file header.")
        im.text_wrapped(
            "All required files are ready."
            if m.files_ready()
            else "Select each required file before continuing."
        )

    def normalization_step(self):
        m = self.model
        if im.button("Load / reload data"):
            self.error(m.load_data)
        im.set_item_tooltip(
            "Read all selected IRF and decay files, then initialize a background region."
        )
        if im.button("Export corrected IRFs"):
            self.choose("export_irfs")
        im.set_item_tooltip(
            "Save the two background-subtracted, intensity-matched IRFs with their time-bin width."
        )
        maximum = min(
            (len(m.data[key].y) for key in ("irf_vv", "irf_vh") if m.data[key] is not None),
            default=1000000,
        )
        changed, lower = bounded_int("Background from", m.region_lb, minimum=0, maximum=maximum)
        im.set_item_tooltip("First background channel, inclusive; choose a signal-free region.")
        changed2, upper = bounded_int("Background to", m.region_ub, minimum=0, maximum=maximum)
        im.set_item_tooltip("Last background channel boundary, exclusive.")
        if changed or changed2:
            self.error(lambda: m.apply_region(lower, upper))
        if implot.begin_plot("IRF normalization", size=(-1.0, -1.0)):
            implot.setup_axes("Channel", "IRF counts")
            implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
            series = m.plot_series()
            for curve in series:
                y = np.asarray(curve["y"])
                implot.plot_line(curve["name"], np.asarray(curve["x"]), np.where(y > 0, y, np.nan))
            if series:
                positive = np.concatenate(
                    [np.asarray(curve["y"])[np.asarray(curve["y"]) > 0] for curve in series]
                )
                minimum = max(float(positive.min()) * 0.5, 1e-12) if positive.size else 1e-12
                maximum = max(float(positive.max()), minimum) * 1.1 if positive.size else 1.0
                region = implot.drag_rect(
                    1,
                    float(m.region_lb),
                    minimum,
                    float(m.region_ub),
                    maximum,
                    col=(70, 200, 90, 180),
                    flags=implot.DRAG_TOOL_FLAGS_NO_FIT,
                )
                if region.modified:
                    self.error(lambda: m.apply_region(int(region.x_min), int(region.x_max)))
            implot.end_plot()

    def components_step(self):
        if im.button("Save spectra"):
            if self.model.spk_path:
                self.error(self.model.save_spectra)
            else:
                self.choose("save_spectra")
        im.set_item_tooltip(
            "Save the lifetime and rotation components as amplitude/value pairs in JSON."
        )
        im.same_line()
        if im.button("Load spectra"):
            self.choose("load_spectra")
        im.set_item_tooltip("Replace both component lists from a saved spectrum file.")
        for spec, state in zip(self.spectrum_specs, self.forms):
            draw_form(spec, self.model, state)

    def content(self, box):
        m = self.model
        step = self.steps[self.step_index]
        im.text(step["title"])
        im.text_wrapped(step.get("subtitle", ""))
        im.separator()
        if self.step_index == 0:
            im.text_wrapped(_clean_html_text(m.welcome_html()))
        elif self.step_index == 1:
            self.data_step()
        elif self.step_index == 2:
            self.normalization_step()
        elif self.step_index == 3:
            for attr, label, tip in [
                ("g_factor", "g-factor", "Detection-efficiency ratio between VV and VH channels."),
                ("l1", "l1", "Polarization-mixing correction of the parallel channel."),
                ("l2", "l2", "Polarization-mixing correction of the perpendicular channel."),
            ]:
                changed, value = bounded_float(
                    label,
                    getattr(m, attr),
                    minimum=0.001 if attr == "g_factor" else -10.0,
                    maximum=100.0 if attr == "g_factor" else 10.0,
                    step=0.01,
                )
                im.set_item_tooltip(tip)
                self.item_rects[attr] = im.get_item_rect()
                if changed:
                    setattr(m, attr, value)
                    self.tour.notify_used(attr)
        elif self.step_index == 4:
            self.components_step()
        else:
            im.text_wrapped(_clean_html_text(m.finish_html()))
            if im.button("Create fits"):
                self.error(m.create_fits)
            im.set_item_tooltip(
                "Create the VV, VH and global fits with configured spectra, corrected IRFs and linked parameters."
            )

    def render(self):
        vp = im.get_main_viewport()
        box = (*vp.pos, *vp.size)
        self.item_rects.clear()
        for form in self.forms:
            form.rects.clear()
        im.begin_disabled(self.dialog is not None)
        self.docks.draw(box)
        im.end_disabled()
        if self.dialog is not None:
            pressed = self.file_window.begin(box)
            result = self.dialog.draw()
            if result:
                action = self.file_action
                self.dialog = None
                if action == "load_spectra":
                    self.error(lambda: self.model.load_spectra(result[0]))
                elif action == "save_spectra":
                    self.error(lambda: self.model.save_spectra(result[0]))
                elif action == "export_irfs":
                    self.error(lambda: self.model.export_irfs(result[0]))
                else:
                    setattr(self.model, action, str(result[0]))
                    if self.model.files_ready():
                        self.tour.notify_used("data_vv_path")
            elif result is False or pressed == "close":
                self.dialog = None
            self.file_window.end()
        self.help_window.draw(box)
        self.tour.draw(*vp.size)


def make_app():
    return AnisotropyApp()
