"""Native workflow-based spot detection with ROI editing and Gaussian picking."""

from __future__ import annotations

import copy
import dataclasses
import json
from pathlib import Path

from emtk import im
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog

from chisurf.core.datastore import rows_from_table
from chisurf.core.roi import RegionCollection
from chisurf.emtk.dataset_picker import DatasetPicker
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.plugins.calculator.inputs import bounded_int
from chisurf.plugins.calculator.native_form import fields, plain
from chisurf.plugins.microscopy.psf_determination.gui.canvas import ImageCanvas
from chisurf.plugins.microscopy.psf_determination.gui.jobs import SnapshotJob

from .regions import RegionControls
from .view_model import SpotFinderViewModel


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

    def controls(self, box):
        if im.button("Help"):
            self.help_window.show()
        im.set_item_tooltip(
            "Explain detection recipes, ROI restriction, picking and measurement-container outputs."
        )
        im.same_line()
        if im.button("Guide"):
            self.tour.start()
        im.set_item_tooltip(
            "Work through the known-field demo with actual actions and image picking."
        )
        im.begin_disabled(self.job.busy or self.dialog is not None or self.picker.is_open)
        for label, tip, action in [
            (
                "Add files",
                "Select photon or camera imaging files for preview and batch detection.",
                lambda: self.choose("add_files"),
            ),
            (
                "MMFDB datasets",
                "Select registered photon/camera datasets from the MMFDB catalog.",
                self.picker.open,
            ),
        ]:
            if im.button(label):
                action()
            im.set_item_tooltip(tip)
        for i, path in enumerate(list(self.model.files)):
            if im.selectable(Path(path).name, self.file_index == i):
                self.file_index = i
            im.set_item_tooltip(path)
        im.begin_disabled(not self.model.files)
        if im.button("Remove file"):
            self.model.files.pop(min(self.file_index, len(self.model.files) - 1))
            self.file_index = max(0, min(self.file_index, len(self.model.files) - 1))
        im.set_item_tooltip("Remove the selected input from this detection batch.")
        im.same_line()
        if im.button("Clear files"):
            self.model.files.clear()
        im.set_item_tooltip("Remove every input file from the batch without deleting the files.")
        im.end_disabled()
        actions = [
            (
                "Load demo",
                "Simulate/cache the known four-object photon field for validating a detection.",
                lambda: self.start("load_demo"),
            ),
            (
                "Preview",
                "Detect in the first input only and write nothing.",
                lambda: self.start("preview"),
            ),
            (
                "Detect",
                "Detect in every input; retain a run-table row even for empty or failed files.",
                lambda: self.start("run"),
            ),
            (
                "Add picks",
                "Add fitted picked ellipses to the current detection and remeasure the regions.",
                lambda: self.start("add_picked_to_detection"),
            ),
            (
                "Clear picks",
                "Forget every manually picked Gaussian proposal.",
                lambda: self.start("clear_picked"),
            ),
            (
                "Export",
                "Export all files’ measured region rows as CSV or TSV.",
                lambda: self.choose("export_results"),
            ),
            (
                "Save settings",
                "Save files, workflow deviations, routing, ROI composition and display state to JSON.",
                lambda: self.choose("save_settings"),
            ),
            (
                "Load settings",
                "Restore the complete analysis configuration from JSON.",
                lambda: self.choose("load_settings"),
            ),
        ]
        for label, tip, action in actions:
            if im.button(label):
                action()
                self.tour.notify_used(label)
            im.set_item_tooltip(tip)
            self.item_rects[label] = im.get_item_rect()
        fields(
            self.model, self.sections[:1], item_rects=self.item_rects, on_used=self.tour.notify_used
        )
        changed, self.channel_text = im.input_text(
            "Detector channels", self.channel_text, hint="All channels, or 0,1"
        )
        im.set_item_tooltip(
            "Photon-routing channels to sum; blank selects every available detector channel."
        )
        if changed:
            try:
                self.model.channels = list(
                    dict.fromkeys(int(v.strip()) for v in self.channel_text.split(",") if v.strip())
                )
            except ValueError:
                self.error = "Detector channels must be comma-separated integers."
        _, self.model.frame = bounded_int("Frame", self.model.frame, minimum=-1, maximum=1000000000)
        im.set_item_tooltip("Photon/image frame to analyze; -1 sums all available frames.")
        _, self.model.write_results = im.checkbox("Write results", self.model.write_results)
        im.set_item_tooltip(
            "Detect stores each label image and region table in its own measurement container; Preview always writes nothing."
        )
        self.regions.draw()
        im.end_disabled()
        im.text_wrapped(plain(self.model.summary()))
        im.text_wrapped(self.job.progress if self.job.busy else self.model.status_text)
        if self.error or self.job.error:
            im.text_wrapped(self.error or self.job.error)

    def image_view(self, box):
        _, self.region_filter = im.input_text(
            "Filter regions", self.region_filter, hint="Region name or file"
        )
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
            changed, index = im.combo("Selected region", current, labels)
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
        if im.begin_tab_bar("spot_tables"):
            for index, label in enumerate(["Run", "Region measurements"]):
                if im.begin_tab_item(label):
                    self.table_view = index
                    im.end_tab_item()
                im.set_item_tooltip(
                    "Review all input outcomes."
                    if index == 0
                    else "Measured centroid, area, intensity and second moments of each region."
                )
            im.end_tab_bar()
        if self.table_view == 0:
            self.table("run", self.model.run_entries(), self.sections[-1]["columns"])
        else:
            result = self.model._current_result()
            rows = rows_from_table(result.table) if result is not None else []
            columns = [
                dict(key=key, label=key, description="Measured " + key)
                for key in self.model.selection_columns()
            ]
            self.table("measurements", rows, columns)

    @staticmethod
    def table(key, rows, columns):
        if not columns:
            im.text_unformatted("No results yet.")
            return
        if im.begin_table(
            key,
            len(columns),
            im.TableFlags.BORDERS
            | im.TableFlags.ROW_BG
            | im.TableFlags.RESIZABLE
            | im.TableFlags.SCROLL_X
            | im.TableFlags.SCROLL_Y,
            (0, -1),
        ):
            for column in columns:
                im.table_setup_column(column["label"])
            im.table_headers_row()
            im.set_item_tooltip(
                "Measurement results; each row remains associated with its source file and region label."
            )
            for row in rows:
                im.table_next_row()
                for i, column in enumerate(columns):
                    im.table_set_column_index(i)
                    im.text_unformatted(str(row.get(column["key"], "")))
                    im.set_item_tooltip(column.get("description", ""))
            im.end_table()

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
