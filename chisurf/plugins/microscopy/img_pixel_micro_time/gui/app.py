"""Native emtk mean micro-time tool (settings form and maps from ``micro_time_emtk.view.json``) on the shared pixel shell."""

from __future__ import annotations

from pathlib import Path

from emtk.docking import Region, Split

from ...imaging_emtk.pixel_app import PixelToolApp
from .model import MicroTimeModel

HERE = Path(__file__).parent


class MicroTimeApp(PixelToolApp):
    """Mean micro-time (photon-weighted arrival time, ns) of every detector window."""

    GUI_DIR = HERE
    SPEC = "micro_time_emtk.view.json"
    TITLE = "Mean micro-time"
    HELP_TITLE = "Mean micro-time - Help"
    ROLE = "pixel_micro_time"
    LAYOUT = Split("h", 0.30, Region("settings"), Region("views"))

    def __init__(
        self, model: MicroTimeModel | None = None, coordinator=None, ndx_callback=None, **binding
    ) -> None:
        super().__init__(model or MicroTimeModel(), coordinator, ndx_callback, **binding)


def make_app(coordinator=None, **kwargs) -> MicroTimeApp:
    """Factory named by the manifest's ``entrypoints.emtk``."""
    from chisurf.emtk.i18n import install

    install()
    return MicroTimeApp(coordinator=coordinator, **kwargs)
