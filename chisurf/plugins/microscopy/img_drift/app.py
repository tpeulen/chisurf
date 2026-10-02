"""Native EMTK drift-correction surface."""

from __future__ import annotations

import numpy as np
from emtk import i18n, im, implot
from emtk.app import ImApp

from .gui.view_model import DriftViewModel
from .strings import install_translations, tr

install_translations()


class ImgDriftApp(ImApp):
    """Measure, inspect and export inter-frame image drift."""

    def __init__(self, model: DriftViewModel | None = None) -> None:
        self.model = model or DriftViewModel()
        self.stack_target = ""
        self.csv_target = ""
        self.message = self.model.status
        super().__init__(self.render)

    def _text(self, label: str, value: str, tip: str) -> tuple[bool, str]:
        changed, result = im.input_text(tr(label), value)
        im.set_item_tooltip(tr(tip))
        return changed, result

    def render(self) -> None:
        im.begin(tr("Drift correction"), (0, 0, *im.get_main_viewport().size))
        im.heading(tr("Drift correction"), level=2)
        changed, value = self._text("Image stack", self.model.filename, "TIFF stack or photon-stream image to analyze.")
        if changed and value != self.model.filename:
            self.model.set_filename(value)
            self.message = self.model.status
        im.same_line()
        if im.button(tr("Measure")):
            im.set_item_tooltip(tr("Measure inter-frame drift for the selected channel."))
            ok = self.model.compute()
            self.message = self.model.status if ok else self.model.status
        else:
            im.set_item_tooltip(tr("Measure inter-frame drift for the selected channel."))
        im.separator()
        im.heading(tr("Parameters"), level=3)
        changed, reference = im.combo(tr("Reference"), ["first", "mean", "middle"].index(self.model.reference), ["first", "mean", "middle"])
        im.set_item_tooltip(tr("Frame used as the drift reference."))
        if changed:
            self.model.reference = ["first", "mean", "middle"][reference]
        changed, mode = im.combo(tr("Boundary mode"), ["wrap", "nearest", "reflect"].index(self.model.mode), ["wrap", "nearest", "reflect"])
        im.set_item_tooltip(tr("How pixels outside the image are handled during correction."))
        if changed:
            self.model.mode = ["wrap", "nearest", "reflect"][mode]
        changed, smooth = im.input_float(tr("Smoothing"), float(self.model.smooth), step=0.5, step_fast=2.0)
        im.set_item_tooltip(tr("Smoothing window applied before estimating frame shifts."))
        if changed:
            self.model.smooth = max(0.0, float(smooth))
        changed, subpixel = im.checkbox(tr("Subpixel shifts"), bool(self.model.subpixel))
        im.set_item_tooltip(tr("Estimate fractional-pixel shifts for higher precision."))
        if changed:
            self.model.subpixel = bool(subpixel)
        if self.model.result is not None:
            im.separator()
            im.text_wrapped(self.message)
            if implot.begin_plot(tr("Measured drift"), (-1, 260)):
                for series in self.model.drift_series():
                    implot.plot_line(series["name"], np.asarray(series["x"]), np.asarray(series["y"]))
                implot.end_plot()
            if im.begin_table("drift_shifts", 4, 1, (-1, 180)):
                for heading in (tr("Frame"), "dx", "dy", tr("Magnitude")):
                    im.table_setup_column(heading)
                im.table_headers_row()
                for row in self.model.shift_rows():
                    im.table_next_row()
                    for key in ("frame", "dx", "dy", "magnitude"):
                        im.table_next_column()
                        im.text(str(row[key]))
                im.end_table()
            changed, self.csv_target = self._text("Shifts CSV", self.csv_target, "Destination for the per-frame shift table.")
            if im.button(tr("Export shifts")):
                im.set_item_tooltip(tr("Write the measured shifts to a CSV file."))
                self.message = str(self.model.export(shifts_path=self.csv_target))
            else:
                im.set_item_tooltip(tr("Write the measured shifts to a CSV file."))
            changed, self.stack_target = self._text("Corrected TIFF", self.stack_target, "Destination for the corrected multi-page TIFF.")
            if im.button(tr("Export stack")):
                im.set_item_tooltip(tr("Write a corrected multi-page TIFF."))
                self.message = str(self.model.export(stack_path=self.stack_target))
            else:
                im.set_item_tooltip(tr("Write a corrected multi-page TIFF."))
        else:
            im.text_wrapped(self.message)
        im.end()


def make_app(coordinator=None) -> ImgDriftApp:
    """Build the app; *coordinator* is the imaging hub, which wires itself in afterwards."""
    from chisurf.emtk.i18n import install
    install()
    return ImgDriftApp()
