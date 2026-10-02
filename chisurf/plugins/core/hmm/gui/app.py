"""Native hidden-Markov-model tool (emtk): forms and tables from ``hmm_emtk.view.json``, implot plots, fits in a snapshot job."""

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
from chisurf.emtk.jobs import SnapshotJob
from chisurf.plugins.emtk_layout import LabelColumn, button_row, labelled, layout_spec

from .strings import install_translations, tr
from .view_model import HmmViewModel

install_translations()
HERE = Path(__file__).parent


def hex_colour(text, alpha=255):
    text = str(text).lstrip("#")
    return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16), alpha)


class HmmApp(ImApp):
    def __init__(self, model=None):
        self.model = model or HmmViewModel()
        self.job = SnapshotJob(self.model)
        panels = json.loads((HERE / "hmm_emtk.view.json").read_text())["panels"]
        self.panels = {n: layout_spec(copy.deepcopy(p)) for n, p in panels.items()}
        self.forms = {n: FormState() for n in panels}
        self.columns = {n: LabelColumn() for n in panels}
        self.item_rects = {}
        self.plot_info = {}
        self.dialog = None
        self.dialog_window = None
        self.dialog_action = ""
        self.last_dir = ""
        self.message = ""
        self.help_window = EmTkHelpWindow(
            title=tr("Hidden Markov model") + ": Help", resource=HERE / "help.md", owner=self
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            get_target_rect=lambda key: self.item_rects.get(key)
            or next((f.rects[key] for f in self.forms.values() if key in f.rects), None),
            owner=self,
            wait_for_controls=True,
        )
        for form in self.forms.values():
            form.on_used = self.tour.notify_used
        self.docks = DockManager(
            Split("h", 0.28, Region("controls"),
                  Split("v", 0.46, Region("trace"), Split("h", 0.55, Region("states"), Region("analysis")))),
            name="hmm",
        )
        self.docks.add_window("controls", tr("Model"), self.controls, dock="controls", closable=False)
        self.docks.add_window("trace", tr("Trace"), self.trace_plot, dock="trace", closable=False)
        self.docks.add_window("states", tr("Fitted states"), self.states_window, dock="states", closable=False)
        self.docks.add_window("histogram", tr("Histogram"), self.histogram_plot, dock="analysis", closable=False)
        self.docks.add_window("dwell", "Dwell times", self.dwell_plot, dock="analysis", closable=False)
        self.docks.add_window("scan", "Scan", self.scan_plot, dock="analysis", closable=False)
        super().__init__(self.render, continuous=False)

    # -- plumbing ---------------------------------------------------------------------------- #
    def form(self, name):
        spec, column = self.panels[name], self.columns[name]
        if not column.ready:
            column.measure([f["label"] for f in labelled(spec["sections"])])
        column.pad(spec["sections"])
        draw_form(spec, self.model, self.forms[name])

    def remember(self, name):
        self.item_rects[name] = im.get_item_rect()

    def choose(self, action):
        self.dialog_action = action
        title = {"add": "Add trace files", "save": "Save the fit as JSON"}[action]
        self.dialog = FileDialog(
            title, mode="save" if action == "save" else "open", multiselect=action == "add", directory=self.last_dir or None,
            filename="hmm_fit.json" if action == "save" else "",
            filters="Traces (*.csv *.txt *.dat *.npy);;All files (*)" if action == "add" else "JSON (*.json);;All files (*)",
        )
        self.dialog_window = DialogWindow(title, size=(760, 540))

    def start(self, method):
        if self.job.busy:
            return False
        if not (self.model._traces or self.model.files):
            self.model._status = "No traces loaded."
            return False
        ok = self.job.start(method)
        self.tour.notify_used({"run": "request_run", "run_scan": "request_scan"}[method])
        return ok

    def add_files(self, paths):
        paths = [str(p) for p in paths]
        if paths:
            self.last_dir = str(Path(paths[0]).parent)
            self.model.add_files(paths)
            self.model._status = f"{len(self.model.files)} trace file(s) selected: press Fit."
            self.tour.notify_used("add_files")

    def files_dropped(self, paths):
        """Host drop: every dropped file joins the trace list."""
        paths = [str(p) for p in paths]
        if not paths:
            return False
        self.add_files(paths)
        return True

    on_files_dropped = files_dropped

    def set_traces(self, traces, labels=None):
        """The seam other tools use: analyse traces handed over in memory."""
        self.model.set_traces(traces, labels)

    # -- windows ----------------------------------------------------------------------------- #
    def controls(self, box):
        m = self.model
        m.busy = self.job.busy
        idle = not self.job.busy and self.dialog is None
        has_data = bool(m._traces or m.files)
        pressed = button_row(
            [
                {"label": "Fit", "key": "request_run", "enabled": idle and has_data,
                 "tip": "Fit the model with the chosen number of states and decode the state path."},
                {"label": "Scan states", "key": "request_scan", "enabled": idle and has_data,
                 "tip": "Fit every state count in the range and score each by AIC and BIC."},
                {"label": "Demo trace", "key": "demo", "enabled": idle,
                 "tip": "Replace the traces by a generated three-state trace with known means and dwell times (a demo, not data)."},
                {"label": "Save fit...", "key": "save", "enabled": idle and m.fit is not None,
                 "tip": "Write the last fit (states, transitions, dwell times) as JSON."},
                {"label": "Help", "key": "help", "tip": "Explain the model, the state scan and what refutes a fit."},
                {"label": "Guide", "key": "guide", "tip": "Walk through loading, the state count and the checks of a fit."},
            ],
            remember=self.remember,
        )
        if pressed == "request_run":
            self.start("run")
        elif pressed == "request_scan":
            self.start("run_scan")
        elif pressed == "demo":
            m.load_demo()
            self.tour.notify_used("demo")
            self.tour.notify_used("add_files")
        elif pressed == "save":
            self.choose("save")
        elif pressed == "help":
            self.help_window.show()
        elif pressed == "guide":
            self.tour.start()
        im.text_wrapped(self.job.progress if self.job.busy else (self.job.error and "Error: " + self.job.error) or m.status)
        if self.message:
            im.text_wrapped(self.message)
        im.separator()
        im.text("Traces")
        self.form("files")
        pressed = button_row(
            [
                {"label": "Add files...", "key": "add_files", "enabled": idle,
                 "tip": "Choose binned trace files (several are fitted jointly as separate sequences); dropping files on the window does the same."},
                {"label": "Remove", "key": "remove", "enabled": idle and bool(m.files),
                 "tip": "Remove the selected file (the last one when none is selected)."},
                {"label": "Clear", "key": "clear", "enabled": idle and bool(m.files),
                 "tip": "Remove every trace file."},
            ],
            remember=self.remember,
        )
        if pressed == "add_files":
            self.choose("add")
        elif pressed == "remove":
            m.remove_file()
        elif pressed == "clear":
            m.clear_files()
        if m._traces:
            im.text_disabled(f"{len(m._traces)} trace(s) loaded, {sum(len(t) for t in m._traces)} bins.")
        self.form("model")
        opened = im.collapsing_header("Fitting")
        im.set_item_tooltip("Baum-Welch settings: iterations, tolerance, decoder, seed, acceleration.")
        if opened:
            self.form("fitting")
        opened = im.collapsing_header("State scan range")
        im.set_item_tooltip("The range of state counts the scan scores.")
        if opened:
            self.form("scan")

    def plot(self, name, series, x_label, y_label, log_y=False, empty="Fit the model to see this plot."):
        if not series:
            im.text_wrapped(empty)
            return
        if implot.begin_plot("##" + name, size=(-1.0, -1.0)):
            implot.setup_axes(x_label, y_label)
            implot.setup_legend(implot.LOCATION_NORTH_EAST)
            if log_y:
                implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
            for item in series:
                x, y = np.asarray(item["x"], float), np.asarray(item["y"], float)
                if log_y:
                    y = np.where(y > 0, y, np.nan)
                implot.set_next_line_style(hex_colour(item.get("color", "#888888")), float(item.get("width", 1)))
                implot.plot_line(str(item["name"]), x, y)
                if item.get("symbol"):
                    implot.plot_scatter(str(item["name"]) + "##pts", x, y)
            self.plot_info[name] = {"pos": implot.get_plot_pos(), "size": implot.get_plot_size()}
            implot.end_plot()

    def trace_plot(self, box):
        self.plot("trace", self.model.trace_series(), "time" if self.model.settings.time_step != 1.0 else "bin",
                  "counts per bin", empty="Load a trace (Add files... or Demo trace).")

    def histogram_plot(self, box):
        self.plot("histogram", self.model.histogram_series(), "counts per bin", "occurrences",
                  empty="Load a trace to see the intensity histogram.")

    def dwell_plot(self, box):
        self.plot("dwell", self.model.dwell_series(), "dwell time", "occurrences", log_y=True,
                  empty="Fit the model to see the dwell-time histograms.")

    def scan_plot(self, box):
        self.plot("scan", self.model.scan_series(), "states", "information criterion",
                  empty="Press Scan states to score a range of state counts.")

    def states_window(self, box):
        if self.model.fit is None:
            im.text_wrapped("No fit yet: press Fit.")
            return
        self.form("states")
        im.text("Transitions")
        self.form("transitions")

    # -- frame --------------------------------------------------------------------------------- #
    def animating(self):
        return self.job.busy or super().animating()

    def render(self):
        if self.job.poll():
            self.message = ""
        vp = im.get_main_viewport()
        frame = (0.0, 0.0, *vp.size)
        self.item_rects.clear()
        for form in self.forms.values():
            form.rects.clear()
        self.model.busy = self.job.busy
        im.begin_disabled(self.dialog is not None)
        self.docks.draw(frame)
        im.end_disabled()
        if self.dialog is not None:
            pressed = self.dialog_window.begin(frame)
            result = self.dialog.draw()
            if result:
                action, self.dialog = self.dialog_action, None
                if action == "add":
                    self.add_files(result)
                else:
                    try:
                        self.model.save_result(result[0])
                        self.last_dir = str(Path(result[0]).parent)
                        self.model._status = f"Saved the fit to {result[0]}."
                    except Exception as exc:  # noqa: BLE001
                        self.model._status = f"Error: {exc}"
            elif result is False or pressed == "close":
                self.dialog = None
            self.dialog_window.end()
        self.help_window.draw(frame)
        self.tour.draw(*vp.size)
        if self.job.busy:
            self.request_frame()

    # -- settings ------------------------------------------------------------------------------ #
    def export_settings(self):
        s = self.model.settings
        return {"files": list(self.model.files), "n_states": s.n_states, "covariance_type": s.covariance_type,
                "time_step": s.time_step, "n_iter": s.n_iter, "tol": s.tol, "accelerate": s.accelerate,
                "decode": s.decode, "random_state": s.random_state, "min_states": self.model.min_states,
                "max_states": self.model.max_states, "last_dir": self.last_dir}

    def restore_settings(self, settings):
        if not isinstance(settings, dict):
            return
        for key in ("n_states", "covariance_type", "time_step", "n_iter", "tol", "accelerate", "decode",
                    "random_state", "min_states", "max_states"):
            if key in settings:
                try:
                    setattr(self.model, key, settings[key])
                except (TypeError, ValueError):
                    pass
        files = [str(p) for p in settings.get("files", []) if Path(str(p)).is_file()]
        if files:
            self.model.sel_files = files
        self.last_dir = str(settings.get("last_dir", ""))

    def close(self):
        self.model._observers.clear()


def make_app():
    return HmmApp()
