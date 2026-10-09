"""Qt-free settings of the Setup: Channel Definition tool.

The page is the shared :class:`chisurf.emtk.channel_definition.ChannelDefinitionWidget`; the state of its Setup
row (Save, Rename, Delete, Public, Calibration and their prompts) is :class:`~chisurf.emtk.channel_setup_bar.SetupToolbar`,
re-exported here. What a fresh tool shows is :data:`DEFAULT_SETTINGS`, as in the Qt tool.
"""

from __future__ import annotations

import copy
from typing import Any

from chisurf.emtk.channel_setup_bar import (
    DELETE,
    LATEST,
    OVERWRITE,
    RENAME,
    SAVE,
    UNSAVED,
    SetupToolbar,
)

#: What a fresh tool shows, as in the Qt tool: three detectors, two PIE windows, SPC-130 timing.
DEFAULT_SETTINGS: dict[str, Any] = {
    "windows": {"prompt": [0, 2048], "delayed": [2048, 4095]},
    "detectors": {
        "green": {
            "chs": [8, 0, 3],
            "micro_time_ranges": [[0, 4095]],
            "g_factor": 1.0,
            "l1": 0.0,
            "l2": 0.0,
        },
        "red": {
            "chs": [9, 1, 2],
            "micro_time_ranges": [[0, 2048]],
            "g_factor": 1.0,
            "l1": 0.0,
            "l2": 0.0,
        },
        "yellow": {
            "chs": [9, 1, 2],
            "micro_time_ranges": [[2048, 4095]],
            "g_factor": 1.0,
            "l1": 0.0,
            "l2": 0.0,
        },
    },
    "tttr_reading": {
        "file_type": "SPC-130",
        "macro_time_resolution": 50.0,
        "micro_time_resolution": 50.0,
        "micro_time_binning": 1,
    },
}


def default_settings() -> dict[str, Any]:
    """Return a fresh copy of the settings a new tool starts with."""
    return copy.deepcopy(DEFAULT_SETTINGS)


__all__ = [
    "DEFAULT_SETTINGS",
    "DELETE",
    "LATEST",
    "OVERWRITE",
    "RENAME",
    "SAVE",
    "SetupToolbar",
    "UNSAVED",
    "default_settings",
]
