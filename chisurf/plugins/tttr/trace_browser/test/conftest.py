"""Shared fixtures for the Trace Browser tests: nothing reads or writes the user's real settings.

An autouse fixture redirects the settings folder, the MMFDB and the setups file (including the
path constants that are fixed when the modules are imported) to a temporary folder. Before this
fixture only the Trace Browser's emtk tests did it: running the model tests touched the real
``~/.chisurf/flr/sample_management.db`` and five of them failed on a machine without the
author's saved "ALEX Suite (auto)" setup.
"""

import importlib
import sys

import pytest

#: (module, attribute) pairs holding the setups file path, fixed when the module is imported.
_SETUPS_FILE_CONSTANTS = (("chisurf.core.data_io.detector_setups", "DETECTOR_SETUPS_FILE"),)
#: (module, attribute) pairs holding a SetupTypeConfig whose ``canonical_file`` is that path.
_SETUP_CONFIGS = (
    ("chisurf.core.setup_channel_definition", "CONFIG"),
    ("chisurf.core.data_io.detector_setups", "DETECTOR_CONFIG"),
)


def _module(name):
    """Import *name* (with the real settings, before redirection); ``None`` if unavailable."""
    try:
        return importlib.import_module(name)
    except Exception:  # module unavailable: nothing to redirect then
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
        "G|G": {
            "chs": [1],
            "micro_time_ranges": [[616, 3784]],
            "g_factor": 1.0,
            "l1": 0.0,
            "l2": 0.0,
        },
        "R|G": {
            "chs": [0],
            "micro_time_ranges": [[616, 3784]],
            "g_factor": 1.0,
            "l1": 0.0,
            "l2": 0.0,
        },
        "R|R": {
            "chs": [0],
            "micro_time_ranges": [[4278, 7762]],
            "g_factor": 1.0,
            "l1": 0.0,
            "l2": 0.0,
        },
    },
    "tttr_reading": {"file_type": "PTO", "micro_time_binning": 1, "excitation_period": 8000},
}

#: Overlapping, unsorted channels (several detectors share a channel): the
#: derived channel list must be the sorted union without duplicates.
OVERLAP = {
    "setup_name": "Overlap",
    "windows": {"prompt": [0, 2048]},
    "detectors": {
        "G|G": {
            "chs": [8, 0, 3],
            "micro_time_ranges": [[0, 4095]],
            "g_factor": 1,
            "l1": 0,
            "l2": 0,
        },
        "R|G": {
            "chs": [9, 1, 2],
            "micro_time_ranges": [[0, 2048]],
            "g_factor": 1,
            "l1": 0,
            "l2": 0,
        },
        "R|R": {
            "chs": [9, 1, 2],
            "micro_time_ranges": [[2048, 4095]],
            "g_factor": 1,
            "l1": 0,
            "l2": 0,
        },
    },
    "tttr_reading": {"file_type": "Auto", "micro_time_binning": 1},
}


def gated_photons(path, setup):
    """``(photons, last macro time)`` per detector of *setup*, read straight from the file.

    A detector's photons are those on its routing channels inside one of its micro-time
    gates (inclusive); the last macro time is ``None`` for a detector without photons.
    """
    import numpy as np
    import tttrlib

    data = tttrlib.TTTR(str(path), "SPC-130")
    routing = np.asarray(data.routing_channels)
    micro = np.asarray(data.micro_times)
    macro = np.asarray(data.macro_times, dtype=np.int64)
    out = []
    for detector in setup["detectors"].values():
        gate = np.zeros(len(micro), bool)
        for lo, hi in detector["micro_time_ranges"]:
            gate |= (micro >= lo) & (micro <= hi)
        mask = np.isin(routing, detector["chs"]) & gate
        out.append((int(mask.sum()), int(macro[mask][-1]) if mask.any() else None))
    return out


def trace_bins(path, setup, window_s):
    """Bins of a trace by the binner's rule.

    A bin holds ``floor(window / macro-time resolution)`` clocks; each detector's trace runs to
    its own last photon (``last // clocks + 1`` bins) and the traces are padded to the longest.
    """
    import math

    import tttrlib

    resolution = float(tttrlib.TTTR(str(path), "SPC-130").header.macro_time_resolution)
    clocks = max(1, int(math.floor(window_s / resolution)))
    return max(last // clocks + 1 for _, last in gated_photons(path, setup) if last is not None)


def expected_trace(path, setup, window_s):
    """``(time_axis, counts)`` of *setup* on the file by the trace's definition.

    Column *k* counts detector *k*'s gated photons per window of ``floor(window / resolution)``
    clocks; the time axis is ``arange(bins) * window``.
    """
    import math

    import numpy as np
    import tttrlib

    data = tttrlib.TTTR(str(path), "SPC-130")
    routing = np.asarray(data.routing_channels)
    micro = np.asarray(data.micro_times)
    macro = np.asarray(data.macro_times, dtype=np.int64)
    clocks = max(1, int(math.floor(window_s / float(data.header.macro_time_resolution))))
    bins = trace_bins(path, setup, window_s)
    counts = np.zeros((bins, len(setup["detectors"])))
    for k, detector in enumerate(setup["detectors"].values()):
        gate = np.zeros(len(micro), bool)
        for lo, hi in detector["micro_time_ranges"]:
            gate |= (micro >= lo) & (micro <= hi)
        mask = np.isin(routing, detector["chs"]) & gate
        counts[:, k] = np.bincount(macro[mask] // clocks, minlength=bins)[:bins]
    return np.arange(bins) * window_s, counts
