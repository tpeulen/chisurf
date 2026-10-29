"""Burst selection runs the shared excitation-window check before it uses PIE windows.

The simulated PIE demo of Excitation Windows (32 ps, pulses at 2 and 52 ns) searched with the
windows of another instrument: the result carries the warning and the detected windows; with the
detected windows it carries none. The preview offers the detected windows and the user takes them.
"""

from __future__ import annotations

import pytest

pytest.importorskip("tttrlib")

from chisurf.plugins.burst.burst_selection.api.selection import analyze_file  # noqa: E402
from chisurf.core.fluorescence.simulation.pie_demo import make_demo  # noqa: E402

DETECTORS = {"green": {"chs": [0], "micro_time_ranges": []},
             "red": {"chs": [1], "micro_time_ranges": []}}


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    return make_demo(tmp_path_factory.mktemp("demo"))


def test_wrong_windows_are_reported_in_the_result(demo):
    result = analyze_file(demo, windows={"prompt": (0, 2048), "delayed": (2048, 4095)},
                          detectors=DETECTORS)
    assert any("PIE windows do not match" in w for w in result.warnings), result.warnings


def test_matching_windows_say_nothing(demo):
    result = analyze_file(demo, windows={"prompt": (50, 1613), "delayed": (1613, 3125)},
                          detectors=DETECTORS)
    assert not result.warnings


def test_the_preview_offers_the_detected_windows(demo):
    import tttrlib

    from chisurf.plugins.burst.burst_selection.gui.model import BurstSelectionModel

    model = BurstSelectionModel.__new__(BurstSelectionModel)
    model.windows = {"prompt": [0, 2048], "delayed": [2048, 4095]}
    model.detectors = DETECTORS
    model.window_resolution_s = None
    model.window = "All"
    model.windows_check = None
    model._check_windows(tttrlib.TTTR(str(demo)))
    assert model.windows_check_offer and "do not match" in model.windows_check_text()
    model.settings_changed = lambda: None
    assert model.use_detected_windows()
    assert model.windows["prompt"][0] < 2e-9 / 32e-12 < model.windows["prompt"][1]
