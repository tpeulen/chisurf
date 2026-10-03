"""The emtk H2MM app over :class:`H2mmViewModel`: no Qt tool behind it (cards H0, H1, H3 core).

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

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget
from chisurf.emtk.jobs import SnapshotJob
from chisurf.plugins.emtk_layout import LabelColumn, button_row, cap_widths, group_by_width, labelled

from .model import H2mmViewModel
from .plots import ResultPlots

HERE = Path(__file__).parent


class H2mmNativeApp(TourTarget, ImApp):
    """Immediate-mode H2MM app: settings form, actions through ``SnapshotJob``, result tables and plots."""

    def __init__(self, model: H2mmViewModel | None = None) -> None:
        self.model = model or H2mmViewModel()
        self.job = SnapshotJob(self.model)
        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        self.plots = ResultPlots()
        self.form = FormState()
        spec = load_view_spec(str(HERE / "h2mm.view.json"))
        sections = spec["sections"]
        self.settings_sections = [s for s in sections if s.get("type") == "panel"]
        self.tables = [s for s in sections if s.get("type") == "table"]
        for table, height in zip(self.tables, (110, 90)):
            table["height"] = height
        cap_widths(self.settings_sections)
        self.labels = LabelColumn()
        self._measured = False
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
        self.docks = DockManager(
            Split("h", 0.38, Region("controls"), Split("v", 0.34, Region("results"), Split("h", 0.5, Region("tdp"), Region("dwells")))),
            name="burst_h2mm",
        )
        self.docks.add_window("controls", "H2MM settings", self._controls, dock="controls", closable=False)
        self.docks.add_window("results", "Rates and states", self._results, dock="results", closable=False)
        self.docks.add_window("tdp", "Transition density (TDP)", self._tdp, dock="tdp", closable=False)
        self.docks.add_window("dwells", "Dwell time distributions", self._dwells, dock="dwells", closable=False)
        super().__init__(gui=self._render)

    # -- tour / help -------------------------------------------------------------------------------------- #
    def start_guide(self) -> None:
        self.tour.start()

    def show_help(self) -> None:
        self.help_window.show()

    def track(self, name: str) -> None:
        self.on_used(name)

    # -- actions -------------------------------------------------------------------------------------------- #
    def run(self) -> None:
        problem = self.model.can_run()
        if problem:
            self.model.status_text = problem
            return
        self.model.status_text = "Fitting H2MM models ..."
        self.job.start("compute")

    def stop(self) -> None:
        self.model.stop()

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
        pressed = button_row(
            [
                {"label": "Run H2MM", "key": "toolAction_run", "enabled": not problem and not running,
                 "tip": "Fit the photon-by-photon HMM to the bursts of the folder: every state count of the scan, then the "
                        "criterion picks one." if not problem else
                        "Fit the photon-by-photon HMM. " + problem},
                {"label": "Stop", "key": "Stop", "enabled": running,
                 "tip": "Stop the running fit at its next progress checkpoint." if running
                 else "Nothing is running; a fit in progress can be stopped here."},
                {"label": "Guide", "key": "guide", "tip": "Start a step-by-step guided tour of this tool."},
                {"label": "Help", "key": "help", "tip": "Open the help window with reference documentation."},
            ],
            remember=self.remember,
        )
        if pressed == "toolAction_run":
            self.track("toolAction_run")
            self.run()
        elif pressed == "Stop":
            self.stop()
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
        if running:  # edits during a fit go to a throw-away copy: the run has its own snapshot
            target = copy.copy(self.model)
            target._observers = []
        im.begin_disabled(running)
        draw_sections(self._fields(), target, self.form)
        im.end_disabled()
        if "data_folder" in self.form.rects:
            self.item_rects["folder"] = tuple(self.form.rects["data_folder"])

    def _results(self, box=None) -> None:
        self.remember("results", box)
        im.text_wrapped(self.model.status_text)
        if self.model.analysis is None:
            im.text_wrapped("No H2MM fit yet. Select a burst folder, set the detector channels and press Run H2MM.")
            return
        draw_sections(self.tables, self.model, self.form)

    def _tdp(self, box=None) -> None:
        self.plots.draw_tdp(self.model.analysis)

    def _dwells(self, box=None) -> None:
        self.plots.draw_dwells(self.model.analysis)

    def _render(self) -> None:
        if self.job.poll() or self.job.busy:
            ctx = get_current_context()
            ctx.request_frame_at(ctx.io.now + 0.1)
        w, h = im.get_main_viewport().size
        self.docks.draw((0.0, 0.0, float(w), float(h)))
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


def create_app(**kwargs) -> H2mmNativeApp:
    """Factory named by ``entrypoints.emtk``."""
    from chisurf.emtk.i18n import install

    install()
    return H2mmNativeApp(**kwargs)
