"""Native EMTK flow-map surface."""

from __future__ import annotations

import numpy as np
from emtk import i18n, im, implot
from emtk.app import ImApp

from .gui.view_model import FlowViewModel
from .strings import install_translations, tr

install_translations()


class ImgFlowApp(ImApp):
    """Estimate and inspect a velocity field from an image stack."""

    def __init__(self, model: FlowViewModel | None = None) -> None:
        self.model = model or FlowViewModel()
        self.csv_target = ""
        self.message = self.model.status
        super().__init__(self.render)

    def _text(self, label: str, value: str, tip: str):
        changed, result = im.input_text(tr(label), value)
        im.set_item_tooltip(tr(tip))
        return changed, result

    def render(self) -> None:
        im.begin(tr("Flow map"), (0, 0, *im.get_main_viewport().size))
        im.heading(tr("Flow map"), level=2)
        changed, filename = self._text("Image stack", self.model.filename, "TIFF stack or photon-stream image to analyze.")
        if changed and filename != self.model.filename:
            self.model.set_filename(filename)
            self.message = self.model.status
        if im.button(tr("Load demo")):
            im.set_item_tooltip(tr("Generate a scan with a known flow profile."))
            try:
                self.model.load_demo()
                self.message = self.model.status
            except Exception as exc:  # noqa: BLE001
                self.message = f"{type(exc).__name__}: {exc}"
        else:
            im.set_item_tooltip(tr("Generate a scan with a known flow profile."))
        im.same_line()
        if im.button(tr("Map flow")):
            im.set_item_tooltip(tr("Estimate one velocity vector for each image tile."))
            self.model.compute()
            self.message = self.model.status
        else:
            im.set_item_tooltip(tr("Estimate one velocity vector for each image tile."))
        im.separator()
        im.heading(tr("Parameters"), level=3)
        methods = ["stics", "pcf"]
        changed, index = im.combo(tr("Estimator"), methods.index(self.model.method), methods)
        im.set_item_tooltip(tr("Correlation estimator used to determine the velocity."))
        if changed:
            self.model.method = methods[index]
        for label, attr, tip, step in (("Tile size", "tile", "Spatial resolution of the flow map.", 1), ("Frame lags", "n_lags", "Number of frame lags used by STICS.", 1), ("Min quality", "min_quality", "Drop vectors below this fit-quality threshold.", 0.05)):
            if attr == "min_quality":
                changed, value = im.input_float(tr(label), float(getattr(self.model, attr)), step=step, step_fast=0.5)
            else:
                changed, value = im.input_int(tr(label), int(getattr(self.model, attr)), step=step)
            im.set_item_tooltip(tr(tip))
            if changed:
                setattr(self.model, attr, max(0.0 if attr == "min_quality" else 1, value))
        im.text_wrapped(self.message)
        if self.model.result is not None:
            if implot.begin_plot(tr("Velocity profile"), (-1, 260)):
                for series in self.model.profile_series():
                    implot.plot_line(series["name"], np.asarray(series["x"]), np.asarray(series["y"]))
                implot.end_plot()
            if im.begin_table("flow_vectors", 5, 1, (-1, 180)):
                for heading in ("x", "y", "vx", "vy", tr("quality")):
                    im.table_setup_column(heading)
                im.table_headers_row()
                for row in self.model.vector_rows():
                    im.table_next_row()
                    for key in ("x", "y", "vx", "vy", "quality"):
                        im.table_next_column()
                        im.text(str(row.get(key, "")))
                im.end_table()
            _, self.csv_target = self._text("CSV output", self.csv_target, "Destination for one row per velocity vector.")
            if im.button(tr("Export CSV")):
                im.set_item_tooltip(tr("Write the velocity vectors and quality values to CSV."))
                self.message = self.model.export_csv(self.csv_target) if self.csv_target else tr("Choose a CSV output path first.")
            else:
                im.set_item_tooltip(tr("Write the velocity vectors and quality values to CSV."))
        im.end()


def make_app(coordinator=None) -> ImgFlowApp:
    """Build the app; *coordinator* is the imaging hub, which wires itself in afterwards."""
    from chisurf.emtk.i18n import install
    install()
    return ImgFlowApp()

