"""The emtk burst-MLE app over :class:`MleViewModel` (cards ML2 to ML5): no Qt wizard behind it.

Files, detector window, IRF settings and the fit-parameter table are the spec ``mle_native.view.json`` (the files and the
parameters as ``data_table`` sections); the detector definition is the shared one-page detector editor; the decay fit,
the burst-lifetime histogram and the inspected burst draw only what the engine computed, or say there is none.
Auto IRF/background and the batch over every burst run on a snapshot through ``SnapshotJob``.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import numpy as np
from emtk import im, implot
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.im_core import get_current_context
from emtk.view_form import FormState, draw_sections
from emtk.widgets.view_spec import load_view_spec

from chisurf.core.support.i18n import tr
from chisurf.emtk.channel_definition import ChannelDefinitionWidget
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget
from chisurf.emtk.jobs import SnapshotJob
from chisurf.plugins.emtk_layout import (
    LabelColumn,
    action_caption,
    action_tooltip,
    button_row,
    cap_widths,
    labelled,
    window_size,
)

from . import fit_view
from .model import MleViewModel

HERE = Path(__file__).parent
REGION_FILL = (46, 117, 182, 60)


class MleNativeApp(TourTarget, ImApp):
    """Immediate-mode burst-MLE app: files, detector editor, settings, fit, batch, plots."""

    DIALOGS = {
        "add_files": ("Open burst tables", "open", [("BUR", ["*.bur"])]),
        "add_folder": ("Add burst folder", "folder", None),
        "save_settings": ("Save burst-MLE settings", "save", [("JSON", ["*.json"])]),
        "load_settings": ("Load burst-MLE settings", "open", [("JSON", ["*.json"])]),
        "add_irf_files": ("Open measured IRF files", "open", None),
        "add_bg_files": ("Open measured background files", "open", None),
    }

    def __init__(self, model: MleViewModel | None = None) -> None:
        self.model = model or MleViewModel()
        self.job = SnapshotJob(self.model)
        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        self.form = FormState()
        primary = json.loads((HERE / "mle_native.view.json").read_text(encoding="utf-8"))
        self.window_size = window_size(primary, (1100, 720))
        spec = load_view_spec(str(HERE / "mle_native.view.json"))
        sections = spec["sections"]
        self.sections = [
            s
            for s in sections
            if s.get("title") not in ("Burst", "Burst lifetimes", "IRF", "Measured IRF and background")
        ]
        self.pattern_sections = [
            s for s in sections if s.get("title") == "Measured IRF and background"
        ]
        self.irf_sections = [s for s in sections if s.get("title") == "IRF"]
        for s in self.irf_sections:
            s["collapsed"] = False
        self.burst_sections = [s for s in sections if s.get("title") == "Burst"]
        self.tables = [s for s in sections if s.get("type") == "table"]
        for table in self.tables:
            table["height"] = 90
        cap_widths(self.sections + self.burst_sections + self.irf_sections + self.pattern_sections)
        self.labels = LabelColumn()
        self._measured = False
        self.dialog = None
        self.dialog_action = ""
        self._dialog_window: Any = None
        self.gate_min: float | None = None
        self.gate_max: float | None = None
        self._editor_read_only_before_job: bool | None = None
        self.editor = ChannelDefinitionWidget(
            self.model.session.definition_payload(),
            on_changed=self.model.set_setup,
            host_app=self,
        )
        self.help_window = EmTkHelpWindow(
            title="Burst Lifetime MLE - Help & Reference",
            resource=HERE / "help.md",
            owner=self.model,
            on_start_guide=self.start_guide,
            size=(700.0, 520.0),
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            on_step_change=self._tour_step,
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
                Split("v", 0.62, Region("plots_a"), Region("plots_b")),
            ),
            name="burst_mle",
        )
        add = self.docks.add_window
        add("controls", "Burst MLE", self._controls, dock="controls", closable=False)
        add("irf", "IRF", self._irf, dock="controls", closable=False)
        add("patterns", "IRF/BG files", self._patterns, dock="controls", closable=False)
        add("detectors", "Detector setup", self._detectors, dock="controls", closable=False)
        add("decay", "Decay and fit", self._decay, dock="plots_a", closable=False)
        add("inspect", "Inspected burst", self._inspect, dock="plots_a", closable=False)
        add("lifetimes", "Burst lifetimes", self._lifetimes, dock="plots_b", closable=False)
        add("results", "Lifetime table", self._results, dock="plots_b", closable=False)
        super().__init__(gui=self._render)

    # -- tour / help -------------------------------------------------------------------------------------- #
    def _tour_step(self, index, step) -> None:
        """Expose the real example control when the tour awaits its use."""
        name = (step.get("target") or {}).get("name")
        if name == "add_irf_files":
            self.docks.focus("patterns")
        elif name in ("load_example", "optimize", "window_start"):
            self.docks.focus("controls")

    def start_guide(self) -> None:
        self.tour.start()

    def show_help(self) -> None:
        self.help_window.show()

    def track(self, name: str) -> None:
        self.on_used(name)

    # -- actions ------------------------------------------------------------------------------------------ #
    def auto_extract(self) -> None:
        self.model.status_text = "Estimating IRF and background ..."
        self.job.start("auto_extract")

    def fit_bursts(self) -> None:
        if self.model.session.df_bursts is None:
            self.model.status_text = "Add burst files first."
            return
        ready, _n = self.model.input_status()
        if not ready:
            self.model.status_text = (
                "No IRF and background for the current detector yet: press Auto IRF/background."
            )
            return
        self.model.status_text = "Fitting bursts ..."
        self.job.start("run_batch")

    def optimize(self) -> None:
        """Run Opt on a snapshot: the search refits many times and applies the best configuration at the end."""
        if not self.model.input_status()[0]:
            self.model.status_text = str(
                tr("Nothing to optimise yet: press Auto IRF/background or load an IRF and a background.")
            )
            return
        self.model.status_text = str(tr("Optimising ..."))
        self.job.start("optimize")

    def save_fit(self) -> None:
        """Store the current detector's fit settings on the selected detector setup."""
        try:
            self.model.save_fit_to_setup(self.editor.model)
        except Exception as exc:
            self.model.status_text = f"Error: {exc}"

    def stop(self) -> None:
        self.model.stop()

    def browse(self, action: str) -> None:
        from emtk.dialog_window import DialogWindow
        from emtk.file_dialog import FileDialog

        title, mode, filters = self.DIALOGS[action]
        options: dict[str, Any] = {"filters": filters} if filters else {}
        files = self.model.session.bur_files
        if files:
            # burst tables sit in <measurement folder>/<analysis>/<ending>/; measured IRF / background files beside the raw data
            pattern = action in ("add_irf_files", "add_bg_files")
            options["directory"] = str(files[0].parents[2] if pattern else files[0].parent)
        filename = "burst_mle_settings.json" if action == "save_settings" else ""
        self.dialog = FileDialog(
            title, mode=mode, filename=filename, multiselect=action in ("add_files", "add_irf_files", "add_bg_files"), **options
        )
        self.dialog_action = action
        self._dialog_window = DialogWindow(title, size=(640.0, 460.0), key="burst-mle-file")
        self._dialog_window.show()

    def _dialog_done(self, result: list[str]) -> None:
        action = self.dialog_action
        try:
            if action in ("add_files", "add_folder"):
                self.model.add_files(result)
            elif action == "add_irf_files":
                self.model.add_irf_files(result)
            elif action == "add_bg_files":
                self.model.add_bg_files(result)
            elif action == "save_settings":
                self.model.save_settings(result[0])
                self.model.status_text = f"Settings saved to {result[0]}"
            elif action == "load_settings":
                self.model.load_settings(result[0])
                self.editor.model.data = copy.deepcopy(
                    {
                        "detectors": self.model.session.detectors,
                        "windows": {},
                        "tttr_reading": {"file_type": self.model.session.file_type},
                    }
                )
                self.model.status_text = f"Settings loaded from {result[0]}"
        except Exception as exc:
            self.model.status_text = f"Error: {exc}"

    # -- drawing ------------------------------------------------------------------------------------------ #
    def _fields(self):
        if not self._measured:
            fields = list(labelled(self.sections + self.irf_sections + self.pattern_sections))
            self.labels.measure([f["label"] for f in fields])
            self.labels.pad(fields)
            self._measured = True
        return self.sections

    def _controls(self, box=None) -> None:
        running = self.job.busy
        has_data = self.model.session.df_bursts is not None
        has_results = bool(self.model.burst_results)
        ready, _n = self.model.input_status()
        pressed = button_row(
            [
                {
                    "label": "Add files",
                    "key": "add_files",
                    "enabled": not running,
                    "tip": "Choose burst (.bur) tables; the analysis folder they belong to is read whole.",
                },
                {
                    "label": "Add folder",
                    "key": "add_folder",
                    "enabled": not running,
                    "tip": "Add every burst table below a folder.",
                },
                {
                    "label": "Clear",
                    "key": "clear_files",
                    "enabled": has_data and not running,
                    "tip": "Remove all burst files and the results."
                    if has_data
                    else "No burst files to remove.",
                },
                {
                    "label": "Auto IRF/background",
                    "key": "auto",
                    "enabled": has_data and not running,
                    "tip": "Pick the binning and fit window and estimate a Gaussian IRF and the background from the photons "
                    "outside the bursts, then fit. A measured IRF and background give better lifetimes."
                    if has_data
                    else "Add burst files first.",
                },
                {
                    "label": "Refit",
                    "key": "toolAction_restart",
                    "enabled": ready and not running,
                    "tip": "Fit the current decay again with the current settings."
                    if ready
                    else "Needs an IRF and a background.",
                },
                {
                    "label": str(tr("Opt")),
                    "key": "optimize",
                    "enabled": ready and not running,
                    "tip": str(
                        tr(
                            "Optimise the VH shift, the sub-bin shifts, the IRF window and the IRF thresholds "
                            "(Opt iterations in the IRF tab) for the lowest 2I*, then refit. The result is never "
                            "worse than the current settings."
                        )
                    )
                    if ready
                    else str(tr("Needs an IRF and a background.")),
                },
                {
                    "label": "Fit bursts",
                    "key": "toolAction_run",
                    "enabled": has_data and ready and not running,
                    "tip": "Fit every burst of every file and detector by maximum likelihood (worker processes)."
                    if ready
                    else "Needs burst files and an IRF and a background: press Auto IRF/background first.",
                },
                {
                    "label": "Stop",
                    "key": "Stop",
                    "enabled": running,
                    "tip": "Stop the running fit."
                    if running
                    else "Nothing is running; a fit in progress can be stopped here.",
                },
                {
                    "label": "Save results",
                    "key": "save_results",
                    "enabled": has_results and not running,
                    "tip": "Write the per-burst fits as b?4 tables beside the burst folders."
                    if has_results
                    else "Fit the bursts first.",
                },
                {
                    "label": str(tr("Save fit")),
                    "key": "save_fit",
                    "enabled": not running,
                    "tip": str(
                        tr(
                            "Store this detector's window, IRF thresholds, shifts, 2I*/BIFL options and fix flags "
                            "on the selected detector setup; they are applied again whenever the detector is selected."
                        )
                    ),
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
                    "tip": "Read settings and detectors from a JSON file.",
                },
                {
                    "label": action_caption("guide"),
                    "key": "guide",
                    "tip": action_tooltip("guide"),
                },
                {
                    "label": action_caption("help"),
                    "key": "help",
                    "tip": action_tooltip("help"),
                },
            ],
            remember=self.remember,
        )
        if pressed == "toolAction_run":
            self.track("toolAction_run")
            self.fit_bursts()
        elif pressed == "toolAction_restart":
            self.track("toolAction_restart")
            self.model.refit()
        elif pressed == "auto":
            self.track("auto")
            self.auto_extract()
        elif pressed == "optimize":
            self.track("optimize")
            self.optimize()
        elif pressed == "save_fit":
            self.save_fit()
        elif pressed == "Stop":
            self.stop()
        elif pressed == "clear_files":
            self.model.clear_files()
        elif pressed == "save_results":
            try:
                self.model.export_results()
            except Exception as exc:
                self.model.status_text = f"Error: {exc}"
        elif pressed in self.DIALOGS:
            self.browse(pressed)
        elif pressed == "guide":
            self.start_guide()
        elif pressed == "help":
            self.show_help()
        if running or self.job.progress:
            im.text_wrapped(self.job.progress or self.model.status_text)
        elif self.job.error:
            im.push_style_color(im.Col.TEXT, (0.9, 0.4, 0.4, 1.0))
            im.text_wrapped(self.job.error)
            im.pop_style_color()
        else:
            im.text_wrapped(self.model.status_text)
        ok, n_files = self.model.input_status()
        if ok:
            im.push_style_color(im.Col.TEXT, (0.3, 0.85, 0.4, 1.0))
            message = str(tr("IRF and background loaded for {detector}; {count} burst file(s)"))
            im.text_wrapped(message.format(detector=self.model.current_detector, count=n_files))
            im.pop_style_color()
        else:
            im.push_style_color(im.Col.TEXT, (0.8, 0.8, 0.4, 1.0))
            message = str(tr("No IRF and background for {detector} yet; {count} burst file(s)"))
            im.text_wrapped(message.format(
                detector=self.model.current_detector or str(tr("the detector")), count=n_files,
            ))
            im.pop_style_color()
        self.remember("input_status")
        im.separator()
        target = (
            self.model.values_snapshot() if running else self.model
        )  # edits during a run go to a throw-away copy
        im.begin_disabled(running)
        draw_sections(self._fields(), target, self.form)
        im.end_disabled()
        for attr, key in (
            ("fit_model", "fit_model"),
            ("micro_time_start", "window_start"),
            ("micro_time_stop", "window_stop"),
            ("current_detector", "detector"),
        ):
            if attr in self.form.rects:
                self.item_rects[key] = tuple(self.form.rects[attr])

    def _irf(self, box=None) -> None:
        self.remember("irf", box)
        im.text_wrapped(
            tr("IRF and background as the fit sees them: the estimated or loaded patterns after shift, window and threshold.")
        )
        draw_sections(self.irf_sections, self.model, self.form)

    def _patterns(self, box=None) -> None:
        self.remember("patterns", box)
        running = self.job.busy
        im.text_wrapped(
            tr(
                "Measured IRF and background files replace the estimate from the non-burst photons "
                "for the detectors they are set for."
            )
        )
        target = self.model.values_snapshot() if running else self.model
        im.begin_disabled(running)
        draw_sections(self.pattern_sections, target, self.form)
        pressed = button_row(
            [
                {
                    "label": str(tr("Add IRF files")),
                    "key": "add_irf_files",
                    "enabled": not running,
                    "tip": str(tr("Choose measured IRF files (scatter or short-lifetime reference).")),
                },
                {
                    "label": str(tr("Clear IRF")),
                    "key": "clear_irf_files",
                    "enabled": bool(self.model.irf_file_rows()) and not running,
                    "tip": str(tr("Forget the measured IRF files; Auto IRF/background estimates the IRF again.")),
                },
                {
                    "label": str(tr("Add background files")),
                    "key": "add_bg_files",
                    "enabled": not running,
                    "tip": str(tr("Choose measured background files (a sample-free measurement).")),
                },
                {
                    "label": str(tr("Clear background")),
                    "key": "clear_bg_files",
                    "enabled": bool(self.model.bg_file_rows()) and not running,
                    "tip": str(tr("Forget the measured background files; Auto IRF/background estimates the background again.")),
                },
            ],
            remember=self.remember,
        )
        im.end_disabled()
        if pressed == "clear_irf_files":
            self.model.clear_irf_files()
        elif pressed == "clear_bg_files":
            self.model.clear_bg_files()
        elif pressed in self.DIALOGS:
            self.track(pressed)
            self.browse(pressed)

    def _detectors(self, box=None) -> None:
        self.remember("detectors", box)
        if self.job.busy:
            im.text_wrapped(str(tr("Detector settings are locked while Burst MLE is running.")))
            return
        self.editor.draw()

    def _decay(self, box=None) -> None:
        self.remember("decay", box)
        curves = self.model.fit_curves
        if curves is None:
            im.text_wrapped(
                tr("No fit yet. Add burst files and press Auto IRF/background: the decay, the model, the IRF and the background of the current file appear here.")
            )
            return
        if implot.begin_plot("Decay histogram and fit", (-1, -1)):
            implot.setup_axes("Micro-time window (channels, VV then VH)", "Photons")
            implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
            implot.plot_scatter("Data (VV|VH)", curves.x, curves.data, size=2.5)
            drawn = np.isfinite(curves.model) & (curves.model > 0)  # a log axis cannot show the empty part before a tail
            implot.plot_line("Model (fit)", curves.x[drawn], curves.model[drawn])
            if curves.irf is not None:
                implot.plot_line("IRF", curves.x, curves.irf)
            implot.plot_line("Background", curves.x, curves.background)
            implot.end_plot()

    def _inspect(self, box=None) -> None:
        bursts = self.model.n_bursts
        if not bursts:
            im.text_wrapped(
                tr("No bursts loaded: add burst files to inspect one burst's decay per detector.")
            )
            return
        draw_sections(self.burst_sections, self.model, self.form)
        data = self.model.inspected_burst()
        if not data:
            im.text_wrapped(tr("The raw photon file of this burst could not be read."))
            return
        if implot.begin_plot("Inspected burst", (-1, -1)):
            implot.setup_axes("Micro-time window (channels, VV then VH)", "Photons")
            for det, hist in data.items():
                implot.plot_line(det, list(range(hist.size)), hist)
            implot.end_plot()
        im.text(f"burst {self.model.nav_burst} of {bursts}")

    def _lifetimes(self, box=None) -> None:
        self.remember("distribution", box)
        histograms = fit_view.lifetime_histograms(
            fit_view.burst_lifetimes(self.model.burst_results)
        )
        if not histograms:
            im.text_wrapped(
                tr("No burst lifetimes yet: press Fit bursts. The histogram of the fitted lifetimes appears here.")
            )
            return
        everything = [
            v for h in fit_view.burst_lifetimes(self.model.burst_results).values() for v in h
        ]
        if self.gate_min is None or self.gate_max is None:
            self.gate_min, self.gate_max = float(min(everything)), float(max(everything))
        peak = max(float(counts.max()) for _, _, counts, _ in histograms)
        if implot.begin_plot("Fitted lifetime histogram", (-1, -1)):
            implot.setup_axes("Lifetime tau (ns)", "Bursts")
            for label, centres, counts, width in histograms:
                implot.plot_bars(label, centres, counts, bar_size=width * 0.9)
            rect = implot.drag_rect(
                502, self.gate_min, 0.0, self.gate_max, max(peak, 1.0), REGION_FILL
            )
            if rect.modified:
                self.gate_min, self.gate_max = rect.x_min, max(rect.x_min, rect.x_max)
            implot.end_plot()
        inside = sum(1 for v in everything if self.gate_min <= v <= self.gate_max)
        im.text(f"{inside} of {len(everything)} lifetimes inside the gate")

    def _results(self, box=None) -> None:
        if not self.model.burst_results:
            im.text_wrapped(tr("No lifetime table yet: press Fit bursts."))
            return
        draw_sections(self.tables, self.model, self.form)

    def _sync_editor_read_only(self) -> None:
        """Retain the editor's own policy while locking all of its dialogs during a fit."""
        if self.job.busy:
            if self._editor_read_only_before_job is None:
                self._editor_read_only_before_job = self.editor.read_only
            self.editor.read_only = True
        elif self._editor_read_only_before_job is not None:
            self.editor.read_only = self._editor_read_only_before_job
            self._editor_read_only_before_job = None

    def _render(self) -> None:
        changed = self.job.poll()
        self._sync_editor_read_only()
        if not self.job.busy:
            self.editor.poll()
            if self.model.detector_editor_data is not None:
                status = self.model.status_text
                self.editor.load_definition(self.model.detector_editor_data)
                self.model.detector_editor_data = None
                self.model.status_text = status
        if changed or self.job.busy:
            ctx = get_current_context()
            ctx.request_frame_at(ctx.io.now + 0.1)
        w, h = im.get_main_viewport().size
        self.docks.draw((0.0, 0.0, float(w), float(h)))
        frame = (0.0, 0.0, float(w), float(h))
        self._sync_editor_read_only()
        im.begin_disabled(self.editor.read_only)
        self.editor.draw_dialogs(frame)
        im.end_disabled()
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

    # -- host input --------------------------------------------------------------------------------------- #
    def files_dropped(self, paths) -> bool:
        if self.job.busy:
            self.model.status_text = str(
                tr("Wait for the running Burst MLE job before changing its inputs.")
            )
            return False
        paths = list(paths)
        return bool(paths) and self.model.add_files(paths) > 0

    on_paths_dropped = files_dropped

    def close(self) -> None:
        self.model.stop()
        if self._editor_read_only_before_job is not None:
            self.editor.read_only = self._editor_read_only_before_job
            self._editor_read_only_before_job = None
        self.editor.close()


def create_app(**kwargs) -> MleNativeApp:
    """Factory named by ``entrypoints.emtk``."""
    from chisurf.emtk.i18n import install

    install()
    return MleNativeApp(**kwargs)
