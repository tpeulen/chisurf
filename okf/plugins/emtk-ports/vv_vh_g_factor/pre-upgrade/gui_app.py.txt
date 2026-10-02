"""Native VV/VH calibration, slow-protein mixing and anisotropy batch analysis."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from emtk import im, implot
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.plugins.tttr.tttr_splitter.gui.jobs import BackgroundJob

from .client import VvVhGFactorClient
from .model import GFactorModel


class GFactorApp(ImApp):
    def __init__(self, client=None):
        self.model = GFactorModel()
        self.client = client or VvVhGFactorClient()
        self.help = EmTkHelpWindow(
            title="Scientific workflow help", resource=Path(__file__).with_name("help.md")
        )
        self.guide = EmTkGuidedTour(steps=Path(__file__).with_name("guide.json"))
        self.job = BackgroundJob()
        self.dialog = None
        self.dialog_callback = None
        self.show_fast = self.show_slow = self.show_raw = self.show_corrected = True
        self.log_y = True
        self.plot_signature = None
        self.settings_signature = self.fingerprint()
        self.docks = DockManager(
            Split(
                "h",
                0.35,
                Region("controls"),
                Split("v", 0.6, Region("decays"), Region("anisotropy")),
            )
        )
        self.docks.add_window(
            "controls", "G-factor and mixing", self.draw_controls, dock="controls"
        )
        self.docks.add_window("batch", "Batch anisotropy", self.draw_batch, dock="controls")
        self.docks.add_window("decays", "VV/VH decays", self.draw_decays, dock="decays")
        self.docks.add_window(
            "anisotropy", "Anisotropy r(t)", self.draw_anisotropy, dock="anisotropy"
        )
        super().__init__(gui=self.render, continuous=True)

    def fingerprint(self):
        settings = self.model.export_settings()
        settings.pop("batch_files", None)
        return json.dumps(settings, sort_keys=True)

    def button(self, label, tip, callback):
        if im.button(label):
            callback()
        im.set_item_tooltip(tip)

    def numeric(self, label, value, tip, integer=False):
        im.text(label + ":")
        im.set_next_item_width(-1)
        changed, value = (
            im.input_int("##" + label, int(value), step=0)
            if integer
            else im.input_float("##" + label, float(value), step=0)
        )
        im.set_item_tooltip(tip)
        return changed, value

    def check(self, label, value, tip):
        changed, value = im.checkbox(label, value)
        im.set_item_tooltip(tip)
        return changed, value

    def choose(self, title, callback, mode="open", multiple=False):
        if self.job.running:
            return
        self.dialog = FileDialog(
            title,
            mode=mode,
            multiselect=multiple,
            filters="VV/VH decay (*.dat *.txt);;All files (*)"
            if mode != "save"
            else "Results (*.json *.tsv *.txt)",
        )
        self.dialog_callback = callback

    def run(self, operation, on_complete=None):
        if self.job.running:
            return False
        model = self.model.snapshot()

        def work():
            operation(model)
            return model

        def publish(model):
            self.model = model
            self.plot_signature = None
            self.settings_signature = self.fingerprint()
            if on_complete:
                on_complete()

        return self.job.start(work, publish, lambda exc: setattr(self.model, "message", str(exc)))

    def load(self, path, slow=False):
        def operation(model):
            model.load(path, slow=slow)
            if model.fast is not None:
                model.compute(self.client)

        return self.run(operation)

    def calculate(self):
        return self.run(lambda model: model.compute(self.client))

    def archive(self):
        if self.job.running:
            return False
        if not self.model.fast_file:
            self.model.message = "Load a reference decay before archival."
            return False
        source = self.model.fast_file
        parameters = self.model.archive_parameters()

        def work():
            result = self.client.archive_g_factor(source, parameters)
            if not result.get("ok", True) or not result.get("calibration_id"):
                raise ValueError(
                    result.get("error") or "Calibration archival did not return an identifier."
                )
            return result

        return self.job.start(
            work,
            lambda result: setattr(
                self.model, "message", f"Archived calibration {result['calibration_id']}"
            ),
            lambda exc: setattr(self.model, "message", str(exc)),
        )

    def draw_controls(self, box):
        model = self.model
        im.text_wrapped(model.message)
        if self.job.running:
            self.button(
                "Stop",
                "Discard pending calibration results; an archival operation already running may finish.",
                self.job.stop,
            )
        im.begin_disabled(self.job.running or self.dialog is not None)
        self.button(
            "Fast reference VV/VH…",
            "Load the fast-rotating reference dye used for tail-matching G calibration.",
            lambda: self.choose("Fast reference", lambda paths: self.load(paths[0])),
        )
        im.text_wrapped(model.fast_file or "No reference decay loaded.")
        self.button(
            "Slow protein VV/VH…",
            "Load the slow-rotating protein reference for linked polarization-mixing estimates.",
            lambda: self.choose(
                "Slow protein reference", lambda paths: self.load(paths[0], slow=True)
            ),
        )
        im.text_wrapped(model.slow_file or "No slow reference loaded.")
        _, model.flip = self.check(
            "Flip VV/VH",
            model.flip,
            "Swap parallel and perpendicular detection labels consistently across calculation and plots.",
        )
        _, model.background = self.check(
            "Background correction",
            model.background,
            "Subtract separate channel means from the selected background region.",
        )
        for index, label in enumerate(("Tail region start", "Tail region stop")):
            _, model.region[index] = self.numeric(
                label, model.region[index], "Bin range used to match reference dye tails."
            )
        for index, label in enumerate(("Background start", "Background stop")):
            _, model.background_region[index] = self.numeric(
                label,
                model.background_region[index],
                "Bin range used to estimate each channel background.",
            )
        _, model.shift = self.numeric(
            "VH interpolation shift",
            model.shift,
            "Shift the VH time axis by this many TAC bins, including fractional bins.",
        )
        _, model.manual_g = self.check(
            "Manual G override",
            model.manual_g,
            "Use an explicitly entered G-factor instead of the current calculated value.",
        )
        if model.manual_g:
            _, model.g_override = self.numeric(
                "Manual G",
                model.g_override,
                "Positive detector sensitivity ratio used for corrected anisotropy.",
            )
        for label, key in [
            ("G raw", "g_factor_uncorrected"),
            ("G raw SD", "g_factor_stddev_uncorrected"),
            ("G corrected", "g_factor_corrected"),
            ("G corrected SD", "g_factor_stddev_corrected"),
            ("Background VV", "bg_parallel_avg"),
            ("Background VH", "bg_perpendicular_avg"),
        ]:
            value = model.result.get(key)
            im.text(
                f"{label}: {float(value):.6g}" if value is not None else f"{label}: unavailable"
            )
        self.button(
            "Calculate G",
            "Recompute tail matching and FP mixing with the current settings.",
            self.calculate,
        )
        im.separator()
        im.text("Slow-reference mixing estimate")
        for attr, label, tip in [
            ("fp_dt_ns", "FP time step ns", "Nanoseconds per slow-reference bin."),
            (
                "fp_rho_ns",
                "Rotational correlation ns",
                "Rotational time used in the Perrin relation.",
            ),
            (
                "fp_r0",
                "Fundamental anisotropy r0",
                "Limiting anisotropy of the reference fluorophore.",
            ),
        ]:
            _, value = self.numeric(label, getattr(model, attr), tip)
            setattr(model, attr, value)
        for enabled, attr, label, tip in [
            (
                "manual_tau",
                "tau_override",
                "Manual lifetime ns",
                "Override the intensity first-moment lifetime.",
            ),
            (
                "manual_rs",
                "rs_override",
                "Manual steady anisotropy",
                "Override the Perrin steady-state anisotropy target.",
            ),
            (
                "manual_l",
                "l_override",
                "Manual linked l1=l2",
                "Override the single linked polarization-mixing parameter.",
            ),
        ]:
            _, flag = self.check(label + " override", getattr(model, enabled), tip)
            setattr(model, enabled, flag)
            if flag:
                _, value = self.numeric(label, getattr(model, attr), tip)
                setattr(model, attr, value)
        if model.fp_result:
            for key in ("tau_estimate_ns", "tau_used_ns", "r_expected", "l1", "l2"):
                im.text(f"{key}: {model.fp_result.get(key)}")
            im.text_wrapped(model.fp_result["warning"])
        self.button(
            "Export calibration JSON…",
            "Export values, uncertainty, mixing diagnostics and scientific settings.",
            lambda: self.choose(
                "Calibration results",
                lambda paths: self.run(lambda model: model.save_results(paths[0])),
                mode="save",
            ),
        )
        self.button(
            "Archive reference calibration",
            "Register raw reference decay, corrected traces, anisotropy and calibration provenance through the existing MMFDB RPC.",
            self.archive,
        )
        im.end_disabled()
        self.button(
            "Help", "Read calibration conventions and the linked-mixing limits.", self.help.show
        )
        self.button(
            "Guide",
            "Walk through fast/slow references, tail matching and export.",
            self.guide.start,
        )

    def draw_batch(self, box):
        im.begin_disabled(self.job.running or self.dialog is not None)
        self.button(
            "Add VV/VH batch files…",
            "Queue decays to evaluate r∞ using a frozen current G/mixing/background/shift configuration.",
            lambda: self.choose("Batch VV/VH decays", self.add_batch, multiple=True),
        )
        self.button(
            "Clear batch", "Remove batch inputs and computed rows.", lambda: self.clear_batch()
        )
        for index, path in enumerate(list(self.model.batch_files)):
            im.selectable(f"{Path(path).name}##batch{index}")
            im.set_item_tooltip(path + " — right-click to remove.")
            if im.begin_popup_context_item(f"batchmenu{index}"):
                if im.menu_item("Remove batch input"):
                    self.model.batch_files.remove(path)
                im.set_item_tooltip("Remove only this queued input; retain its source.")
                im.end_popup()
        self.button(
            "Run batch",
            "Compute corrected steady anisotropy per queued file using the current calibration snapshot.",
            lambda: self.run(lambda model: model.compute_batch(self.job.cancelled.is_set)),
        )
        self.button(
            "Save batch table…",
            "Write per-file steady anisotropy, region, backgrounds, G and errors as TSV.",
            lambda: self.choose(
                "Batch anisotropy table",
                lambda paths: self.run(lambda model: model.export_batch(paths[0])),
                mode="save",
            ),
        )
        for row in self.model.batch_results:
            im.text_wrapped(
                f"{Path(row['file']).name}: r∞={row.get('r_inf')} {row.get('error', '')}"
            )
        im.end_disabled()

    def add_batch(self, paths):
        for path in paths:
            if str(path) not in self.model.batch_files:
                self.model.batch_files.append(str(path))

    def clear_batch(self):
        self.model.batch_files = []
        self.model.batch_results = []

    def series(self):
        return [
            (label, self.model.decay_series(slow))
            for label, slow, enabled in [
                ("Fast", False, self.show_fast),
                ("Slow", True, self.show_slow),
            ]
            if enabled
        ]

    def draw_decays(self, box):
        for attr, label in [
            ("show_fast", "Fast reference"),
            ("show_slow", "Slow reference"),
            ("show_raw", "Raw"),
            ("show_corrected", "Corrected"),
            ("log_y", "Log counts"),
        ]:
            _, value = self.check(
                label,
                getattr(self, attr),
                "Show/hide this diagnostic trace or change the decay intensity scale.",
            )
            setattr(self, attr, value)
            im.same_line()
        im.new_line()
        if implot.begin_plot("##vvvh", (-1, -1)):
            implot.setup_axes("TAC bin", "Counts")
            if self.log_y:
                implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
            series = self.series()
            vectors = [
                v[key]
                for _, v in series
                if v
                for key in ("vv_raw", "vh_raw", "vv_corrected", "vh_corrected")
            ]
            vectors = [vector for vector in vectors if np.any(np.isfinite(vector))]
            if vectors:
                peak = max(float(np.nanmax(v)) for v in vectors)
                length = max(map(len, vectors))
                sig = (id(self.model.fast), id(self.model.slow), self.log_y, peak, self.model.shift)
                implot.setup_axes_limits(
                    0,
                    length,
                    1 if self.log_y else 0,
                    max(2, peak * 1.1),
                    cond=implot.COND_ALWAYS if sig != self.plot_signature else implot.COND_ONCE,
                )
                self.plot_signature = sig
            for label, data in series:
                if not data:
                    continue
                for key, axis, enabled in [
                    ("vv_raw", "time", self.show_raw),
                    ("vh_raw", "shifted_time", self.show_raw),
                    ("vv_corrected", "time", self.show_corrected),
                    ("vh_corrected", "shifted_time", self.show_corrected),
                ]:
                    if enabled:
                        vector = data[key]
                        vector = np.where(vector > 0, vector, np.nan) if self.log_y else vector
                        implot.plot_line(label + " " + key.replace("_", " "), data[axis], vector)
            if self.model.fast is not None:
                changed = []
                for index, value in enumerate(self.model.region):
                    result = implot.drag_line_x(10 + index, value, col=(255, 200, 40, 255))
                    changed.append(result)
                    if result.modified and not self.job.running:
                        self.model.region[index] = result.value
                if self.model.background:
                    for index, value in enumerate(self.model.background_region):
                        result = implot.drag_line_x(20 + index, value, col=(100, 180, 255, 255))
                        if result.modified and not self.job.running:
                            self.model.background_region[index] = result.value
            implot.end_plot()
        im.set_item_tooltip(
            "Drag yellow tail boundaries and blue background boundaries to change calibration ranges."
        )

    def draw_anisotropy(self, box):
        if implot.begin_plot("##anisotropy", (-1, -1)):
            implot.setup_axes("TAC bin", "Anisotropy r(t)")
            for label, data in self.series():
                if not data:
                    continue
                if self.show_raw:
                    implot.plot_line(label + " raw", data["time"], data["r_raw"])
                if self.show_corrected:
                    implot.plot_line(label + " corrected", data["time"], data["r_corrected"])
            implot.end_plot()

    def render(self):
        self.job.poll()
        vp = im.get_main_viewport()
        frame = (0.0, 0.0, *vp.size)
        self.docks.draw(frame)
        if self.help.open:
            self.help.draw(frame)
        if self.guide.active:
            self.guide.draw(*vp.size)
        if self.dialog:
            if im.begin("VV/VH file chooser"):
                result = self.dialog.draw()
                if result:
                    callback = self.dialog_callback
                    self.dialog = None
                    callback(result)
                elif result is False:
                    self.dialog = None
            im.end()
        signature = self.fingerprint()
        if signature != self.settings_signature and not self.job.running:
            self.settings_signature = signature
            if self.model.fast is not None:
                self.calculate()

    def on_paths_dropped(self, paths):
        if paths:
            self.load(paths[0])

    def export_settings(self):
        return {
            **self.model.export_settings(),
            "display": {
                key: getattr(self, key)
                for key in ("show_fast", "show_slow", "show_raw", "show_corrected", "log_y")
            },
        }

    def restore_settings(self, state):
        self.model.restore_settings(state)
        for name, value in state.get("display", {}).items():
            if name in ("show_fast", "show_slow", "show_raw", "show_corrected", "log_y"):
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
