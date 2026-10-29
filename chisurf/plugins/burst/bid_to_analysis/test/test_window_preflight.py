"""BID → Analysis runs the shared excitation-window check on the measurement a selection indexes.

The simulated PIE demo of Excitation Windows (32 ps, pulses at 2 and 52 ns) with a burst-ID
selection beside it. Imported with the windows of another instrument, the conversion reports the
warning and the detected windows; with matching windows (or none given) it says nothing; a
donor-only measurement gives the note, not a warning. The GUI offers the detected windows for the
first queued measurement and the user takes them into the working setup.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("tttrlib")

from chisurf.plugins.burst.bid_to_analysis import convert_bid_file  # noqa: E402

DETECTORS = {"green": {"chs": [0], "micro_time_ranges": []},
             "red": {"chs": [1], "micro_time_ranges": []}}
WRONG = {"prompt": [0, 2048], "delayed": [2048, 4095]}
RIGHT = {"prompt": [50, 1613], "delayed": [1613, 3125]}
INTERVALS = np.array([[100, 180], [900, 1010], [5000, 5120]])


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))


def _with_selection(ptu):
    bid = ptu.with_suffix(".bid")
    np.savetxt(bid, INTERVALS, fmt="%d")
    return bid


@pytest.fixture
def pie_bid(tmp_path):
    from chisurf.plugins.core.excitation_windows.demo import make_demo

    return _with_selection(make_demo(tmp_path / "data"))


@pytest.fixture
def donor_only_bid(tmp_path):
    from chisurf.plugins.core.excitation_windows import demo as d
    from chisurf.plugins.tttr import demo_lib

    macro, micro, routing = d.photon_stream(n_photons=100_000)
    routing = np.asarray(routing)
    keep = ~((routing == 1) & (micro.astype(float) * d.RESOLUTION_S > 51e-9))  # no acceptor pulse
    path = tmp_path / "data" / "donor_only.ptu"
    path.parent.mkdir(parents=True)
    cfg = demo_lib.config(macro_resolution_s=d.MACRO_S, micro_resolution_s=d.RESOLUTION_S,
                          n_micro=d.N_MICRO)
    demo_lib.write_ptu(path, cfg, macro[keep], micro[keep], routing[keep])
    return _with_selection(path)


def _convert(bid, windows):
    warnings: list[str] = []
    convert_bid_file(bid, windows=windows, detectors=DETECTORS, warnings=warnings)
    return warnings


def test_wrong_windows_are_reported(pie_bid):
    warnings = _convert(pie_bid, WRONG)
    assert len(warnings) == 1 and "PIE windows do not match" in warnings[0], warnings
    assert "prompt 50–1613" in warnings[0]


def test_matching_windows_say_nothing(pie_bid):
    assert _convert(pie_bid, RIGHT) == []


def test_no_windows_given_says_nothing(pie_bid):
    assert _convert(pie_bid, None) == []


def test_a_donor_only_measurement_gives_a_note_not_a_warning(donor_only_bid):
    warnings = _convert(donor_only_bid, WRONG)
    assert len(warnings) == 1 and "One excitation pulse" in warnings[0], warnings
    assert "do not match" not in warnings[0]


def test_the_gui_offers_the_detected_windows_and_takes_them(pie_bid):
    from emtk.testing import RecordingPainter

    from chisurf.plugins.burst.bid_to_analysis.gui.app import create_app

    app = create_app()
    try:
        app.setup.model.data["windows"] = dict(WRONG)
        app.setup.model.data["detectors"] = dict(DETECTORS)
        app.add_files([pie_bid])
        app.draw(RecordingPainter(), 0, 0, 1200, 800)
        check = app.windows_check
        assert check.windows_check_offer and "do not match" in check.windows_check_text()
        assert check.use_detected_windows()
        windows = app.setup.model.data["windows"]
        assert windows["prompt"][0] < 2e-9 / 32e-12 < windows["prompt"][1]
        assert windows["delayed"][0] < 52e-9 / 32e-12 < windows["delayed"][1]
        app.draw(RecordingPainter(), 0, 0, 1200, 800)
        assert check.windows_check_quiet and not check.windows_check_offer
    finally:
        app.close()


def test_a_conversion_warning_reaches_the_log_and_the_status_line(pie_bid):
    from chisurf.plugins.burst.bid_to_analysis.gui.app import create_app

    app = create_app()
    try:
        app.setup.model.data["windows"] = dict(WRONG)
        app.setup.model.data["detectors"] = dict(DETECTORS)
        app.add_files([pie_bid])
        app.process()
        app.future.result(timeout=60)
        app.poll()
        assert app.rows[0]["status"] == "Done"
        assert any("PIE windows do not match" in m for m in app.messages)
        assert "PIE windows do not match" in app.status
    finally:
        app.close()
