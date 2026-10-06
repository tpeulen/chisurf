"""Native bead-stack inspection, Gaussian PSF fitting and batch export."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from emtk import im, implot
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog
from emtk.view_form import FormState, draw_form

from chisurf.emtk.dataset_picker import DatasetPicker
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.plugins.emtk_layout import LabelColumn, button_row, labelled, layout_spec

from .canvas import ImageCanvas
from .jobs import SnapshotJob
from .view_model import PsfViewModel

HERE = Path(__file__).parent


class BeadNavigator:
    """The bead-index field: ``attr`` for the form, the range follows the detected beads, a change selects and fits."""

    busy = False

    def __init__(self, app):
        self._app = app

    @property
    def bead_index(self):
        return self._app.bead_index

    @bead_index.setter
    def bead_index(self, value):
        value = int(value)
        if value != self._app.bead_index:
            self._app.bead_index = value
            self._app.start("select_bead_index", value)

    def bounds(self, name):
        return 0, max(0, len(self._app.model.detected_beads) - 1)

    def enabled(self, name):
        return bool(self._app.model.detected_beads) and not self.busy


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
        self.last_dir = ""
        self._stack = None
        self._restore_selection = None
        self.item_rects = {}
        self.beads = BeadNavigator(self)
        self.panels = self.build_panels()
        self.forms = {n: FormState() for n in self.panels}
        self.columns = {n: LabelColumn() for n in self.panels}
        self.help_window = EmTkHelpWindow(
            title="PSF determination: Help", resource=HERE / "help.md", owner=self
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            get_target_rect=lambda key: (
                self.item_rects.get(key)
                or next((f.rects[key] for f in self.forms.values() if key in f.rects), None)
            ),
            owner=self,
            wait_for_controls=True,
        )
        for form in self.forms.values():
            form.on_used = self.tour.notify_used
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

    def build_panels(self):
        """The Qt tool's value sections (one source of truth), as spin forms."""
        spec = json.loads((HERE / "psf.view.json").read_text())["sections"][0]["sections"][0][
            "sections"
        ]
        out = {}
        for panel in spec:
            if panel.get("type") != "panel":
                continue
            panel = copy.deepcopy(panel)
            panel["n_col"] = 1
            for field in panel["sections"]:
                field["style"] = "spin"
            key = {"PSF parameters": "psf", "Detection": "detection"}[panel["title"]]
            panel["description"] = {
                "psf": "Pixel size, z step and the ROI cut around a bead for the 3-D Gaussian fit.",
                "detection": "Thresholds that decide which bright regions count as beads.",
            }[key]
            out[key] = layout_spec({"sections": [panel]})
        out["beads"] = layout_spec(
            {
                "sections": [
                    {
                        "type": "panel",
                        "title": "Beads",
                        "description": "Walk through the detected beads; selecting one fits it and opens its z slice.",
                        "sections": [
                            {
                                "type": "value",
                                "attr": "bead_index",
                                "label": "Bead index",
                                "kind": "int",
                                "style": "spin",
                                "minimum": 0,
                                "maximum": 100000,
                                "step": 1,
                                "description": "Zero-based index of the detected bead; selecting a bead fits it and opens its z slice.",
                            }
                        ],
                    }
                ]
            }
        )
        return out

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
        directory = self.last_dir or (
            str(Path(self.model.filename).parent) if self.model.filename else None
        )
        self.dialog = FileDialog(
            action.replace("_", " ").title(),
            mode="open" if load else "save",
            filters=filters,
            filename=filename,
            directory=directory,
        )
        self.file_window = DialogWindow(self.dialog.title, size=(700, 540), key=f"file_{id(self)}")
        self.file_window.show()

    def remember(self, name):
        self.item_rects[name] = im.get_item_rect()

    def form(self, name):
        spec, column = self.panels[name], self.columns[name]
        if not column.ready:
            column.measure([f["label"] for f in labelled(spec["sections"])])
        column.pad(spec["sections"])
        draw_form(spec, self.model if name != "beads" else self.beads, self.forms[name])

    def do(self, key):
        m = self.model
        {
            "load_stack": lambda: self.choose("load_stack"),
            "demo": self.load_demo,
            "mmfdb": self.picker.open,
            "detect_beads": lambda: self.start("detect_beads"),
            "fit_selected": lambda: self.start("fit_selected"),
            "fit_all": lambda: self.start("fit_all"),
            "export_csv": lambda: self.choose("export_csv"),
            "save_settings": lambda: self.choose("save_settings"),
            "load_settings": lambda: self.choose("load_settings"),
            "help": self.help_window.show,
            "guide": self.tour.start,
        }[key]()
        self.tour.notify_used(key)

    def load_demo(self):
        if self.job.busy:
            return
        self.error = ""
        self.model.load_demo()
        self.bead_index = 0

    def controls(self, box):
        m = self.model
        idle = not (self.job.busy or self.dialog is not None or self.picker.is_open)
        pressed = button_row(
            [
                {
                    "label": "Load stack",
                    "key": "load_stack",
                    "enabled": idle,
                    "tip": "Load a 2-D TIFF image or a 3-D TIFF bead stack (or drop the file on the window).",
                },
                {
                    "label": "Demo stack",
                    "key": "demo",
                    "enabled": idle,
                    "tip": "Replace the stack by a generated one with five beads of known size (a demo, not data).",
                },
                {
                    "label": "MMFDB dataset",
                    "key": "mmfdb",
                    "enabled": idle,
                    "tip": "Select a registered TIFF dataset from the MMFDB catalog.",
                },
                {
                    "label": "Detect",
                    "key": "detect_beads",
                    "enabled": idle and m.enabled("detect_beads"),
                    "tip": "Find beads using the adaptive quantile threshold and the separation filters.",
                },
                {
                    "label": "Fit selected",
                    "key": "fit_selected",
                    "enabled": idle and m.enabled("fit_selected"),
                    "tip": "Fit a 3-D Gaussian to the clicked or selected bead.",
                },
                {
                    "label": "Fit all",
                    "key": "fit_all",
                    "enabled": idle and m.enabled("fit_all"),
                    "tip": "Fit every detected bead and report the complete batch including failures.",
                },
                {
                    "label": "Export CSV",
                    "key": "export_csv",
                    "enabled": idle and m.enabled("export_csv"),
                    "tip": "Refit and export all detected beads with physical widths and fit quality.",
                },
                {
                    "label": "Save settings",
                    "key": "save_settings",
                    "enabled": idle,
                    "tip": "Save calibration, ROI, detection and display settings to JSON.",
                },
                {
                    "label": "Load settings",
                    "key": "load_settings",
                    "enabled": idle,
                    "tip": "Restore settings and reopen the stored source stack when available.",
                },
                {
                    "label": "Help",
                    "key": "help",
                    "tip": "Explain how a bead stack gives the PSF and what to check.",
                },
                {
                    "label": "Guide",
                    "key": "guide",
                    "tip": "Walk through loading, detection, fitting and the checks.",
                },
            ],
            remember=self.remember,
        )
        if pressed:
            self.do(pressed)
        if self.job.busy:
            im.text_wrapped(self.job.progress)
        if self.error or self.job.error:
            im.text_wrapped("Error: " + (self.error or self.job.error))
        im.text_wrapped(m.filename or ("Demo stack" if m.stack is not None else "No stack loaded."))
        im.text_disabled(f"{len(m.detected_beads)} detected beads")
        im.separator()
        self.form("psf")
        self.form("detection")
        self.beads.busy = not idle
        self.form("beads")

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

    export_settings = settings

    def restore_settings(self, data):
        if isinstance(data, dict):
            self.apply_settings(data)

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
        for form in self.forms.values():
            form.rects.clear()
        self.docks.draw((0, 0, *vp.size))
        if self.dialog:
            pressed = self.file_window.begin((0, 0, *vp.size))
            result = self.dialog.draw()
            if result:
                try:
                    path = Path(result[0])
                    self.last_dir = str(path.parent)
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
        self.help_window.draw((0.0, 0.0, *vp.size))
        self.tour.draw(*vp.size)


def make_app(**kwargs):
    from chisurf.emtk.i18n import install

    install()
    return PsfDeterminationApp(model=kwargs.get("model"))
