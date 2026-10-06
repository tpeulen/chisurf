"""Native emtk FRC resolution tool (form and views from ``frc_emtk.view.json``).

The settings form is the spec; the resolution, the FRC curve, the two halves and the ring table are the spec's views, drawn from what
:class:`~.model.FrcModel` measured. The shell (dock windows, file dialogs, worker, help, guide) is
:class:`~..imaging_emtk.app_base.ImagingToolApp`.
"""

from __future__ import annotations

from pathlib import Path

from emtk.docking import Region, Split

from ...imaging_emtk.app_base import ImagingToolApp
from .model import IMAGE_FILE_FILTER, FrcModel

HERE = Path(__file__).parent


class ImgFrcApp(ImagingToolApp):
    """Fourier ring correlation: the resolution an acquisition actually achieved."""

    GUI_DIR = HERE
    SPEC = "frc_emtk.view.json"
    TITLE = "FRC resolution"
    HELP_TITLE = "FRC resolution - Help"
    LAYOUT = Split(
        "h",
        0.40,
        Region("settings"),
        Split("v", 0.22, Region("report"), Split("h", 0.42, Region("plot"), Region("diag"))),
    )
    DIALOGS = {
        "open": ("Open image", "open", IMAGE_FILE_FILTER, "open_path"),
        "open_second": ("Open second image", "open", IMAGE_FILE_FILTER, "open_second_path"),
        "export": ("Export FRC curve", "save", "CSV (*.csv)", "write_export"),
    }
    #: model event -> the control a tour step waits for
    OUTCOMES = {"file": "filename", "computed": "measure"}

    def __init__(self, model: FrcModel | None = None) -> None:
        super().__init__(model or FrcModel())


def make_app(coordinator=None) -> ImgFrcApp:
    """Factory named by the manifest's ``entrypoints.emtk``; *coordinator* is the imaging hub, which wires itself in afterwards."""
    return ImgFrcApp()
