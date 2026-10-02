"""Native VV/VH calibration, slow-protein mixing and anisotropy batch analysis (emtk)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
from emtk import im, implot
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog
from emtk.view_form import FormState, draw_form

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.plugins.emtk_layout import LabelColumn, button_row, labelled, layout_spec
from chisurf.plugins.tttr.tttr_splitter.gui.jobs import BackgroundJob

from .client import VvVhGFactorClient
from .model import GFactorModel

HERE = Path(__file__).parent
DISPLAY = ("show_fast", "show_slow", "show_raw", "show_corrected", "log_y")


class GFactorApp(ImApp):
    def __init__(self, client=None):
        self.model = GFactorModel()
        self.client = client or VvVhGFactorClient()
        self.item_rects = {}
        panels = json.loads((HERE / "gfactor_emtk.view.json").read_text())["panels"]
        self.panels = {n: layout_spec(copy.deepcopy(p)) for n, p in panels.items()}
        self.forms = {n: FormState() for n in panels}
        self.labels = {n: LabelColumn() for n in panels}
        self.help = EmTkHelpWindow(
            title="VV/VH G-factor: Help", resource=HERE / "help.md", owner=self
        )
        self.guide = EmTkGuidedTour(
            steps=HERE / "guide.json",
            get_target_rect=lambda key: self.item_rects.get(key)
            or next((f.rects[key] for f in self.forms.values() if key in f.rects), None),
            owner=self,
            wait_for_controls=True,
        )
        for form in self.forms.values():
            form.on_used = self.guide.notify_used
        self.job = BackgroundJob()
        self.dialog = None
        self.dialog_window = None
        self.dialog_callback = None
        self.last_dir = ""
        self.show_fast = self.show_slow = self.show_raw = self.show_corrected = True
        self.log_y = True
        self.plot_signature = None
        self.plot_info = {}
        self.settings_signature = self.fingerprint()
        self.docks = DockManager(
            Split("h", 0.43, Region("controls"), Split("v", 0.58, Region("decays"), Region("anisotropy"))),
            name="vv_vh_g_factor",
        )
        self.docks.add_window("controls", "G-factor and mixing", self.draw_controls, dock="controls", closable=False)
        self.docks.add_window("batch", "Batch anisotropy", self.draw_batch, dock="controls", closable=False)
        self.docks.add_window("decays", "VV/VH decays", self.draw_decays, dock="decays", closable=False)
        self.docks.add_window("anisotropy", "Anisotropy r(t)", self.draw_anisotropy, dock="anisotropy", closable=False)
        super().__init__(gui=self.render, continuous=True)

    # -- plumbing ---------------------------------------------------------------------------- #
    def fingerprint(self):
        settings = self.model.export_settings()
        settings.pop("batch_files", None)
        return json.dumps(settings, sort_keys=True)

    def form(self, name, model=None):
        spec, column = self.panels[name], self.labels[name]
        if not column.ready:
            column.measure([f["label"] for f in labelled(spec["sections"])])
        column.pad(spec["sections"])
        draw_form(spec, model or self.model, self.forms[name])

    def remember(self, name):
        self.item_rects[name] = im.get_item_rect()

    def choose(self, title, callback, mode="open", multiple=False, filename=""):
        if self.job.running:
            return
        self.dialog = FileDialog(
            title, mode=mode, multiselect=multiple, filename=filename, directory=self.last_dir or None,
            filters="VV/VH decay (*.dat *.txt);;All files (*)" if mode != "save" else "Results (*.json *.tsv *.txt);;All files (*)",
        )
        self.dialog_window = DialogWindow(title, size=(760, 540))
        self.dialog_callback = callback

    def run(self, operation, on_complete=None):
        if self.job.running:
            return False
        model = self.model.snapshot()

        def work():
            operation(model)
            return model

        def publish(done):
            self.model = done
            self.plot_signature = None
            self.settings_signature = self.fingerprint()
            if on_complete:
                on_complete()

        return self.job.start(work, publish, lambda exc: setattr(self.model, "message", f"Error: {exc}"))

    def load(self, path, slow=False):
        self.last_dir = str(Path(path).parent)

        def operation(model):
            model.load(path, slow=slow)
            if model.fast is not None:
                model.compute(self.client)

        ok = self.run(operation)
        if ok and not slow:
            self.guide.notify_used("load_fast")
        if ok and slow:
            self.guide.notify_used("load_slow")
        return ok

    def calculate(self):
        return self.run(lambda model: model.compute(self.client))

    def archive(self):
        if self.job.running:
            return False
        if not self.model.fast_file:
            self.model.message = "Load a reference decay before archival."
            return False
        source, parameters = self.model.fast_file, self.model.archive_parameters()

        def work():
            result = self.client.archive_g_factor(source, parameters)
            if not result.get("ok", True) or not result.get("calibration_id"):
                raise ValueError(result.get("error") or "Calibration archival did not return an identifier.")
            return result

        return self.job.start(
            work,
            lambda result: setattr(self.model, "message", f"Archived calibration {result['calibration_id']}"),
            lambda exc: setattr(self.model, "message", f"Error: {exc}"),
        )

    def add_batch(self, paths):
        for path in paths:
            self.last_dir = str(Path(path).parent)
            if str(path) not in self.model.batch_files:
                self.model.batch_files.append(str(path))

    def clear_batch(self):
        self.model.batch_files = []
        self.model.batch_results = []

    def files_dropped(self, paths):
        """Host drop: the first file is the fast reference, the second the slow protein, any more join the batch queue."""
        paths = [str(p) for p in paths]
        if not paths:
            return False
        self.load(paths[0])
        if len(paths) > 1:
            # the slow reference loads after the fast one finishes (one job at a time)
            self._follow = [lambda: self.load(paths[1], slow=True)]
            if paths[2:]:
                self._follow.append(lambda: self.add_batch(paths[2:]))
        return True

    on_files_dropped = files_dropped
    on_paths_dropped = files_dropped

    # -- windows ----------------------------------------------------------------------------- #
    def path_row(self, label, path, empty):
        im.text(label)
        im.same_line()
        im.text_disabled(("..." + path[-52:]) if len(path) > 55 else (path or empty))
        if path:
            im.set_item_tooltip(path)

    def draw_controls(self, box):
        m = self.model
        m.busy = self.job.running
        busy = self.job.running or self.dialog is not None
        pressed = button_row(
            [
                {"label": "Fast reference...", "key": "load_fast", "enabled": not busy,
                 "tip": "Load the fast-rotating reference dye VV/VH decay used for the tail-matching G calibration."},
                {"label": "Slow protein...", "key": "load_slow", "enabled": not busy,
                 "tip": "Load the slow-rotating protein VV/VH decay for the linked polarization-mixing estimate."},
                {"label": "Export calibration JSON...", "key": "export", "enabled": m.g_factor is not None and not busy,
                 "tip": "Export values, uncertainty, mixing diagnostics and scientific settings."},
                {"label": "Archive reference calibration", "key": "archive", "enabled": m.g_factor is not None and not busy,
                 "tip": "Register the raw reference decay, corrected traces, anisotropy and calibration provenance through the MMFDB RPC."},
                {"label": "Stop", "key": "stop", "enabled": self.job.running,
                 "tip": "Discard the pending result; an archival already running may finish."},
                {"label": "Help", "key": "help", "tip": "Read the calibration conventions and the limits of the linked mixing estimate."},
                {"label": "Guide", "key": "guide", "tip": "Walk through the fast and slow references, the tail region and the export."},
            ],
            remember=lambda name: self.item_rects.__setitem__(name, im.get_item_rect()),
        )
        if pressed == "load_fast":
            self.choose("Fast reference", lambda paths: self.load(paths[0]))
        elif pressed == "load_slow":
            self.choose("Slow protein reference", lambda paths: self.load(paths[0], slow=True))
        elif pressed == "export":
            self.choose("Calibration results", lambda paths: self.run(lambda model: model.save_results(paths[0])),
                        mode="save", filename="calibration.json")
        elif pressed == "archive":
            self.archive()
        elif pressed == "stop":
            self.job.stop()
        elif pressed == "help":
            self.help.show()
        elif pressed == "guide":
            self.guide.start()
        self.path_row("Fast:", m.fast_file, "no reference decay loaded")
        self.path_row("Slow:", m.slow_file, "no slow reference loaded")
        im.text_wrapped(m.message or "Load the fast-rotating reference dye VV/VH decay.")
        im.separator()
        self.form("tail", m)
        self.form("results", m)
        self.form("mixing", m)
        self.form("mixing_results", m)
        im.text_wrapped(m.fp_result.get("warning") or "Warning: load FP VV/VH data to estimate l1/l2.")

    def draw_batch(self, box):
        m = self.model
        busy = self.job.running or self.dialog is not None
        pressed = button_row(
            [
                {"label": "Add files...", "key": "add", "enabled": not busy,
                 "tip": "Queue VV/VH decays to evaluate r(inf) with the frozen current G, mixing, background and shift."},
                {"label": "Run batch", "key": "run", "enabled": not busy and bool(m.batch_files) and m.g_factor is not None,
                 "tip": "Compute the corrected steady anisotropy of every queued file with the current calibration."},
                {"label": "Save table...", "key": "save", "enabled": not busy and bool(m.batch_results),
                 "tip": "Write per-file r(inf), region, backgrounds, G and errors as a tab-separated file."},
                {"label": "Clear batch", "key": "clear", "enabled": not busy and bool(m.batch_files),
                 "tip": "Remove every queued input and computed row."},
            ],
            remember=lambda name: self.item_rects.__setitem__(name, im.get_item_rect()),
        )
        if pressed == "add":
            self.choose("Batch VV/VH decays", self.add_batch, multiple=True)
        elif pressed == "run":
            self.run(lambda model: model.compute_batch(self.job.cancelled.is_set))
        elif pressed == "save":
            self.choose("Batch anisotropy table", lambda paths: self.run(lambda model: model.export_batch(paths[0])),
                        mode="save", filename="batch_anisotropy.tsv")
        elif pressed == "clear":
            self.clear_batch()
        if not m.batch_files:
            im.text_wrapped("No files queued. Add VV/VH decays to evaluate their steady anisotropy with this calibration.")
        self.form("batch", m)

    # -- plots ------------------------------------------------------------------------------- #
    def series(self):
        return [
            (label, self.model.decay_series(slow))
            for label, slow, enabled in [("Fast", False, self.show_fast), ("Slow", True, self.show_slow)]
            if enabled
        ]

    def draw_decays(self, box):
        used, avail = 0.0, im.get_content_region_avail()[0]
        spacing = im.get_style().item_spacing[0]
        for attr, label in [("show_fast", "Fast reference"), ("show_slow", "Slow reference"), ("show_raw", "Raw"),
                            ("show_corrected", "Corrected"), ("log_y", "Log counts")]:
            width = im.calc_text_size(label)[0] + 2 * im.get_frame_height() + spacing
            if used and used + width > avail:
                im.new_line()
                used = 0.0
            elif used:
                im.same_line()
            _, value = im.checkbox(label, getattr(self, attr))
            setattr(self, attr, value)
            im.set_item_tooltip("Show or hide this trace group, or change the intensity scale.")
            used += width
        im.new_line()
        if self.model.fast is None and self.model.slow is None:
            im.text_wrapped("Load a VV/VH decay (button, or drop a file on the window).")
            return
        if implot.begin_plot("##vvvh", (-1, -1)):
            implot.setup_axes("TAC bin", "Counts")
            implot.setup_legend(implot.LOCATION_NORTH_EAST)
            if self.log_y:
                implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
            series = self.series()
            vectors = [v[k] for _, v in series if v for k in ("vv_raw", "vh_raw", "vv_corrected", "vh_corrected")]
            vectors = [v for v in vectors if np.any(np.isfinite(v))]
            if vectors:
                peak = max(float(np.nanmax(v)) for v in vectors)
                length = max(map(len, vectors))
                sig = (id(self.model.fast), id(self.model.slow), self.log_y, peak)
                implot.setup_axes_limits(0, length, 1 if self.log_y else 0, max(2, peak * 1.1),
                                         cond=implot.COND_ALWAYS if sig != self.plot_signature else implot.COND_ONCE)
                self.plot_signature = sig
            for label, data in series:
                if not data:
                    continue
                for key, axis, enabled in [("vv_raw", "time", self.show_raw), ("vh_raw", "shifted_time", self.show_raw),
                                           ("vv_corrected", "time", self.show_corrected),
                                           ("vh_corrected", "shifted_time", self.show_corrected)]:
                    if enabled:
                        vector = data[key]
                        vector = np.where(vector > 0, vector, np.nan) if self.log_y else vector
                        implot.plot_line(label + " " + key.replace("_", " "), data[axis], vector)
            if self.model.fast is not None:
                for index, value in enumerate(self.model.region):
                    result = implot.drag_line_x(10 + index, value, col=(255, 200, 40, 255))
                    if result.modified and not self.job.running:
                        self.model.region[index] = round(result.value, 1)
                if self.model.background:
                    for index, value in enumerate(self.model.background_region):
                        result = implot.drag_line_x(20 + index, value, col=(100, 180, 255, 255))
                        if result.modified and not self.job.running:
                            self.model.background_region[index] = round(result.value, 1)
            self.plot_info = {
                "pos": implot.get_plot_pos(), "size": implot.get_plot_size(),
                "tail": [implot.plot_to_pixels(float(v), 100.0) for v in self.model.region],
                "background": [implot.plot_to_pixels(float(v), 100.0) for v in self.model.background_region],
            }
            implot.end_plot()

    def draw_anisotropy(self, box):
        if self.model.fast is None and self.model.slow is None:
            im.text_wrapped("The anisotropy r(t) of the loaded decays appears here.")
            return
        if implot.begin_plot("##anisotropy", (-1, -1)):
            implot.setup_axes("TAC bin", "Anisotropy r(t)")
            implot.setup_legend(implot.LOCATION_NORTH_EAST)
            implot.setup_axes_limits(0, max(len(self.model.fast[0]) if self.model.fast else 0,
                                            len(self.model.slow[0]) if self.model.slow else 0),
                                     -0.2, 0.6, cond=implot.COND_ONCE)
            for label, data in self.series():
                if not data:
                    continue
                if self.show_raw:
                    implot.plot_line(label + " raw", data["time"], data["r_raw"])
                if self.show_corrected:
                    implot.plot_line(label + " corrected", data["time"], data["r_corrected"])
            implot.end_plot()

    # -- frame ------------------------------------------------------------------------------- #
    def render(self):
        self.job.poll()
        follow = getattr(self, "_follow", None)
        if follow and not self.job.running:
            follow.pop(0)()
        vp = im.get_main_viewport()
        frame = (0.0, 0.0, *vp.size)
        self.item_rects.clear()
        for form in self.forms.values():
            form.rects.clear()
        im.begin_disabled(self.dialog is not None)
        self.docks.draw(frame)
        im.end_disabled()
        if self.dialog is not None:
            pressed = self.dialog_window.begin(frame)
            result = self.dialog.draw()
            if result:
                callback, self.dialog = self.dialog_callback, None
                callback(result)
            elif result is False or pressed == "close":
                self.dialog = None
            self.dialog_window.end()
        self.help.draw(frame)
        self.guide.draw(*vp.size)
        signature = self.fingerprint()
        if signature != self.settings_signature and not self.job.running:
            self.settings_signature = signature
            if self.model.fast is not None:
                self.calculate()

    # -- settings ---------------------------------------------------------------------------- #
    def export_settings(self):
        return {**self.model.export_settings(), "last_dir": self.last_dir,
                "display": {key: getattr(self, key) for key in DISPLAY}}

    def restore_settings(self, state):
        self.model.restore_settings(state)
        self.last_dir = str(state.get("last_dir", ""))
        for name, value in (state.get("display") or {}).items():
            if name in DISPLAY:
                setattr(self, name, bool(value))
        paths = [(self.model.fast_file, False), (self.model.slow_file, True)]
        settings = self.model.export_settings()

        def operation(model):
            for path, slow in paths:
                if path and Path(path).is_file():
                    model.load(path, slow=slow)
            model.restore_settings(settings)
            if model.fast is not None:
                model.compute(self.client)

        self.run(operation)

    def close(self):
        self.job.close()


def create_app(client=None):
    return GFactorApp(client=client)


make_app = create_app
