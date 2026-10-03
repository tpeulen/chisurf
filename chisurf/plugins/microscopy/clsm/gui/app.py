"""Native CLSM reconstruction, brush/ROI selection, fluorescence decays and exports."""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from emtk import im, implot
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog

from chisurf.emtk.dataset_picker import DatasetPicker
from chisurf.emtk.help_guide import EmTkHelpWindow
from chisurf.emtk.image_canvas import ImageCanvas
from chisurf.emtk.jobs import SnapshotJob
from chisurf.emtk.regions import RegionControls
from chisurf.plugins.calculator.native_form import fields

from ..core import imaging
from .view_model import ClsmViewModel


class ClsmApp(ImApp):
    def __init__(self, model=None):
        self.model = model or ClsmViewModel()
        self.job = SnapshotJob(self.model)
        self.canvas = ImageCanvas("clsm_pixels")
        self.regions = RegionControls(
            self.model,
            self.choose,
            on_change=self.apply_regions,
            get_image=lambda: self.model.current_image,
        )
        self.picker = DatasetPicker(on_paths=self.open_paths)
        self.dialog = None
        self.file_window = None
        self.action = ""
        self.error = ""
        self._pending_setup = None
        self._pending_pipeline = None
        self.status = "Load TTTR data, build a CLSM image and add a representation."
        self.paint = True
        self.selection_version = 0
        self._future = None
        self._future_version = 0
        self._decay_deadline = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="clsm-decay")
        self._frame_signature = (self.model.decay.frame_mode, self.model.decay.frame_idx)
        self._curve_name = ""
        self._roi_name = "Selection"
        self.sections = json.loads(Path(__file__).with_name("clsm.view.json").read_text())[
            "sections"
        ][0]["sections"]
        self.help = EmTkHelpWindow(
            title="CLSM Pixel Select — Help",
            resource=Path(__file__).with_name("help.md"),
            owner=self,
        )
        self.docks = DockManager(
            Split("h", 0.33, Region("controls"), Split("v", 0.65, Region("image"), Region("decay")))
        )
        self.docks.add_window(
            "controls",
            "Acquisition, images and selections",
            self.controls,
            dock="controls",
            closable=False,
        )
        self.docks.add_window("image", "CLSM image", self.image, dock="image", closable=False)
        self.docks.add_window(
            "decay", "Fluorescence decays", self.decay_plot, dock="decay", closable=False
        )
        super().__init__(self.render, continuous=False)

    def open_paths(self, paths):
        if paths:
            self.start("load_file", str(paths[0]))

    def on_files_dropped(self, paths):
        if self.job.busy:
            return False
        self.open_paths(paths)
        return bool(paths)

    def start(self, method, *args):
        if self.job.busy:
            return False
        self.selection_version += 1
        self._decay_deadline = None
        self.error = ""
        return self.job.start(method, *args)

    def selection_changed(self):
        self.selection_version += 1
        if self.model.live_update:
            self._decay_deadline = time.monotonic() + 0.12

    def brush(self, point):
        if self.job.busy or self.model.selection_mask is None:
            return
        _, y, x = point
        kernel = self.model.brush_kernel()
        h, w = kernel.shape
        ny, nx = self.model.selection_mask.shape
        x0, y0 = x - w // 2, y - h // 2
        xa, ya = max(0, x0), max(0, y0)
        xb, yb = min(nx, x0 + w), min(ny, y0 + h)
        if xb <= xa or yb <= ya:
            return
        patch = kernel[ya - y0 : yb - y0, xa - x0 : xb - x0]
        before = self.model.selection_mask[ya:yb, xa:xb] > 0
        self.model.selection_mask[ya:yb, xa:xb] = np.clip(
            self.model.selection_mask[ya:yb, xa:xb] + patch, 0, 30000
        )
        if not np.array_equal(before, self.model.selection_mask[ya:yb, xa:xb] > 0):
            self.selection_changed()
            im.request_frame()

    def apply_regions(self):
        roi = self.model.regions.combined()
        if roi is not None and self.model.current_image is not None:
            self.model.selection_mask = roi.to_mask(
                self.model.current_image.shape, image=self.model.current_image
            ).astype(float)
            self.selection_changed()

    def request_decay(self):
        self._decay_deadline = time.monotonic()

    def _start_decay(self):
        m = self.model
        clsm = m.clsm_images.get(m.current_clsm_name)
        if clsm is None or m.selection_mask is None:
            return
        if not np.any(m.selection_mask > 0):
            m.current_decay = None
            return
        self._future_version = self.selection_version
        self._future = self._executor.submit(
            imaging.decay_of_selection,
            clsm,
            m.tttr_data,
            m.selection_mask.copy(),
            int(m.decay.tac_coarsening),
            m.decay.frame_mode in ("sum", "mean"),
            int(m.decay.frame_idx),
        )

    def publish_dataset(self):
        if not self.model.current_decay:
            self.error = "Compute a selection decay first."
            return False
        from chisurf.core.data import DataCurve
        from chisurf.emtk.datasets import register_dataset

        decay = self.model.current_decay
        name = self.model.add_decay_curve(self._curve_name or None)
        curve = DataCurve(
            x=np.asarray(decay["time_ns"]),
            y=np.asarray(decay["counts"]),
            ey=np.asarray(decay["noise"]),
            name=name,
            load_filename_on_init=False,
        )
        register_dataset(curve)
        self.status = "Added decay to ChiSurf experiment data."
        return True

    def choose(self, action):
        self.action = action
        load = action in ("load_file", "load_regions", "load_settings")
        filt = (
            "TTTR / Imaging (*.ptu *.pto *.ht3 *.spc *.pt3 *.h5 *.hdf5);;All files (*)"
            if action == "load_file"
            else "Regions (*.json *.tif *.tiff *.npy)"
            if "regions" in action
            else "TIFF (*.tif *.tiff)"
            if action == "image"
            else "CSV (*.csv)"
            if action == "decay"
            else "JSON (*.json)"
        )
        self.dialog = FileDialog(
            action.replace("_", " ").title(),
            mode="open" if load else "save",
            filters=filt,
            filename=""
            if load
            else {
                "image": "clsm.tif",
                "decay": "decay.csv",
                "save_regions": "regions.json",
                "save_settings": "clsm.json",
            }.get(action, ""),
        )
        self.file_window = DialogWindow(self.dialog.title, size=(700, 540), key="clsm_file")
        self.file_window.show()

    def controls(self, box):
        if im.button("Help"):
            self.help.show()
        im.set_item_tooltip(
            "Explain marker reconstruction, intensity/lifetime representations and brush-selected decays."
        )
        im.begin_disabled(self.job.busy or self.dialog is not None or self.picker.is_open)
        for label, tip, action in [
            (
                "Open TTTR / imaging",
                "Load photon data or follow an imaging HDF5 source reference.",
                lambda: self.choose("load_file"),
            ),
            (
                "MMFDB dataset",
                "Resolve registered photon data to a local input file.",
                self.picker.open,
            ),
            (
                "Build CLSM",
                "Reconstruct and fill a scanner image using the acquisition settings.",
                lambda: self.start("add_clsm"),
            ),
            (
                "Add representation",
                "Compute the selected intensity or micro-time representation.",
                lambda: self.start("add_representation"),
            ),
            (
                "Compute decay",
                "Compute the photon histogram of selected pixels.",
                self.request_decay,
            ),
            (
                "Add decay → ChiSurf",
                "Publish the current decay as a real ChiSurf experimental dataset.",
                self.publish_dataset,
            ),
            (
                "Export image",
                "Save the current physical image as a TIFF.",
                lambda: self.choose("image"),
            ),
            (
                "Export decay CSV",
                "Export time, counts and Poisson noise of the current decay.",
                lambda: self.choose("decay"),
            ),
        ]:
            if im.button(label):
                action()
            im.set_item_tooltip(tip)
        names = self.model.setup_names
        index = (
            names.index(self.model.setup.setup_name) if self.model.setup.setup_name in names else 0
        )
        im.text_unformatted("Setup preset")
        changed, index = im.combo("##Setup preset", index, names)
        im.set_item_tooltip(
            "Restore scanner markers, file type and reading routine from a named acquisition preset."
        )
        if changed:
            self.model.apply_preset(names[index])
        fields(
            self.model,
            [
                {
                    "type": "value",
                    "target": "setup",
                    "attr": "channels_text",
                    "kind": "str",
                    "label": "Detector channels",
                    "description": "Comma-separated photon routing channels.",
                }
            ],
        )
        for attr, source, remove in [
            ("current_clsm_name", self.model.clsm_image_names, "remove_clsm"),
            (
                "current_representation_name",
                self.model.representation_names,
                "remove_representation",
            ),
        ]:
            names = source()
            if names:
                current = getattr(self.model, attr)
                changed, index = im.combo(
                    "CLSM image" if attr == "current_clsm_name" else "Representation",
                    names.index(current) if current in names else 0,
                    names,
                )
                im.set_item_tooltip(
                    "Choose among independently reconstructed channel images or stored representations."
                )
                if changed:
                    if attr == "current_representation_name":
                        self.model.select_representation(names[index])
                        self.selection_changed()
                    else:
                        self.model.current_clsm_name = names[index]
                if im.button(
                    "Remove " + ("CLSM" if attr == "current_clsm_name" else "representation")
                ):
                    getattr(self.model, remove)(getattr(self.model, attr))
                    self.selection_changed()
                im.set_item_tooltip(
                    "Remove this stored image/representation; retained sources stay available."
                )
        fields(self.model, self.sections[1:3], changed=self.settings_changed)
        fields(
            self.model,
            [
                {
                    "type": "toggle",
                    "target": "setup",
                    "attr": "use_pixel_markers",
                    "label": "Use pixel markers",
                    "description": "Use explicit per-pixel marker records instead of time-derived raster positions.",
                },
                {
                    "type": "value",
                    "target": "setup",
                    "attr": "marker_pixel",
                    "kind": "int",
                    "label": "Pixel marker",
                    "minimum": 0,
                    "maximum": 255,
                    "description": "Routing marker code for the beginning of a pixel.",
                },
                {
                    "type": "value",
                    "target": "setup",
                    "attr": "n_lines",
                    "kind": "int",
                    "label": "Lines/frame",
                    "minimum": 0,
                    "maximum": 65536,
                    "description": "Explicit scanner line count; zero uses pixels/line.",
                },
            ],
        )
        _, self.paint = im.checkbox("Paint selection", self.paint)
        im.set_item_tooltip(
            "Reserve left-mouse dragging for selecting/erasing pixels; use the middle button to pan."
        )
        if im.button("Clear selection"):
            self.model.clear_selection()
            self.selection_changed()
        im.set_item_tooltip("Clear painted pixels and the active decay.")
        _, self._roi_name = im.input_text("Region name", self._roi_name)
        im.set_item_tooltip("Name for the saved painted mask.")
        if im.button("Save painted region"):
            self.model.add_roi(self._roi_name)
        im.set_item_tooltip("Capture painted pixels as a reusable named mask region.")
        self.regions.draw()
        for label, action in [
            ("Save settings", "save_settings"),
            ("Load settings", "load_settings"),
        ]:
            if im.button(label):
                self.choose(action)
            im.set_item_tooltip(
                "Persist/restore acquisition, brush and representation settings plus region geometry."
            )
        im.end_disabled()
        im.text_wrapped(self.model.filename)
        im.text_wrapped(self.job.progress if self.job.busy else self.status)
        if self.error or self.job.error:
            im.text_wrapped(self.error or self.job.error)

    def settings_changed(self):
        signature = (self.model.decay.frame_mode, int(self.model.decay.frame_idx))
        if signature != self._frame_signature:
            self._frame_signature = signature
            image = self.model.representations.get(self.model.current_representation_name)
            if image is not None:
                self.model.decay.frame_idx = min(
                    int(self.model.decay.frame_idx), max(0, len(image) - 1)
                )
                self.model.refresh_current_image()
        self.selection_changed()

    def image(self, box):
        self.canvas.colormap = self.model.colormap
        self.canvas.draw(
            self.model.current_image,
            selection=self.model.selection_mask,
            selection_version=self.selection_version,
            analysis=self.model.regions,
            on_change=self.apply_regions,
            pick_enabled=not self.job.busy and self.dialog is None and not self.picker.is_open,
            analysis_editable=not self.job.busy,
            on_brush=self.brush if self.paint else None,
        )
        self.model.colormap = self.canvas.colormap
        summary = self.model.region_summary()
        if summary:
            im.text_unformatted(summary)

    def decay_plot(self, box):
        if implot.begin_plot("Selected pixel decays", (-1, -1)):
            implot.setup_axes("Time [ns]", "Photon counts")
            implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
            implot.setup_legend()
            for series in self.model.decay_series():
                implot.plot_line(series["name"], series["x"], series["y"])
            implot.end_plot()
            im.set_item_tooltip(
                "Photon histograms from saved regions and the current selected pixels; time is calibrated from the TTTR header."
            )

    def apply_setup_settings(self, payload):
        if self.job.busy:
            self._pending_setup = dict(payload)
            return
        channels = []
        for detector in (payload.get("detectors") or {}).values():
            if isinstance(detector, dict):
                channels.extend(detector.get("chs") or [])
        if channels:
            self.model.setup.channels_text = ",".join(map(str, dict.fromkeys(channels)))

    def apply_pipeline_context(self, payload):
        if self.job.busy:
            self._pending_pipeline = dict(payload)
            return
        files = payload.get("files") or ([payload["file"]] if payload.get("file") else [])
        if files:
            self.open_paths(files)

    def state_dict(self):
        return dict(
            setup=vars(self.model.setup),
            brush=vars(self.model.brush),
            decay=vars(self.model.decay),
            regions=self.model.regions.to_dict(),
            colormap=self.model.colormap,
        )

    def apply_state(self, data):
        from chisurf.core.roi import RegionCollection

        for name in ("setup", "brush", "decay"):
            group = getattr(self.model, name)
            for key, value in data.get(name, {}).items():
                if key in vars(group):
                    setattr(group, key, value)
        if "regions" in data:
            self.model.regions = RegionCollection.from_dict(data["regions"])
        self.model.colormap = data.get("colormap", self.model.colormap)
        self.settings_changed()

    def animating(self):
        return (
            self.job.busy
            or self._future is not None
            or self._decay_deadline is not None
            or self.picker.is_open
            or super().animating()
        )

    def close(self):
        self._executor.shutdown(wait=False, cancel_futures=True)

    def render(self):
        if self.job.poll():
            self.selection_version += 1
            self.canvas.reset()
        if self._future is not None and self._future.done():
            try:
                t, y, noise = self._future.result()
                if self._future_version == self.selection_version:
                    self.model.current_decay = dict(time_ns=t, counts=y, noise=noise)
                    self.model.notify("decay")
            except Exception as exc:
                self.error = str(exc)
            self._future = None
        if (
            self._decay_deadline is not None
            and self._future is None
            and not self.job.busy
            and time.monotonic() >= self._decay_deadline
        ):
            self._decay_deadline = None
            self._start_decay()
        vp = im.get_main_viewport()
        self.docks.draw((0, 0, *vp.size))
        if self.dialog:
            pressed = self.file_window.begin((0, 0, *vp.size))
            result = self.dialog.draw()
            if result:
                try:
                    path = Path(result[0])
                    if self.action == "load_file":
                        self.start("load_file", str(path))
                    elif self.action == "image":
                        from chisurf.core.fio.image import imwrite

                        if self.model.current_image is None:
                            raise ValueError("Create an image representation first.")
                        imwrite(path.with_suffix(".tif"), self.model.current_image, axes="YX")
                    elif self.action == "decay":
                        if self.model.current_decay is None:
                            raise ValueError("Compute a selection decay first.")
                        d = self.model.current_decay
                        np.savetxt(
                            path.with_suffix(".csv"),
                            np.column_stack([d["time_ns"], d["counts"], d["noise"]]),
                            delimiter=",",
                            header="time_ns,counts,noise",
                            comments="",
                        )
                    elif self.action == "save_regions":
                        self.regions.save(path)
                    elif self.action == "load_regions":
                        self.regions.load(path)
                    elif self.action == "save_settings":
                        path.with_suffix(".json").write_text(
                            json.dumps(self.state_dict(), indent=2)
                        )
                    elif self.action == "load_settings":
                        self.apply_state(json.loads(path.read_text()))
                    self.dialog = None
                except Exception as exc:
                    self.error = str(exc)
            elif result is False or pressed == "close":
                self.dialog = None
            self.file_window.end()
        self.picker.render((0, 0, *vp.size))
        if self.help.open:
            self.help.draw((0, 0, *vp.size))


def make_app(**kwargs):
    from chisurf.emtk.i18n import install

    install()
    return ClsmApp(model=kwargs.get("model"))
