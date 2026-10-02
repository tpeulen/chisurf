"""Native emtk flow-map tool (form and views from ``flow_emtk.view.json``).

The settings form is the spec; the headline numbers, the arrows over the image, the profile across the field and the tile table are the spec's views,
drawn from what :class:`~.model.FlowModel` computed. The shell (dock windows, file dialogs, worker, help, guide) is
:class:`~..imaging_emtk.app_base.ImagingToolApp`. The demo (``Load demo``) is the plugin's own: it simulates a photon stream with a known flow.
"""

from __future__ import annotations

from pathlib import Path

from emtk.docking import Region, Split

from ...imaging_emtk.app_base import ImagingToolApp
from .model import IMAGE_FILE_FILTER, FlowModel

HERE = Path(__file__).parent


class ImgFlowApp(ImagingToolApp):
    """Flow maps: one velocity vector per tile, read off where a correlation peak is."""

    GUI_DIR = HERE
    SPEC = "flow_emtk.view.json"
    TITLE = "Flow maps"
    HELP_TITLE = "Flow maps - Help"
    LAYOUT = Split("h", 0.40, Region("settings"),
                   Split("v", 0.20, Region("report"), Split("h", 0.5, Region("field"), Region("diag"))))
    DIALOGS = {
        "open": ("Open image", "open", IMAGE_FILE_FILTER, "open_path"),
        "export": ("Export flow map", "save", "CSV (*.csv)", "write_export"),
    }
    #: model event -> the control a tour step waits for
    OUTCOMES = {"file": "filename", "demo": "demo", "computed": "map_flow"}

    def __init__(self, model: FlowModel | None = None) -> None:
        super().__init__(model or FlowModel())


def make_app(coordinator=None) -> ImgFlowApp:
    """Factory named by the manifest's ``entrypoints.emtk``; *coordinator* is the imaging hub, which wires itself in afterwards."""
    return ImgFlowApp()
