"""Native emtk photon-counting-histogram tool (form from ``pch.view.json``).

The form is a view spec drawn by :func:`emtk.view_form.draw_form`; only the two
plots (intensity trace, histogram with its fit range) and the file dialog are
hand-drawn. All state and work is in :class:`~.model.PchModel`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from emtk import im, implot
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog
from emtk.view_form import FormState, draw_form

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.emtk.jobs import SnapshotJob

from .model import TTTR_FILE_FILTER, PchModel

HERE = Path(__file__).parent

#: Ids of the two fit-range lines on the histogram plot.
_LINE_LOW, _LINE_HIGH = 101, 102


class PchApp(ImApp):
    """Photon Counting Histogram: load, compute, fit and save."""

    def __init__(self, model: PchModel | None = None) -> None:
        self.model = model or PchModel()
        self.job = SnapshotJob(self.model)
        self.model.runner = self.start_job
        self.spec = json.loads((HERE / "pch.view.json").read_text(encoding="utf-8"))
        self.form = FormState()
        self.dialog: FileDialog | None = None
        self.dialog_kind = ""
        self.item_rects: dict[str, tuple] = {}
        self.help_window = EmTkHelpWindow(
            title="PCH Analysis — Help", resource=HERE / "help.md", owner=self
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            owner=self,
            wait_for_controls=True,
            get_target_rect=lambda key: self.item_rects.get(key) or self.form.rects.get(key),
        )
        self.form.on_used = self.tour.notify_used
        self._outcome = (None, None, None)
        self._reported_error = ""
        self.docks = DockManager(Split("h", 0.6, Region("plots"), Region("settings")))
        self.docks.add_window("plots", "Photon counting histogram", self.draw_plots,
                              dock="plots", closable=False)
        self.docks.add_window("settings", "PCH settings", self.draw_settings,
                              dock="settings", closable=False)
        super().__init__(self.render, continuous=True)

    # ── jobs ───────────────────────────────────────────────────────────
    def start_job(self, method: str) -> bool:
        """Run the model method *method* on a snapshot in a worker thread."""
        self._reported_error = ""
        return self.job.start(method)

    # ── one frame ──────────────────────────────────────────────────────
    def render(self) -> None:
        self.job.poll()
        self.model.busy = self.job.busy
        if self.job.error and self.job.error != self._reported_error:
            # A worker that raised: show it once; the model clears it on the next action.
            self._reported_error = self.job.error
            self.model.error_text = f"{self.job.error}"
        vp = im.get_main_viewport()
        box = (*vp.pos, *vp.size)
        self.form.rects.clear()
        self._open_requested_dialog()
        self.docks.draw(box)
        self._draw_dialog(box)
        self._tour_outcomes()
        self.help_window.draw(box)
        self.tour.draw(*vp.size)

    def _tour_outcomes(self) -> None:
        """Tell the tour when a file is loaded, a histogram computed or a fit done.

        The tour waits for the outcome, not the button press: pressing *Load
        TTTR* only opens a dialog. Each outcome step is highlighted on the button
        that produces it.
        """
        for key, button in (("file_loaded", "load"), ("computed", "compute"), ("fitted", "fit")):
            if button in self.form.rects:
                self.item_rects[key] = self.form.rects[button]
        model = self.model
        now = (model.filename or None, id(model.result) if model.result else None,
               id(model.fit_result) if model.fit_result else None)
        for key, before, current in zip(("file_loaded", "computed", "fitted"), self._outcome, now):
            if current is not None and current != before:
                self.tour.notify_used(key)
        self._outcome = now

    # ── windows ────────────────────────────────────────────────────────
    def draw_settings(self, box: Any) -> None:
        """The form window: Help/Guide, then the spec."""
        if im.button("Help"):
            self.help_window.show()
        im.set_item_tooltip("Explain the photon counting histogram, the settings and the outputs.")
        self.item_rects["help"] = im.get_item_rect()
        im.same_line()
        if im.button("Guide"):
            self.tour.start()
        im.set_item_tooltip("Walk through loading a file, computing the histogram and fitting it.")
        self.item_rects["guide"] = im.get_item_rect()
        im.separator()
        draw_form(self.spec, self.model, self.form)

    def draw_plots(self, box: Any) -> None:
        """The intensity trace above the histogram."""
        _, avail_h = im.get_content_region_avail()[:2]
        height = max(80.0, (avail_h - 8.0) / 2.0)
        self._trace_plot(height)
        self._histogram_plot(height)

    def _trace_plot(self, height: float) -> None:
        model = self.model
        if implot.begin_plot("Intensity trace##trace", (-1.0, height), implot.FLAGS_NO_LEGEND):
            implot.setup_axes("Time (s)", "Photon Counts")
            if len(model.trace_x):
                implot.plot_line("counts", model.trace_x, model.trace_y)
            implot.end_plot()
        self.item_rects["trace_plot"] = im.get_item_rect()

    def _histogram_plot(self, height: float) -> None:
        model = self.model
        if implot.begin_plot("Photon counting histogram##hist", (-1.0, height)):
            implot.setup_axes("Photon Count k", "P(k)")
            implot.setup_legend(implot.LOCATION_NORTH_EAST)
            implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
            k, p = model.histogram_points()
            if len(k):
                implot.plot_scatter("P(k)", k, p)
            kf, pf = model.fit_curve()
            if len(kf):
                implot.plot_line("fit", kf, pf)
            if model.result is not None:
                low = implot.drag_line_x(_LINE_LOW, float(model.fit_low))
                high = implot.drag_line_x(_LINE_HIGH, float(model.fit_high))
                if low.modified or high.modified:
                    model.set_region(float(low.value), float(high.value))
                    self.tour.notify_used("region")
            implot.end_plot()
        im.set_item_tooltip(
            "Drag the two vertical lines to choose the k range of the fit; "
            "the χ² of an existing fit is recomputed over it."
        )
        self.item_rects["region"] = im.get_item_rect()

    # ── file dialog ────────────────────────────────────────────────────
    def _open_requested_dialog(self) -> None:
        """Turn the model's ``dialog`` request into a :class:`FileDialog`."""
        kind, self.model.dialog = self.model.dialog, ""
        if not kind or self.dialog is not None:
            return
        directory = self.model.folder or None
        if kind == "open":
            self.dialog = FileDialog("Open TTTR", mode="open", filters=TTTR_FILE_FILTER,
                                     directory=directory)
        else:
            self.dialog = FileDialog("Save Base Name", mode="save", filename="results",
                                     filters="All Files (*)", directory=directory)
        self.dialog_kind = kind

    def _draw_dialog(self, box: Any) -> None:
        if self.dialog is None:
            return
        if im.begin(self.dialog.title):
            result = self.dialog.draw()
            if result:
                kind, self.dialog = self.dialog_kind, None
                if kind == "open":
                    self.tour.notify_used("load")
                    self.model.open_file(result[0])
                else:
                    self.model.save_to(result[0])
            elif result is False:
                self.dialog = None
        im.end()

    # ── files dropped on the window ────────────────────────────────────
    def on_paths_dropped(self, paths: Any) -> None:
        self.model.on_paths_dropped(list(paths))

    def files_dropped(self, paths: Any) -> bool:
        self.on_paths_dropped(paths)
        return bool(paths)

    # ── persistence ────────────────────────────────────────────────────
    def export_settings(self) -> dict:
        return self.model.export_settings()

    def restore_settings(self, state: dict) -> None:
        self.model.restore_settings(state)

    def close(self) -> None:
        """Nothing to release: workers are daemon threads and no file stays open."""


def make_app() -> PchApp:
    """Factory named by the manifest's ``entrypoints.emtk``."""
    return PchApp()
