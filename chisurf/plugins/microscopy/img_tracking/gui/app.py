"""Native emtk particle-tracking tool (form and views from ``tracking_emtk.view.json``).

The settings form is the spec; the movie with its detection markers, the trajectories, the MSD, the track-length
histogram and the per-track table are the spec's views, drawn from what :class:`~.model.TrackingModel` computed.
The shell (dock windows, file dialogs, worker, help, guide) is :class:`~..imaging_emtk.app_base.ImagingToolApp`.
"""

from __future__ import annotations

from pathlib import Path

from ...imaging_emtk.app_base import ImagingToolApp
from .model import IMAGE_FILE_FILTER, TrackingModel

HERE = Path(__file__).parent


class ImgTrackingApp(ImagingToolApp):
    """Particle tracking: detect, link, fit the transport."""

    GUI_DIR = HERE
    SPEC = "tracking_emtk.view.json"
    TITLE = "Particle tracking"
    HELP_TITLE = "Particle tracking - Help"
    DIALOGS = {
        "open": ("Open image stack", "open", IMAGE_FILE_FILTER, "open_path"),
        "export": ("Export tracks", "save", "CSV (*.csv)", "write_export"),
    }
    #: model event -> the control a tour step waits for
    OUTCOMES = {"file": "filename", "computed": "track"}

    def __init__(self, model: TrackingModel | None = None) -> None:
        super().__init__(model or TrackingModel())


def make_app(coordinator=None) -> ImgTrackingApp:
    """Factory named by the manifest's ``entrypoints.emtk``; *coordinator* is the imaging hub, which wires itself in afterwards."""
    return ImgTrackingApp()
