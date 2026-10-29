"""Colocalization holds the gates of a setup's detector windows against the photon stream.

The scan is the confocal PIE scan of the FRC pre-flight tests (donor on routing 0, acceptor on
routing 5). Gates made for another instrument give the line in the result's ``warnings`` and the
offer in the window; taking it computes again through the detected gates; matching gates, a
donor-only scan and a camera image say nothing.
"""

from __future__ import annotations

import copy

import pytest

pytest.importorskip("tttrlib")

from chisurf.plugins.microscopy.img_coloc import core  # noqa: E402
from chisurf.plugins.microscopy.img_frc.test.test_window_preflight import (  # noqa: E402
    MATCHING,
    WRONG,
    pie_scan,
)

#: The acceptor detector gated in the matching setup too, so both channels are windows.
BOTH = {**MATCHING, "red": {"chs": [5], "micro_time_ranges": [[0, 3124]]}}


@pytest.fixture(scope="module")
def scan(tmp_path_factory):
    return str(pie_scan(tmp_path_factory.mktemp("scan") / "pie_scan.ptu"))


def _run(path, windows):
    return core.compute_colocalization(path, "green", "red", windows=windows)


def test_gates_of_another_instrument_are_in_the_result(scan):
    out = _run(scan, WRONG)
    assert len(out["warnings"]) == 1 and "do not match the data" in out["warnings"][0]


def test_gates_that_hold_the_pulses_say_nothing(scan, tmp_path):
    assert _run(scan, BOTH)["warnings"] == []
    donor = str(pie_scan(tmp_path / "donor_only.ptu", donor_only=True))
    assert _run(donor, BOTH)["warnings"] == []


def test_a_camera_image_is_not_checked(tmp_path):
    from chisurf.plugins.microscopy.img_coloc.demo import make_demo

    assert core.compute_colocalization(str(make_demo(tmp_path)), 0, 1)["warnings"] == []


def test_the_window_offers_the_detected_gates_and_takes_them(scan):
    from chisurf.plugins.microscopy.img_coloc.gui.model import ColocModel

    model = ColocModel()
    model.apply_setup_settings({"name": "wrong", "detectors": copy.deepcopy(WRONG)})
    model.open_path(scan)
    assert model._metrics, model.results_text
    assert model.windows_check_offer and "do not match" in model.windows_check_text()
    assert "Detector gates do not match the data" in model.status_line
    assert "do not match" in model.summary_text
    assert model.use_detected_windows()
    green = model.detectors["green"]["micro_time_ranges"]
    assert any(lo <= 2e-9 / 32e-12 < hi for lo, hi in green), green
    assert model.setup_name == "wrong" and model._metrics
    assert not model.windows_check_offer and "do not match" not in model.summary_text
