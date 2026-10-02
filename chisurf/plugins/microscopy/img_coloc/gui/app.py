"""Native colocalization workstation sharing the exact Qt scientific model."""
from __future__ import annotations

import copy
import json
import queue
import threading
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from emtk import i18n, im, implot
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog

from chisurf.core.roi import EllipseROI, PolygonROI, RectangleROI, RegionCollection
from chisurf.emtk.dataset_picker import DatasetPicker
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.emtk.image_canvas import ImageCanvas
from chisurf.emtk.regions import RegionControls
from chisurf.plugins.calculator.inputs import bounded_float, bounded_int

from .view_model import ColocViewModel


class GateControls(RegionControls):
    """Shared region editor, with new geometry in measured intensity units."""
    def __init__(self, app):
        self.app = app
        super().__init__(SimpleNamespace(regions=app.model.gates), app.choose,
                         on_change=app.gates_changed, get_image=app.model.histogram_image)

    def add_shape(self, kind):
        a0, a1, b0, b1 = self.app.model.gate_extent()
        cx, cy = (a0 + a1) / 2, (b0 + b1) / 2
        rx, ry = (a1 - a0) / 4, (b1 - b0) / 4
        if kind == "ellipse":
            roi = EllipseROI(cx, cy, rx, ry, name="Ellipse")
        elif kind == "polygon":
            roi = PolygonROI(np.array([[cx-rx, cy+ry], [cx, cy-ry], [cx+rx, cy+ry]]), name="Polygon")
        else:
            roi = RectangleROI(cx-rx, cy-ry, cx+rx, cy+ry, name="Rectangle")
        self.selected = self.app.model.gates.add(roi)
        self.changed()
        return self.selected


class ColocApp(ImApp):
    def __init__(self, model=None, **kwargs):
        self.model = model or ColocViewModel()
        self.busy = False
        self.error = ""
        self.progress = ""
        self._generation = 0
        self._messages = queue.SimpleQueue()
        self._thread = None
        self._dirty_roi = False
        self._dirty_gate = False
        self.paint_roi = False
        self.paint_gate = False
        self.erase = False
        self._mask_version = 0
        self.dialog = None
        self.file_window = None
        self.action = ""
        self.fields = json.loads(Path(__file__).with_name("coloc.view.json").read_text())["sections"][0]["sections"][0]["sections"]
        self.canvases = {key: ImageCanvas("coloc_" + key) for key in ("a", "b", "mask", "scatter", "ccf", "objects")}
        self.gate_controls = GateControls(self)
        self.picker = DatasetPicker(kinds=["raw_data", "raw_measurement"],
                                    formats=["tif", "tiff", "ptu", "pto", "ht3", "spc"],
                                    on_paths=self.open_paths)
        self.help = EmTkHelpWindow(title="Colocalization — Help", resource=Path(__file__).with_name("help.md"), owner=self)
        self.tour = EmTkGuidedTour(Path(__file__).with_name("guide.json"), owner=self)
        self.docks = DockManager(Split("h", .30, Region("settings"), Region("views")))
        self.docks.add_window("settings", "Analysis settings", self.controls, dock="settings", closable=False)
        for key, title, draw in [
            ("coefficients", "Coefficients", self.coefficients),
            ("channels", "Channels", self.channels),
            ("scatter", "Intensity scatter", self.scatter),
            ("mask", "Colocalized pixels", lambda b: self.image("mask", self.model.coloc_mask_image())),
            ("ccf", "van Steensel CCF", lambda b: self.plot(self.model.ccf_series(), "shift / px", "PCC")),
            ("ccf2d", "CCF map (2-D)", lambda b: self.image("ccf", self.model.ccf_map_image())),
            ("profiles", "PCC vs intensity", lambda b: self.plot(self.model.profile_series(), "intensity / ratio", "PCC")),
            ("objects", "Objects", lambda b: self.image("objects", self.model.object_map_image())),
            ("distances", "Object distances", lambda b: self.plot(self.model.object_distance_series(), "nearest-neighbour distance / px", "objects")),
        ]:
            self.docks.add_window(key, title, draw, dock="views", closable=False)
        super().__init__(self.render, continuous=False)

    def start(self, method="compute"):
        if self.busy or not self.model.filename:
            return False
        # Detach every editable collection and image mask. Cancel invalidates the
        # generation, so a late worker cannot replace the visible result.
        snapshot = copy.copy(self.model)
        for key in ("detectors", "gates", "roi_mask", "gate_paint"):
            setattr(snapshot, key, copy.deepcopy(getattr(self.model, key)))
        snapshot._observers = []
        self._generation += 1
        generation = self._generation
        self.busy, self.error, self.progress = True, "", "Computing colocalization…"
        def run():
            try:
                if method == "compute":
                    ok = snapshot.compute(progress=lambda f, text: self._messages.put((generation, "progress", text)))
                else:
                    getattr(snapshot, method)()
                    ok = not snapshot.results_text.startswith("Failed:")
                self._messages.put((generation, "done", snapshot if ok else snapshot.results_text))
            except Exception as exc:
                self._messages.put((generation, "done", str(exc)))
        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()
        return True

    def cancel(self):
        self._generation += 1
        self.busy = False
        self.progress = "Cancelled"

    def poll(self):
        changed = False
        while not self._messages.empty():
            generation, kind, value = self._messages.get()
            if generation != self._generation:
                continue
            if kind == "progress":
                self.progress = value
            else:
                self.busy = False
                self.progress = ""
                if isinstance(value, ColocViewModel):
                    for key, entry in vars(value).items():
                        if key != "_observers":
                            setattr(self.model, key, entry)
                    self.gate_controls.model.regions = self.model.gates
                    for canvas in self.canvases.values():
                        canvas.reset()
                    changed = True
                else:
                    self.error = str(value)
        return changed

    def open_paths(self, paths):
        if paths and not self.busy:
            self.model.set_filename(str(paths[0]))
            self.start()

    def on_files_dropped(self, paths):
        if self.busy or not paths:
            return False
        self.open_paths(paths)
        return True

    def apply_setup_settings(self, payload):
        if self.busy:
            self.cancel()
        self.model.apply_setup_settings(payload)
        if self.model.filename:
            self.start()

    def choose(self, action):
        self.action = action
        save = action in ("csv", "save_state", "save_regions")
        title = {"open": "Open image", "csv": "Export CSV", "setup": "Import detector setup",
                 "save_state": "Save settings", "load_state": "Load settings",
                 "save_regions": "Save regions", "load_regions": "Load regions"}[action]
        self.dialog = FileDialog(i18n.tr(title), mode="save" if save else "open",
                                 filters="Images and photons (*.tif *.tiff *.png *.pto *.ptu *.ht3 *.spc);;All files (*)" if action == "open" else "CSV (*.csv)" if action == "csv" else "JSON (*.json)",
                                 filename="colocalization.csv" if action == "csv" else "colocalization.json" if save else "")
        self.file_window = DialogWindow(self.dialog.title, size=(700, 540), key="coloc_file")
        self.file_window.show()

    def handle_path(self, action, path):
        if action == "open":
            self.open_paths([path])
        elif action == "csv":
            self.model.export_csv(path)
        elif action == "setup":
            self.apply_setup_settings(json.loads(Path(path).read_text()))
        elif action == "save_state":
            Path(path).write_text(json.dumps(self.export_settings(), indent=2))
        elif action == "load_state":
            self.restore_settings(json.loads(Path(path).read_text()))
        elif action == "save_regions":
            self.model.gates.save(path)
        elif action == "load_regions":
            self.model.gates = RegionCollection.load(path)
            self.gate_controls.model.regions = self.model.gates
            self.gates_changed()

    @staticmethod
    def button(label, tooltip, action):
        if im.button(label):
            action()
        im.set_item_tooltip(tooltip)

    def toolbar(self):
        actions = [
            ("Open", "Open a multichannel image or photon stream; dropping a file also loads and runs it.", lambda: self.choose("open")),
            ("MMFDB", "Load a registered raw image or photon measurement from the database.", self.picker.open),
            ("Setup", "Import named detector windows from a Detector Def JSON setup.", lambda: self.choose("setup")),
            ("Run", "Compute the selected channel pair using all current settings in the background.", self.start),
            ("Background", "Estimate the low intensity quantile of each channel and recompute.", lambda: self.start("estimate_background")),
            ("Export CSV", "Save every scalar coefficient with the source and channel identities.", lambda: self.choose("csv")),
            ("Save settings", "Save analysis parameters, detector windows, gate regions and painted selections as JSON.", lambda: self.choose("save_state")),
            ("Load settings", "Restore the full analysis selection and recompute the saved source.", lambda: self.choose("load_state")),
        ]
        if self.busy:
            actions.append(("Cancel", "Discard the active computation; late results cannot replace the visible analysis.", self.cancel))
        actions.extend([
            ("Help", "Read coefficient definitions, interpretation and the colocalization workflow.", self.help.show),
            ("Guide", "Walk through selecting a source, channel pair, thresholds and result views.", self.tour.start),
        ])
        available = im.get_content_region_avail()[0]
        used = 0
        rows = 1
        for index, (label, tooltip, action) in enumerate(actions):
            item_width = im.calc_text_size(i18n.tr(label))[0] + 12
            if index and used + item_width < available:
                im.same_line()
            elif index:
                used = 0
                rows += 1
            used += item_width + 6
            im.begin_disabled(self.busy and label not in ("Help", "Guide", "Cancel"))
            self.button(label, tooltip, action)
            im.end_disabled()
        self._toolbar_rows = rows

    def controls(self, box):
        windows = list(self.docks.windows)
        selected = self.docks.selected.get("views", "coefficients")
        labels = [i18n.tr(self.docks.windows[key].title) for key in windows if key != "settings"]
        keys = [key for key in windows if key != "settings"]
        changed, index = im.combo("Result view", keys.index(selected) if selected in keys else 0, labels)
        im.set_item_tooltip("Choose any result view, including those beyond the visible tab strip at small window sizes.")
        if changed:
            self.docks.focus(keys[index])
        im.separator()
        im.text_wrapped(self.model.filename or "Choose a two-channel image.")
        im.text_wrapped(self.progress if self.busy else self.error or (self.model.results_text if self.model.filename else ""))
        if self.model.setup_name:
            im.text_wrapped(i18n.tr("Setup") + ": " + self.model.setup_name)
        im.begin_disabled(self.busy)
        self.draw_fields(self.fields)
        self.gate_controls.draw()
        im.end_disabled()

    def draw_fields(self, fields):
        for field in fields:
            kind = field.get("type")
            if kind == "panel":
                opened = im.collapsing_header(field["title"], im.TreeNodeFlags.DEFAULT_OPEN if not field.get("collapsed") else 0)
                im.set_item_tooltip(field["title"])
                if opened:
                    self.draw_fields(field["sections"])
                continue
            if kind == "button_row":
                for button in field["buttons"]:
                    method = button["action"]
                    self.button(button["label"], button["description"], lambda m=method: self.start(m))
                continue
            if kind not in ("choice", "toggle", "value"):
                continue
            attr, label = field["attr"], field["label"]
            old = getattr(self.model, attr)
            if kind == "toggle":
                changed, value = im.checkbox(label, bool(old))
            elif kind == "choice":
                options = getattr(self.model, field["options_source"])() if "options_source" in field else field["options"]
                options = options or [""]
                changed, index = im.combo(label, options.index(old) if old in options else 0, options)
                value = options[index]
            else:
                fn = bounded_int if field.get("kind") == "int" else bounded_float
                changed, value = fn(label, old, minimum=field.get("minimum", -1e9), maximum=field.get("maximum", 1e9), step=field.get("step", 1))
            im.set_item_tooltip(field.get("description", label))
            if changed:
                setattr(self.model, attr, value)

    def coefficients(self, box):
        rows = self.model.metric_rows()
        if not rows:
            im.text_wrapped("Run the selected image to display colocalization coefficients.")
            return
        im.text_wrapped(self.model.results_text)
        if im.begin_table("Coefficients", 2, im.TableFlags.BORDERS | im.TableFlags.ROW_BG):
            im.table_setup_column("Coefficient", im.TableColumnFlags.WIDTH_STRETCH)
            im.table_setup_column("Value", im.TableColumnFlags.WIDTH_FIXED, 150)
            im.table_headers_row()
            for row in rows:
                im.table_next_row()
                im.table_next_column()
                im.text_unformatted(row["name"])
                im.set_item_tooltip("See Help for the definition and interpretation of this coefficient.")
                im.table_next_column()
                im.text_unformatted(row["value"])
            im.end_table()

    def paint(self, target, zyx):
        mask = getattr(self.model, target)
        if mask is None:
            return
        _, y, x = zyx
        half = self.model.brush_size // 2
        mask[max(0,y-half):y+half+1, max(0,x-half):x+half+1] = 0 if self.erase else 1
        self._mask_version += 1
        self._dirty_roi |= target == "roi_mask"
        self._dirty_gate |= target == "gate_paint"

    def gates_changed(self):
        if self.model.gates.get("box") is None:
            self.model.gate_a_max = self.model.gate_a_min
            self.model.gate_b_max = self.model.gate_b_min
        self.model.gate_enabled = bool(len(self.model.gates))
        self.start()

    def channels(self, box):
        _, self.paint_roi = im.checkbox("Paint ROI", self.paint_roi)
        im.set_item_tooltip("Paint an analysis region on Channel A; release the mouse to recompute using that region.")
        im.same_line()
        _, self.erase = im.checkbox("Erase", self.erase)
        im.set_item_tooltip("Erase painted selection pixels with the same brush.")
        width = max(100, im.get_content_region_avail()[0] / 2 - 8)
        if im.begin_child("Channel A", (width, 0)):
            im.text_unformatted("Channel A")
            self.canvases["a"].draw(self.model.image_a(), selection=self.model.roi_mask,
                selection_version=self._mask_version, on_brush=lambda p: self.paint("roi_mask", p) if self.paint_roi and not self.busy else None)
        im.end_child()
        im.same_line()
        if im.begin_child("Channel B", (width, 0)):
            im.text_unformatted("Channel B")
            self.canvases["b"].draw(self.model.image_b(), pick_enabled=False)
        im.end_child()

    def image(self, key, array):
        self.canvases[key].draw(array, pick_enabled=False)

    def scatter(self, box):
        array = self.model.histogram_image()
        if array is None:
            im.text_wrapped("Run the image to inspect the joint intensity histogram.")
            return
        _, self.paint_gate = im.checkbox("Paint gate", self.paint_gate)
        im.set_item_tooltip("Paint the scatter population in intensity space; it combines with named box, ellipse and polygon gates.")
        im.same_line()
        _, self.erase = im.checkbox("Erase", self.erase)
        im.set_item_tooltip("Erase scatter-gate brush pixels.")
        canvas = self.canvases["scatter"]
        texture = canvas.texture(np.asarray(array).T[::-1])
        a0, a1, b0, b1 = self.model.gate_extent()
        input_map = implot.get_input_map()
        pan = input_map.pan
        if self.paint_gate:
            input_map.pan = 2
        try:
            if implot.begin_plot("Intensity scatter", (-1, -1)):
                implot.setup_axes("Channel A intensity", "Channel B intensity")
                implot.setup_axes_limits(a0, a1, b0, b1, implot.COND_ONCE)
                implot.plot_image("Pixel count (log)" if self.model.log_histogram else "Pixel count", texture, (a0,b0), (a1,b1))
                used_handle = False
                for i, entry in enumerate(self.model.gates):
                    if not entry.enabled:
                        continue
                    roi = entry.roi
                    outline = ImageCanvas.outline(roi)
                    if outline is not None:
                        implot.set_next_line_style((70,190,255,255), 2)
                        implot.plot_line(entry.name, outline[:,0], outline[:,1])
                    if self.busy:
                        continue
                    if isinstance(roi, RectangleROI):
                        result = implot.drag_rect(i+100, roi.x0, roi.y0, roi.x1, roi.y1, (70,190,255,255))
                        used_handle |= result.held or result.clicked
                        if result.modified:
                            if entry.name == "box":
                                self.model.gate_a_min, self.model.gate_a_max = result.x_min, result.x_max
                                self.model.gate_b_min, self.model.gate_b_max = result.y_min, result.y_max
                            entry.roi = RectangleROI(result.x_min,result.y_min,result.x_max,result.y_max,name=entry.name)
                            self._dirty_gate = True
                    else:
                        points = [(roi.cx, roi.cy)] if isinstance(roi, EllipseROI) else list(roi.vertices) if isinstance(roi, PolygonROI) else []
                        for j, (x,y) in enumerate(points):
                            result = implot.drag_point(10000+i*100+j, float(x),float(y),(70,190,255,255),5)
                            used_handle |= result.held or result.clicked
                            if result.modified:
                                if isinstance(roi, EllipseROI):
                                    roi.cx, roi.cy = result.x, result.y
                                else:
                                    roi.vertices[j] = [result.x, result.y]
                                self._dirty_gate = True
                if self.paint_gate and not self.busy and not used_handle and implot.is_plot_hovered() and im.is_mouse_down(0):
                    position = implot.get_plot_mouse_pos()
                    ia = int((position.x-a0)/(a1-a0)*array.shape[0])
                    ib = int((position.y-b0)/(b1-b0)*array.shape[1])
                    if 0 <= ia < array.shape[0] and 0 <= ib < array.shape[1]:
                        self.paint("gate_paint", (0,ia,ib))
                implot.end_plot()
                im.set_item_tooltip("Joint histogram: A horizontal, B vertical. Drag blue region handles; right-drag to pan when painting.")
        finally:
            input_map.pan = pan

    @staticmethod
    def plot(series, xlabel, ylabel):
        if not series:
            im.text_wrapped("Enable the corresponding analysis and Run to display this result.")
            return
        if implot.begin_plot("##coloc_profile", (-1,-1)):
            implot.setup_axes(xlabel, ylabel)
            for entry in series:
                implot.plot_line(entry["name"], entry["x"], entry["y"])
            implot.end_plot()
            im.set_item_tooltip("Drag to pan, scroll to zoom and double-click to fit the computed profile.")

    def export_settings(self):
        fields = {}
        def walk(items):
            for item in items:
                if item.get("attr"):
                    fields[item["attr"]] = getattr(self.model, item["attr"])
                walk(item.get("sections", []))
        walk(self.fields)
        return {"fields": fields, "filename": self.model.filename, "detectors": copy.deepcopy(self.model.detectors),
                "setup_name": self.model.setup_name, "gates": self.model.gates.to_dict(),
                "roi_mask": None if self.model.roi_mask is None else self.model.roi_mask.tolist(),
                "gate_paint": None if self.model.gate_paint is None else self.model.gate_paint.tolist()}

    def restore_settings(self, data):
        self.cancel()
        self.model.set_filename(data.get("filename", ""))
        for key, value in data.get("fields", {}).items():
            if hasattr(self.model, key) and not key.startswith("_"):
                setattr(self.model, key, value)
        self.model.detectors = copy.deepcopy(data.get("detectors", {}))
        self.model.setup_name = data.get("setup_name", "")
        self.model.gates = RegionCollection.from_dict(data.get("gates", {}))
        self.gate_controls.model.regions = self.model.gates
        for key in ("roi_mask", "gate_paint"):
            value = data.get(key)
            setattr(self.model,key, None if value is None else np.asarray(value, dtype=float))
        self.start()

    def render(self):
        self.poll()
        if not im.is_mouse_down(0) and not self.busy:
            if self._dirty_roi:
                self._dirty_roi = False
                self.start()
            elif self._dirty_gate:
                self._dirty_gate = False
                # Convert painted bins without calling the synchronous Qt callback.
                painted = self.model.gate_paint
                if self.paint_gate and painted is not None:
                    from chisurf.core.roi import MaskROI
                    self.model.gates.remove("painted")
                    if np.any(painted):
                        histogram = self.model._result.histogram
                        self.model.gates.add(MaskROI.from_histogram((painted > 0).T, histogram["edges_a"], histogram["edges_b"], name="painted"))
                self.model.gate_enabled = bool(len(self.model.gates))
                self.start()
        vp = im.get_main_viewport()
        im.set_next_window_pos((0,0), im.Cond.ALWAYS)
        toolbar_height = 26 * max(1, getattr(self,"_toolbar_rows",2)) + 10
        im.set_next_window_size((vp.size[0],toolbar_height), im.Cond.ALWAYS)
        if im.begin("Colocalization actions", flags=im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_MOVE | im.WindowFlags.NO_RESIZE):
            self.toolbar()
        im.end()
        self.docks.draw((0,toolbar_height,vp.size[0],max(1,vp.size[1]-toolbar_height)))
        if self.dialog:
            pressed = self.file_window.begin((0,0,*vp.size))
            result = self.dialog.draw()
            if result:
                try:
                    self.handle_path(self.action, str(result[0]))
                except Exception as exc:
                    self.error = str(exc)
                self.dialog = None
            elif result is False or pressed == "close":
                self.dialog = None
            self.file_window.end()
        self.picker.render((0,0,*vp.size))
        self.help.draw((0,0,*vp.size))
        self.tour.draw(*vp.size)

    def animating(self):
        return super().animating() or self.busy or self.picker.is_open

    def close(self):
        self.cancel()


def make_app(**kwargs):
    from chisurf.emtk.i18n import install
    install()
    from .native_i18n import install as install_native
    install_native()
    return ColocApp(**kwargs)
