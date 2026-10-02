"""Native EMTK Fourier-ring-correlation surface."""

from __future__ import annotations

import numpy as np
from emtk import im, implot
from emtk.app import ImApp

from .gui.view_model import FrcViewModel
from .strings import install_translations, tr

install_translations()


class ImgFrcApp(ImApp):
    def __init__(self, model: FrcViewModel | None = None) -> None:
        self.model = model or FrcViewModel()
        self.csv_target = ""
        self.message = self.model.status
        super().__init__(self.render)

    def render(self) -> None:
        im.begin(tr("FRC resolution"), (0, 0, *im.get_main_viewport().size))
        im.heading(tr("FRC resolution"), level=2)
        changed, filename = im.input_text(tr("Image stack"), self.model.filename)
        im.set_item_tooltip(tr("TIFF stack or photon-stream image to measure."))
        if changed and filename != self.model.filename:
            self.model.set_filename(filename)
            self.message = self.model.status
        splits = ["even_odd", "halves", "channels", "two_files"]
        changed, index = im.combo(tr("Split"), splits.index(self.model.split), splits)
        im.set_item_tooltip(tr("How the acquisition is divided into independent images."))
        if changed:
            self.model.split = splits[index]
        criteria = ["fixed_1/7", "half_bit", "two_sigma"]
        changed, index = im.combo(tr("Criterion"), criteria.index(self.model.criterion), criteria)
        im.set_item_tooltip(tr("Threshold criterion used to report the resolution."))
        if changed:
            self.model.criterion = criteria[index]
        changed, smooth = im.input_int(tr("Smoothing"), int(self.model.smooth), step=1)
        im.set_item_tooltip(tr("Smoothing width applied to the FRC curve."))
        if changed:
            self.model.smooth = max(0, int(smooth))
        if im.button(tr("Measure")):
            im.set_item_tooltip(tr("Calculate the Fourier-ring-correlation resolution."))
            self.model.compute()
            self.message = self.model.status
        else:
            im.set_item_tooltip(tr("Calculate the Fourier-ring-correlation resolution."))
        im.text_wrapped(self.message)
        if self.model.result is not None:
            if implot.begin_plot(tr("FRC curve"), (-1, 280)):
                for series in self.model.frc_series():
                    implot.plot_line(series["name"], np.asarray(series["x"]), np.asarray(series["y"]))
                implot.end_plot()
            _, self.csv_target = im.input_text(tr("CSV output"), self.csv_target)
            im.set_item_tooltip(tr("Destination for the FRC curve and threshold values."))
            if im.button(tr("Export CSV")):
                im.set_item_tooltip(tr("Write the measured FRC curve to CSV."))
                self.message = self.model.export_csv(self.csv_target) if self.csv_target else tr("Choose a CSV output path first.")
        im.end()


def make_app(coordinator=None) -> ImgFrcApp:
    """Build the app; *coordinator* is the imaging hub, which wires itself in afterwards."""
    from chisurf.emtk.i18n import install
    install()
    return ImgFrcApp()

