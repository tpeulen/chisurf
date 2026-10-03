"""Native CLSM map simulation; calculations use the unchanged Qt-free model."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path

import numpy as np
from emtk import im
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog
from emtk.view_form import FormState, draw_form

from chisurf.emtk.dataset_picker import DatasetPicker
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.emtk.image_canvas import ImageCanvas
from chisurf.emtk.jobs import SnapshotJob
from chisurf.plugins.emtk_layout import button_row, layout_spec

from .view_model import ClsmGeneratorViewModel

FORMATS = (".pto", ".npz", ".ptu", ".spc", ".ht3")


class _Rows(list):
    revision = 0


LIFETIME_SPEC = {"sections": [{"type": "custom", "key": "data_table",
    "description": "One lifetime map (in ns) per detector, in detector order. Select a row for Remove selected; Delete removes it.",
    "options": {"source": "lifetime_rows", "height": 96, "row_key": "detector", "selected_call": "select_lifetime",
                "delete_call": "delete_lifetime", "status": True, "columns": [
        {"key": "detector", "title": "Detector", "width": 70, "description": "The detector the map belongs to (0, 1, ...)."},
        {"key": "file", "title": "Lifetime map", "description": "File name of the lifetime map; the full path is in the tooltip."},
        {"key": "folder", "title": "Folder", "description": "The folder of the file."}]}}]}


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
        panel = json.loads(json.dumps(spec["sections"][0]["sections"][0]["sections"][3]))
        panel["collapsible"] = True
        for sec in panel["sections"]:
            if sec.get("type") == "value" and sec.get("kind") in ("int", "float"):
                sec["style"] = "spin"
                if sec.get("kind") == "float" and not sec.get("step"):
                    decimals = int(sec.get("decimals", 2))
                    sec["step"] = 10.0 ** -(decimals if decimals <= 2 else decimals - 1)
        self.simulation_spec = layout_spec({"sections": [panel]})
        self.forms = {k: FormState(on_used=lambda n: self.tour.notify_used(n)) for k in ("lifetimes", "simulation")}
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

    # table sources for the specs
    @property
    def lifetime_rows(self):
        rows = _Rows([{"detector": i, "file": Path(p).name, "folder": str(Path(p).parent)}
                      for i, p in enumerate(self.model.lifetime_paths)])
        rows.revision = hash(tuple(self.model.lifetime_paths))
        return rows

    def select_lifetime(self, record):
        if isinstance(record, dict):
            self.selected_lifetime = record["detector"]

    def delete_lifetime(self, record):
        if isinstance(record, dict) and not self.job.busy:
            self.selected_lifetime = record["detector"]
            self.remove_lifetime()

    def enabled(self, name):
        return not (self.job.busy or self.dialog is not None or self.picker.is_open)

    def controls(self, box):
        pressed = button_row([
            {"label": "Help", "key": "Help", "tip": "Explain detector maps, simulation units, cancellation and export formats."},
            {"label": "Guide", "key": "Guide", "tip": "Walk through loading maps, generating and saving a photon image."},
        ], remember=self.remember)
        if pressed == "Help":
            self.help_window.show()
        elif pressed == "Guide":
            self.tour.start()
        busy = self.job.busy or self.dialog is not None or self.picker.is_open
        im.begin_disabled(busy)
        pressed = button_row([
            {"label": "Intensity image", "key": "Intensity image", "tip": "Load the relative pixel brightness from TIFF, NPY or NPZ."},
            {"label": "Add lifetime maps", "key": "Add lifetime maps", "tip": "Add one fluorescence lifetime map in ns per detector, in detector order."},
            {"label": "Database lifetime maps", "key": "Database lifetime maps", "tip": "Select registered lifetime map datasets from MMFDB in detector order."},
            {"label": "Remove selected", "key": "Remove selected", "enabled": bool(self.model.lifetime_paths), "tip": "Remove the selected detector's lifetime map without deleting its file."},
            {"label": "Clear maps", "key": "Clear maps", "enabled": bool(self.model.lifetime_paths), "tip": "Remove all detector lifetime maps without deleting files."},
        ], remember=self.remember)
        if pressed == "Intensity image":
            self.choose("intensity")
        elif pressed == "Add lifetime maps":
            self.choose("lifetime")
        elif pressed == "Database lifetime maps":
            self.picker.open()
        elif pressed == "Remove selected":
            self.remove_lifetime()
        elif pressed == "Clear maps":
            self.model.sel_lifetime_files = []
        if pressed:
            self.tour.notify_used(pressed)
        im.text_wrapped(self.model.intensity_path or "No intensity image loaded.")
        im.set_item_tooltip(self.model.intensity_path or "Load the image that sets pixel brightness.")
        self.remember("intensity_path")
        self.forms["lifetimes"].rects.clear()
        draw_form(LIFETIME_SPEC, self, self.forms["lifetimes"])
        self.item_rects.update(self.forms["lifetimes"].rects)
        self.forms["simulation"].rects.clear()
        draw_form(self.simulation_spec, self.model, self.forms["simulation"])
        self.item_rects.update(self.forms["simulation"].rects)
        im.end_disabled()
        im.begin_disabled(busy)
        pressed = button_row([
            {"label": "Generate", "key": "Generate", "tip": "Simulate the photon image on a background worker using the loaded maps."},
            {"label": "Save photon stream", "key": "Save photon stream", "enabled": self.model.has_result(), "tip": "Save the generated photon stream and its reconstructed intensity TIFF."},
            {"label": "Save settings", "key": "Save settings", "tip": "Save paths, acquisition settings, detector order and map display preferences as JSON."},
            {"label": "Load settings", "key": "Load settings", "tip": "Restore saved map inputs, detector order, acquisition and display preferences."},
        ], remember=self.remember)
        if pressed == "Generate":
            self.generate()
        elif pressed == "Save photon stream":
            self.choose("save")
        elif pressed == "Save settings":
            self.choose("save_settings")
        elif pressed == "Load settings":
            self.choose("load_settings")
        if pressed:
            self.tour.notify_used(pressed)
        im.text("Output format")
        im.same_line(120)
        im.set_next_item_width(120)
        _, index = im.combo("##output_format", FORMATS.index(self.output_format), list(FORMATS))
        self.output_format = FORMATS[index]
        self.remember("output_format")
        im.set_item_tooltip("PTO preserves the measurement and embedded intensity; NPZ exports photon arrays. Other formats use tttrlib writers.")
        im.end_disabled()
        if self.job.busy:
            im.text_wrapped(self.job.progress)
            if self.job.method == "generate" and not self.job.canceled:
                if im.button("Cancel generation"):
                    self.job.cancel()
                im.set_item_tooltip("Discard the running simulation's result; the C++ calculation finishes safely in the background.")
                self.remember("Cancel generation")
        else:
            im.text_wrapped(self.model.status_text)
        self.remember("status")
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
        im.text("Map")
        im.same_line(80)
        im.set_next_item_width(-1)
        edited, index = im.combo("##map", index, [entry["label"] for entry in entries])
        self.remember("map")
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
        with _pointer_masked(self.tour.active):
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
