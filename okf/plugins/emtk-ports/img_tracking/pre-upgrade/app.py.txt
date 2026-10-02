"""Native EMTK particle-tracking surface."""

from __future__ import annotations

import numpy as np
from emtk import im, implot
from emtk.app import ImApp

from .gui.view_model import ImgTrackingViewModel
from .strings import install_translations, tr

install_translations()


class ImgTrackingApp(ImApp):
    def __init__(self, model: ImgTrackingViewModel | None = None) -> None:
        self.model = model or ImgTrackingViewModel()
        self.csv_target = ""
        super().__init__(self.render)

    def render(self) -> None:
        im.begin(tr("Particle tracking"), (0, 0, *im.get_main_viewport().size))
        im.heading(tr("Particle tracking"), level=2)
        changed, filename = im.input_text(tr("Image stack"), self.model.filename)
        im.set_item_tooltip(tr("Image stack to track; simulation can be used without a file."))
        if changed:
            self.model.set_filename(filename)
        changed, simulate = im.checkbox(tr("Simulate movie"), bool(self.model.use_simulation))
        im.set_item_tooltip(tr("Generate a deterministic Brownian-particle movie for validation."))
        if changed:
            self.model.use_simulation = bool(simulate)
        if im.button(tr("Track")):
            im.set_item_tooltip(tr("Detect particles, link trajectories and fit transport."))
            self.model.compute()
        else:
            im.set_item_tooltip(tr("Detect particles, link trajectories and fit transport."))
        im.separator()
        changed, threshold = im.input_float(tr("Detection threshold"), float(self.model.threshold), step=0.5, step_fast=2.0)
        im.set_item_tooltip(tr("Detection threshold in noise units."))
        if changed:
            self.model.threshold = max(0.0, float(threshold))
        changed, max_distance = im.input_float(tr("Max link distance"), float(self.model.max_distance), step=0.5, step_fast=2.0)
        im.set_item_tooltip(tr("Maximum distance allowed when linking particles between frames."))
        if changed:
            self.model.max_distance = max(0.1, float(max_distance))
        im.text_wrapped(self.model.results_text)
        if self.model.result is not None:
            if implot.begin_plot(tr("Trajectories"), (-1, 280)):
                for series in self.model.track_series():
                    implot.plot_line(series["name"], np.asarray(series["x"]), np.asarray(series["y"]))
                implot.end_plot()
            if implot.begin_plot(tr("Mean squared displacement"), (-1, 220)):
                for series in self.model.msd_series():
                    implot.plot_line(series["name"], np.asarray(series["x"]), np.asarray(series["y"]))
                implot.end_plot()
            _, self.csv_target = im.input_text(tr("CSV output"), self.csv_target)
            im.set_item_tooltip(tr("Destination for linked detections."))
            if im.button(tr("Export CSV")):
                im.set_item_tooltip(tr("Write linked detections to CSV."))
                if self.csv_target:
                    self.model.export_csv(self.csv_target)
        im.end()


def make_app(coordinator=None) -> ImgTrackingApp:
    """Build the app; *coordinator* is the imaging hub, which wires itself in afterwards."""
    from chisurf.emtk.i18n import install
    install()
    return ImgTrackingApp()

