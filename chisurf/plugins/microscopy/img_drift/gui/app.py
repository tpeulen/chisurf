"""Native emtk drift-correction tool (form and views from ``drift_emtk.view.json``).

The settings form is the spec; the drift trace, the before / after projections and the shift table are the spec's views,
drawn from what :class:`~.model.DriftModel` measured. The shell (dock windows, file dialogs, worker, help, guide) is
:class:`~..imaging_emtk.app_base.ImagingToolApp`.
"""

from __future__ import annotations

from pathlib import Path

from emtk.docking import Region, Split

from ...imaging_emtk.app_base import ImagingToolApp
from .model import IMAGE_FILE_FILTER, DriftModel

HERE = Path(__file__).parent


class ImgDriftApp(ImagingToolApp):
    """Drift correction: measure the inter-frame drift, show it, export the corrected stack."""

    GUI_DIR = HERE
    SPEC = "drift_emtk.view.json"
    TITLE = "Drift correction"
    HELP_TITLE = "Drift correction - Help"
    LAYOUT = Split("h", 0.40, Region("settings"), Region("views"))
    DIALOGS = {
        "open": ("Open image", "open", IMAGE_FILE_FILTER, "open_path"),
        "export_stack": ("Export corrected stack", "save", "TIFF (*.tif *.tiff)", "write_stack"),
        "export_shifts": ("Export drift shifts", "save", "CSV (*.csv)", "write_shifts"),
    }
    #: model event -> the control a tour step waits for
    OUTCOMES = {"file": "filename", "computed": "measure"}

    def __init__(self, model: DriftModel | None = None) -> None:
        super().__init__(model or DriftModel())


def make_app(coordinator=None) -> ImgDriftApp:
    """Factory named by the manifest's ``entrypoints.emtk``; *coordinator* is the imaging hub, which wires itself in afterwards."""
    return ImgDriftApp()
