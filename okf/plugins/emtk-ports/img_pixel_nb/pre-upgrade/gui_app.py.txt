"""Pure EMTK Number & Brightness workstation, using the same estimator as Qt."""

from __future__ import annotations

import copy
import json
import time
from pathlib import Path

import numpy as np
from emtk import im, implot
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog

from chisurf.core.roi import EllipseROI, PolygonROI, RectangleROI, RegionCollection
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.emtk.image_canvas import ImageCanvas
from chisurf.plugins.calculator.inputs import bounded_float, bounded_int
from chisurf.plugins.microscopy.img_pixel_intensity.gui.app import IntensityApp

from .native_model import NativeNBModel
from .view_model import PLANE_AXES

_MAPS = {
    "intensity": ("Intensity", "intensity_map", "counts"),
    "B": ("Brightness B", "b_map", "counts"),
    "N": ("Number N", "n_map", "dimensionless"),
    "epsilon": ("Molecular brightness ε", "epsilon_map", "counts / molecule"),
    "n": ("Molecular number n", "number_map", "dimensionless"),
    "gated": ("Gated pixels", "gated_intensity_map", "counts"),
    "plane": ("Parameter plane", "plane_histogram", "pixels"),
    "cross_B": ("Cross brightness", "cross_brightness_map", "counts"),
    "cross_N": ("Cross number", "cross_number_map", "dimensionless"),
    "frames": ("Frames (movie)", "frame_stack", "counts"),
}


class NBApp(IntensityApp):
    def __init__(self, model=None, **kwargs):
        super().__init__(model=model or NativeNBModel(), **kwargs)
        self.canvases = {
            key: ImageCanvas("nb_" + key, image_label=title, image_unit=unit)
            for key, (title, method, unit) in _MAPS.items()
        }
        self.docks = DockManager(Split("h", 0.30, Region("controls"), Region("maps")))
        self.docks.add_window(
            "controls", "N&B analysis", self.controls, dock="controls", closable=False
        )
        for key, (title, method, unit) in _MAPS.items():
            self.docks.add_window(
                key, title, lambda box, k=key: self.image_view(k), dock="maps", closable=False
            )
        self.help = EmTkHelpWindow(
            title="Number & Brightness — Help",
            resource=Path(__file__).with_name("help.md"),
            owner=self,
        )
        self.tour = EmTkGuidedTour(Path(__file__).with_name("guide.json"), owner=self)
        spec = json.loads(Path(__file__).with_name("nb.view.json").read_text())
        self.sections = spec["sections"][0]["sections"][0]["sections"][2:]
        self.selected_gate = ""
        self.map_index = 0
        self.loop_movie = True
        self.job_method = ""

    def start(self, method, *args):
        if not self.job.busy:
            self.model._cancel.clear()
            self.job_method = method
        return super().start(method, *args)

    def cancel(self):
        self.model._cancel.set()

    def controls(self, box):
        for i, (label, tip, action) in enumerate(
            [
                (
                    "Help",
                    "Explain the N&B equations, detector corrections, gates and output artifacts.",
                    self.help.show,
                ),
                (
                    "Guide",
                    "Walk through the monomer/dimer demo and population selection.",
                    self.tour.start,
                ),
                (
                    "Open TTTR",
                    "Open confocal photon data containing line and frame markers.",
                    lambda: self.choose("open"),
                ),
                (
                    "MMFDB dataset",
                    "Resolve an authenticated registered photon image to a local file.",
                    self.picker.open,
                ),
                (
                    "Run",
                    "Compute N, B, ε and n for every detector window in the background.",
                    lambda: self.start("compute_job"),
                ),
                (
                    "Create imaging HDF5",
                    "Write all per-window pixel maps and units to an imaging HDF5 table.",
                    lambda: self.choose("hdf5"),
                ),
                (
                    "Save container",
                    "Save an N&B pixel artifact and provenance in the source PTO container.",
                    lambda: self.start("save_container"),
                ),
                ("ndX", "Explore the live N&B pixel table in native ndX.", self.open_ndx),
                (
                    "Next ▶",
                    "Keep source and output and advance the native imaging pipeline.",
                    self.next_step,
                ),
            ]
        ):
            if i % 3:
                im.same_line()
            im.begin_disabled(self.job.busy and label not in ("Help", "Guide"))
            if im.button(label):
                action()
                self.tour.notify_used(label)
            im.set_item_tooltip(tip)
            im.end_disabled()
        titles = [title for title, method, unit in _MAPS.values()]
        keys = list(_MAPS)
        changed, index = im.combo("Map", self.map_index, titles)
        im.set_item_tooltip(
            "Open any of the ten map, population, cross-window or movie views even when dock tabs overflow."
        )
        if changed:
            self.map_index = index
            self.docks.focus(keys[index])
            self.tour.notify_used(titles[index])
            if keys[index] == "epsilon":
                self.tour.notify_used("Brightness ε")
        im.text_wrapped(self.model.filename or "Choose a photon image.")
        im.text_wrapped(self.job.progress if self.job.busy else self.model.results_text)
        if self.job.error or self.error:
            im.text_wrapped(self.job.error or self.error)
        for window, detector in self.model._windows().items():
            im.text_wrapped(
                f"{window} · channels {detector.get('chs', [])} · microtimes {detector.get('micro_time_ranges', [])}"
            )
        if self.job.busy and self.job_method in ("compute_job", "compute_cross_job"):
            if im.button("Cancel"):
                self.cancel()
            im.set_item_tooltip(
                "Stop at the next detector-window checkpoint and discard the unfinished result."
            )
        im.begin_disabled(self.job.busy)
        for label, tip, action in [
            (
                "Load demo",
                "Generate a known monomer/dimer photon image and analyse it.",
                self.load_demo,
            ),
            (
                "Calibrate analog",
                "Fit variance against mean of a static gradient to infer analog detector gain and offset.",
                self.model.calibrate_analog,
            ),
            (
                "Import detector setup",
                "Import the step-0 detector channels and microtime windows from a JSON setup.",
                lambda: self.choose("setup"),
            ),
        ]:
            if im.button(label):
                action()
                self.tour.notify_used(label)
            im.set_item_tooltip(tip)
        for section in self.sections:
            if not im.collapsing_header(section["title"]):
                continue
            for field in section["sections"]:
                self.field(field)
        self.gate_controls()
        im.end_disabled()

    def field(self, field):
        kind = field.get("type")
        attr = field.get("attr")
        if not attr:
            return
        value = getattr(self.model, attr)
        label = field["label"]
        if kind == "choice":
            options = field.get("options") or getattr(self.model, field["options_source"])()
            changed, index = im.combo(
                label, options.index(value) if value in options else 0, options
            )
            value = options[index]
        elif kind == "toggle":
            changed, value = im.checkbox(label, bool(value))
        else:
            function = bounded_int if field.get("kind") == "int" else bounded_float
            changed, value = function(
                label, value, minimum=field.get("minimum", -1e9), maximum=field.get("maximum", 1e9)
            )
        im.set_item_tooltip(field["description"])
        if changed:
            setattr(self.model, attr, value)
            self.model.refresh_display()
            if attr == "cross_window" and self.model._by_window:
                self.start("compute_cross_job")

    def load_demo(self):
        try:
            self.model.load_demo()
            self.start("compute_job")
        except Exception as exc:
            self.error = str(exc)

    def gate_controls(self):
        if not im.collapsing_header("Gate regions"):
            return
        x0, x1, y0, y1 = self.model.plane_extent()
        for kind in ("Rectangle", "Ellipse", "Polygon"):
            if im.button("Add " + kind):
                if kind == "Rectangle":
                    roi = RectangleROI(x0, y0, (x0 + x1) / 2, (y0 + y1) / 2, name=kind)
                elif kind == "Ellipse":
                    roi = EllipseROI(
                        (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 4, (y1 - y0) / 4, name=kind
                    )
                else:
                    roi = PolygonROI(np.array([[x0, y0], [x1, y0], [(x0 + x1) / 2, y1]]), name=kind)
                self.selected_gate = self.model.gates.add(roi)
                self.model.notify_gates()
            im.set_item_tooltip(
                "Add an editable "
                + kind.lower()
                + " in parameter coordinates, selecting pixels in the population."
            )
        choices = ["or", "and", "xor"]
        for label, action in [("Load gates", "gates_load"), ("Save gates", "gates_save")]:
            if im.button(label):
                self.choose(action)
            im.set_item_tooltip(
                "Import or export all named gate shapes, enabled/inverted flags and combination rule as JSON."
            )
        _, index = im.combo("Combine gates", choices.index(self.model.gates.combine), choices)
        self.model.gates.combine = choices[index]
        im.set_item_tooltip(
            "Union, intersect or exclusively combine enabled gates, preserving inverted regions."
        )
        for entry in list(self.model.gates):
            im.push_id(entry.name)
            _, entry.enabled = im.checkbox(entry.name, entry.enabled)
            im.set_item_tooltip("Include this population gate in the image selection.")
            _, entry.invert = im.checkbox("Invert", entry.invert)
            im.set_item_tooltip("Select pixels outside this population gate.")
            roi = entry.roi
            changed, name = im.input_text("Gate name", entry.name)
            im.set_item_tooltip("Rename this gate; its geometry and inclusion state are preserved.")
            if changed and name.strip():
                self.model.gates.rename(entry.name, name)
            if im.button("Duplicate"):
                self.model.gates.add(copy.deepcopy(entry), name=entry.name + " copy")
                self.model.notify_gates()
            im.set_item_tooltip(
                "Copy this gate's geometry and inclusion flags to a new uniquely named region."
            )
            keys = (
                ("x0", "y0", "x1", "y1")
                if isinstance(roi, RectangleROI)
                else ("cx", "cy", "rx", "ry", "angle")
                if isinstance(roi, EllipseROI)
                else ()
            )
            for key in keys:
                changed, value = bounded_float(key, getattr(roi, key))
                im.set_item_tooltip("Gate geometry in the selected parameter-plane axis units.")
                if changed:
                    setattr(roi, key, value)
                    self.model.notify_gates()
            if isinstance(roi, PolygonROI):
                for i, vertex in enumerate(roi.vertices):
                    for j, axis in enumerate(("x", "y")):
                        changed, value = bounded_float(f"{axis}{i}", float(vertex[j]))
                        im.set_item_tooltip(
                            "Edit this polygon vertex in parameter-plane coordinates."
                        )
                        if changed:
                            roi.vertices[i, j] = value
                            self.model.notify_gates()
            if im.button("Remove"):
                self.model.gates.remove(entry.name)
                self.model.notify_gates()
            im.set_item_tooltip("Remove this gate; remaining gates continue selecting pixels.")
            im.pop_id()
        if im.button("Clear gates"):
            self.model.clear_gates()
        im.set_item_tooltip("Remove every gate and show all valid pixels again.")
        im.text_wrapped(self.model.gate_summary())

    def image_view(self, name):
        if name == "frames":
            _, self.loop_movie = im.checkbox("Loop movie", self.loop_movie)
            im.set_item_tooltip(
                "Restart at the first scanner frame after the last frame; turn off to play once."
            )
            if im.button("Stop movie"):
                self.playing = False
                self.canvases["frames"].z = 0
            im.set_item_tooltip("Stop playback and return to the first scanner frame.")
            frames = self.model._disp("frames")
            if (
                not self.loop_movie
                and frames is not None
                and self.canvases["frames"].z >= len(frames) - 1
                and time.monotonic() - self._last_frame >= 1 / self.fps
            ):
                self.playing = False
            return super().image_view(name)
        windows = self.model.window_names()
        changed, index = im.combo(
            "Detector window",
            windows.index(self.model.display_window) if self.model.display_window in windows else 0,
            windows,
        )
        im.set_item_tooltip(
            "Display one detector/microtime window; every window is retained for output and cross N&B."
        )
        self.model.display_window = windows[index]
        if changed and self.model._by_window:
            self.start("compute_cross_job")
        canvas = self.canvases[name]
        if name in ("cross_B", "cross_N") and self.job.busy:
            im.text_wrapped(self.job.progress)
            return
        array = getattr(self.model, _MAPS[name][1])()
        if name != "plane":
            canvas.draw(array, pick_enabled=False)
            return
        if array is None:
            im.text_wrapped("Run first to inspect the parameter plane and select a population.")
            return
        x0, x1, y0, y1 = self.model.plane_extent()
        if implot.begin_plot("Population gates", (-1, -1)):
            implot.setup_axes(PLANE_AXES[self.model.plane_x], PLANE_AXES[self.model.plane_y])
            implot.setup_axes_limits(x0, x1, y0, y1, implot.COND_ONCE)
            implot.plot_image("Pixel count", canvas.texture(array), (x0, y0), (x1, y1))
            for i, entry in enumerate(self.model.gates):
                if not entry.enabled:
                    continue
                roi = entry.roi
                points = canvas.outline(roi)
                if points is not None:
                    implot.plot_line(entry.name, points[:, 0], points[:, 1])
                if isinstance(roi, RectangleROI):
                    result = implot.drag_rect(i * 100, roi.x0, roi.y0, roi.x1, roi.y1)
                    if result.modified:
                        roi.x0, roi.y0, roi.x1, roi.y1 = (
                            result.x_min,
                            result.y_min,
                            result.x_max,
                            result.y_max,
                        )
                        self.model.notify_gates()
                    if result.hovered:
                        im.set_tooltip(
                            "Drag this population gate to move it; drag its corners or edges to resize it."
                        )
                elif isinstance(roi, EllipseROI):
                    center = implot.drag_point(i * 100, roi.cx, roi.cy)
                    if center.modified:
                        roi.cx, roi.cy = center.x, center.y
                        self.model.notify_gates()
                    for axis, radius, angle in [
                        ("rx", roi.rx, roi.angle),
                        ("ry", roi.ry, roi.angle + np.pi / 2),
                    ]:
                        handle = implot.drag_point(
                            i * 100 + (1 if axis == "rx" else 2),
                            roi.cx + radius * np.cos(angle),
                            roi.cy + radius * np.sin(angle),
                        )
                        if handle.modified:
                            setattr(
                                roi, axis, float(np.hypot(handle.x - roi.cx, handle.y - roi.cy))
                            )
                            if axis == "rx":
                                roi.angle = float(np.arctan2(handle.y - roi.cy, handle.x - roi.cx))
                            self.model.notify_gates()
                        if handle.hovered or center.hovered:
                            im.set_tooltip(
                                "Drag the ellipse center to move it; its axis handles resize and rotate the gate."
                            )
                elif isinstance(roi, PolygonROI):
                    for vertex, (x, y) in enumerate(roi.vertices):
                        handle = implot.drag_point(i * 100 + vertex, float(x), float(y))
                        if handle.modified:
                            roi.vertices[vertex] = [handle.x, handle.y]
                            self.model.notify_gates()
                        if handle.hovered:
                            im.set_tooltip(
                                "Drag this polygon vertex in parameter coordinates to change the selected population."
                            )
            implot.end_plot()

    def choose(self, action):
        if action not in ("setup", "gates_load", "gates_save"):
            return super().choose(action)
        self.action = action
        title = (
            "Import detector setup"
            if action == "setup"
            else "Load gates"
            if action == "gates_load"
            else "Save gates"
        )
        self.dialog = FileDialog(
            title,
            mode="save" if action == "gates_save" else "open",
            filters="JSON (*.json)",
            filename="gates.json" if action == "gates_save" else "",
        )
        self.file_window = DialogWindow(title, size=(700, 540), key="nb_file")
        self.file_window.show()

    def render(self):
        # Process setup-file result before the generic imaging output handler.
        if self.dialog and self.action in ("setup", "gates_load", "gates_save"):
            vp = im.get_main_viewport()
            pressed = self.file_window.begin((0, 0, *vp.size))
            result = self.dialog.draw()
            if result:
                try:
                    path = Path(result[0])
                    if self.action == "setup":
                        self.apply_setup_settings(json.loads(path.read_text()))
                    elif self.action == "gates_load":
                        self.model.gates = RegionCollection.load(str(path))
                        self.model.notify_gates()
                    else:
                        self.model.gates.save(str(path))
                except Exception as exc:
                    self.error = str(exc)
                self.dialog = None
            elif result is False or pressed == "close":
                self.dialog = None
            self.file_window.end()
            dialog, self.dialog = self.dialog, None
            super().render()
            self.dialog = dialog
        else:
            super().render()

    def next_step(self):
        if self.coordinator is None:
            self.error = "Open inside the native Imaging Tools pipeline to use Next."
        else:
            self.coordinator.set_pipeline(
                source=self.model.filename or None, hdf5=self.model.pipeline_hdf5 or None
            )
            self.coordinator.advance_from("pixel_nb")

    def export_settings(self):
        data = super().export_settings()
        data["nb"] = {
            field["attr"]: copy.deepcopy(getattr(self.model, field["attr"]))
            for section in self.sections
            for field in section["sections"]
            if field.get("attr")
        }
        data["gates"] = self.model.gates.to_dict()
        data["map_index"] = self.map_index
        data["loop_movie"] = self.loop_movie
        data["docks"] = self.docks.state()
        return data

    def restore_settings(self, data):
        if self.job.busy:
            return
        super().restore_settings(data)
        for key, value in data.get("nb", {}).items():
            if key in {
                field.get("attr") for section in self.sections for field in section["sections"]
            }:
                setattr(self.model, key, copy.deepcopy(value))
        self.model.gates = RegionCollection.from_dict(data.get("gates", self.model.gates.to_dict()))
        self.map_index = max(0, min(len(_MAPS) - 1, int(data.get("map_index", 0))))
        self.loop_movie = bool(data.get("loop_movie", True))
        if data.get("docks"):
            self.docks.restore(data["docks"])
        else:
            self.docks.focus(list(_MAPS)[self.map_index])


def make_app(**kwargs):
    from chisurf.emtk.i18n import install

    install()
    return NBApp(**kwargs)
