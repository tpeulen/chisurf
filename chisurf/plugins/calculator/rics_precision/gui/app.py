"""Native emtk RICS-precision calculator: the planner for a raster scan.

The settings form and the table of numbers are the view spec ``precision_emtk.view.json``
(field names, ranges and descriptions are those of the Qt spec ``precision.view.json``)
drawn by :func:`emtk.view_form.draw_sections`; the table is its ``data_table``. Only the
error-versus-dwell plot, the file dialog of Export CSV, Help and Guide are drawn here. All
state and work is in :class:`~.view_model.PrecisionViewModel`; the sweep runs on a
:class:`~chisurf.emtk.jobs.SnapshotJob`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import emtk.im as im
import emtk.implot as implot
import numpy as np
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog
from emtk.view_form import FormState, draw_sections

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.emtk.jobs import SnapshotJob

from .view_model import PrecisionViewModel

HERE = Path(__file__).parent
#: Series colours carry data (the Qt plot's blue curve and orange marker).
CURVE_COLOUR = (76, 155, 232, 255)
YOURS_COLOUR = (232, 115, 76, 255)
EXPORT_NAME = "rics_precision.csv"


def finite_runs(x: np.ndarray, y: np.ndarray) -> list[tuple[np.ndarray, np.ndarray]]:
    """The runs of consecutive plottable points (finite, positive: the axes are logarithmic).

    A dwell time the estimator could not realise is a gap in the curve, not a point at zero
    and not a line drawn across it.
    """
    ok = np.isfinite(x) & np.isfinite(y) & (x > 0) & (y > 0)
    runs, start = [], None
    for i, good in enumerate(ok):
        if good and start is None:
            start = i
        elif not good and start is not None:
            runs.append((x[start:i], y[start:i]))
            start = None
    if start is not None:
        runs.append((x[start:], y[start:]))
    return runs


class RicsPrecisionApp(ImApp):
    """Predict how precisely a raster scan measures D, and the best pixel dwell time."""

    def __init__(self, model: PrecisionViewModel | None = None) -> None:
        self.model = model or PrecisionViewModel()
        self.job = SnapshotJob(self.model)
        spec = json.loads((HERE / "precision_emtk.view.json").read_text(encoding="utf-8"))
        self.panels = {panel["name"]: panel for panel in spec["sections"]}
        self.form = FormState()
        self.item_rects: dict[str, tuple] = {}
        #: the last thing the window did that the verdict line does not say (an export)
        self.notice = ""
        self.dialog: FileDialog | None = None
        self.file_window = DialogWindow("Export precision sweep", size=(760.0, 520.0),
                                        key="rics-export")
        self._plot_signature = None
        self.help_window = EmTkHelpWindow(
            title="RICS precision — Help & Reference", resource=HERE / "help.md", owner=self,
            size=(720.0, 540.0))
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json", owner=self, wait_for_controls=True,
            get_target_rect=lambda key: self.item_rects.get(key) or self.form.rects.get(key))
        self.form.on_used = self.tour.notify_used
        self.docks = DockManager(Split("h", 0.40, Region("settings"),
                                       Split("v", 0.5, Region("plot"), Region("numbers"))))
        self.docks.add_window("settings", "Settings", self.draw_settings,
                              dock="settings", closable=False)
        self.docks.add_window("plot", "Error vs dwell", self.draw_plot, dock="plot", closable=False)
        self.docks.add_window("numbers", "Numbers", self.draw_numbers, dock="numbers",
                              closable=False)
        super().__init__(gui=self.render, continuous=False)

    # -- actions ------------------------------------------------------------------
    def start_guide(self) -> None:
        """Start the guided tour (hosts with their own Guide button call this)."""
        self.tour.start()

    def show_help(self) -> None:
        """Open the help window."""
        self.help_window.show()

    def predict(self) -> bool:
        """Start the sweep on a worker; refused while one runs."""
        if self.job.busy:
            return False
        self.notice = ""
        self.model.busy = True
        started = self.job.start("predict")
        if not started:
            self.model.busy = False
        return started

    def start_export(self) -> bool:
        """Open the file dialog of Export CSV; before a prediction there is nothing to write."""
        if self.model.sweep is None:
            self.notice = "Predict something first."
            return False
        self.notice = ""
        self.dialog = FileDialog("Export precision sweep", mode="save", filename=EXPORT_NAME,
                                 filters="CSV (*.csv)")
        self.file_window = DialogWindow("Export precision sweep", size=(760.0, 520.0),
                                        key="rics-export")
        return True

    def write_csv(self, path) -> None:
        """Write the sweep as CSV (:class:`ValueError` before a prediction)."""
        self.model.export_csv(path)

    def _export_to(self, chosen: str) -> None:
        path = Path(chosen)
        if path.suffix.lower() != ".csv":
            path = path.with_suffix(".csv")
        try:
            self.write_csv(path)
            self.notice = f"Wrote {path}"
        except Exception as exc:  # noqa: BLE001 - shown to the user
            self.notice = f"Could not write {path.name}: {exc}"

    def status_line(self) -> str:
        """What the status line says: the sweep's progress, an export notice, or the verdict."""
        if self.job.busy:
            return self.job.progress or "Predicting…"
        return self.notice or self.model.status

    # -- windows ------------------------------------------------------------------
    def draw_settings(self, box: Any) -> None:
        """The left window: Predict, Export CSV, the four setting panels, then Guide and Help."""
        im.begin_disabled(self.job.busy)
        draw_sections(self.panels["settings"]["sections"], self.model, self.form)
        im.end_disabled()
        if im.button("Guide"):
            self.start_guide()
        im.set_item_tooltip("A step-by-step walk through the tool.")
        self.item_rects["guide"] = im.get_item_rect()
        im.same_line()
        if im.button("Help"):
            self.show_help()
        im.set_item_tooltip("The short help page: reading the curve and what moves the answer.")
        self.item_rects["help"] = im.get_item_rect()

    def draw_plot(self, box: Any) -> None:
        """Predicted error against pixel dwell time on log axes, with the user's own setting."""
        sweep = self.model.sweep
        series = self.model.sweep_series() if sweep is not None else []
        if implot.begin_plot("##sweep", (-1, -1)):
            implot.setup_axes("pixel dwell / µs", "predicted error / %")
            implot.setup_axis_scale(implot.AXIS_X1, implot.SCALE_LOG10)
            implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
            implot.setup_legend()
            if series:
                signature = id(sweep)
                self._plot_signature = signature
                for item in series:
                    xs = np.asarray(item.get("x", []), dtype=np.float64)
                    ys = np.asarray(item.get("y", []), dtype=np.float64)
                    if item.get("no_line"):
                        keep = np.isfinite(xs) & np.isfinite(ys) & (xs > 0) & (ys > 0)
                        if keep.any():
                            implot.set_next_marker_style(implot.MARKER_DIAMOND, 9.0, YOURS_COLOUR)
                            implot.plot_scatter(item.get("name", "your setting"), xs[keep], ys[keep])
                        continue
                    for index, (rx, ry) in enumerate(finite_runs(xs, ys)):
                        label = item.get("name", "predicted error") if index == 0 else f"##run{index}"
                        implot.set_next_line_style(CURVE_COLOUR, 2.0)
                        implot.set_next_marker_style(implot.MARKER_CIRCLE, 4.0, CURVE_COLOUR)
                        implot.plot_line(label, rx, ry)
            else:
                implot.plot_dummy("press Predict to sweep the dwell time")
            implot.end_plot()
        im.set_item_tooltip(
            "Predicted relative error on D against pixel dwell time (log axes), with your own "
            "setting marked. Both ends rise: too fast and the molecule has not moved between "
            "pixels, too slow and it has already decorrelated.")
        self.item_rects["plot"] = im.get_item_rect()

    def draw_numbers(self, box: Any) -> None:
        """The right-hand lower window: the verdict line and the table of numbers."""
        im.text_wrapped(self.status_line())
        im.set_item_tooltip("The verdict on your own dwell time, the progress of a sweep, or what "
                            "went wrong.")
        self.item_rects["status"] = im.get_item_rect()
        draw_sections(self.panels["numbers"]["sections"], self.model, self.form, titles=False)

    # -- one frame ----------------------------------------------------------------
    def render(self) -> None:
        self.job.poll()
        if self.job.error:                                  # an exception out of the worker itself
            self.model._status = f"Prediction failed: {self.job.error}"
        self.model.busy = self.job.busy
        request, self.model.request = self.model.request, ""
        if request == "predict":
            self.predict()
        elif request == "export":
            self.start_export()
        viewport = im.get_main_viewport()
        box = (*viewport.pos, *viewport.size)
        self.form.rects.clear()
        im.begin_disabled(self.dialog is not None)
        self.docks.draw(box)
        im.end_disabled()
        self._draw_file_dialog(box)
        self.help_window.draw(box)
        self.tour.draw(*viewport.size)
        # frames follow while a sweep runs (its result is polled), and while a dialog is open
        self.continuous = self.job.busy or self.dialog is not None

    def _draw_file_dialog(self, box: Any) -> None:
        if self.dialog is None:
            return
        pressed = self.file_window.begin(box)
        result = self.dialog.draw()
        self.file_window.end()
        if result:
            self.dialog = None
            self._export_to(str(result[0]))
        elif result is False or pressed == "close":
            self.dialog = None

    # -- persistence ----------------------------------------------------------------
    def export_settings(self) -> dict:
        """The inputs of the planner."""
        return self.model.export_settings()

    def restore_settings(self, state: dict) -> None:
        """Restore :meth:`export_settings`."""
        self.model.restore_settings(state)
        self.form.buffers.clear()

    def close(self) -> None:
        """Stop waiting for a running sweep (its worker is a daemon thread)."""
        self.job.thread = None


def make_app(**kwargs: Any) -> RicsPrecisionApp:
    """Build the standalone planner (the manifest's ``entrypoints.emtk``)."""
    from chisurf.emtk.i18n import install

    install()
    return RicsPrecisionApp()


__all__ = ["RicsPrecisionApp", "make_app", "finite_runs"]
