"""Native bead-stack inspection, Gaussian PSF fitting and batch export."""

from __future__ import annotations

import json
from pathlib import Path

from emtk import im, implot
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog

from chisurf.emtk.dataset_picker import DatasetPicker
from chisurf.plugins.calculator.inputs import bounded_int
from chisurf.plugins.calculator.native_form import fields

from .canvas import ImageCanvas
from .jobs import SnapshotJob
from .view_model import PsfViewModel


class PsfDeterminationApp(ImApp):
    def __init__(self, model=None):
        self.model = model or PsfViewModel()
        self.job = SnapshotJob(self.model)
        self.canvas = ImageCanvas("bead_stack")
        self.canvas.colormap = self.model.colormap
        self.profile_axis = "x"
        self.bead_index = 0
        self.dialog = None
        self.file_window = None
        self.dialog_action = ""
        self.error = ""
        self._stack = None
        self._restore_selection = None
        self.item_rects = {}
        self.sections = json.loads(Path(__file__).with_name("psf.view.json").read_text())[
            "sections"
        ][0]["sections"]
        self.picker = DatasetPicker(formats=["tiff", "tif"], on_paths=self.open_paths)
        self.docks = DockManager(
            Split(
                "h",
                0.3,
                Region("controls"),
                Split(
                    "v",
                    0.60,
                    Region("stack"),
                    Split("h", 0.55, Region("profiles"), Region("results")),
                ),
            )
        )
        self.docks.add_window(
            "controls", "Controls", self.controls, dock="controls", closable=False
        )
        self.docks.add_window("stack", "Bead stack", self.stack_view, dock="stack", closable=False)
        self.docks.add_window(
            "profiles", "x / y / z profiles", self.profiles, dock="profiles", closable=False
        )
        self.docks.add_window(
            "results", "Fit results", self.results, dock="results", closable=False
        )
        super().__init__(self.render, continuous=False)

    def on_files_dropped(self, paths):
        if self.job.busy:
            return False
        self.open_paths(paths)
        return bool(paths)

    def open_paths(self, paths):
        if paths:
            self.start("load_stack", str(paths[0]))

    def start(self, method, *args):
        if self.job.busy:
            return False
        if method == "load_stack":
            self._restore_selection = None
        if method == "detect_beads" and self.model.stack is None:
            self.error = "Load a stack first."
            return False
        if method == "fit_selected" and self.model.selected_bead is None:
            self.error = "Click a bead or detect beads first."
            return False
        if method in ("fit_all", "export_csv") and not self.model.detected_beads:
            self.error = "Detect beads first."
            return False
        self.error = ""
        return self.job.start(method, *args)

    def pick_bead(self, point):
        if self.job.busy:
            return
        self.model.selected_bead = tuple(point)
        self.start("fit_selected")

    def choose(self, action):
        self.dialog_action = action
        load = action in ("load_stack", "load_settings")
        filters = (
            "TIFF (*.tif *.tiff);;All files (*)"
            if action == "load_stack"
            else "CSV (*.csv)"
            if action == "export_csv"
            else "JSON (*.json)"
        )
        filename = (
            "psf_batch_results.csv"
            if action == "export_csv"
            else "psf_settings.json"
            if action == "save_settings"
            else ""
        )
        directory = str(Path(self.model.filename).parent) if self.model.filename else None
        self.dialog = FileDialog(
            action.replace("_", " ").title(),
            mode="open" if load else "save",
            filters=filters,
            filename=filename,
            directory=directory,
        )
        self.file_window = DialogWindow(self.dialog.title, size=(700, 540), key=f"file_{id(self)}")
        self.file_window.show()

    def controls(self, box):
        actions = [
            (
                "Load stack",
                "Load a 2-D TIFF image or a 3-D TIFF bead stack.",
                lambda: self.choose("load_stack"),
            ),
            (
                "MMFDB dataset",
                "Select a registered TIFF dataset from the MMFDB catalog.",
                self.picker.open,
            ),
            (
                "Detect",
                "Find beads using the adaptive quantile threshold and separation filters.",
                lambda: self.start("detect_beads"),
            ),
            (
                "Fit selected",
                "Fit a 3-D Gaussian to the clicked or selected bead.",
                lambda: self.start("fit_selected"),
            ),
            (
                "Fit all",
                "Fit every detected bead and report the complete batch including failures.",
                lambda: self.start("fit_all"),
            ),
            (
                "Export CSV",
                "Refit and export all detected beads with physical widths and fit quality.",
                lambda: self.choose("export_csv"),
            ),
            (
                "Save settings",
                "Save calibration, ROI, detection and display settings to JSON.",
                lambda: self.choose("save_settings"),
            ),
            (
                "Load settings",
                "Restore settings and reopen the stored source stack when available.",
                lambda: self.choose("load_settings"),
            ),
        ]
        im.begin_disabled(self.job.busy or self.dialog is not None or self.picker.is_open)
        for label, tip, action in actions:
            if im.button(label):
                action()
            im.set_item_tooltip(tip)
            self.item_rects[label] = im.get_item_rect()
        im.separator()
        fields(self.model, self.sections[:1], item_rects=self.item_rects)
        im.begin_disabled(not self.model.detected_beads)
        changed, self.bead_index = bounded_int(
            "Bead index",
            self.bead_index,
            minimum=0,
            maximum=max(0, len(self.model.detected_beads) - 1),
        )
        im.set_item_tooltip(
            "Navigate detected beads by zero-based index; selecting a bead fits it and opens its z slice."
        )
        if changed:
            self.start("select_bead_index", self.bead_index)
        im.end_disabled()
        im.end_disabled()
        if self.model.filename:
            im.text_wrapped(self.model.filename)
        im.text_unformatted(f"{len(self.model.detected_beads)} detected beads")
        if self.job.busy:
            im.text_wrapped(self.job.progress)
        if self.error or self.job.error:
            im.text_wrapped(self.error or self.job.error)

    def stack_view(self, box):
        self.canvas.draw(
            self.model.stack,
            markers=self.model.detected_beads,
            on_pick=self.pick_bead,
            fit_circle=self.model.fit_circle(),
            pick_enabled=not self.job.busy and self.dialog is None and not self.picker.is_open,
        )
        self.model.colormap = self.canvas.colormap
        self.item_rects["stack"] = self.canvas.rect

    def profiles(self, box):
        if im.begin_tab_bar("psf_profiles"):
            for axis in ("x", "y", "z"):
                if im.begin_tab_item(axis + " profile"):
                    self.profile_axis = axis
                    im.end_tab_item()
                im.set_item_tooltip(
                    f"Inspect the measured {axis} profile and Gaussian fit through the bead center."
                )
            im.end_tab_bar()
        axis = self.profile_axis
        if implot.begin_plot(axis + " profile", (-1, -1)):
            implot.setup_axes(axis + (" [slices]" if axis == "z" else " [pixels]"), "Intensity")
            implot.setup_legend()
            for series in getattr(self.model, axis + "_profile_series")():
                if series.get("no_line"):
                    implot.set_next_marker_style(implot.MARKER_CIRCLE, 4.0, (220, 220, 220, 255))
                    implot.plot_scatter(series["name"], series["x"], series["y"])
                else:
                    implot.set_next_line_style((255, 70, 70, 255), 2.0)
                    implot.plot_line(series["name"], series["x"], series["y"])
            implot.end_plot()
            im.set_item_tooltip(
                "Measured bead intensity and its fitted 3-D Gaussian evaluated along this axis."
            )

    def results(self, box):
        im.text_wrapped(self.model.results_text)

    def settings(self):
        names = (
            "pixel_size_nm",
            "z_step_nm",
            "roi_xy",
            "roi_z",
            "pixels_per_frame",
            "min_distance",
            "min_area",
            "colormap",
            "filename",
            "selected_bead",
        )
        return dict(
            {name: getattr(self.model, name) for name in names},
            display=dict(
                z=self.canvas.z,
                gamma=self.canvas.gamma,
                auto_levels=self.canvas.auto_levels,
                low=self.canvas.low,
                high=self.canvas.high,
            ),
        )

    def apply_settings(self, data):
        allowed = {
            name: getattr(self.model, name)
            for name in (
                "pixel_size_nm",
                "z_step_nm",
                "roi_xy",
                "roi_z",
                "pixels_per_frame",
                "min_distance",
                "min_area",
                "colormap",
            )
        }
        for name in allowed:
            if name in data:
                setattr(self.model, name, type(allowed[name])(data[name]))
        display = data.get("display", {})
        for name in ("z", "gamma", "auto_levels", "low", "high"):
            if name in display:
                setattr(self.canvas, name, display[name])
        self.canvas.colormap = self.model.colormap
        filename = data.get("filename", "")
        selection = data.get("selected_bead")
        if filename and Path(filename).is_file():
            if self.start("load_stack", filename):
                self._restore_selection = (
                    display.get("z", 0),
                    tuple(selection) if selection else None,
                )
        elif selection and self.model.stack is not None:
            self.model.selected_bead = tuple(selection)

    def animating(self):
        return self.job.busy or self.picker.is_open or super().animating()

    def render(self):
        changed = self.job.poll()
        if not self.job.busy and self.job.error:
            self._restore_selection = None
        if changed:
            if self.model.stack is not self._stack:
                self.canvas.reset()
                self._stack = self.model.stack
            if self.model.selected_bead:
                self.canvas.z = int(self.model.selected_bead[0])
            if self._restore_selection:
                self.canvas.z, self.model.selected_bead = self._restore_selection
                self._restore_selection = None
        vp = im.get_main_viewport()
        self.docks.draw((0, 0, *vp.size))
        if self.dialog:
            pressed = self.file_window.begin((0, 0, *vp.size))
            result = self.dialog.draw()
            if result:
                try:
                    path = Path(result[0])
                    if self.dialog_action == "save_settings":
                        path.with_suffix(".json").write_text(json.dumps(self.settings(), indent=2))
                    elif self.dialog_action == "load_settings":
                        self.apply_settings(json.loads(path.read_text()))
                    else:
                        if self.dialog_action == "export_csv":
                            path = path.with_suffix(".csv")
                        self.start(self.dialog_action, str(path))
                    self.dialog = None
                except Exception as exc:
                    self.error = str(exc)
            elif result is False:
                self.dialog = None
            self.file_window.end()
            if pressed == "close":
                self.dialog = None
        self.picker.render((0, 0, *vp.size))


def make_app(**kwargs):
    from chisurf.emtk.i18n import install

    install()
    return PsfDeterminationApp(model=kwargs.get("model"))
