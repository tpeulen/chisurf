"""The background is a rate per detector (B_G|G, B_R|G, B_R|R in kHz), as ndX names it.

A burst carries the rate times its duration (kHz x ms = counts), and a table read from a
measurement's container starts with the rates Burst Analysis stored there.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.burst.accurate_fret import core as _core


def test_a_rate_is_taken_off_each_burst_times_its_duration():
    columns = {"Duration (ms)": np.array([1.0, 2.0, 4.0])}
    i_dd = np.array([10.0, 10.0, 10.0])
    i_da = np.array([5.0, 5.0, 5.0])
    (dd, da, aa), missing = _core.subtract_background([i_dd, i_da, None], (1.5, 2.0, 0.4), columns)
    np.testing.assert_allclose(dd, [8.5, 7.0, 4.0])
    np.testing.assert_allclose(da, [3.0, 1.0, 0.0])  # never negative
    assert aa is None and missing == []


def test_a_detector_duration_wins_and_no_duration_is_reported():
    columns = {"Duration (G|G) (ms)": np.array([2.0]), "Duration (ms)": np.array([1.0])}
    (dd, da, _aa), missing = _core.subtract_background(
        [np.array([10.0]), np.array([10.0]), None], (1.0, 1.0, 0.0), columns
    )
    np.testing.assert_allclose(dd, [8.0])  # G|G's own duration
    np.testing.assert_allclose(da, [9.0])  # R|G falls back to the burst's
    (dd, *_), missing = _core.subtract_background([np.array([10.0]), None, None], (1.0, 0, 0), {})
    np.testing.assert_allclose(dd, [10.0])
    assert missing == ["B_G|G"]


def test_a_table_from_a_container_starts_with_its_stored_rates(monkeypatch):
    from chisurf.plugins.burst.accurate_fret.gui.view_model import AccurateFretViewModel
    from chisurf.plugins.ndxplorer import calibration_bridge

    stored = {"B_G|G": 1.79, "B_R|G": 0.69, "B_R|R": 0.43}
    monkeypatch.setattr(calibration_bridge, "background_from_container", lambda source: stored)
    model = AccurateFretViewModel()
    model.filename = "m000.pto/run"
    assert model.take_stored_background()
    assert (model.background_dd, model.background_da, model.background_aa) == pytest.approx(
        (1.79, 0.69, 0.43)
    )
