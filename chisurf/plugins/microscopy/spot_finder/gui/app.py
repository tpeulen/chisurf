"""Native workflow-based spot detection with ROI editing and Gaussian picking."""

from __future__ import annotations

import contextlib
import copy
import dataclasses
import json
from pathlib import Path

from emtk import im
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog
from emtk.view_form import FormState, draw_form

from chisurf.core.datastore import rows_from_table
from chisurf.core.roi import RegionCollection
from chisurf.emtk.dataset_picker import DatasetPicker
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.plugins.calculator.native_form import plain
from chisurf.plugins.emtk_layout import button_row, layout_spec
from chisurf.plugins.microscopy.psf_determination.gui.canvas import ImageCanvas
from chisurf.plugins.microscopy.psf_determination.gui.jobs import SnapshotJob

from .regions import RegionControls
from .view_model import SpotFinderViewModel


class _Rows(list):
    revision = 0


@contextlib.contextmanager
def _pointer_masked(active):
    """A table under the guided-tour card must not take the press meant for the card's buttons (an emtk gap: a
    ``data_table`` takes a press whatever is drawn over it); while the tour is shown the table sees no pointer input."""
    if not active:
        yield
        return
    io = im.get_current_context().io
    saved = (list(io.mouse_clicked), list(io.mouse_down), list(io.mouse_released), list(io.mouse_double_clicked), io.mouse_pos)
    io.mouse_clicked, io.mouse_down, io.mouse_released = [False] * 5, [False] * 5, [False] * 5
    io.mouse_double_clicked = [False] * 5
    io.mouse_pos = (-1e6, -1e6)
    try:
        yield
    finally:
        io.mouse_clicked, io.mouse_down, io.mouse_released, io.mouse_double_clicked, io.mouse_pos = saved


def _table(source, columns, **extra):
    return {"sections": [{"type": "custom", "key": "data_table", "description": extra.pop("description"),
                          "options": {"source": source, "columns": columns, "status": True, **extra}}]}


FILE_SPEC = _table("file_rows", [
    {"key": "file", "title": "Imaging files", "description": "The input file; the full path is in the tooltip."},
    {"key": "folder", "title": "Folder", "description": "The folder of the file."}],
    description="The files of this detection batch. Select one for Remove file; Delete removes the selected row.",
    height=96, row_key="row", selected_call="select_file", delete_call="delete_file")
RUN_SPEC = _table("run_rows", [
    {"key": "input", "title": "File", "description": "The input file."},
    {"key": "status", "title": "Status", "width": 80, "description": "ok, empty or failed."},
    {"key": "n_regions", "title": "Regions", "width": 80, "description": "Number of regions found."},
    {"key": "container", "title": "Written to", "description": "The measurement container the result was written to."},
    {"key": "reason", "title": "Reason", "description": "Why a file produced no regions."}],
    description="One row per input file of the last run, including empty and failed ones.", expand=True, reserve=4)
MEASURE_SPEC = {"sections": [{"type": "custom", "key": "data_table",
    "description": "Measured geometry and intensity of every region of the shown result.",
    "options": {"source": "measure_rows", "columns_source": "measure_columns", "expand": True, "reserve": 4, "status": True,
                "fit_columns": True}}]}
INPUT_SPEC = {"sections": [{"type": "panel", "title": "Input", "n_col": 2, "collapsible": True,
    "description": "Which detector channels and frame are analyzed, and whether Detect writes results.", "sections": [
    {"type": "value", "attr": "channel_field", "kind": "str", "label": "Detector channels", "width": 150,
     "description": "Photon-routing channels to sum, comma separated; blank selects every available detector channel."},
    {"type": "value", "attr": "frame", "kind": "int", "style": "spin", "label": "Frame", "minimum": -1, "maximum": 1000000000,
     "description": "Photon/image frame to analyze; -1 sums all available frames."},
    {"type": "toggle", "attr": "write_results", "label": "Write results",
     "description": "Detect stores each label image and region table in its own measurement container; Preview always writes nothing."}]}]}


def _spin(sections):
    for sec in sections:
        if sec.get("type") == "value" and sec.get("kind") in ("int", "float") and not sec.get("read_only"):
            sec["style"] = "spin"
        _spin(sec.get("sections", []))


class SpotFinderApp(ImApp):
    def __init__(self, model=None):
        self.model = model or SpotFinderViewModel()
        self.job = SnapshotJob(self.model)
        self.canvas = ImageCanvas("spot_field")
        self.canvas.colormap = "inferno"
        self.regions = RegionControls(self.model, self.choose)
        self.file_index = 0
        self.table_view = 0
        self.region_filter = ""
        self.channel_text = ",".join(map(str, self.model.channels))
        self.dialog = None
        self.file_window = None
        self.dialog_action = ""
        self.error = ""
        self.item_rects = {}
        self._deferred_context = {}
        self._image = None
        self.sections = json.loads(Path(__file__).with_name("spot_finder.view.json").read_text())[
            "sections"
        ][0]["sections"]
        detection = self.sections[0]["sections"]
        top = [s for s in detection if s.get("attr") in ("workflow", "name")]
        panels = [json.loads(json.dumps(s)) for s in detection if s.get("type") == "panel"]
        for panel in panels:
            panel["collapsible"] = True
            panel["sections"] = [x for x in panel["sections"] if x.get("type") != "button_row"]
        _spin(panels)
        self.spec_top = layout_spec({"sections": json.loads(json.dumps(top))})
        self.spec_detector = layout_spec({"sections": panels})
        self.forms = {k: FormState(on_used=lambda n: self.tour.notify_used(n)) for k in
                      ("files", "main", "detector", "input", "tables")}
        self.picker = DatasetPicker(
            formats=["tif", "tiff", "ptu", "pto", "ht3", "spc", "pt3"], on_paths=self.open_paths
        )
        self.help_window = EmTkHelpWindow(
            title="Spot Finder — Help", resource=Path(__file__).with_name("help.md"), owner=self
        )
        self.tour = EmTkGuidedTour(
            steps=Path(__file__).with_name("guide.json"),
            get_target_rect=lambda key: self.item_rects.get(key),
            owner=self,
            wait_for_controls=True,
        )
        for step in self.tour.steps:
            target = step.get("target", {})
            if target.get("title"):
                step["target"] = {"key": target["title"]}
        self.docks = DockManager(
            Split("h", 0.34, Region("controls"), Split("v", 0.70, Region("image"), Region("run")))
        )
        self.docks.add_window(
            "controls",
            "Detection and analysis regions",
            self.controls,
            dock="controls",
            closable=False,
        )
        self.docks.add_window("image", "Regions", self.image_view, dock="image", closable=False)
        self.docks.add_window(
            "run", "Run and region measurements", self.tables, dock="run", closable=False
        )
        super().__init__(self.render, continuous=False)

    def open_paths(self, paths):
        if self.job.busy:
            return
        for path in paths:
            value = str(path)
            if value not in self.model.files:
                self.model.files.append(value)
        self.model.notify("settings")

    def on_files_dropped(self, paths):
        self.open_paths(paths)
        return not self.job.busy

    def choose(self, action):
        self.dialog_action = action
        opens = action in ("add_files", "load_regions", "load_settings")
        filters = (
            "Imaging (*.pto *.ptu *.ht3 *.spc *.pt3 *.tif *.tiff);;All files (*)"
            if action == "add_files"
            else "Tables (*.tsv *.csv)"
            if action == "export_results"
            else "Regions (*.json *.tif *.tiff *.npy);;All files (*)"
            if "regions" in action
            else "JSON (*.json)"
        )
        filename = (
            "regions.tsv"
            if action == "export_results"
            else "regions.json"
            if action == "save_regions"
            else "spot_finder.json"
            if action == "save_settings"
            else ""
        )
        self.dialog = FileDialog(
            action.replace("_", " ").title(),
            mode="open" if opens else "save",
            filename=filename,
            filters=filters,
            multiselect=action == "add_files",
        )
        self.file_window = DialogWindow(self.dialog.title, size=(700, 540), key=f"file_{id(self)}")
        self.file_window.show()

    def start(self, method, *args):
        self.error = ""
        if method in ("run", "preview"):
            allowed, reason = self.model.can_run()
            if not allowed:
                self.error = reason
                return False
        if method == "export_results" and not self.model.has_results():
            self.error = "No regions to export."
            return False
        return self.job.start(method, *args)

    def pick_spot(self, point):
        if self.job.busy:
            return
        self.model.picked_point = tuple(point)
        self.tour.notify_used("Pick by clicking")
        self.start("pick_spot")

    # ── table sources and callbacks (the specs read these) ────────────────

    @property
    def file_rows(self):
        rows = _Rows([{"row": i, "file": Path(p).name, "folder": str(Path(p).parent), "path": p}
                      for i, p in enumerate(self.model.files)])
        rows.revision = hash(tuple(self.model.files))
        return rows

    def select_file(self, record):
        self.file_index = record["row"] if isinstance(record, dict) else 0

    def delete_file(self, record):
        if isinstance(record, dict) and not self.job.busy:
            self.remove_file(record["row"])

    def remove_file(self, index):
        if 0 <= index < len(self.model.files):
            self.model.files.pop(index)
            self.file_index = max(0, min(self.file_index, len(self.model.files) - 1))

    @property
    def run_rows(self):
        rows = _Rows(self.model.run_entries())
        rows.revision = hash(json.dumps(rows, default=str))
        return rows

    @property
    def measure_rows(self):
        result = self.model._current_result()
        rows = _Rows(rows_from_table(result.table) if result is not None else [])
        rows.revision = hash((id(result), len(rows)))
        return rows

    def measure_columns(self):
        return [{"key": key, "title": key, "description": "Measured " + key} for key in self.model.selection_columns()]

    # the input fields the Qt shared setup page carried, as attributes of the app for the spec
    @property
    def channel_field(self):
        return self.channel_text

    @channel_field.setter
    def channel_field(self, value):
        self.channel_text = str(value)
        try:
            self.model.channels = list(dict.fromkeys(int(v.strip()) for v in self.channel_text.split(",") if v.strip()))
            self.error = ""
        except ValueError:
            self.error = "Detector channels must be comma-separated integers."

    @property
    def frame(self):
        return self.model.frame

    @frame.setter
    def frame(self, value):
        self.model.frame = int(value)

    @property
    def write_results(self):
        return self.model.write_results

    @write_results.setter
    def write_results(self, value):
        self.model.write_results = bool(value)

    def enabled(self, name):
        return not (self.job.busy or self.dialog is not None or self.picker.is_open)

    def controls(self, box):
        pressed = button_row([
            {"label": "Help", "key": "help", "tip": "Explain detection recipes, ROI restriction, picking and measurement-container outputs."},
            {"label": "Guide", "key": "guide", "tip": "Work through the known-field demo with actual actions and image picking."},
        ], remember=self.remember)
        if pressed == "help":
            self.help_window.show()
        elif pressed == "guide":
            self.tour.start()
        busy = self.job.busy or self.dialog is not None or self.picker.is_open
        im.begin_disabled(busy)
        pressed = button_row([
            {"label": "Add files", "key": "Add files", "tip": "Select photon or camera imaging files for preview and batch detection."},
            {"label": "MMFDB datasets", "key": "MMFDB datasets", "tip": "Select registered photon/camera datasets from the MMFDB catalog."},
            {"label": "Remove file", "key": "Remove file", "enabled": bool(self.model.files), "tip": "Remove the selected input from this detection batch."},
            {"label": "Clear files", "key": "Clear files", "enabled": bool(self.model.files), "tip": "Remove every input file from the batch without deleting the files."},
        ], remember=self.remember)
        if pressed == "Add files":
            self.choose("add_files")
        elif pressed == "MMFDB datasets":
            self.picker.open()
        elif pressed == "Remove file":
            self.remove_file(self.file_index)
        elif pressed == "Clear files":
            self.model.files.clear()
        self.forms["files"].rects.clear()
        with _pointer_masked(self.tour.active):
            draw_form(FILE_SPEC, self, self.forms["files"])
        self.item_rects.update(self.forms["files"].rects)
        self.forms["main"].rects.clear()
        draw_form(self.spec_top, self.model, self.forms["main"])
        self.item_rects.update(self.forms["main"].rects)
        self.regions.draw()
        self.forms["detector"].rects.clear()
        draw_form(self.spec_detector, self.model, self.forms["detector"])
        self.item_rects.update(self.forms["detector"].rects)
        self.forms["input"].rects.clear()
        draw_form(INPUT_SPEC, self, self.forms["input"])
        self.item_rects.update(self.forms["input"].rects)
        im.end_disabled()
        actions = [
            ("Load demo", "Simulate/cache the known four-object photon field for validating a detection.", lambda: self.start("load_demo"), True),
            ("Preview", "Detect in the first input only and write nothing.", lambda: self.start("preview"), True),
            ("Detect", "Detect in every input; retain a run-table row even for empty or failed files.", lambda: self.start("run"), True),
            ("Add picks", "Add fitted picked ellipses to the current detection and remeasure the regions.", lambda: self.start("add_picked_to_detection"), True),
            ("Clear picks", "Forget every manually picked Gaussian proposal.", lambda: self.start("clear_picked"), True),
            ("Export", "Export all files' measured region rows as CSV or TSV.", lambda: self.choose("export_results"), self.model.has_results()),
            ("Save settings", "Save files, workflow deviations, routing, ROI composition and display state to JSON.", lambda: self.choose("save_settings"), True),
            ("Load settings", "Restore the complete analysis configuration from JSON.", lambda: self.choose("load_settings"), True),
        ]
        im.begin_disabled(busy)
        pressed = button_row([{"label": l, "key": l, "tip": t, "enabled": e} for l, t, _a, e in actions], remember=self.remember)
        im.end_disabled()
        if pressed and not busy:
            dict((l, a) for l, _t, a, _e in actions)[pressed]()
            self.tour.notify_used(pressed)
        summary = plain(self.model.summary()).strip()
        status = self.job.progress if self.job.busy else self.model.status_text
        if summary and summary != plain(status).strip():
            im.text_wrapped(summary)
        im.text_wrapped(plain(status))
        self.remember("status")
        if self.error or self.job.error:
            im.text_wrapped(self.error or self.job.error)

    def image_view(self, box):
        im.text("Filter regions")
        im.same_line(110)
        im.set_next_item_width(-1)
        _, self.region_filter = im.input_text(
            "##filter_regions", self.region_filter, hint="Region name or file"
        )
        self.remember("filter_regions")
        im.set_item_tooltip(
            "Filter detected-region names; measurements and image picking remain available."
        )
        entries = self.model.region_entries()
        displayed = [e for e in entries if self.region_filter.casefold() in e["label"].casefold()]
        labels = [e["label"] + " · " + e["badge"] for e in displayed]
        current = next(
            (i for i, e in enumerate(displayed) if e["id"] == self.model.current_region), 0
        )
        if displayed:
            im.text("Selected region")
            im.same_line(110)
            im.set_next_item_width(-1)
            changed, index = im.combo("##selected_region", current, labels)
            self.remember("selected_region")
            im.set_item_tooltip(
                "Browse each found region across all input files and inspect its measured geometry."
            )
            if changed:
                self.model.current_region = displayed[index]["id"]
        im.text_wrapped(plain(self.model.current_region_info()))
        image = self.model.detection_image()
        current = self.model._current_result()
        found = []
        if current is not None:
            from chisurf.core.roi import regionprops

            found = [
                props.as_ellipse(f"Region {props.label}")
                for props in regionprops(current.labels, current.intensity)
            ]
        self.canvas.draw(
            image,
            markers=self.model.current_region_marker(),
            found=found,
            picked=self.model.picked_regions(),
            analysis=self.model.regions,
            on_change=self.model.apply_regions,
            on_pick=self.pick_spot,
            pick_enabled=not self.job.busy and self.dialog is None and not self.picker.is_open,
            analysis_editable=not self.job.busy and self.dialog is None and not self.picker.is_open,
        )
        self.item_rects["Regions"] = self.canvas.rect
        self.item_rects["Pick by clicking"] = self.canvas.rect

    def tables(self, box):
        from emtk.im_core import Col

        for index, label in enumerate(["Run", "Region measurements"]):
            if index:
                im.same_line()
            selected = self.table_view == index
            if selected:
                im.push_style_color(Col.BUTTON, im.get_style().color(Col.TAB_SELECTED))
            if im.button(label):
                self.table_view = index
            if selected:
                im.pop_style_color(1)
            im.set_item_tooltip("Review all input outcomes." if index == 0 else
                                "Measured centroid, area, intensity and second moments of each region.")
            self.remember("tab_run" if index == 0 else "tab_measurements")
        self.forms["tables"].rects.clear()
        # a tour card drawn over a table would lose its button presses to the table (emtk gap): the tour has the table
        with _pointer_masked(self.tour.active):
            draw_form(RUN_SPEC if self.table_view == 0 else MEASURE_SPEC, self, self.forms["tables"])
        self.item_rects["Run"] = self.item_rects.get("run_rows") or self.item_rects.get("measure_rows")
        self.item_rects.update(self.forms["tables"].rects)

    def state_dict(self):
        settings = {
            field.name: getattr(self.model.settings, field.name)
            for field in dataclasses.fields(self.model.settings)
            if field.name != "roi"
        }
        return dict(
            files=self.model.files,
            settings=settings,
            regions=self.model.regions.to_dict(),
            channels=self.model.channels,
            frame=self.model.frame,
            name=self.model.name,
            write_results=self.model.write_results,
            pick_window=self.model.pick_window,
            display=dict(
                colormap=self.canvas.colormap,
                gamma=self.canvas.gamma,
                auto_levels=self.canvas.auto_levels,
                low=self.canvas.low,
                high=self.canvas.high,
            ),
        )

    def apply_state(self, state):
        from ..core.spots import SpotFinderSettings

        accepted = {field.name for field in dataclasses.fields(SpotFinderSettings)} - {"roi"}
        values = {key: value for key, value in state.get("settings", {}).items() if key in accepted}
        self.model.settings = SpotFinderSettings(**values)
        if "regions" in state:
            self.model.regions = RegionCollection.from_dict(state["regions"])
        self.model.files = [str(path) for path in state.get("files", [])]
        for key in ("channels", "frame", "name", "write_results", "pick_window"):
            if key in state:
                setattr(self.model, key, state[key])
        for key, value in state.get("display", {}).items():
            if key in ("colormap", "gamma", "auto_levels", "low", "high"):
                setattr(self.canvas, key, value)
        self.channel_text = ",".join(map(str, self.model.channels))
        self.model.apply_regions()

    def _apply_context(self, method, payload):
        if self.job.busy:
            self._deferred_context[method] = copy.deepcopy(payload)
            return
        getattr(self.model, method)(payload)
        self.channel_text = ",".join(map(str, self.model.channels))

    def apply_setup_settings(self, payload):
        self._apply_context("apply_setup_settings", payload)

    def apply_pipeline_context(self, payload):
        self._apply_context("apply_pipeline_context", payload)

    def apply_calibration(self, payload):
        self._apply_context("apply_calibration", payload)

    def animating(self):
        return self.job.busy or self.picker.is_open or super().animating()

    def render(self):
        self.job.poll()
        if not self.job.busy and self._deferred_context:
            pending = self._deferred_context
            self._deferred_context = {}
            for method, payload in pending.items():
                self._apply_context(method, payload)
        image = self.model.detection_image()
        if image is not self._image:
            self.canvas.reset()
            self._image = image
        vp = im.get_main_viewport()
        self.docks.draw((0, 0, *vp.size))
        if self.dialog:
            pressed = self.file_window.begin((0, 0, *vp.size))
            result = self.dialog.draw()
            if result:
                try:
                    path = Path(result[0])
                    if self.dialog_action == "add_files":
                        self.open_paths(result)
                    elif self.dialog_action == "export_results":
                        if path.suffix.lower() not in (".tsv", ".csv"):
                            path = path.with_suffix(".tsv")
                        self.start("export_results", str(path))
                    elif self.dialog_action == "save_settings":
                        path.with_suffix(".json").write_text(
                            json.dumps(self.state_dict(), indent=2)
                        )
                    elif self.dialog_action == "load_settings":
                        self.apply_state(json.loads(path.read_text()))
                    elif self.dialog_action == "save_regions":
                        self.regions.save(path)
                    elif self.dialog_action == "load_regions":
                        self.regions.load(path)
                    self.dialog = None
                except Exception as exc:
                    self.error = str(exc)
            elif result is False:
                self.dialog = None
            self.file_window.end()
            if pressed == "close":
                self.dialog = None
        self.picker.render((0, 0, *vp.size))
        if self.help_window.open:
            self.help_window.draw((0, 0, *vp.size))
        if self.tour.active:
            self.tour.draw(*vp.size)


def make_app(**kwargs):
    from chisurf.emtk.i18n import install

    install()
    return SpotFinderApp(model=kwargs.get("model"))
