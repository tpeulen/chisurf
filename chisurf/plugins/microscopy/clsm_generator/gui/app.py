"""Native CLSM map simulation; calculations use the unchanged Qt-free model."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from emtk import im
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog

from chisurf.emtk.dataset_picker import DatasetPicker
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.emtk.image_canvas import ImageCanvas
from chisurf.emtk.jobs import SnapshotJob
from chisurf.plugins.calculator.native_form import fields

from .view_model import ClsmGeneratorViewModel

FORMATS = (".pto", ".npz", ".ptu", ".spc", ".ht3")


class GenerationJob(SnapshotJob):
    """Cancellation discards a simulation result without touching its C++ worker."""

    canceled = False

    def start(self, method, *args):
        if self.busy:
            return False
        self.canceled = False
        self.method = method
        return super().start(method, *args)

    def cancel(self):
        if self.busy:
            self.canceled = True
            self.progress = "Canceled; waiting for simulator to finish safely."

    def poll(self):
        if not self.canceled:
            return super().poll()
        while not self.messages.empty():
            if self.messages.get()[0] == "done":
                self.busy = False
                self.progress = ""
                self.model.status_text = "Generation canceled; previous result retained."
                self.model.notify("done")
        return False


class ClsmGeneratorApp(ImApp):
    def __init__(self, model=None):
        self.model = model or ClsmGeneratorViewModel()
        self.job = GenerationJob(self.model)
        self.canvas = ImageCanvas("clsm_generator", image_label="Intensity")
        self.canvas.colormap = "inferno"
        self.selected_lifetime = 0
        self.output_format = ".pto"
        self.dialog = self.file_window = None
        self.dialog_action = ""
        self.error = ""
        self.item_rects = {}
        self._image = None
        self.picker = DatasetPicker(
            formats=["tif", "tiff", "npy", "npz"],
            kinds=["raw_data", "raw_measurement", "image_data", "external_reference"],
            on_paths=lambda paths: self.load_maps(paths, lifetime=True),
        )
        spec = json.loads(Path(__file__).with_name("generator.view.json").read_text())
        self.parameters = spec["sections"][0]["sections"][0]["sections"][3]["sections"]
        self.help_window = EmTkHelpWindow(
            title="CLSM Generator — Help", resource=Path(__file__).with_name("help.md"), owner=self
        )
        self.tour = EmTkGuidedTour(
            steps=Path(__file__).with_name("guide.json"),
            get_target_rect=lambda key: self.item_rects.get(key),
            owner=self,
            wait_for_controls=True,
        )
        self.docks = DockManager(Split("h", 0.35, Region("inputs"), Region("maps")))
        self.docks.add_window(
            "inputs", "Inputs and simulation", self.controls, dock="inputs", closable=False
        )
        self.docks.add_window("maps", "Maps", self.maps, dock="maps", closable=False)
        super().__init__(self.render, continuous=False)

    def button(self, label, tip, action):
        pressed = im.button(label)
        im.set_item_tooltip(tip)
        self.item_rects[label] = im.get_item_rect()
        if pressed:
            action()
            self.tour.notify_used(label)

    def choose(self, action):
        if self.job.busy:
            return
        self.dialog_action = action
        save = action in ("save", "save_settings")
        settings = action in ("save_settings", "load_settings")
        filters = (
            "JSON (*.json)"
            if settings
            else (
                "Photon stream (*.pto *.npz *.ptu *.spc *.ht3)"
                if save
                else "Maps (*.tif *.tiff *.npy *.npz);;All files (*)"
            )
        )
        filename = (
            "clsm_generator.json" if settings else "clsm_sim" + self.output_format if save else ""
        )
        self.dialog = FileDialog(
            action.replace("_", " ").title(),
            mode="save" if save else "open",
            filters=filters,
            filename=filename,
            multiselect=action == "lifetime",
        )
        self.file_window = DialogWindow(
            self.dialog.title, size=(700, 540), key=f"clsm_file_{id(self)}"
        )
        self.file_window.show()

    def load_maps(self, paths, *, lifetime=False):
        if self.job.busy:
            return False
        paths = [str(path) for path in paths]
        if not paths:
            return False
        self.error = ""
        if lifetime:
            self.model.sel_lifetime_files = self.model.lifetime_paths + paths
            failed = [path for path in paths if self.model._load(path) is None]
        else:
            self.model.sel_intensity = paths[0]
            failed = [] if self.model._intensity_in is not None else paths[:1]
        if failed:
            self.error = "Could not load map: " + ", ".join(failed)
        return not failed

    def on_files_dropped(self, paths):
        return self.load_maps(paths, lifetime=self.model._intensity_in is not None)

    def validate(self):
        ok, reason = self.model.can_generate()
        if not ok:
            return reason
        if len(self.model._lifetime_in) != len(self.model.lifetime_paths):
            return "Every detector must have a readable lifetime map."
        intensity = self.model._intensity_in
        if not intensity.size or not np.isfinite(intensity).all() or (intensity < 0).any():
            return "Intensity must contain finite, nonnegative pixels."
        for field in self.parameters:
            value = getattr(self.model, field["attr"])
            if not np.isfinite(value) or not field["minimum"] <= value <= field["maximum"]:
                return "Invalid simulation parameter: " + field["label"]
            if field["kind"] == "int" and int(value) != value:
                return "Simulation count must be an integer: " + field["label"]
        return ""

    def generate(self):
        self.error = self.validate()
        return not self.error and self.job.start("generate")

    def save(self, path):
        path = Path(path)
        if not path.suffix:
            path = path.with_suffix(self.output_format)
        self.error = ""
        if not self.model.has_result():
            self.error = "Generate a photon image before saving."
        elif path.suffix.lower() not in FORMATS:
            self.error = "Choose .pto, .npz, .ptu, .spc or .ht3 for the photon stream."
        elif not path.parent.is_dir():
            self.error = "Output directory does not exist."
        if self.error:
            return False
        return self.job.start("save", str(path))

    def controls(self, box):
        self.button(
            "Help",
            "Explain detector maps, simulation units, cancellation and export formats.",
            self.help_window.show,
        )
        im.same_line()
        self.button(
            "Guide",
            "Walk through loading maps, generating and saving a photon image.",
            self.tour.start,
        )
        im.begin_disabled(self.job.busy or self.dialog is not None or self.picker.is_open)
        self.button(
            "Intensity image",
            "Load the relative pixel brightness from TIFF, NPY or NPZ.",
            lambda: self.choose("intensity"),
        )
        im.text_wrapped(self.model.intensity_path or "No intensity image loaded.")
        im.set_item_tooltip(
            self.model.intensity_path or "Load the image that sets pixel brightness."
        )
        self.button(
            "Add lifetime maps",
            "Add one fluorescence lifetime map in ns per detector, in detector order.",
            lambda: self.choose("lifetime"),
        )
        self.button(
            "Database lifetime maps",
            "Select registered lifetime map datasets from MMFDB in detector order.",
            self.picker.open,
        )
        for index, path in enumerate(self.model.lifetime_paths):
            if im.selectable(
                f"Detector {index}: {Path(path).name}", self.selected_lifetime == index
            ):
                self.selected_lifetime = index
            im.set_item_tooltip(path + " — lifetime in ns; detector " + str(index))
        im.begin_disabled(not self.model.lifetime_paths)
        self.button(
            "Remove selected",
            "Remove the selected detector's lifetime map without deleting its file.",
            self.remove_lifetime,
        )
        im.same_line()
        self.button(
            "Clear maps",
            "Remove all detector lifetime maps without deleting files.",
            lambda: setattr(self.model, "sel_lifetime_files", []),
        )
        im.end_disabled()
        if im.collapsing_header("Simulation"):
            fields(
                self.model,
                self.parameters,
                item_rects=self.item_rects,
                on_used=self.tour.notify_used,
            )
        im.set_item_tooltip(
            "Expand the acquisition and lifetime/intensity quantization parameters."
        )
        self.button(
            "Generate",
            "Simulate the photon image on a background worker using the loaded maps.",
            self.generate,
        )
        im.same_line()
        im.begin_disabled(not self.model.has_result())
        self.button(
            "Save photon stream",
            "Save the generated photon stream and its reconstructed intensity TIFF.",
            lambda: self.choose("save"),
        )
        im.end_disabled()
        _, index = im.combo("Output format", FORMATS.index(self.output_format), list(FORMATS))
        self.output_format = FORMATS[index]
        im.set_item_tooltip(
            "PTO preserves the measurement and embedded intensity; NPZ exports photon arrays. Other formats use tttrlib writers."
        )
        self.button(
            "Save settings",
            "Save paths, acquisition settings, detector order and map display preferences as JSON.",
            lambda: self.choose("save_settings"),
        )
        im.same_line()
        self.button(
            "Load settings",
            "Restore saved map inputs, detector order, acquisition and display preferences.",
            lambda: self.choose("load_settings"),
        )
        im.end_disabled()
        if self.job.busy:
            im.text_wrapped(self.job.progress)
            if self.job.method == "generate" and not self.job.canceled:
                self.button(
                    "Cancel generation",
                    "Discard the running simulation's result; the C++ calculation finishes safely in the background.",
                    self.job.cancel,
                )
        else:
            im.text_wrapped(self.model.status_text)
        if self.error or self.job.error:
            im.text_wrapped(self.error or self.job.error)

    def remove_lifetime(self):
        paths = self.model.lifetime_paths.copy()
        if paths:
            paths.pop(min(self.selected_lifetime, len(paths) - 1))
            self.model.sel_lifetime_files = paths
            self.selected_lifetime = max(0, min(self.selected_lifetime, len(paths) - 1))

    def maps(self, box):
        entries = self.model.view_entries()
        if not entries:
            im.text_wrapped(
                "Load an intensity image and one lifetime map per detector, then Generate."
            )
            return
        index = next(
            (i for i, entry in enumerate(entries) if entry["id"] == self.model.current_view), 0
        )
        edited, index = im.combo("Map", index, [entry["label"] for entry in entries])
        im.set_item_tooltip(
            "Browse input brightness, each detector lifetime and reconstructed photon counts."
        )
        if edited:
            self.model.current_view = entries[index]["id"]
        image = self.model.current_view_image()
        if image is not self._image:
            self.canvas.reset()
            self._image = image
        is_lifetime = self.model.current_view.startswith("lifetime")
        self.canvas.image_label = "Lifetime" if is_lifetime else "Intensity"
        self.canvas.image_unit = (
            "ns" if is_lifetime else "photons" if self.model.current_view == "recon" else "relative"
        )
        self.canvas.draw(image, pick_enabled=False, analysis_editable=False)
        self.item_rects["Maps"] = self.canvas.rect

    def state_dict(self):
        return dict(
            intensity_path=self.model.intensity_path,
            lifetime_paths=list(self.model.lifetime_paths),
            parameters={
                field["attr"]: getattr(self.model, field["attr"]) for field in self.parameters
            },
            current_view=self.model.current_view,
            output_format=self.output_format,
            display={
                key: getattr(self.canvas, key)
                for key in ("colormap", "gamma", "auto_levels", "low", "high")
            },
        )

    def apply_state(self, state):
        if self.job.busy:
            return False
        for field in self.parameters:
            value = state.get("parameters", {}).get(
                field["attr"], getattr(self.model, field["attr"])
            )
            if not np.isfinite(value) or not field["minimum"] <= value <= field["maximum"]:
                raise ValueError("Invalid saved parameter: " + field["attr"])
            if field["kind"] == "int" and int(value) != value:
                raise ValueError("Non-integer saved parameter: " + field["attr"])
        self.model.sel_intensity = state.get("intensity_path", "")
        self.model.sel_lifetime_files = state.get("lifetime_paths", [])
        for field in self.parameters:
            if field["attr"] in state.get("parameters", {}):
                setattr(self.model, field["attr"], state["parameters"][field["attr"]])
        self.model.current_view = state.get("current_view", "intensity_in")
        self.output_format = (
            state.get("output_format", ".pto")
            if state.get("output_format", ".pto") in FORMATS
            else ".pto"
        )
        for key in ("colormap", "gamma", "auto_levels", "low", "high"):
            if key in state.get("display", {}):
                setattr(self.canvas, key, state["display"][key])
        self.canvas.gamma = max(0.01, float(self.canvas.gamma))
        if self.canvas.colormap not in ("magma", "inferno", "viridis", "gray"):
            self.canvas.colormap = "inferno"
        return True

    def animating(self):
        return self.job.busy or self.picker.is_open or super().animating()

    def render(self):
        self.job.poll()
        vp = im.get_main_viewport()
        self.docks.draw((0, 0, *vp.size))
        if self.dialog:
            close = self.file_window.begin((0, 0, *vp.size))
            result = self.dialog.draw()
            if result:
                try:
                    path = Path(result[0])
                    if self.dialog_action in ("intensity", "lifetime"):
                        self.load_maps(result, lifetime=self.dialog_action == "lifetime")
                    elif self.dialog_action == "save":
                        self.save(path)
                    elif self.dialog_action == "save_settings":
                        path.with_suffix(".json").write_text(
                            json.dumps(self.state_dict(), indent=2)
                        )
                    elif self.dialog_action == "load_settings":
                        self.apply_state(json.loads(path.read_text()))
                    self.dialog = None
                except Exception as exc:
                    self.error = str(exc)
            elif result is False:
                self.dialog = None
            self.file_window.end()
            if close == "close":
                self.dialog = None
        if self.help_window.open:
            self.help_window.draw((0, 0, *vp.size))
        self.picker.render((0, 0, *vp.size))
        if self.tour.active:
            self.tour.draw(*vp.size)


def make_app(**kwargs):
    from chisurf.emtk.i18n import install

    install()
    from .translations import install_translations

    install_translations()
    return ClsmGeneratorApp(model=kwargs.get("model"))
