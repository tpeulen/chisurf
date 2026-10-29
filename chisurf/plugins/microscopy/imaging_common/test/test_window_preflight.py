"""The per-pixel imaging tools hold their detector windows' gates against the photon stream.

The scan is the confocal PIE scan of the FRC pre-flight tests (32 ps, 3125 channels, pulses at 2
and 52 ns, donor on routing 0, acceptor on routing 5). Gates made for another instrument give the
warning and the offer on Run; taking it fills the windows through the detected gates and computes
again; gates that hold the pulses, ungated windows, a donor-only scan and an image file say nothing.
"""

from __future__ import annotations

import copy

import pytest

pytest.importorskip("tttrlib")

from chisurf.plugins.microscopy.imaging_common import windows  # noqa: E402
from chisurf.plugins.microscopy.img_frc.test.test_window_preflight import (  # noqa: E402
    MATCHING,
    WRONG,
    pie_scan,
)

DONOR_PEAK = 2e-9 / 32e-12  # the donor pulse, in channels


@pytest.fixture(scope="module")
def scan(tmp_path_factory):
    return str(pie_scan(tmp_path_factory.mktemp("scan") / "pie_scan.ptu"))


def test_gates_of_another_instrument_warn(scan):
    lines = windows.gate_warnings(scan, WRONG)
    assert len(lines) == 1 and lines[0].startswith("Detector gates do not match the data")


def test_gates_that_hold_the_pulses_and_ungated_windows_say_nothing(scan):
    assert windows.gate_warnings(scan, MATCHING) == []
    assert windows.gate_warnings(scan, {"green": {"chs": [0], "micro_time_ranges": []}}) == []


def test_a_donor_only_scan_and_an_image_file_say_nothing(tmp_path):
    from chisurf.plugins.microscopy.img_frc.demo import make_demo

    donor = str(pie_scan(tmp_path / "donor_only.ptu", donor_only=True))
    assert windows.gate_warnings(donor, MATCHING) == []
    assert windows.gate_warnings(str(make_demo(tmp_path)), WRONG) == []


def test_taking_gates_keeps_the_calibration_of_a_window():
    detectors = {"green": {"chs": [0], "micro_time_ranges": [(2048, 4095)], "irf": ["irf.ptu"]}}
    taken = windows.take_gates(
        detectors, {"detectors": {"green": {"micro_time_ranges": [[0, 3125]]}}}
    )
    assert taken["green"]["micro_time_ranges"] == [(0, 3125)]
    assert taken["green"]["irf"] == ["irf.ptu"] and detectors["green"]["micro_time_ranges"] == [
        (2048, 4095)
    ]


@pytest.mark.parametrize(
    "module, cls",
    [
        ("chisurf.plugins.microscopy.img_pixel_phasor.gui.model", "PhasorModel"),
        ("chisurf.plugins.microscopy.img_pixel_micro_time.gui.model", "MicroTimeModel"),
        ("chisurf.plugins.microscopy.img_pixel_intensity.gui.model", "IntensityModel"),
    ],
)
def test_a_pixel_tool_offers_the_detected_gates_and_takes_them(scan, module, cls):
    import importlib

    model = getattr(importlib.import_module(module), cls)()
    model.apply_setup_settings({"detectors": copy.deepcopy(WRONG)})
    model.open_path(scan)
    model.run_maps()
    assert model._columns, model.results_text
    assert model.windows_check_offer and "do not match" in model.windows_check_text()
    assert "Detector gates do not match the data" in model.status_line
    assert model.use_detected_windows()
    green = model.detectors["green"]["micro_time_ranges"]
    assert any(lo <= DONOR_PEAK < hi for lo, hi in green), green
    assert model._columns and not model.windows_check_offer and model.windows_check_quiet


def test_a_pixel_tool_with_matching_gates_says_nothing(scan):
    from chisurf.plugins.microscopy.img_pixel_phasor.gui.model import PhasorModel

    model = PhasorModel()
    model.apply_setup_settings({"detectors": copy.deepcopy(MATCHING)})
    model.open_path(scan)
    model.run_maps()
    assert model._columns and model.windows_check_quiet and not model.windows_check_offer
    assert "do not match" not in model.status_line


def test_a_new_file_drops_the_check(scan, tmp_path):
    from chisurf.plugins.microscopy.img_pixel_phasor.gui.model import PhasorModel

    model = PhasorModel()
    model.apply_setup_settings({"detectors": copy.deepcopy(WRONG)})
    model.open_path(scan)
    model.run_maps()
    assert model.windows_check_offer
    model.open_path(str(tmp_path / "other.ptu"))
    assert model.windows_check is None and model.windows_check_quiet


@pytest.mark.parametrize(
    "module",
    [
        "chisurf.plugins.microscopy.img_pixel_phasor.gui.app",
        "chisurf.plugins.microscopy.img_coloc.gui.app",
    ],
)
def test_the_detectors_editor_shows_the_taken_gates(scan, module):
    import importlib

    app = importlib.import_module(module).make_app()
    model = app.model
    model.runner = None
    app.apply_setup_settings({"detectors": copy.deepcopy(WRONG)})
    model.open_path(scan)
    if hasattr(model, "run_maps"):
        model.run_maps()
    assert model.use_detected_windows()
    shown = app.editor.model.get_settings()["detectors"]["green"]["micro_time_ranges"]
    assert any(lo <= DONOR_PEAK < hi for lo, hi in shown), shown
    app.close()
