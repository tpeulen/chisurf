"""Qt-free model of the emtk mean micro-time window (the analysis is :class:`~.view_model.MicroTimeViewModel`, shared with the Qt tool)."""

from __future__ import annotations

import numpy as np

from ...imaging_emtk.pixel_model import PixelModelMixin
from .view_model import MicroTimeViewModel


class MicroTimeModel(PixelModelMixin, MicroTimeViewModel):
    """Per-pixel mean micro-time plus the state of the emtk window."""

    TOOL_NAME = "Mean micro-time"
    SETTINGS = ("n_ph_min",)
    COLUMN_UNITS = {**MicroTimeViewModel.COLUMN_UNITS, "mean_micro_time": "nanoseconds"}

    def __init__(self) -> None:
        MicroTimeViewModel.__init__(self)
        self.status_line = ""

    def compute(self, progress=None):
        if not super().compute(progress=progress):
            return False
        # tttrlib uses -1 for pixels below the threshold; the imaging product uses zero, never a negative arrival time.
        for maps in self._by_window.values():
            for key in ("mean_micro_time", "mt_frames"):
                if key in maps:
                    maps[key] = np.maximum(np.nan_to_num(maps[key]), 0.0)
        for window, maps in self._by_window.items():
            self._columns[f"mean_micro_time ({window})"] = maps["mean_micro_time"]
        return True

    def artifact_name(self) -> str:
        return "mean_micro_time"
