"""The emtk H2MM app over :class:`H2mmViewModel`: no Qt tool behind it (cards H0-H5).

Settings are the AutoForm spec ``h2mm.view.json`` (typed, clamped, a description on every field); Run and Stop work
on a snapshot of the model through :class:`chisurf.emtk.jobs.SnapshotJob`; the rate and state tables are the spec's
own ``table`` sections; the transition-density and dwell-time plots draw only what the analysis holds
(:mod:`.result_view`). With no fit every result window says so.
"""

from __future__ import annotations

import copy
from pathlib import Path

from emtk import im
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.im_core import get_current_context
from emtk.view_form import FormState, draw_sections
from emtk.widgets.view_spec import load_view_spec

from chisurf.emtk.channel_definition import ChannelDefinitionWidget
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget
from chisurf.emtk.jobs import SnapshotJob
from chisurf.plugins.emtk_layout import (
    LabelColumn,
    button_row,
    cap_widths,
    group_by_width,
    labelled,
)

from .model import H2mmViewModel
from .plots import ResultPlots

HERE = Path(__file__).parent


class H2mmNativeApp(TourTarget, ImApp):
    """Immediate-mode H2MM app: settings form, detector editor, actions through ``SnapshotJob``, tables and plots."""

    #: Dialog actions: (title, mode, filters).
    DIALOGS = {
        "folder": ("Select burst (.bur) folder", "folder", None),
        "save_settings": ("Save H2MM settings", "save", [("JSON", ["*.json"])]),
        "load_settings": ("Load H2MM settings", "open", [("JSON", ["*.json"])]),
        "export_dwells": ("Export dwell table", "save", [("CSV", ["*.csv"])]),
        "save_plot": ("Save plots", "save", [("PNG", ["*.png"])]),
    }

    def __init__(self, model: H2mmViewModel | None = None) -> None:
        self.model = model or H2mmViewModel()
        self.job = SnapshotJob(self.model)
        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        self.plots = ResultPlots()
        self.form = FormState()
        spec = load_view_spec(str(HERE / "h2mm.view.json"))
        sections = spec["sections"]
        self.settings_sections = [
            s for s in sections if s.get("type") == "panel" and s.get("title") != "Burst"
        ]
        self.burst_sections = [
            s for s in sections if s.get("type") == "panel" and s.get("title") == "Burst"
        ]
        self.tables = [s for s in sections if s.get("type") == "table"]
        for table, height in zip(self.tables, (110, 90)):
            table["height"] = height
        cap_widths(self.settings_sections + self.burst_sections)
        self.labels = LabelColumn()
        self._measured = False
        self.dialog = None
        self.dialog_action = ""
        self._dialog_window = None
        self.nano_colours: set[str] | None = None
        self.nano_states: set[int] | None = None
        self.editor = ChannelDefinitionWidget(self.model.setup, on_changed=self.model.set_setup)
        self.help_window = EmTkHelpWindow(
            title="Photon-by-Photon HMM (H2MM) - Help & Reference",
            resource=HERE / "help.md",
            owner=self.model,
            on_start_guide=self.start_guide,
            size=(700.0, 520.0),
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            get_target_rect=lambda k: self.item_rects.get(k) or self.form.rects.get(k),
            owner=self.model,
            wait_for_controls=True,
        )
        self.form.on_used = self.tour.notify_used
        self.on_used = self.tour.notify_used
        self.editor.on_used = self.tour.notify_used
        self.docks = DockManager(
            Split(
                "h",
                0.40,
                Region("controls"),
                Split(
                    "v",
                    0.26,
                    Region("results"),
                    Split("v", 0.5, Region("plots_a"), Region("plots_b")),
                ),
            ),
            name="burst_h2mm",
        )
        add = self.docks.add_window
        add("controls", "H2MM settings", self._controls, dock="controls", closable=False)
        add("detectors", "Detector setup", self._detectors, dock="controls", closable=False)
        add("results", "Rates and states", self._results, dock="results", closable=False)
        add("dwell_fret", "Dwell FRET", self._dwell_fret, dock="plots_a", closable=False)
        add("selection", "Selection", self._selection, dock="plots_a", closable=False)
        add("decays", "Decays", self._decays, dock="plots_a", closable=False)
        add("scans", "LL scan", self._scans, dock="plots_a", closable=False)
        add("tdp", "TDP", self._tdp, dock="plots_b", closable=False)
        add("dwells", "Dwell times", self._dwells, dock="plots_b", closable=False)
        add("path", "State path", self._path, dock="plots_b", closable=False)
        super().__init__(gui=self._render)

    # -- tour / help -------------------------------------------------------------------------------------- #
    def start_guide(self) -> None:
        self.tour.start()

    def show_help(self) -> None:
        self.help_window.show()

    def track(self, name: str) -> None:
        self.on_used(name)

    # -- actions -------------------------------------------------------------------------------------------- #
    def _start(self, method: str, message: str) -> None:
        self.model.status_text = message
        self.model._cancel.clear()
        self.job.start(method)

    def run(self) -> None:
        problem = self.model.can_run()
        if problem:
            self.model.status_text = problem
            return
        self._start("compute", "Fitting H2MM models ...")

    def restart(self) -> None:
        problem = self.model.can_run()
        if problem:
            self.model.status_text = problem
            return
        self._start("restart", "Refitting H2MM models ...")

    def stop(self) -> None:
        self.model.stop()

    def bootstrap(self) -> None:
        self._start("bootstrap", "Bootstrapping ...")

    def ll_scan(self) -> None:
        self._start("ll_scan", "Likelihood scan ...")

    def open_dwells_in_ndx(self) -> bool:
        """Open the per-dwell table in ndX (the Qt tool's action); says why when that is not possible."""
        from chisurf.core.datastore import row_count

        table = self.model.dwell_table()
        if table is None or row_count(table) == 0:
            self.model.status_text = "No dwells to explore: run a fit first."
            return False
        try:
            from ndxplorer.core.data_source import DataSource

            from chisurf.plugins.ndxplorer.window import build_ndxplorer_window

            self._ndx_window = build_ndxplorer_window(data_source=DataSource(table))
            self._ndx_window.show()
        except Exception as exc:
            self.model.status_text = f"ndX could not be opened: {exc}"
            return False
        self.model.status_text = f"{row_count(table)} dwells opened in ndX."
        return True

    def browse(self, action: str) -> None:
        """Open the file dialog for *action*."""
        from emtk.dialog_window import DialogWindow
        from emtk.file_dialog import FileDialog

        title, mode, filters = self.DIALOGS[action]
        options = {"filters": filters} if filters else {}
        filename = {
            "save_settings": "h2mm_settings.json",
            "export_dwells": "h2mm_dwells.csv",
            "save_plot": "h2mm.png",
        }.get(action, "")
        if mode == "folder" and self.model.data_folder:
            options["directory"] = str(self.model.data_folder)
        elif self.model.data_folder and mode != "folder":
            options["directory"] = str(self.model.data_folder)
        self.dialog = FileDialog(title, mode=mode, filename=filename, **options)
        self.dialog_action = action
        self._dialog_window = DialogWindow(title, size=(640.0, 460.0), key="burst-h2mm-file")
        self._dialog_window.show()

    def _dialog_done(self, result: list[str]) -> None:
        action, path = self.dialog_action, result[0]
        try:
            if action == "folder":
                self.model.data_folder = path
                self.model.status_text = f"Data folder: {path}"
            elif action == "save_settings":
                self.model.save_settings(path)
                self.model.status_text = f"Settings saved to {path}"
            elif action == "load_settings":
                self.model.load_settings(path)
                self.editor.model.data = copy.deepcopy(self.model.setup)
                self.model.status_text = f"Settings loaded from {path}"
            elif action == "export_dwells":
                n = self.model.export_dwells(path)
                self.model.status_text = f"{n} dwells written to {path}"
            elif action == "save_plot":
                self.save_plot(path)
                self.model.status_text = f"Plots saved to {path}"
        except Exception as exc:
            self.model.status_text = f"Error: {exc}"

    def save_plot(self, path: str) -> None:
        """Write the result plots (dwell FRET, TDP, model selection, dwell times) of the shown fit as one PNG."""
        from emtk.figure import Figure

        from . import result_view

        ana = self.model.analysis
        if ana is None:
            raise ValueError("Run a fit first.")
        fig = Figure(2, 2, size=(1200, 960))
        ax = fig.ax(0, 0)
        info = result_view.dwell_fret(ana)
        for state, counts in info.counts.items():
            ax.line(info.centers, counts, label=f"S{state}")
        ax.set_labels(x="Apparent FRET E", y="Dwells").set_title("Dwell FRET states").legend()
        ax = fig.ax(0, 1)
        points = result_view.transition_points(ana)
        if points is not None:
            ax.scatter(points[0], points[1], size=2.0)
        ax.set_labels(x="E before", y="E after").set_title("Transition density")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax = fig.ax(1, 0)
        sel = result_view.model_selection(ana)
        if sel is not None:
            ax.line(sel[0], sel[1], marker="o", label="BIC")
            ax.line(sel[0], sel[2], marker="s", label="ICL")
            ax.legend()
        ax.set_labels(x="States", y="Criterion").set_title("Model selection")
        ax = fig.ax(1, 1)
        hist, _ = result_view.dwell_histograms(ana)
        for h in hist:
            ax.line(h.centers_ms, h.counts, label=f"S{h.state}")
        ax.set_labels(x="Dwell time (ms)", y="Counts").set_title("Dwell times")
        if hist:
            ax.legend()
        if not str(path).lower().endswith(".png"):
            path = f"{path}.png"
        fig.save(path)

    # -- drawing ------------------------------------------------------------------------------------------- #
    def _fields(self):
        if not self._measured:
            fields = list(labelled(self.settings_sections))
            self.labels.measure([f["label"] for f in fields])
            self.labels.pad(fields)
            self._measured = True
        return self.settings_sections

    def _controls(self, box=None) -> None:
        running = self.job.busy
        problem = self.model.can_run()
        has_fit = self.model.bundle is not None
        idle_fit = has_fit and not running
        pressed = button_row(
            [
                {
                    "label": "Browse folder",
                    "key": "folder",
                    "enabled": not running,
                    "tip": "Choose the folder with the burst (.bur) tables of a finished burst analysis.",
                },
                {
                    "label": "Run H2MM",
                    "key": "toolAction_run",
                    "enabled": not problem and not running,
                    "tip": "Fit the photon-by-photon HMM to the bursts of the folder: every state count of the scan, then the "
                    "criterion picks one. A fit of unchanged inputs is kept."
                    if not problem
                    else "Fit the photon-by-photon HMM. " + problem,
                },
                {
                    "label": "Restart",
                    "key": "toolAction_restart",
                    "enabled": not problem and not running,
                    "tip": "Refit even when nothing changed. The restarts are seeded: the same seed reproduces the answer; "
                    "change the seed to draw a new sample."
                    if not problem
                    else "Refit. " + problem,
                },
                {
                    "label": "Stop",
                    "key": "Stop",
                    "enabled": running,
                    "tip": "Stop the running fit at its next progress checkpoint."
                    if running
                    else "Nothing is running; a fit in progress can be stopped here.",
                },
                {
                    "label": "Bootstrap",
                    "key": "bootstrap",
                    "enabled": idle_fit,
                    "tip": "Estimate confidence intervals of E and S by refitting 20 bootstrap resamples of the bursts."
                    if has_fit
                    else "Run a fit first; the bootstrap resamples its bursts.",
                },
                {
                    "label": "LL scan",
                    "key": "ll_scan",
                    "enabled": idle_fit,
                    "tip": "Profile the log-likelihood over each state's E (and S): a flat profile means the data do not "
                    "determine that state."
                    if has_fit
                    else "Run a fit first; the scan profiles its states.",
                },
                {
                    "label": "Save plot",
                    "key": "save_plot",
                    "enabled": has_fit,
                    "tip": "Write the dwell FRET, TDP, model selection and dwell-time plots of the fit as one PNG."
                    if has_fit
                    else "Run a fit first.",
                },
                {
                    "label": "Dwells in ndX",
                    "key": "ndx",
                    "enabled": has_fit,
                    "tip": "Open the per-dwell table (state, duration, E, S, edge flag) in ndXplorer."
                    if has_fit
                    else "Run a fit first.",
                },
                {
                    "label": "Export dwells",
                    "key": "export_dwells",
                    "enabled": has_fit,
                    "tip": "Write the per-dwell table as CSV." if has_fit else "Run a fit first.",
                },
                {
                    "label": "Save settings",
                    "key": "save_settings",
                    "tip": "Write the settings and the detector definition to a JSON file.",
                },
                {
                    "label": "Load settings",
                    "key": "load_settings",
                    "enabled": not running,
                    "tip": "Read settings and the detector definition from a JSON file.",
                },
                {
                    "label": "Guide",
                    "key": "guide",
                    "tip": "Start a step-by-step guided tour of this tool.",
                },
                {
                    "label": "Help",
                    "key": "help",
                    "tip": "Open the help window with reference documentation.",
                },
            ],
            remember=self.remember,
        )
        if pressed == "toolAction_run":
            self.track("toolAction_run")
            self.run()
        elif pressed == "toolAction_restart":
            self.restart()
        elif pressed == "Stop":
            self.stop()
        elif pressed == "bootstrap":
            self.bootstrap()
        elif pressed == "ll_scan":
            self.ll_scan()
        elif pressed == "ndx":
            self.open_dwells_in_ndx()
        elif pressed in self.DIALOGS:
            self.browse(pressed)
        elif pressed == "guide":
            self.start_guide()
        elif pressed == "help":
            self.show_help()
        if problem and not running:
            im.text_wrapped(problem)
        if running or self.job.progress:
            im.text_wrapped(self.job.progress or self.model.status_text)
        elif self.job.error:
            im.text_colored(self.job.error, (0.9, 0.4, 0.4, 1.0))
        im.separator()
        target = self.model
        if running:  # edits during a run go to a throw-away copy: the run has its own snapshot
            target = copy.copy(self.model)
            target._observers = []
        im.begin_disabled(running)
        draw_sections(self._fields(), target, self.form)
        im.end_disabled()
        if "data_folder" in self.form.rects:
            self.item_rects["folder_field"] = tuple(self.form.rects["data_folder"])

    def _detectors(self, box=None) -> None:
        self.remember("detectors", box)
        self.editor.draw()

    def _results(self, box=None) -> None:
        self.remember("results", box)
        im.text_wrapped(self.model.status_text)
        if self.model.analysis is None:
            im.text_wrapped(
                "No H2MM fit yet. Select a burst folder, define the detectors and press Run H2MM."
            )
            return
        draw_sections(self.tables, self.model, self.form)

    def _dwell_fret(self, box=None) -> None:
        self.plots.draw_dwell_fret(self.model.analysis, self.model.uncertainty)

    def _selection(self, box=None) -> None:
        self.plots.draw_model_selection(self.model.analysis)

    def _decays(self, box=None) -> None:
        from . import result_view

        decays = result_view.state_decay_curves(self.model.analysis, self.model.bundle)
        if decays is not None:
            if self.nano_colours is None:  # the donor alone: every colour at once is unreadable
                self.nano_colours = {decays.colours[0]} if decays.colours else set()
            if self.nano_states is None:
                self.nano_states = set(range(decays.n_states))
            for colour in decays.colours:
                on, now = im.checkbox(f"{colour}##nano_colour", colour in self.nano_colours)
                im.set_item_tooltip(f"Show the {colour} decays.")
                (self.nano_colours.add if now else self.nano_colours.discard)(colour)
                im.same_line()
            for state in range(decays.n_states):
                on, now = im.checkbox(f"S{state}##nano_state", state in self.nano_states)
                im.set_item_tooltip(f"Show state {state}.")
                (self.nano_states.add if now else self.nano_states.discard)(state)
                im.same_line()
            im.new_line()
        self.plots.draw_decays(decays, self.nano_colours or set(), self.nano_states or set())

    def _scans(self, box=None) -> None:
        self.plots.draw_scans(self.model.scans, self.model.uncertainty)

    def _tdp(self, box=None) -> None:
        self.plots.draw_tdp(self.model.analysis)

    def _dwells(self, box=None) -> None:
        self.plots.draw_dwells(self.model.analysis)

    def _path(self, box=None) -> None:
        bursts = self.model.nav_bursts()
        if bursts:
            self.model.nav_burst = max(0, min(int(self.model.nav_burst), len(bursts) - 1))
            draw_sections(self.burst_sections, self.model, self.form)
            self.plots.draw_state_path(
                self.model.analysis, self.model.bundle.data, bursts[self.model.nav_burst]
            )
        else:
            self.plots.draw_state_path(None, None, 0)

    def _render(self) -> None:
        self.editor.poll()
        if self.job.poll() or self.job.busy:
            ctx = get_current_context()
            ctx.request_frame_at(ctx.io.now + 0.1)
        w, h = im.get_main_viewport().size
        self.docks.draw((0.0, 0.0, float(w), float(h)))
        frame = (0.0, 0.0, float(w), float(h))
        self.editor.draw_dialogs(frame)
        if self.dialog is not None:
            pressed = self._dialog_window.begin(frame)
            result = self.dialog.draw()
            self._dialog_window.end()
            if result:
                self._dialog_done(result)
                self.dialog = None
            elif result is False or pressed == "close":
                self.dialog = None
        if self.help_window.open:
            self.help_window.draw((0.0, 0.0, w, h))
        if self.tour.active:
            self.tour.draw(w, h)

    # -- host input ---------------------------------------------------------------------------------------- #
    def files_dropped(self, paths) -> bool:
        """A dropped folder (or the folder of a dropped file) becomes the burst folder."""
        for path in map(Path, paths):
            folder = path if path.is_dir() else path.parent
            if folder.is_dir():
                self.model.data_folder = str(folder)
                return True
        return False

    on_paths_dropped = files_dropped

    def close(self) -> None:
        self.model.stop()
        self.editor.close()


def create_app(**kwargs) -> H2mmNativeApp:
    """Factory named by ``entrypoints.emtk``."""
    from chisurf.emtk.i18n import install

    install()
    return H2mmNativeApp(**kwargs)
