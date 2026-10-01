"""Shared fixtures for the Trace Browser tests: nothing reads or writes the user's real settings.

An autouse fixture redirects the settings folder, the MMFDB and the setups file (including the
path constants that are fixed when the modules are imported) to a temporary folder. Before this
fixture only the Trace Browser's emtk tests did it: running the model tests touched the real
``~/.chisurf/flr/sample_management.db`` and five of them failed on a machine without the
author's saved "ALEX Suite (auto)" setup.
"""

import importlib
import json
import sys

import pytest

#: (module, attribute) pairs holding the setups file path, fixed when the module is imported.
_SETUPS_FILE_CONSTANTS = (
    ("chisurf.core.data_io.detector_setups", "DETECTOR_SETUPS_FILE"),
    ("chisurf.gui.widgets.wizard.tttr_channeldefinition.tttr_detector_setups", "DETECTOR_SETUPS_FILE"),
    ("chisurf.gui.widgets.wizard.tttr_channeldefinition.tttr_channel_definition", "DETECTOR_SETUPS_FILE"),
)
#: (module, attribute) pairs holding a SetupTypeConfig whose ``canonical_file`` is that path.
_SETUP_CONFIGS = (
    ("chisurf.core.setup_channel_definition", "CONFIG"),
    ("chisurf.gui.widgets.wizard.tttr_channeldefinition.tttr_detector_setups", "DETECTOR_CONFIG"),
)


def _module(name):
    """Import *name* (with the real settings, before redirection); ``None`` if unavailable."""
    try:
        return importlib.import_module(name)
    except Exception:  # Qt or a binding missing: nothing to redirect then
        return sys.modules.get(name)


@pytest.fixture(autouse=True)
def hermetic_settings(tmp_path, monkeypatch):
    """Redirect the settings folder, the MMFDB and the setups file to *tmp_path*."""
    modules = {name: _module(name) for name, _ in _SETUPS_FILE_CONSTANTS + _SETUP_CONFIGS}
    home = tmp_path / "settings"
    home.mkdir()
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(home))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(home))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(home / "mmfdb_test.db"))
    setups_file = home / "detector_setups.json"
    for name, attr in _SETUPS_FILE_CONSTANTS:
        if modules.get(name) is not None:
            monkeypatch.setattr(modules[name], attr, setups_file)
    for name, attr in _SETUP_CONFIGS:
        module = modules.get(name)
        if module is not None:
            config = getattr(module, attr)
            monkeypatch.setattr(config, "canonical_file", setups_file)
    return home


#: The saved setup "ALEX Suite (auto)" as the user's own detector_setups.json holds it
#: (copied from there on 2026-10-01; detectors, windows and reading block).
ALEX = {
    "setup_name": "ALEX Suite (auto)",
    "windows": {"prompt": [616, 3784], "delayed": [4278, 7762]},
    "detectors": {
        "green": {"chs": [1], "micro_time_ranges": [[616, 3784]], "g_factor": 1.0, "l1": 0.0, "l2": 0.0},
        "red": {"chs": [0], "micro_time_ranges": [[616, 3784]], "g_factor": 1.0, "l1": 0.0, "l2": 0.0},
        "yellow": {"chs": [0], "micro_time_ranges": [[4278, 7762]], "g_factor": 1.0, "l1": 0.0, "l2": 0.0},
    },
    "tttr_reading": {"file_type": "PTO", "micro_time_binning": 1, "excitation_period": 8000},
}

#: Overlapping, unsorted channels (the Qt setup page's own default detector layout): the
#: derived channel list must be the sorted union without duplicates.
OVERLAP = {
    "setup_name": "Overlap",
    "windows": {"prompt": [0, 2048]},
    "detectors": {
        "green": {"chs": [8, 0, 3], "micro_time_ranges": [[0, 4095]], "g_factor": 1, "l1": 0, "l2": 0},
        "red": {"chs": [9, 1, 2], "micro_time_ranges": [[0, 2048]], "g_factor": 1, "l1": 0, "l2": 0},
        "yellow": {"chs": [9, 1, 2], "micro_time_ranges": [[2048, 4095]], "g_factor": 1, "l1": 0, "l2": 0},
    },
    "tttr_reading": {"file_type": "Auto", "micro_time_binning": 1},
}
