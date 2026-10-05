"""The native Burst Selection app (cards BS1 to BS6): emtk over :class:`.model.BurstSelectionModel`, no Qt behind it.

Files, output, the burst search, the filter, the display, the histogram, the scatter, the bursts and the summary are
the spec ``native.view.json`` (tables as ``data_table`` / ``table`` sections); the parameters of the selected search
are generated from the JSON Schema tttrlib publishes; the detector definition is the shared one-page detector editor.
The plots draw only what the model computed from the photons, or say there is nothing. A run goes through
:class:`chisurf.emtk.jobs.SnapshotJob`; the diagnostics of the visible window are recomputed (debounced) after every
change, as the Qt tool does.
"""

from __future__ import annotations

import copy
import time
from pathlib import Path
from typing import Any, Callable

from emtk import im, implot
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.im_core import get_current_context
from emtk.view_form import FormState, draw_sections
from emtk.widgets.view_spec import load_view_spec

from chisurf.emtk.channel_definition import ChannelDefinitionWidget
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget
from chisurf.emtk.jobs import SnapshotJob
from chisurf.plugins.emtk_layout import LabelColumn, button_row, cap_widths, labelled

from .model import BurstSelectionModel

HERE = Path(__file__).parent
#: Seconds without a change before the visible window is filtered again.
DIAGNOSTICS_DELAY = 0.35


def _sections(spec: dict, *titles: str) -> list[dict]:
    return [s for s in spec["sections"] if s.get("title") in titles]


class BurstSelectionNativeApp(TourTarget, ImApp):
    """Immediate-mode Burst Selection: files, detector editor, search, filter, run, diagnostics, features, output.

    Parameters
    ----------
    model : BurstSelectionModel, optional
        The state (default: a new model that restores the last settings).
    on_run_done : callable, optional
        Called with the model after a run finished (the Burst Analysis hub hands the bursts on).
    restore : bool
        Read the settings remembered by the previous session (default ``True``).
    """

    DIALOGS = {
        "add_files": ("Add TTTR files", "open"),
        "add_folder": ("Add a folder of TTTR files", "folder"),
        "save_bur": ("Save the burst table (.bur)", "save"),
        "export_bur": ("Export the displayed table (.bur)", "save"),
        "export_cif": ("Export as flrCIF", "save"),
        "save_settings": ("Save Burst Selection settings", "save"),
        "load_settings": ("Load Burst Selection settings", "open"),
    }
    FILTERS = {
        "save_bur": [("Burst table", ["*.bur"])],
        "export_bur": [("Burst table", ["*.bur"]), ("All files", ["*"])],
        "export_cif": [("flrCIF", ["*.cif", "*.mmcif"]), ("All files", ["*"])],
        "save_settings": [("JSON", ["*.json"])],
        "load_settings": [("JSON", ["*.json"])],
    }

    def __init__(
        self,
        model: BurstSelectionModel | None = None,
        *,
        on_run_done: Callable[[BurstSelectionModel], None] | None = None,
        restore: bool = True,
    ) -> None:
        self.model = model or BurstSelectionModel()
        if model is None and restore:
            self.model.restore()
        self.on_run_done = on_run_done
        self.job = SnapshotJob(self.model)
        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        self.form = FormState()
        spec = load_view_spec(str(HERE / "native.view.json"))
        cap_widths(spec["sections"])
        self.files_sections = _sections(spec, "Files")
        self.output_sections = _sections(spec, "Output")
        self.search_sections = _sections(spec, "Burst search")
        self.filter_sections = _sections(spec, "Channel selection", "Macro time interval", "Filter")
        self.display_sections = _sections(spec, "Display")
        self.hist_sections = _sections(spec, "Histogram")
        self.gmm_table = _sections(spec, "GMM")
        self.scatter_sections = _sections(spec, "Scatter")
        self.burst_table = _sections(spec, "Bursts")
        self.summary_table = _sections(spec, "Summary")
        self.gmm_settings_sections = _sections(spec, "GMM settings")
        self.metadata_sections = _sections(spec, "Metadata")
        self.labels = LabelColumn()
        self.dialog = None
        self.dialog_action = ""
        self._dialog_window = None
        self.panel_dialog = ""
        self._panel_window = None
        self.picker = None
        self._ndx_window = None
        self._diag_due: float | None = time.monotonic()
        self._signature = None
        self.message = ""
        self.editor = ChannelDefinitionWidget(
            self._editor_settings(), on_changed=self._setup_changed
        )
        if self.model.setup_name:
            try:
                self.editor.model.select_setup(self.model.setup_name)
            except Exception:  # noqa: BLE001 - the editor shows its own default
                pass
        else:
            try:  # the last used setup, as the Qt tool opens it
                self.editor.model.refresh_setups()
                self.editor.model.open_last_used()
            except Exception:  # noqa: BLE001 - no store: the editor starts empty
                pass
        self.help_window = EmTkHelpWindow(
            title="Burst Selection - Help & Reference",
            resource=HERE / "help.md",
            owner=self.model,
            on_start_guide=self.start_guide,
            size=(720.0, 540.0),
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            get_target_rect=lambda k: self.item_rects.get(k) or self.form.rects.get(k),
            on_step_change=self._tour_step,
            owner=self.model,
            wait_for_controls=True,
        )
        self.form.on_used = self._used
        self.on_used = self.tour.notify_used
        self.editor.on_used = self.tour.notify_used
        self.docks = DockManager(
            Split(
                "h",
                0.38,
                Region("controls"),
                Split("v", 0.52, Region("plots_a"), Region("plots_b")),
            ),
            name="burst_selection",
        )
        add = self.docks.add_window
        add("files", "Burst Selection", self._files, dock="controls", closable=False)
        add("settings", "Filter settings", self._settings, dock="controls", closable=False)
        add("detectors", "Detector setup", self._detectors, dock="controls", closable=False)
        add("summary", "Summary", self._summary, dock="controls", closable=False)
        add("trace", "Count rate", self._trace, dock="plots_a", closable=False)
        add("dt", "Inter-photon time", self._dt, dock="plots_a", closable=False)
        add("decay", "Micro-time decay", self._decay, dock="plots_a", closable=False)
        add("duration", "Burst duration", self._duration, dock="plots_a", closable=False)
        add("histogram", "Histogram", self._histogram, dock="plots_b", closable=False)
        add("scatter", "Scatter", self._scatter, dock="plots_b", closable=False)
        add("table", "Bursts", self._bursts, dock="plots_b", closable=False)
        super().__init__(gui=self._render)

    # -- tour / help ----------------------------------------------------------------------------------------- #
    def start_guide(self) -> None:
        self.tour.start()

    def show_help(self) -> None:
        self.help_window.show()

    def track(self, name: str) -> None:
        self.on_used(name)

    def _tour_step(self, _index: int, step: dict) -> None:
        """A step's target names the dock window of its control (``"tab"``); bring that tab to the front."""
        window = (step.get("target") or {}).get("tab")
        if window and self.docks.window(window) is not None:
            self.docks.focus(window)

    def _used(self, name: str) -> None:
        self.tour.notify_used(name)
        self._diag_due = time.monotonic() + DIAGNOSTICS_DELAY

    # -- detector setup -------------------------------------------------------------------------------------- #
    def _editor_settings(self) -> dict:
        return {
            "detectors": copy.deepcopy(self.model.detectors),
            "windows": copy.deepcopy(self.model.windows),
            "tttr_reading": {"file_type": self.model.file_type or "auto"},
            "setup_name": self.model.setup_name,
        }

    def _setup_changed(self, settings: dict) -> None:
        name = getattr(self.editor.model, "current_name", "") if hasattr(self, "editor") else ""
        self.model.set_setup({**settings, "setup_name": name or settings.get("setup_name", "")})
        self._diag_due = time.monotonic() + DIAGNOSTICS_DELAY

    def apply_setup(self, settings: dict, name: str = "") -> None:
        """Take a detector definition from outside (the Burst Analysis workflow)."""
        if name:
            try:
                self.editor.model.select_setup(name)
                return
            except Exception:  # noqa: BLE001 - not in the store: take the definition as given
                pass
        self.editor.model.data = copy.deepcopy({**settings, "setup_name": name})
        self.model.set_setup({**settings, "setup_name": name})

    # -- actions --------------------------------------------------------------------------------------------- #
    @property
    def running(self) -> bool:
        return bool(self.job.busy)

    def run(self, force: bool = False) -> bool:
        """Run (or, with *force*, Restart) the search over every file; ``False`` when it did not start."""
        why = self.model.prepare_run(force=force)
        if why is not None:
            self.model.status_text = why
            return False
        self.job.start("run")
        return True

    def run_step(self) -> bool:
        """The workflow hub's Next: run unless an identical search is already displayed."""
        if (
            self.model.has_processed
            and self.model.prepare_run() is not None
            and self.model.unchanged
        ):
            return False
        return self.run()

    def browse(self, action: str) -> None:
        from emtk.dialog_window import DialogWindow
        from emtk.file_dialog import FileDialog

        from chisurf.core.fio.staging import TTTR_EXTENSIONS

        title, mode = self.DIALOGS[action]
        options: dict[str, Any] = {}
        if self.model.files:
            options["directory"] = str(self.model.files[0].parent)
        filters = self.FILTERS.get(action)
        if action == "add_files":
            filters = [
                ("TTTR files", sorted("*" + ext for ext in TTTR_EXTENSIONS)),
                ("All files", ["*"]),
            ]
        if filters:
            options["filters"] = filters
        filename = ""
        if action == "save_bur" and self.model.files:
            filename = self.model.files[0].with_suffix(".bur").name
        elif action == "export_cif":
            filename = "bursts.cif"
        elif action == "save_settings":
            filename = "burst_selection_settings.json"
        self.dialog = FileDialog(
            title, mode=mode, filename=filename, multiselect=action == "add_files", **options
        )
        self.dialog_action = action
        self._dialog_window = DialogWindow(title, size=(660.0, 470.0), key="burst-selection-file")
        self._dialog_window.show()

    def _dialog_done(self, result: list[str]) -> None:
        action = self.dialog_action
        try:
            if action in ("add_files", "add_folder"):
                if not self.model.add_paths([Path(p) for p in result]):
                    self.model.status_text = (
                        "Nothing new to add (already listed, or no TTTR files)."
                    )
                self._diag_due = time.monotonic()
            elif action == "save_bur":
                self.model.save_bur(result[0])
            elif action == "export_bur":
                self.model.export_bur(result[0])
            elif action == "export_cif":
                self.model.export_flr_cif(result[0])
            elif action == "save_settings":
                self.model.save_settings(result[0])
                self.model.status_text = f"Settings saved to {result[0]}"
            elif action == "load_settings":
                self.model.load_settings(result[0])
                self.model.status_text = f"Settings loaded from {result[0]}"
                self._diag_due = time.monotonic()
        except Exception as exc:  # noqa: BLE001 - shown in the status line
            self.model.status_text = f"Error: {exc}"

    def open_panel(self, name: str) -> None:
        from emtk.dialog_window import DialogWindow

        titles = {"metadata": "Metadata", "gmm": "GMM settings"}
        self.panel_dialog = name
        self._panel_window = DialogWindow(
            titles[name], size=(460.0, 420.0), key=f"burst-selection-{name}"
        )
        self._panel_window.show()

    def send_to_ndx(self) -> bool:
        """Open the last run's burst output in ndX (needs a run)."""
        path = self.model.output_path()
        if not path:
            self.model.status_text = "No burst output to send: run the search first."
            return False
        try:
            from chisurf.plugins.ndxplorer.mmfdb_launcher import open_path_in_ndxplorer

            self._ndx_window = open_path_in_ndxplorer(path)
        except Exception as exc:  # noqa: BLE001 - ndX is optional
            self.model.status_text = f"Could not send to ndX: {exc}"
            return False
        if self._ndx_window is None:
            self.model.status_text = "ndX could not be opened."
            return False
        self.model.status_text = f"Opened {path} in ndX."
        return True

    def open_registered_in_ndx(self) -> None:
        """Pick a burst selection registered in MMFDB and open it in ndX."""
        from chisurf.emtk.dataset_picker import DatasetPicker
        from chisurf.plugins.ndxplorer.mmfdb_launcher import BURST_FORMATS, BURST_KINDS

        def chosen(selection) -> None:
            path = getattr(selection, "local_path", None)
            if not path:
                self.model.status_text = "The selected burst selection has no local path."
                return
            from chisurf.plugins.ndxplorer.mmfdb_launcher import open_path_in_ndxplorer

            self._ndx_window = open_path_in_ndxplorer(path)

        try:
            self.picker = DatasetPicker(
                kinds=BURST_KINDS,
                formats=BURST_FORMATS,
                scope="all",
                on_paths=lambda _p: None,
                on_selected=chosen,
            )
            self.picker.open()
        except Exception as exc:  # noqa: BLE001 - no database
            self.picker = None
            self.model.status_text = f"MMFDB is not available: {exc}"

    def _press(self, key: str) -> None:
        m = self.model
        self.track(key)
        try:
            if key == "toolAction_run":
                self.run()
            elif key == "toolAction_restart":
                self.run(force=True)
            elif key == "toolAction_clear":
                m.clear()
            elif key == "toolAction_refresh":
                self._diag_due = time.monotonic()
            elif key in self.DIALOGS:
                self.browse(key)
            elif key == "metadata":
                self.open_panel("metadata")
            elif key == "ndx_current":
                self.send_to_ndx()
            elif key == "ndx_mmfdb":
                self.open_registered_in_ndx()
            elif key == "guide":
                self.start_guide()
            elif key == "help":
                self.show_help()
        except Exception as exc:  # noqa: BLE001 - shown in the status line
            m.status_text = f"Error: {exc}"

    # -- windows --------------------------------------------------------------------------------------------- #
    def _files(self, box=None) -> None:
        m = self.model
        busy = self.running
        has_files = bool(m.files)
        has_result = m.has_processed
        shown = m.display_frame is not None
        pressed = button_row(
            [
                {
                    "label": "Add files",
                    "key": "add_files",
                    "enabled": not busy,
                    "keys": ["toolAction_add"],
                    "tip": "Choose TTTR files to search (drop files or folders on the window works too).",
                },
                {
                    "label": "Add folder",
                    "key": "add_folder",
                    "enabled": not busy,
                    "keys": ["toolAction_batch"],
                    "tip": "Add every TTTR file of a folder (the Qt batch dialog).",
                },
                {
                    "label": "Run",
                    "key": "toolAction_run",
                    "enabled": has_files and not busy,
                    "tip": "Search the bursts of every file and write the burst tables."
                    if has_files
                    else "Add TTTR files first.",
                },
                {
                    "label": "Restart",
                    "key": "toolAction_restart",
                    "enabled": has_files and not busy,
                    "tip": "Search again even though files and settings are unchanged.",
                },
                {
                    "label": "Clear",
                    "key": "toolAction_clear",
                    "enabled": has_files and not busy,
                    "tip": "Remove every file and result (the settings stay).",
                },
                {
                    "label": "Refresh plots",
                    "key": "toolAction_refresh",
                    "enabled": has_files and not busy,
                    "tip": "Filter the visible window again and redraw the plots.",
                },
                {
                    "label": "Save .bur",
                    "key": "save_bur",
                    "enabled": has_result and not busy,
                    "tip": "Write the burst tables of every file as one .bur."
                    if has_result
                    else "Run the search first.",
                },
                {
                    "label": "Export .bur",
                    "key": "export_bur",
                    "enabled": shown,
                    "tip": "Write the displayed table (with File Idx) as a tab-separated .bur.",
                },
                {
                    "label": "Export flrCIF",
                    "key": "export_cif",
                    "enabled": shown,
                    "tip": "Write the displayed table and the metadata as flrCIF.",
                },
                {
                    "label": "Metadata",
                    "key": "metadata",
                    "tip": "Edit the analysis metadata written with the flrCIF export.",
                },
                {
                    "label": "Open in ndX",
                    "key": "ndx_current",
                    "enabled": has_result and not busy,
                    "tip": "Open the last run's burst folder in ndXplorer."
                    if has_result
                    else "Run the search first.",
                },
                {
                    "label": "ndX from MMFDB",
                    "key": "ndx_mmfdb",
                    "tip": "Pick a burst selection registered in MMFDB and open it in ndXplorer.",
                },
                {
                    "label": "Save settings",
                    "key": "save_settings",
                    "tip": "Write the filter, search, display and GMM settings to a JSON file.",
                },
                {
                    "label": "Load settings",
                    "key": "load_settings",
                    "enabled": not busy,
                    "tip": "Read settings from a JSON file.",
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
        if pressed:
            self._press(pressed)
        if busy or self.job.progress:
            im.text_wrapped(self.job.progress or m.status_text)
        elif self.job.error:
            im.text_colored(f"Error: {self.job.error}", (0.9, 0.4, 0.4, 1.0))
        else:
            im.text_wrapped(m.status_text)
        self.remember("status")
        im.text_wrapped(m.setup_text())
        im.separator()
        im.begin_disabled(busy)
        draw_sections(self.files_sections, m, self.form)
        draw_sections(self.output_sections, m, self.form)
        im.end_disabled()

    def _settings(self, box=None) -> None:
        m = self.model
        busy = self.running
        target = copy.copy(m) if busy else m  # edits during a run go nowhere
        params = m.search_sections()
        nested = m.nested_sections()
        static = self.search_sections + self.filter_sections + self.display_sections
        if not self.labels.ready:
            self.labels.measure([f["label"] for f in labelled(static + params + nested)])
            self.labels.pad(static)
        self.labels.pad(params + nested)
        im.begin_disabled(busy)
        draw_sections(self.search_sections, target, self.form)
        self.remember("search", None)
        if params:
            draw_sections(params, m.search, self.form)
        if nested:
            im.text("Per-group search parameters")
            draw_sections(nested, m.inner_search, self.form)
        if im.button("Save as setup default"):
            self.track("save_defaults")
            try:
                m.save_defaults_to_setup()
            except Exception as exc:  # noqa: BLE001 - shown in the status line
                m.status_text = f"Error: {exc}"
        im.set_item_tooltip(
            "Store the current filter and search as the defaults of the selected detector setup "
            "(read again whenever the setup is chosen)."
        )
        self.remember("save_defaults")
        draw_sections(self.filter_sections, target, self.form)
        draw_sections(self.display_sections, target, self.form)
        im.end_disabled()

    def _detectors(self, box=None) -> None:
        self.remember("detectors", box)
        self.editor.draw()

    def _summary(self, box=None) -> None:
        m = self.model
        if not m.has_processed and m.display_frame is None:
            im.text_wrapped(
                "No search yet: add TTTR files and press Run. The key figures of the run appear here."
            )
            return
        draw_sections(self.summary_table, m, self.form)

    def _empty(self, text: str) -> None:
        im.text_wrapped(text)

    def _trace(self, box=None) -> None:
        self.remember("trace", box)
        m = self.model
        curves = m.trace_curves()
        if not curves:
            self._empty(
                "No count-rate trace: add TTTR files. The trace of the visible window of the active file "
                "(all photons and the selected burst photons) appears here."
            )
            return
        if implot.begin_plot(f"Count rate ({m.trace_bin_ms:g} ms bins)", (-1, -1)):
            implot.setup_axes("Time in the window (s)", "Count rate (Hz)")
            if "all" in curves:
                implot.plot_line("All photons", *curves["all"])
            if "selected" in curves:
                implot.plot_line("Selected photons", *curves["selected"])
            implot.end_plot()

    def _dt(self, box=None) -> None:
        self.remember("dt", box)
        m = self.model
        curves = m.dt_curves()
        if not curves:
            self._empty(
                "No inter-photon times: add TTTR files. dT of every photon of the visible window appears here."
            )
            return
        if implot.begin_plot("Inter-photon time", (-1, -1)):
            implot.setup_axes("Photon index", "dT (ms)")
            implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
            if "all" in curves:
                implot.plot_scatter("All photons", *curves["all"], size=1.5)
            if "selected" in curves:
                implot.plot_scatter("Selected photons", *curves["selected"], size=1.5)
            limits = m.thresholds()
            for n, key in enumerate(("dt_min", "dt_max")):
                if limits[key] is not None:
                    moved = implot.drag_line_y(700 + n, float(limits[key]), None, 1.5)
                    if moved.modified and moved.value > 0:
                        setattr(m, key, float(moved.value))
                        self._used(key)
            implot.end_plot()

    def _decay(self, box=None) -> None:
        self.remember("decay", box)
        curves = self.model.decay_curves()
        if not curves:
            self._empty(
                "No micro-time decay: add TTTR files. The decay of the file and of the burst photons appears here."
            )
            return
        if implot.begin_plot("Micro-time histogram", (-1, -1)):
            implot.setup_axes("Micro time (ns)", "Counts")
            implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
            if "all" in curves:
                implot.plot_line("All photons", *curves["all"])
            if "selected" in curves:
                implot.plot_line("Selected photons", *curves["selected"])
            implot.end_plot()

    def _duration(self, box=None) -> None:
        self.remember("duration", box)
        m = self.model
        if not m.show_selected_photons:
            self._empty("Selected photons are hidden (Display): burst durations are not drawn.")
            return
        hist = m.duration_histogram()
        if hist is None:
            self._empty("No bursts in the visible window: their duration histogram appears here.")
            return
        centres, counts, width = hist
        if implot.begin_plot("Burst duration", (-1, -1)):
            implot.setup_axes("Burst duration (ms)", "Bursts")
            implot.plot_bars("Bursts", centres, counts, bar_size=width * 0.9)
            implot.end_plot()
        im.text(f"Total bursts in the window: {int(counts.sum())}")

    def _histogram(self, box=None) -> None:
        self.remember("histogram", box)
        m = self.model
        draw_sections(self.hist_sections, m, self.form)
        pressed = button_row(
            [
                {
                    "label": "Auto range",
                    "key": "auto_range",
                    "tip": "Set the range to the data range of the feature.",
                },
                {
                    "label": "Fit GMM",
                    "key": "fit_gmm",
                    "enabled": m.display_frame is not None,
                    "tip": "Fit the histogram with a Gaussian mixture (components above).",
                },
                {
                    "label": "GMM settings",
                    "key": "gmm_settings",
                    "tip": "Advanced Gaussian-mixture settings.",
                },
            ],
            remember=self.remember,
        )
        if pressed == "auto_range":
            m.auto_range()
        elif pressed == "fit_gmm":
            self.track("fit_gmm")
            try:
                result = m.fit_gmm()
                if result.get("error"):
                    m.status_text = result["error"]
            except Exception as exc:  # noqa: BLE001
                m.status_text = f"GMM fitting failed: {exc}"
        elif pressed == "gmm_settings":
            self.open_panel("gmm")
        hist = m.histogram()
        if hist is None:
            self._empty(
                "No burst table yet: the histogram of the chosen feature appears after a run or a preview."
            )
            return
        centres, counts, width = hist
        if implot.begin_plot(f"Histogram of {m.hist_feature}", (-1, -112 if m.gmm_rows() else -1)):
            implot.setup_axes(m.hist_feature, "Bursts")
            if m.hist_log:
                implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
            implot.plot_bars("Bursts", centres, counts, bar_size=width * 0.9)
            gmm = m.gmm_result or {}
            if gmm.get("x") is not None:
                implot.plot_line("GMM fit", gmm["x"], gmm["total"])
                for i, comp in enumerate(gmm["components"]):
                    implot.plot_line(f"Gaussian {i + 1}", gmm["x"], comp)
            implot.end_plot()
        if m.gmm_rows():
            draw_sections(self.gmm_table, m, self.form)

    def _scatter(self, box=None) -> None:
        self.remember("scatter", box)
        m = self.model
        draw_sections(self.scatter_sections, m, self.form)
        xy = m.scatter()
        if xy is None:
            self._empty(
                "No burst table yet: the scatter of two burst features appears after a run or a preview."
            )
            return
        if implot.begin_plot(f"{m.scatter_y} vs {m.scatter_x}", (-1, -1)):
            implot.setup_axes(m.scatter_x, m.scatter_y)
            implot.plot_scatter(f"Bursts ({len(xy[0])})", xy[0], xy[1], size=2.5)
            implot.end_plot()

    def _bursts(self, box=None) -> None:
        self.remember("bursts", box)
        m = self.model
        if m.display_frame is None:
            self._empty("No bursts yet: press Run (or wait for the preview of the visible window).")
            return
        im.text(
            ("Preview of the visible window" if m.preview else "Bursts of the active file")
            + (f": {m.active_file.name}" if m.active_file else "")
        )
        draw_sections(self.burst_table, m, self.form)

    def _panel(self, frame) -> None:
        if not self.panel_dialog:
            return
        pressed = self._panel_window.begin(frame)
        if self.panel_dialog == "metadata":
            draw_sections(self.metadata_sections, self.model, self.form)
        else:
            draw_sections(self.gmm_settings_sections, self.model.gmm, self.form)
            if im.button("Fit GMM with these settings"):
                try:
                    self.model.fit_gmm()
                except Exception as exc:  # noqa: BLE001
                    self.model.status_text = f"GMM fitting failed: {exc}"
            im.set_item_tooltip("Refit the histogram with the settings above.")
        self._panel_window.end()
        if pressed == "close":
            self.panel_dialog = ""

    # -- the frame ------------------------------------------------------------------------------------------- #
    def _diagnostics_tick(self) -> None:
        """Filter the visible window again once the settings have been still for a moment."""
        m = self.model
        if self.running or not m.files:
            return
        signature = (str(m.active_file), m.has_processed, len(m.files))
        if signature != self._signature:
            self._signature = signature
            self._diag_due = self._diag_due or time.monotonic()
        if self._diag_due is None or time.monotonic() < self._diag_due:
            return
        self._diag_due = None
        try:
            m.load_diagnostics()
        except Exception as exc:  # noqa: BLE001 - shown in the status line
            m.status_text = f"Diagnostics unavailable: {exc}"

    def _render(self) -> None:
        self.editor.poll()
        ctx = get_current_context()
        if self.job.poll():
            self.model.remember()
            self._diag_due = time.monotonic()
            if self.on_run_done is not None and not self.job.error:
                self.on_run_done(self.model)
        if self.job.busy or self._diag_due is not None:
            ctx.request_frame_at(ctx.io.now + 0.1)
        self._diagnostics_tick()
        w, h = im.get_main_viewport().size
        frame = (0.0, 0.0, float(w), float(h))
        self.docks.draw(frame)
        self.editor.draw_dialogs(frame)
        self._panel(frame)
        if self.dialog is not None:
            pressed = self._dialog_window.begin(frame)
            result = self.dialog.draw()
            self._dialog_window.end()
            if result:
                self._dialog_done(result)
                self.dialog = None
            elif result is False or pressed == "close":
                self.dialog = None
        if self.picker is not None:
            self.picker.render(frame)
            if not getattr(self.picker, "is_open", True):
                self.picker = None
        if self.help_window.open:
            self.help_window.draw(frame)
        if self.tour.active:
            self.tour.draw(w, h)

    # -- host input ------------------------------------------------------------------------------------------ #
    def files_dropped(self, paths) -> bool:
        paths = [Path(p) for p in paths]
        added = bool(paths) and self.model.add_paths(paths) > 0
        if added:
            self._diag_due = time.monotonic()
        return added

    on_paths_dropped = files_dropped
    on_files_dropped = files_dropped

    # -- persistence ----------------------------------------------------------------------------------------- #
    def export_settings(self) -> dict[str, Any]:
        return self.model.export_settings()

    def restore_settings(self, state: dict[str, Any] | None) -> None:
        if state:
            self.model.import_settings(state)

    def close(self) -> None:
        self.model.remember()
        self.editor.close()
        if self.picker is not None:
            try:
                self.picker.close()
            except Exception:  # noqa: BLE001
                pass


def create_app(**kwargs) -> BurstSelectionNativeApp:
    """Factory named by ``entrypoints.emtk``."""
    from chisurf.emtk.i18n import install

    install()
    return BurstSelectionNativeApp(**kwargs)
