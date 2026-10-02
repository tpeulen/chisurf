"""Native phasor imaging: calibrated maps, movies and editable lifetime cursors."""

from __future__ import annotations

import copy
import json
import time
from pathlib import Path

import numpy as np
from emtk import im, implot
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region, Split
from emtk.events import CONTROL_MODIFIER, META_MODIFIER
from emtk.file_dialog import FileDialog

from chisurf.core.roi import EllipseROI, PolygonROI, RectangleROI, RegionCollection
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.emtk.image_canvas import ImageCanvas
from chisurf.plugins.calculator.inputs import bounded_float, bounded_int
from chisurf.plugins.microscopy.img_pixel_intensity.gui.app import IntensityApp
from chisurf.plugins.microscopy.img_pixel_nb.gui.app import NBApp

from .native_model import NativePhasorModel

MAPS = {
    "intensity": ("Intensity", "intensity_map", "counts"),
    "selected": ("Selected pixels", "masked_intensity_map", "counts"),
    "g": ("Phasor g", "g_map", "dimensionless"),
    "s": ("Phasor s", "s_map", "dimensionless"),
    "plane": ("Phasor plot", "phasor_histogram_map", "pixels"),
    "g_movie": ("Phasor g movie", "g_frames", "dimensionless"),
    "s_movie": ("Phasor s movie", "s_frames", "dimensionless"),
    "frames": ("Photon frames", "frame_stack", "counts"),
    "plane_movie": ("Phasor plot movie", "phasor_histogram_frames", "pixels"),
}


class PhasorApp(IntensityApp):
    # Share established native region JSON/geometry controls and file dialogs.
    gate_controls = NBApp.gate_controls

    def start(self, method, *args):
        if not self.job.busy:
            self.model._cancel.clear()
            self.job_method = method
        return super().start(method, *args)

    def cancel(self):
        self.model._cancel.set()

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
            filename="phasor-cursors.json" if action == "gates_save" else "",
        )
        self.file_window = DialogWindow(title, size=(700, 540), key="phasor_file")
        self.file_window.show()

    def __init__(self, model=None, **kwargs):
        super().__init__(model=model or NativePhasorModel(), **kwargs)
        self.canvases = {
            key: ImageCanvas("phasor_" + key, image_label=title, image_unit=unit)
            for key, (title, _, unit) in MAPS.items()
        }
        self.docks = DockManager(Split("h", 0.29, Region("controls"), Region("maps")))
        self.docks.add_window(
            "controls", "Phasor analysis", self.controls, dock="controls", closable=False
        )
        for key, (title, _, _) in MAPS.items():
            self.docks.add_window(
                key, title, lambda box, k=key: self.image_view(k), dock="maps", closable=False
            )
        self.help = EmTkHelpWindow(
            title="Phasor-FLIM — Help", resource=Path(__file__).with_name("help.md"), owner=self
        )
        self.tour = EmTkGuidedTour(Path(__file__).with_name("guide.json"), owner=self)
        self.selected_gate = ""
        self.map_index = 0
        self.loop_movie = True
        self.job_method = ""
        self.irf_window = ""
        self.channels_text = "0"
        self.ranges_text = "[]"
        self.irf_text = ""
        self.scatter = False

    def controls(self, box):
        actions = [
            (
                "Help",
                "Explain phasor coordinates, reference calibration, lifetime cursors and output artifacts.",
                self.help.show,
            ),
            (
                "Guide",
                "Walk through source, calibration, map selection and persistence.",
                self.tour.start,
            ),
            (
                "Open TTTR",
                "Load a confocal photon file with scanner markers.",
                lambda: self.choose("open"),
            ),
            (
                "MMFDB dataset",
                "Resolve authenticated registered photon data to a local file.",
                self.picker.open,
            ),
            (
                "Run",
                "Compute every configured detector window in the background.",
                lambda: self.start("compute_job"),
            ),
            (
                "Import detector setup",
                "Read detector channels, microtime windows and per-detector IRF paths from JSON.",
                lambda: self.choose("setup"),
            ),
            (
                "Create imaging HDF5",
                "Merge per-detector g/s and photon columns into an imaging table.",
                lambda: self.choose("hdf5"),
            ),
            (
                "Save container",
                "Persist the phasor table and provenance in the source PTO container.",
                lambda: self.start("save_container"),
            ),
            ("ndX", "Explore the same live per-pixel phasor table in native ndX.", self.open_ndx),
            (
                "Next ▶",
                "Keep source/output and advance the native imaging pipeline.",
                self.next_step,
            ),
        ]
        for i, (label, tip, action) in enumerate(actions):
            if i % 2:
                im.same_line()
            im.begin_disabled(self.job.busy and label not in ("Help", "Guide"))
            if im.button(label):
                action()
                self.tour.notify_used(label)
            im.set_item_tooltip(tip)
            im.end_disabled()
        if self.job.busy:
            if im.button("Cancel"):
                self.cancel()
            im.set_item_tooltip(
                "Cancel at the next worker checkpoint and discard uncommitted results."
            )
        im.text_wrapped(self.model.filename or "Choose a photon image.")
        im.text_wrapped(self.job.progress if self.job.busy else self.model.results_text)
        if self.error or self.job.error:
            im.text_wrapped(self.error or self.job.error)
        changed, self.map_index = im.combo("View", self.map_index, [v[0] for v in MAPS.values()])
        im.set_item_tooltip(
            "Choose any static map, photon/phasor movie or cursor-gated view, including overflowing dock tabs."
        )
        if changed:
            self.docks.focus(list(MAPS)[self.map_index])
        im.begin_disabled(self.job.busy)
        _, self.model.n_ph_min = bounded_int(
            "Min photons", self.model.n_ph_min, minimum=1, maximum=10000
        )
        im.set_item_tooltip(
            "Minimum photons per pixel for a valid phasor; Run applies changed thresholds."
        )
        _, self.model.frequency = bounded_float(
            "Frequency (MHz, -1=auto)", self.model.frequency, minimum=-1, maximum=1000
        )
        im.set_item_tooltip(
            "Modulation frequency in MHz; -1 derives the reference frequency from the TTTR header. Run applies changes."
        )
        self.detector_controls()
        im.end_disabled()
        self.gate_controls()

    def detector_controls(self):
        if not im.collapsing_header("Detector calibration"):
            return
        windows = list(self.model._windows())
        if not windows:
            return
        _, index = im.combo(
            "Edit detector",
            windows.index(self.irf_window) if self.irf_window in windows else 0,
            windows,
        )
        im.set_item_tooltip(
            "Choose the detector whose channels, microtime windows and reference IRF are edited."
        )
        name = windows[index]
        detector = self.model._windows()[name]
        if self.irf_window != name:
            self.irf_window = name
            self.channels_text = ",".join(str(v) for v in detector.get("chs", [0]))
            self.ranges_text = json.dumps(detector.get("micro_time_ranges", []))
            self.irf_text = str((detector.get("irf") or [""])[0])
        _, self.channels_text = im.input_text("Channels", self.channels_text)
        im.set_item_tooltip("Comma-separated TTTR routing channels, for example 0,1.")
        _, self.ranges_text = im.input_text("Microtime windows", self.ranges_text)
        im.set_item_tooltip(
            "JSON microtime channel intervals, for example [[0,128],[256,512]]; [] selects all microtimes."
        )
        _, self.irf_text = im.input_text("Reference IRF", self.irf_text)
        im.set_item_tooltip(
            "Path to this detector's reference TTTR file; blank computes the raw uncalibrated phasor."
        )
        if im.button("Apply detector"):
            try:
                channels = [int(v.strip()) for v in self.channels_text.split(",") if v.strip()]
                ranges = json.loads(self.ranges_text)
                if (
                    not channels
                    or not isinstance(ranges, list)
                    or any(not isinstance(v, list) or len(v) != 2 or v[0] > v[1] for v in ranges)
                ):
                    raise ValueError("Specify channels and ascending microtime interval pairs.")
                self.model.detectors[name] = dict(
                    detector,
                    chs=channels,
                    micro_time_ranges=ranges,
                    irf=[self.irf_text] if self.irf_text else [],
                )
                self.error = ""
            except (ValueError, TypeError) as exc:
                self.error = str(exc)
        im.set_item_tooltip(
            "Apply detector selection/reference settings; press Run to recompute all windows."
        )

    def image_view(self, name):
        windows = list(self.model._by_window)
        if windows:
            changed, index = im.combo(
                "Detector window",
                windows.index(self.model.display_window)
                if self.model.display_window in windows
                else 0,
                windows,
            )
            im.set_item_tooltip(
                "Select the displayed detector/microtime window; every detector remains in saved outputs."
            )
            if changed:
                self.model.display_window = windows[index]
                self.model.refresh_display()
        array = getattr(self.model, MAPS[name][1])()
        canvas = self.canvases[name]
        if name.endswith("movie") or name == "frames":
            _, self.playing = im.checkbox("Play movie", self.playing)
            im.set_item_tooltip("Animate acquisition frames of the selected detector.")
            im.same_line()
            _, self.loop_movie = im.checkbox("Loop movie", self.loop_movie)
            im.set_item_tooltip("Restart at the first acquisition frame after the last.")
            if im.button("Stop movie"):
                self.playing = False
                canvas.z = 0
            im.set_item_tooltip("Stop playback and return to the first frame.")
            _, self.fps = bounded_float("Frames per second", self.fps, minimum=0.1, maximum=60)
            im.set_item_tooltip(
                "Playback rate; no temporal resampling of photon data is performed."
            )
            if array is not None:
                canvas.z = min(canvas.z, len(array) - 1)
                if self.playing and time.monotonic() - self._last_frame >= 1 / self.fps:
                    if canvas.z < len(array) - 1:
                        canvas.z += 1
                    elif self.loop_movie:
                        canvas.z = 0
                    else:
                        self.playing = False
                    self._last_frame = time.monotonic()
                _, canvas.z = bounded_int("Frame", canvas.z, minimum=0, maximum=len(array) - 1)
                im.set_item_tooltip("Acquisition frame index; these are temporal scanner frames.")
                array = array[canvas.z]
        if name.startswith("plane"):
            self.phasor_plot(canvas, array, frame=canvas.z if name == "plane_movie" else None)
        else:
            canvas.draw(array, pick_enabled=False)

    def phasor_plot(self, canvas, array, frame=None):
        _, self.scatter = im.checkbox("Show scatter", self.scatter)
        im.set_item_tooltip(
            "Display each finite valid pixel in the static phasor plane instead of log-density bins."
        )
        if array is None:
            im.text_wrapped(
                "Run first to inspect the phasor cloud and select lifetime populations."
            )
            return
        x0, x1, y0, y1 = self.model.cursor_extent()
        if implot.begin_plot("Phasor populations", (-1, -1)):
            implot.setup_axes("g", "s")
            implot.setup_axes_limits(x0, x1, y0, y1, implot.COND_ONCE)
            if self.scatter:
                g, s = self.model.g_map(), self.model.s_map()
                n = self.model._disp("n_photons")
                if frame is not None:
                    g, s = self.model.g_frames()[frame], self.model.s_frames()[frame]
                    valid = np.isfinite(g) & np.isfinite(s) & ~((g == 0) & (s == 0))
                else:
                    valid = np.isfinite(g) & np.isfinite(s) & (n > 0)
                implot.plot_scatter("Pixels", g[valid].ravel(), s[valid].ravel())
            else:
                implot.plot_image(
                    "log(1 + pixels)",
                    canvas.texture(array),
                    (x0, y0),
                    (x1, y1),
                    uv0=(0, 1),
                    uv1=(1, 0),
                )
            angle = np.linspace(0, np.pi, 201)
            implot.plot_line("Universal semicircle", 0.5 + 0.5 * np.cos(angle), 0.5 * np.sin(angle))
            for i, entry in enumerate(self.model.cursors):
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
                        self.model.notify_cursors()
                    if result.hovered:
                        im.set_tooltip(
                            "Drag cursor edges/corners to resize, or drag inside to move the selected population."
                        )
                elif isinstance(roi, EllipseROI):
                    center = implot.drag_point(i * 100, roi.cx, roi.cy)
                    if center.modified:
                        roi.cx, roi.cy = center.x, center.y
                        self.model.notify_cursors()
                    for j, (axis, radius, angle) in enumerate(
                        [("rx", roi.rx, roi.angle), ("ry", roi.ry, roi.angle + np.pi / 2)]
                    ):
                        handle = implot.drag_point(
                            i * 100 + j + 1,
                            roi.cx + radius * np.cos(angle),
                            roi.cy + radius * np.sin(angle),
                        )
                        if handle.modified:
                            setattr(
                                roi, axis, float(np.hypot(handle.x - roi.cx, handle.y - roi.cy))
                            )
                            if axis == "rx":
                                roi.angle = float(np.arctan2(handle.y - roi.cy, handle.x - roi.cx))
                            self.model.notify_cursors()
                        if center.hovered or handle.hovered:
                            im.set_tooltip(
                                "Drag center to move the ellipse; drag axis handles to resize and rotate it."
                            )
                elif isinstance(roi, PolygonROI):
                    for j, (x, y) in enumerate(roi.vertices):
                        handle = implot.drag_point(i * 100 + j, float(x), float(y))
                        if handle.modified:
                            roi.vertices[j] = [handle.x, handle.y]
                            self.model.notify_cursors()
                        if handle.hovered:
                            im.set_tooltip(
                                "Drag a polygon vertex in g/s coordinates to adjust the lifetime population."
                            )
            implot.end_plot()

    def render(self):
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
                        self.model.cursors = RegionCollection.load(str(path))
                        self.model.notify_cursors()
                    else:
                        self.model.cursors.save(str(path))
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
            self.coordinator.advance_from("pixel_phasor")

    def export_settings(self):
        data = super().export_settings()
        data.update(
            phasor={"n_ph_min": self.model.n_ph_min, "frequency": self.model.frequency},
            cursors=self.model.cursors.to_dict(),
            map_index=self.map_index,
            loop_movie=self.loop_movie,
            scatter=self.scatter,
            docks=self.docks.state(),
        )
        return data

    def restore_settings(self, data):
        if self.job.busy:
            return
        # Restore scientific settings before starting the background snapshot.
        self.model.n_ph_min = max(1, min(10000, int(data.get("phasor", {}).get("n_ph_min", 3))))
        self.model.frequency = max(
            -1, min(1000, float(data.get("phasor", {}).get("frequency", -1)))
        )
        self.model.cursors = RegionCollection.from_dict(
            data.get("cursors", self.model.cursors.to_dict())
        )
        self.map_index = max(0, min(len(MAPS) - 1, int(data.get("map_index", 0))))
        self.loop_movie = bool(data.get("loop_movie", True))
        self.scatter = bool(data.get("scatter", False))
        super().restore_settings(data)
        if data.get("docks"):
            self.docks.restore(data["docks"])

    def animating(self):
        return super().animating() or (self.playing and not self.view_ndx)

    def key(self, key, text="", modifiers=0):
        if (
            not self.view_ndx
            and key.lower() in ("enter", "return")
            and modifiers & (CONTROL_MODIFIER | META_MODIFIER)
        ):
            self.start("compute_job")
            return True
        if key.lower() == "escape" and self.job.busy:
            self.cancel()
            return True
        return super().key(key, text, modifiers)

    def close(self):
        self.cancel()
        super().close()


def make_app(**kwargs):
    from chisurf.emtk.i18n import install

    install()
    return PhasorApp(**kwargs)
