"""Native emtk per-pixel intensity tool (settings form and maps from ``intensity_emtk.view.json``).

The settings are the spec, the maps are its ``image_panel`` windows; the shell (dock windows, file dialogs, worker, help, guide,
the imaging hub's contract, ndX, the shared detector editor) is
:class:`~...imaging_emtk.pixel_app.PixelToolApp`.
"""

from __future__ import annotations

from pathlib import Path

from emtk.docking import Region, Split

from ...imaging_emtk.pixel_app import PixelToolApp
from .model import IntensityModel

HERE = Path(__file__).parent


class IntensityApp(PixelToolApp):
    """Per-pixel intensity and count rate of every detector window."""

    GUI_DIR = HERE
    SPEC = "intensity_emtk.view.json"
    TITLE = "Intensity"
    HELP_TITLE = "Per-pixel intensity - Help"
    ROLE = "pixel_intensity"
    LAYOUT = Split("h", 0.30, Region("settings"), Region("views"))

    def __init__(self, model: IntensityModel | None = None, coordinator=None, ndx_callback=None, **binding) -> None:
        super().__init__(model or IntensityModel(), coordinator, ndx_callback, **binding)


def make_app(coordinator=None, **kwargs) -> IntensityApp:
    """Factory named by the manifest's ``entrypoints.emtk``; *coordinator* is the imaging hub (it hands in the setup and the file)."""
    from chisurf.emtk.i18n import install

    install()
    return IntensityApp(coordinator=coordinator, **kwargs)
