"""Native CLSM reconstruction, brush/ROI selection, fluorescence decays and exports."""

from __future__ import annotations

import contextlib
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
from emtk.view_form import FormState, draw_form

from chisurf.emtk.dataset_picker import DatasetPicker
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.emtk.image_canvas import ImageCanvas
from chisurf.emtk.jobs import SnapshotJob
from chisurf.emtk.regions import RegionControls
from chisurf.plugins.emtk_layout import button_row, layout_spec

from ..core import imaging
from .view_model import ClsmViewModel


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


CHANNEL_SPEC = layout_spec({"sections": [{"type": "value", "attr": "channels_text", "kind": "str", "label": "Detector channels", "width": 150,
    "description": "Comma-separated photon routing channels."}]})
MARKER_SPEC = layout_spec({"sections": [
    {"type": "toggle", "attr": "use_pixel_markers", "label": "Use pixel markers",
     "description": "Use explicit per-pixel marker records instead of time-derived raster positions."},
    {"type": "value", "attr": "marker_pixel", "kind": "int", "style": "spin", "label": "Pixel marker", "minimum": 0, "maximum": 255,
     "description": "Routing marker code for the beginning of a pixel."},
    {"type": "value", "attr": "n_lines", "kind": "int", "style": "spin", "label": "Lines/frame", "minimum": 0, "maximum": 65536,
     "description": "Explicit scanner line count; zero uses pixels/line."}]})


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
        self.item_rects = {}
        self.tour = EmTkGuidedTour(steps=Path(__file__).with_name("guide.json"), get_target_rect=lambda k: self.item_rects.get(k),
                                   owner=self, wait_for_controls=True)
        self.group_forms = self._group_forms()
        self.skip_group = False
        self.forms = {k: FormState(on_used=lambda n: self.tour.notify_used(n)) for k in ("channels", "markers")}
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
        mask = self.model.selection_mask
        if mask is not None and mask.any():
            self.tour.notify_used("CLSM image")  # the guide's "paint a decay" step waits for a painted pixel
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
            self.request_frame()

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

    def _group_forms(self):
        """(title, target group, spec) of the Acquisition and Brush & Decay panels, one spec per target of the Qt spec."""
        panels = self.sections[1:3]
        out = []
        for panel in panels:
            run = []
            for sec in panel["sections"]:
                target = sec.get("target")
                if run and run[-1][0] == target:
                    run[-1][1].append(sec)
                else:
                    run.append((target, [sec]))
            for i, (target, secs) in enumerate(run):
                secs = json.loads(json.dumps(secs))
                for sec in secs:
                    sec.pop("target", None)
                    if sec.get("type") == "value" and sec.get("kind") in ("int", "float") and not sec.get("read_only"):
                        sec["style"] = "spin"
                out.append((panel["title"] if i == 0 else "", target, layout_spec({"sections": secs})))
        return out

    def controls(self, box):
        busy = self.job.busy or self.dialog is not None or self.picker.is_open
        pressed = button_row([
            {"label": "Help", "key": "help", "tip": "Explain marker reconstruction, intensity/lifetime representations and brush-selected decays."},
            {"label": "Guide", "key": "guide", "tip": "Walk through loading a CLSM scan, building an image and painting a decay."},
        ], remember=self.remember)
        if pressed == "help":
            self.help.show()
        elif pressed == "guide":
            self.tour.start()
        im.begin_disabled(busy)
        actions = [
            ("Open TTTR / imaging", "Load photon data or follow an imaging HDF5 source reference.", lambda: self.choose("load_file"), True),
            ("MMFDB dataset", "Resolve registered photon data to a local input file.", self.picker.open, True),
            ("Build CLSM", "Reconstruct and fill a scanner image using the acquisition settings.", lambda: self.start("add_clsm"), self.model.tttr_data is not None),
            ("Add representation", "Compute the selected intensity or micro-time representation.", lambda: self.start("add_representation"), bool(self.model.clsm_image_names())),
            ("Compute decay", "Compute the photon histogram of selected pixels.", self.request_decay, self.model.selection_mask is not None),
            ("Add decay → ChiSurf", "Publish the current decay as a real ChiSurf experimental dataset.", self.publish_dataset, self.model.current_decay is not None),
            ("Export image", "Save the current physical image as a TIFF.", lambda: self.choose("image"), self.model.current_image is not None),
            ("Export decay CSV", "Export time, counts and Poisson noise of the current decay.", lambda: self.choose("decay"), self.model.current_decay is not None),
        ]
        pressed = button_row([{"label": l, "key": l, "tip": t, "enabled": e} for l, t, _a, e in actions], remember=self.remember)
        if pressed:
            dict((l, a) for l, _t, a, _e in actions)[pressed]()
            self.tour.notify_used(pressed)
        status = self.job.progress if self.job.busy else self.status
        im.text_wrapped(status)
        self.remember("status")
        if self.error or self.job.error:
            im.text_wrapped(self.error or self.job.error)

        if self.model.filename:
            im.text_disabled(Path(self.model.filename).name)
            im.set_item_tooltip(self.model.filename)
        names = self.model.setup_names
        index = names.index(self.model.setup.setup_name) if self.model.setup.setup_name in names else 0
        im.text("Setup preset")
        im.same_line(150)
        im.set_next_item_width(-1)
        changed, index = im.combo("##Setup preset", index, names)
        self.remember("setup_preset")
        im.set_item_tooltip("Restore scanner markers, file type and reading routine from a named acquisition preset.")
        if changed:
            self.model.apply_preset(names[index])
        self.forms["channels"].rects.clear()
        draw_form(CHANNEL_SPEC, self.model.setup, self.forms["channels"])
        self.item_rects.update(self.forms["channels"].rects)
        for attr, source, remove, label, tip, removed in [
            ("current_clsm_name", self.model.clsm_image_names, "remove_clsm", "CLSM image",
             "Choose among independently reconstructed channel images.", "Remove CLSM"),
            ("current_representation_name", self.model.representation_names, "remove_representation", "Representation",
             "Choose among stored representations.", "Remove representation"),
        ]:
            names = source()
            if not names:
                continue
            current = getattr(self.model, attr)
            im.text(label)
            im.same_line(150)
            narrow = im.get_content_region_avail()[0] < 330.0
            im.set_next_item_width(-1 if narrow else im.get_content_region_avail()[0] - 90.0)
            changed, index = im.combo("##" + attr, names.index(current) if current in names else 0, names)
            self.remember(attr)
            im.set_item_tooltip(tip)
            if changed:
                if attr == "current_representation_name":
                    self.model.select_representation(names[index])
                    self.selection_changed()
                else:
                    self.model.current_clsm_name = names[index]
            if not narrow:
                im.same_line()
            if im.button("Remove##remove_" + attr):
                getattr(self.model, remove)(getattr(self.model, attr))
                self.selection_changed()
            im.set_item_tooltip("Remove this stored image/representation; retained sources stay available.")
            self.remember(removed)
        for title, target, spec in self.group_forms:
            if title:
                if not im.collapsing_header(title, 0 if title == "Acquisition" else im.TreeNodeFlags.DEFAULT_OPEN):
                    self.skip_group = True
                else:
                    self.skip_group = False
                im.set_item_tooltip(f"Expand or collapse {title}.")
                self.remember(f"{title}.fold")
            if self.skip_group:
                continue
            group = getattr(self.model, target)
            before = dict(vars(group))
            form = self.forms.setdefault(f"{title}:{target}", FormState(on_used=self.tour.notify_used))
            form.rects.clear()
            draw_form(spec, group, form)
            self.item_rects.update(form.rects)
            if dict(vars(group)) != before:
                self.settings_changed()
        self.forms["markers"].rects.clear()
        before = dict(vars(self.model.setup))
        draw_form(MARKER_SPEC, self.model.setup, self.forms["markers"])
        self.item_rects.update(self.forms["markers"].rects)
        im.text("Selection")
        _, self.paint = im.checkbox("Paint selection", self.paint)
        self.remember("paint")
        im.set_item_tooltip("Reserve left-mouse dragging for selecting/erasing pixels; use the middle button to pan.")
        pressed = button_row([
            {"label": "Clear selection", "key": "Clear selection", "tip": "Clear painted pixels and the active decay."},
            {"label": "Save painted region", "key": "Save painted region", "tip": "Capture painted pixels as a reusable named mask region."},
        ], remember=self.remember)
        if pressed == "Clear selection":
            self.model.clear_selection()
            self.selection_changed()
        elif pressed == "Save painted region":
            self.model.add_roi(self._roi_name)
        im.text("Region name")
        im.same_line(150)
        im.set_next_item_width(-1)
        _, self._roi_name = im.input_text("##roi_name", self._roi_name)
        self.remember("roi_name")
        im.set_item_tooltip("Name for the saved painted mask.")
        self.regions.draw()
        pressed = button_row([
            {"label": "Save settings", "key": "Save settings", "tip": "Persist acquisition, brush and representation settings plus region geometry."},
            {"label": "Load settings", "key": "Load settings", "tip": "Restore acquisition, brush and representation settings plus region geometry."},
        ], remember=self.remember)
        if pressed:
            self.choose("save_settings" if pressed == "Save settings" else "load_settings")
        im.end_disabled()

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
        with _pointer_masked(self.tour.active and not self.tour.awaiting):  # the paint step needs the canvas
            self._draw_canvas()
        self.model.colormap = self.canvas.colormap
        self.item_rects["CLSM image"] = self.canvas.rect
        summary = self.model.region_summary()
        if summary:
            im.text_unformatted(summary)

    def _draw_canvas(self):
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

    def decay_plot(self, box):
        with _pointer_masked(self.tour.active):
            self._draw_decay()

    def _draw_decay(self):
        if implot.begin_plot("Selected pixel decays", (-1, -1)):
            implot.setup_axes("Time [ns]", "Photon counts")
            implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
            implot.setup_legend()
            for series in self.model.decay_series():
                implot.plot_line(series["name"], series["x"], series["y"])
            implot.end_plot()
            self.remember("decay_plot")
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
            m = self.model
            self.status = (f"{Path(m.filename).name if m.filename else 'No file'}: {len(m.clsm_image_names())} CLSM image(s), "
                           f"{len(m.representation_names())} representation(s)"
                           + (f", image {m.current_image.shape[1]} x {m.current_image.shape[0]} px" if m.current_image is not None else ""))
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
        if self.tour.active:
            self.tour.draw(*vp.size)


def make_app(**kwargs):
    from chisurf.emtk.i18n import install

    install()
    return ClsmApp(model=kwargs.get("model"))
