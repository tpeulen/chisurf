"""The native intensity-trace tool: the Qt ``IntensityTrace`` widget as an emtk app.

Controls are ``intensity_trace.view.json`` drawn by :func:`emtk.view_form.draw_form` over :class:`_Form` (the
:class:`..model.IntensityTraceModel`'s fields, this app's actions); the detector list is a custom section. The trace and
histogram grid, and the result views (BIC elbow, dwell times with their fits, transition matrix, FRET per state) are
implot plots in dock windows. Binning and fitting run on a worker, the window stays live.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import numpy as np
from emtk import im, implot
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog
from emtk.view_form import FormState, draw_form

from chisurf.emtk.channel_definition import ChannelDefinitionWidget
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow

from ..model import IntensityTraceModel, dwell_histograms

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent
ROUTING = "Routing channels"
TTTR_FILTER = "TTTR files (*.ptu *.ht3 *.spc *.hdf *.h5 *.hdf5 *.pto);;All files (*)"
CSV_FILTER = "CSV files (*.csv);;All files (*)"
STATE_COLOURS = [(0, 114, 178, 255), (230, 159, 0, 255), (0, 158, 115, 255), (204, 121, 167, 255),
                 (86, 180, 233, 255), (213, 94, 0, 255), (240, 228, 66, 255), (120, 120, 120, 255)]
RESULTS = ("BIC Elbow", "Dwell Times", "HMM Matrix", "FRET Distributions")


def _setups() -> dict:
    from chisurf.core.data_io.detector_setups import load_detector_setups

    try:
        return load_detector_setups()
    except Exception:  # noqa: BLE001 - no setups file: routing channels only
        return {"setups": {}}


class _Form:
    """What the spec reads and writes: the model's fields, the app's settings and actions."""

    def __init__(self, app):
        object.__setattr__(self, "_app", app)

    def __getattr__(self, name):
        app = self._app
        if name in ("setup_name", "dwell_min", "dwell_max", "dwell_bins", "dwell_normalize"):
            return getattr(app, name)
        return getattr(app.model, name)

    def __setattr__(self, name, value):
        app = self._app
        if name in ("setup_name", "dwell_min", "dwell_max", "dwell_bins", "dwell_normalize"):
            setattr(app, name, value)
        else:
            setattr(app.model, name, value)

    def enabled(self, name):
        app, m = self._app, self._app.model
        if name in ("request_help", "request_guide", "request_load", "request_example"):
            return not app.busy
        if name in ("request_matrix", "request_dwell", "request_fret"):
            return m.states is not None and not (name == "request_fret" and m.fret is None)
        if name in ("request_save_dwell",):
            return m.states is not None
        return m.loaded and not app.busy

    def setup_names(self):
        names = [ROUTING, *sorted(self._app.setups.get("setups", {}))]
        if self._app.setup_name not in names:  # a setup from the editor that is not stored (yet)
            names.append(self._app.setup_name)
        return names

    def setup_chosen(self, _value=None):
        self._app.use_setup(self._app.setup_name)

    def window_changed(self, _value=None):
        self._app.rebin()

    def request_load(self):
        self._app.ask("Open TTTR File", "open", TTTR_FILTER, lambda p: self._app.open_file(p[0]))

    def request_example(self):
        from ..demo import demo_folder, make_demo

        self._app.model.window_ms = 2.0
        self._app.model.n_states = 2
        self._app.open_file(str(make_demo(demo_folder())))

    def request_edit_setup(self):
        self._app.docks.focus("setup")

    def request_save_traces(self):
        self._app.ask("Save Traces", "save", CSV_FILTER, lambda p: self._app.save_traces(p[0]), "traces.csv")

    def request_hmm(self):
        self._app.compute_hmm()

    def request_bic(self):
        self._app.compute_bic()

    def request_matrix(self):
        self._app.show_result("HMM Matrix")

    def request_dwell(self):
        self._app.show_result("Dwell Times")

    def request_fret(self):
        self._app.show_result("FRET Distributions")

    def request_save_dwell(self):
        self._app.ask("Save Dwell Time Histograms and Fits", "save", CSV_FILTER,
                      lambda p: self._app.save_dwell(p[0]), "dwell_times.csv")

    def request_help(self):
        self._app.help.show()

    def request_guide(self):
        self._app.tour.start()


class IntensityTraceApp(ImApp):
    def __init__(self, model: IntensityTraceModel | None = None):
        self.model = model or IntensityTraceModel()
        self.setups = _setups()
        self.setup_name = ROUTING
        last = self.setups.get("last_used") or ""
        if last in self.setups.get("setups", {}):
            self.use_setup(last, rebin=False)
        self.dwell_min, self.dwell_max, self.dwell_bins, self.dwell_normalize = 0.0, 1000.0, 31, False
        self.bics: list = []
        self.status = "Load a TTTR file."
        self.tab = "Processing"
        self.result = RESULTS[0]
        self.item_rects: dict = {}
        self._worker: threading.Thread | None = None
        self.dialog = None
        self.dialog_window = None
        self._on_pick = None
        self.spec = json.loads((HERE / "intensity_trace.view.json").read_text(encoding="utf-8"))["panels"]
        self.form_model = _Form(self)
        self.forms = {name: FormState(on_used=self._used) for name in self.spec}
        self.forms["processing"].custom["detectors"] = self._draw_detectors
        self.help = EmTkHelpWindow(title="Intensity trace — Help", resource=PLUGIN / "help.md", owner=self,
                                   on_start_guide=lambda: self.tour.start())
        self.tour = EmTkGuidedTour(steps=PLUGIN / "guide.json", owner=self, wait_for_controls=True,
                                   get_target_rect=self.item_rects.get)
        self.docks = DockManager(Split("v", 0.40, Region("controls"), Split("h", 0.66, Region("traces"),
                                                                              Region("results"))))
        self.docks.add_window("controls", "Controls", self._draw_controls, dock="controls", closable=False)
        self.docks.add_window("traces", "Traces", self._draw_traces, dock="traces", closable=False)
        self.docks.add_window("results", "Results", self._draw_results, dock="results", closable=False)
        # The Qt tool's Setup dialog: the shared detector-setup editor, a tab beside the results.
        self.editor = ChannelDefinitionWidget(on_changed=self.setup_edited)
        self.editor.on_used = self._used
        self.docks.add_window("setup", "Detector Setup", self._draw_setup, dock="results", closable=False)
        self.docks.focus("results")
        self.native_layouts = {"main": self.docks}
        super().__init__(gui=self.render, continuous=False)

    # ── state ─────────────────────────────────────────────────────────────

    @property
    def busy(self) -> bool:
        return self._worker is not None and self._worker.is_alive()

    def _used(self, name):
        self.tour.notify_used(name)

    def _run(self, work, label: str) -> None:
        """Run *work* on a worker; its returned text becomes the status."""
        if self.busy:
            return
        self.status = label

        def run():
            try:
                self.status = work() or self.model.message
            except Exception as exc:  # noqa: BLE001 - shown in the status line
                self.status = f"{type(exc).__name__}: {exc}"
            self.request_frame()

        self._worker = threading.Thread(target=run, daemon=True)
        self._worker.start()

    def wait(self, timeout: float = 300.0) -> None:
        if self._worker is not None:
            self._worker.join(timeout)

    def animating(self):
        return self.busy or getattr(self.editor, "_future", None) is not None or super().animating()

    def use_setup(self, name: str, rebin: bool = True) -> None:
        if name not in self.setups.get("setups", {}) and name != ROUTING and self.model.setup:
            self.setup_name = name  # the editor's setup, still in use
            return
        setup = self.setups.get("setups", {}).get(name) if name != ROUTING else None
        self.setup_name = name if setup is not None else ROUTING
        self.model.setup = setup
        self.model.selected = []
        if rebin:
            self.rebin()

    def setup_edited(self, settings: dict) -> None:
        """The editor changed the setup: bin with it (the Qt tool re-processed the file after its Setup dialog)."""
        if isinstance(settings, dict) and settings.get("detectors"):
            self.model.setup = settings
            self.model.selected = []
            name = str(getattr(self.editor, "setup_name", "") or "")
            self.setup_name = name if name and name != "Unsaved" else "Edited setup"
            self.rebin()

    def _draw_setup(self, box) -> None:
        self.editor.draw()
        self.item_rects["setup_editor"] = tuple(box)

    def open_file(self, path: str) -> None:
        self._run(lambda: self.model.load(path) and self.model.message, f"Reading {Path(path).name}...")

    def rebin(self) -> None:
        if self.model.path:
            self._run(lambda: self.model.reload() and self.model.message, "Binning...")

    def compute_hmm(self) -> None:
        def work():
            msg = self.model.run_hmm()
            base = self.model.export()
            return f"{msg}. Written to {base.name}/"

        self.tab = "HMM"
        self._run(work, f"Fitting a {self.model.n_states}-state HMM...")

    def compute_bic(self) -> None:
        def work():
            self.bics = self.model.bic_curve()
            best = min((b for b in self.bics if np.isfinite(b[1])), key=lambda b: b[1], default=None)
            return f"BIC of 1-{len(self.bics)} states" + (f"; lowest at {best[0]}" if best else "")

        self.show_result("BIC Elbow")
        self._run(work, "Fitting 1-15 state models...")

    def show_result(self, name: str) -> None:
        self.result = name
        self.docks.focus("results")
        self.request_frame()

    def save_traces(self, path: str) -> None:
        if not str(path).endswith(".csv"):
            path = f"{path}.csv"
        self.status = f"Saved {Path(self.model.save_traces(path)).name}"

    def save_dwell(self, path: str) -> None:
        if not str(path).endswith(".csv"):
            path = f"{path}.csv"
        hists = dwell_histograms(self.model.dwell_times(), self.dwell_min, self.dwell_max, self.dwell_bins,
                                 self.dwell_normalize)
        with open(path, "w") as f:
            f.write("State,BinCenter,Count\n")
            for state, (x, y, _fit) in hists.items():
                f.writelines(f"{state},{xc},{yc}\n" for xc, yc in zip(x, y))
            f.write("\nState,Parameter,Value\n")
            for state, (_x, _y, fit) in hists.items():
                if fit is not None:
                    f.write(f"{state},A,{fit[0]}\n{state},tau,{fit[1]}\n")
        self.status = f"Saved {Path(path).name}"

    def on_files_dropped(self, paths) -> bool:
        for p in paths:
            if Path(str(p)).is_file():
                self.open_file(str(p))
                return True
        return False

    def ask(self, title, mode, filters, on_pick, filename=""):
        self.dialog = FileDialog(title, mode=mode, filters=filters, filename=filename)
        self.dialog_window = DialogWindow(title, size=(720, 520))
        self._on_pick = on_pick

    # ── controls ──────────────────────────────────────────────────────────

    def _form(self, name: str) -> None:
        form = self.forms[name]
        form.rects.clear()
        draw_form({"sections": self.spec[name]["sections"]}, self.form_model, form)
        self.item_rects.update(form.rects)

    def _draw_detectors(self, section, model, state, width) -> None:
        im.text("Detector Selection")
        im.set_item_tooltip(section.get("description", ""))
        m = self.model
        names = m.choices()
        chosen = set(m.selected) if m.selected else set(names)
        changed_any = False
        for i, name in enumerate(names):
            if i:
                im.same_line()
            label = name.replace("routing_", "Ch") if name.startswith("routing_") else name
            changed, on = im.checkbox(f"{label}##det{i}", name in chosen)
            im.set_item_tooltip(f"Bin {label} as its own trace.")
            self.item_rects[f"det.{name}"] = im.get_item_rect()
            if changed:
                (chosen.add if on else chosen.discard)(name)
                changed_any = True
        if changed_any:
            m.selected = [n for n in names if n in chosen]
            self._used("detectors")
            self.rebin()

    def _draw_controls(self, box) -> None:
        self._form("file")
        for i, tab in enumerate(("Processing", "HMM")):
            if i:
                im.same_line()
            selected = tab == self.tab
            if selected:
                im.push_style_color(im.Col.BUTTON, im.get_style().color(im.Col.TAB_SELECTED))
            if im.button(tab):
                self.tab = tab
                self._used(f"tab_{tab}")
            if selected:
                im.pop_style_color(1)
            im.set_item_tooltip({"Processing": "Time window, detector selection and histogram settings.",
                                 "HMM": "Fit a hidden Markov model and show its results."}[tab])
            self.item_rects[f"tab_{tab}"] = im.get_item_rect()
        im.separator()
        self._form("processing" if self.tab == "Processing" else "hmm")
        im.text_wrapped(self.status)
        self.item_rects["status"] = im.get_item_rect()

    # ── plots ─────────────────────────────────────────────────────────────

    def _draw_traces(self, box) -> None:
        m = self.model
        if not m.loaded:
            im.text_wrapped("No trace: load a TTTR file (Load TTTR, or drop one here).")
            self.item_rects["traces"] = tuple(box)
            return
        rows = [(label, m.counts[:, i]) for i, label in enumerate(m.labels)] + [("Sum", m.total)]
        hists = dict(m.histograms())
        im.text_disabled(f"Counts per {m.window_ms:g} ms bin; right: how often each count occurs (log).")
        w, h = im.get_content_region_avail()
        extra = (m.states is not None) + (m.states is not None and m.fret is not None)
        h_rows = h * len(rows) / (len(rows) + 1.3 * extra) if extra else h
        plain = implot.FLAGS_NO_LEGEND | implot.FLAGS_NO_TITLE
        hidden_x = implot.AXIS_FLAGS_NO_TICK_LABELS | implot.AXIS_FLAGS_NO_LABEL
        flags = implot.SUBPLOT_FLAGS_LINK_COLS | implot.SUBPLOT_FLAGS_NO_TITLE
        # Linked columns do not fit themselves: the limits are set once per binned trace (a new trace refits, the
        # user's zoom on this one is kept).
        rev = id(m.counts)
        t_max = float(m.time_axis[-1]) if len(m.time_axis) else 1.0
        h_max = max((float(np.max(hist[1])) for hist in hists.values() if hist is not None), default=1.0)
        # the last row also carries the axis labels: give it that room
        ratios = [1.0] * (len(rows) - 1) + [1.8]
        if implot.begin_subplots(f"##traces{rev}", len(rows), 2, (w, h_rows), flags, row_ratios=ratios,
                                 col_ratios=[2.0, 1.0]):
            for k, (label, values) in enumerate(rows):
                last = k == len(rows) - 1
                if implot.begin_plot(f"{label}##trace", (-1, -1), plain):
                    implot.setup_axes("Time (s)", label, 0 if last else hidden_x)
                    implot.setup_axis_limits(implot.AXIS_X1, 0.0, t_max)
                    implot.plot_line(label, m.time_axis, values)
                    implot.end_plot()
                if implot.begin_plot(f"{label}##hist", (-1, -1), plain):
                    implot.setup_axes("Occurrences (log)", "", 0 if last else hidden_x)
                    implot.setup_axis_scale(implot.AXIS_X1, implot.SCALE_LOG10)
                    implot.setup_axis_limits(implot.AXIS_X1, 0.5, h_max * 2.0)
                    hist = hists.get(label)
                    if hist is not None:
                        implot.plot_line(f"{label} histogram", np.asarray(hist[1], float) + 0.5, hist[0])
                    implot.end_plot()
            implot.end_subplots()
        if extra:
            w, h = im.get_content_region_avail()
            if implot.begin_subplots("##states", extra, 2, (w, h), implot.SUBPLOT_FLAGS_NO_TITLE,
                                     row_ratios=[1.4] * (extra - 1) + [1.8], col_ratios=[2.0, 1.0]):
                if implot.begin_plot("Hidden States##states", (-1, -1), plain):
                    implot.setup_axes("Time (s)" if extra == 1 else "", "State", 0 if extra == 1 else hidden_x)
                    implot.plot_stairs("state", m.time_axis, np.asarray(m.states, float))
                    implot.end_plot()
                if implot.begin_plot("State Counts##statebars", (-1, -1), plain):
                    implot.setup_axes("State (sorted)", "Bins")
                    counts = np.bincount(m.states, minlength=int(m.n_states)).astype(float)
                    implot.plot_bars("bins per state", np.arange(len(counts), dtype=float), counts, bar_size=0.8)
                    implot.end_plot()
                if extra == 2:
                    if implot.begin_plot("FRET##fret", (-1, -1), plain):
                        implot.setup_axes("Time (s)", "FRET")
                        implot.plot_line("FRET", m.time_axis, m.fret)
                        implot.end_plot()
                    self._fret_hist_plot("FRET Hist per State##frethist")
                implot.end_subplots()
        im.set_item_tooltip("Each detector's trace with its count histogram, the sum, and after Compute HMM the "
                            "hidden states and FRET efficiency.")
        self.item_rects["traces"] = tuple(box)

    def _fret_hist_plot(self, title: str, size=(-1, -1)) -> None:
        if implot.begin_plot(title, size):
            implot.setup_axes("FRET Efficiency", "Density")
            edges = np.linspace(0.0, 1.0, 51)
            for state, values in self.model.fret_by_state().items():
                if len(values):
                    h, _ = np.histogram(values, bins=edges, density=True)
                    implot.set_next_line_style(STATE_COLOURS[state % len(STATE_COLOURS)], 1.5)
                    implot.plot_stairs(f"State {state}", edges[:-1], h)
            implot.end_plot()

    def _draw_results(self, box) -> None:
        m = self.model
        for i, name in enumerate(RESULTS):
            if i:
                im.same_line()
            selected = name == self.result
            if selected:
                im.push_style_color(im.Col.BUTTON, im.get_style().color(im.Col.TAB_SELECTED))
            if im.button(f"{name}##result_{i}"):
                self.result = name
            if selected:
                im.pop_style_color(1)
            im.set_item_tooltip({"BIC Elbow": "BIC of models with 1 to 15 states.",
                                 "Dwell Times": "Dwell-time histograms per state with exponential fits.",
                                 "HMM Matrix": "Transition probabilities between the states, per bin.",
                                 "FRET Distributions": "FRET efficiency of the bins in each state."}[name])
            self.item_rects[f"result.{name}"] = im.get_item_rect()
        im.separator()
        if self.result == "BIC Elbow":
            if not self.bics:
                im.text_wrapped("Press BIC Elbow (HMM tab) to fit models of 1 to 15 states.")
            elif implot.begin_plot("BIC vs Number of States##bic", (-1, -1), implot.FLAGS_NO_LEGEND):
                implot.setup_axes("Number of States", "BIC (lower is better)")
                pts = [(s, b) for s, b in self.bics if np.isfinite(b)]
                if pts:
                    xs, ys = (np.asarray(v, float) for v in zip(*pts))
                    implot.set_next_marker_style(implot.MARKER_CIRCLE, 4.0)
                    implot.plot_line("BIC", xs, ys)
                implot.end_plot()
        elif m.states is None:
            im.text_wrapped("Compute the HMM (HMM tab) to see its results here.")
        elif self.result == "Dwell Times":
            self._form("dwell")
            hists = dwell_histograms(m.dwell_times(), self.dwell_min, self.dwell_max, self.dwell_bins,
                                     self.dwell_normalize)
            if implot.begin_plot("Dwell Time Distributions##dwell", (-1, -1)):
                implot.setup_axes("Dwell Time (ms)", "Fraction" if self.dwell_normalize else "Count")
                for state, (x, y, fit) in hists.items():
                    colour = STATE_COLOURS[state % len(STATE_COLOURS)]
                    implot.set_next_line_style(colour, 1.5)
                    label = f"State {state}" + (f"  τ = {fit[1]:.1f} ms" if fit else "")
                    implot.plot_stairs(label, x, y)
                    if fit:
                        xf = np.linspace(self.dwell_min, self.dwell_max, 200)
                        implot.set_next_line_style(colour, 2.5)
                        implot.plot_line(f"##fit{state}", xf, fit[0] * np.exp(-xf / fit[1]))
                implot.end_plot()
        elif self.result == "HMM Matrix":
            t = np.asarray(m.transmat, float)
            k = t.shape[0]
            if implot.begin_plot("Transition Matrix##matrix", (-1, -1), implot.FLAGS_NO_LEGEND):
                implot.setup_axes("From State", "To State")
                # row r of the heatmap is drawn at the top: to-state k-1 first, so P(i -> j) sits at (i, j)
                implot.plot_heatmap("P", t.T[::-1].ravel(), k, k, 0.0, float(t.max()), "%.3f",
                                    (-0.5, -0.5), (k - 0.5, k - 0.5))
                implot.end_plot()
        elif self.result == "FRET Distributions":
            if m.fret is None:
                im.text_wrapped("FRET needs two detectors (first detector over the sum).")
            else:
                self._fret_hist_plot("FRET Efficiency Distributions by State##fretdist")
        self.item_rects["results"] = tuple(box)

    def render(self):
        vp = im.get_main_viewport()
        frame = (0.0, 0.0, *vp.size)
        self.editor.poll()
        im.begin_disabled(self.dialog is not None)
        self.docks.draw(frame)
        im.end_disabled()
        if self.dialog is not None:
            pressed = self.dialog_window.begin(frame)
            result = self.dialog.draw()
            self.dialog_window.end()
            if result:
                self.dialog, pick = None, self._on_pick
                pick([str(p) for p in result])
            elif result is False or pressed == "close":
                self.dialog = None
        self.editor.draw_dialogs(frame)
        self.help.draw(frame)
        self.tour.draw(*vp.size)

    def export_settings(self) -> dict:
        m = self.model
        return {"path": m.path, "window_ms": m.window_ms, "n_bins": m.n_bins, "hist_min": m.hist_min,
                "hist_max": m.hist_max, "n_states": m.n_states, "setup": self.setup_name, "selected": m.selected}

    def restore_settings(self, state: dict) -> None:
        m = self.model
        for key in ("window_ms", "n_bins", "hist_min", "hist_max", "n_states"):
            if key in state:
                setattr(m, key, type(getattr(m, key))(state[key]))
        if state.get("setup"):
            self.use_setup(state["setup"], rebin=False)
        m.selected = list(state.get("selected") or [])
        if state.get("path") and Path(state["path"]).is_file():
            self.open_file(state["path"])

    def close(self) -> None:
        self.wait(1.0)
        self.editor.close()


def make_app(**_kwargs) -> IntensityTraceApp:
    from chisurf.emtk.i18n import install

    install()
    return IntensityTraceApp()


__all__ = ["IntensityTraceApp", "make_app"]
