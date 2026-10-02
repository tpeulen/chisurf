"""Qt-free model of the emtk intensity window.

The analysis is :class:`~.view_model.IntensityViewModel` (unchanged, shared with the Qt tool); the actions, status line, dialogs
and the worker hand-off are :class:`~chisurf.plugins.microscopy.imaging_emtk.pixel_model.PixelModelMixin`.
"""

from __future__ import annotations

from ...imaging_emtk.pixel_model import PixelModelMixin
from .view_model import IntensityViewModel


class IntensityModel(PixelModelMixin, IntensityViewModel):
    """Per-pixel intensity and count rate plus the state of the emtk window."""

    TOOL_NAME = "Intensity"
    HDF5_CREATES = True
    SETTINGS = ()

    def __init__(self) -> None:
        IntensityViewModel.__init__(self)
        self.status_line = ""
