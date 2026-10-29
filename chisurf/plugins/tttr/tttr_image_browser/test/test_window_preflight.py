"""The image browser holds the detector gates of its setup against the file's excitation pulses.

A tile is one detector's photons inside its micro-time gates; the setup's PIE windows never shape
an image, so only the gates are checked (the shared excitation-window pre-flight, gate findings
only). The simulated PIE demo of Excitation Windows (32 ps, pulses at 2 and 52 ns) is not an image,
so the gate check is exercised on it directly and through the model; the Leica scans carry the
``warnings`` of a real mosaic load.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("tttrlib")

from chisurf.core.fluorescence.excitation import (  # noqa: E402
    remembered_gate_check,
    windows_message,
)
from chisurf.plugins.core.excitation_windows import demo as pie  # noqa: E402

#: The red detector's gate stops before the acceptor pulse (52 ns = channel 1625).
NARROW = {**pie.wrong_setup(),
          "detectors": {"green": {"chs": [0], "micro_time_ranges": [[0, 1000]]},
                        "red": {"chs": [1], "micro_time_ranges": [[1700, 3000]]}}}
#: Gates over the whole period; the (wrong) PIE windows of the demo's other instrument stay.
WIDE = {**pie.wrong_setup(),
        "detectors": {"green": {"chs": [0], "micro_time_ranges": [[0, 3125]]},
                      "red": {"chs": [1], "micro_time_ranges": [[0, 3125]]}}}


def gate_warnings(path, setup):
    """The browser's line for *path* (as a mosaic load reports it)."""
    line = windows_message(remembered_gate_check(path, setup))
    return [line] if line else []


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    return pie.make_demo(tmp_path_factory.mktemp("pie"))


@pytest.fixture(scope="module")
def donor_only(tmp_path_factory):
    from chisurf.plugins.tttr import demo_lib

    macro, micro, routing = pie.photon_stream(n_photons=100_000)
    t_ns = micro.astype(float) * pie.RESOLUTION_S * 1e9
    keep = ~((routing == 1) & (t_ns > 51.0))  # no acceptor pulse
    path = tmp_path_factory.mktemp("donly") / "donly.ptu"
    cfg = demo_lib.config(macro_resolution_s=pie.MACRO_S, micro_resolution_s=pie.RESOLUTION_S,
                          n_micro=pie.N_MICRO)
    demo_lib.write_ptu(path, cfg, macro[keep], micro[keep], np.asarray(routing)[keep])
    return path


def test_a_gate_that_hides_a_pulse_is_reported(demo):
    lines = gate_warnings(demo, NARROW)
    assert len(lines) == 1 and lines[0].startswith("Detector gates do not match"), lines
    assert "red" in lines[0] and "prompt 50–1613" in lines[0]


def test_gates_that_hold_the_pulses_say_nothing_whatever_the_windows(demo):
    # the PIE windows are another instrument's, but a tile does not use them
    assert gate_warnings(demo, WIDE) == []


def test_a_donor_only_file_says_nothing_about_windows_it_does_not_use(donor_only):
    # one pulse, and gates that hold it: the shared note is about PIE windows, which the browser
    # does not check
    holding = {**NARROW, "detectors": {**NARROW["detectors"],
                                       "red": {"chs": [1], "micro_time_ranges": [[0, 1000]]}}}
    assert gate_warnings(donor_only, holding) == []


def test_a_setup_without_gates_is_not_checked(demo):
    assert gate_warnings(demo, {"detectors": {"green": {"chs": [0]}}}) == []


def test_a_mosaic_load_carries_the_warnings():
    from chisurf.plugins.tttr.tttr_image_browser.core.image import load_image
    from chisurf.plugins.tttr.tttr_image_browser.test.conftest import DATA, two_detector_setup

    data = load_image(str(DATA / "Leica_SP8.ptu"), two_detector_setup(), 128)
    assert data is not None and data["warnings"] == []


def test_the_model_offers_the_detected_gates_and_the_user_takes_them(demo, tmp_path):
    import tttrlib

    from chisurf.plugins.tttr.tttr_image_browser.gui.model import ImageBrowserModel

    model = ImageBrowserModel()
    model.setup_settings = dict(NARROW)
    model.current_file = str(demo)
    line = model.run_windows_preflight(tttrlib.TTTR(str(demo)))
    assert line and line.startswith("Detector gates do not match")
    assert model.windows_check_offer and model.windows_check_text() == line
    assert model.use_detected_windows()
    gates = model.setup_settings["detectors"]["red"]["micro_time_ranges"]
    assert gates[0][0] <= 52e-9 / 32e-12 <= gates[0][1]
    assert model.setup_settings["tttr_reading"]["micro_time_resolution"] == pytest.approx(32.0)
    assert "setup" in model.requests and model.status_line.startswith("Detector gates from the data")
    assert model.windows_check_quiet and not model.windows_check_offer
    # the corrected setup holds the pulses
    assert gate_warnings(demo, model.setup_settings) == []
