"""The Qt-free burst-MLE engine against the Qt wizard on the in-repository BH SPC-132 sample (cards ML0 / ML1).

The wizard delegates its pure steps (burst indices, VV|VH histograms, IRF / background processing, header times,
binning and window selection) to ``engine``; ``MleSession`` composes the same steps without any widget. Both are run
on the same data and compared number for number: burst indices, decay, auto-selected binning and window, the IRF
and background patterns, the fitted parameters and the displayed curves. Real photons, nothing generated.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.burst.burst_mle_analysis import engine

from .conftest import BURST_TABLE, CHANNEL_SETTINGS, build_wizard

pytestmark = pytest.mark.usefixtures("qapp_module")


@pytest.fixture(scope="module")
def pair(qapp_module, sample_copy):
    """A wizard and a session loaded with the same burst file and detectors (nothing fitted yet)."""
    wiz = build_wizard(sample_copy)
    session = engine.MleSession()
    session.set_detectors(CHANNEL_SETTINGS["detectors"], CHANNEL_SETTINGS["file_type"])
    session.add_burst_files([sample_copy / BURST_TABLE])
    session.current_detector = "green"
    yield wiz, session
    wiz.close()


def test_engine_imports_no_qt():
    import subprocess
    import sys

    code = (
        "import sys; import chisurf.plugins.burst.burst_mle_analysis.engine as e; "
        "bad=[m for m in sys.modules if m.split('.')[0] in ('PyQt5','PyQt6','PySide2','PySide6','qtpy','emtk')]; "
        "print(bad); raise SystemExit(1 if bad else 0)"
    )
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr


def test_burst_files_header_and_indices_equal_the_wizards(pair):
    wiz, session = pair
    assert session.df_bursts is not None and engine.row_count(session.df_bursts) == wiz.n_bursts
    assert session.burst_indices() == wiz.get_burst_indices_for_current_file()
    assert session.current_tttr() is not None
    dt, period = engine.header_time_ns(session.current_tttr(), wiz.micro_time_binning)
    assert (dt, period) == wiz._header_time_ns()


def test_auto_extract_equals_the_wizards_one_click(pair):
    wiz, session = pair
    wiz.comboBox_window.setCurrentText("green")
    wiz.auto_extract_irf_bg()
    session.auto_extract()
    assert session.outcome is not None
    assert session.settings.micro_time_binning == wiz.micro_time_binning
    assert list(session.micro_time_range) == list(wiz.micro_time_range)
    for det in ("green", "red"):
        np.testing.assert_array_equal(session.irf_np[det], wiz.irf_np[det])
        np.testing.assert_array_equal(session.bg_np[det], wiz.bg_np[det])
    np.testing.assert_array_equal(session.decay, wiz.decay_of_current_file)
    np.testing.assert_array_equal(session.irf(), wiz.irf)
    np.testing.assert_array_equal(session.background(), wiz.bg)
    # the fit: same optimum, same displayed curves
    assert session.outcome.names[0] == "tau"
    assert session.outcome.x[0] == pytest.approx(wiz.tau_result, abs=6e-4)  # the wizard shows 3 decimals
    assert session.outcome.two_istar == pytest.approx(float(wiz.twoIstar_result), abs=6e-4)
    for field in ("data", "model", "irf", "background", "residuals"):
        np.testing.assert_allclose(getattr(session.outcome.curves, field), getattr(wiz.fit_curves, field), rtol=1e-9, atol=1e-12)
    assert 0.5 < session.outcome.x[0] < 5.0


def test_the_second_detector_and_a_changed_window_equal_the_wizard(pair):
    wiz, session = pair
    wiz.comboBox_window.setCurrentText("red")
    session.current_detector = "red"
    wiz.auto_extract_irf_bg()
    session.auto_extract()
    assert session.outcome.x[0] == pytest.approx(wiz.tau_result, abs=6e-4)  # the wizard shows 3 decimals
    # narrow the window by hand on both
    start, stop = wiz.micro_time_range
    wiz.micro_time_range = (start + 3, stop - 3)
    session.settings.micro_time_start, session.settings.micro_time_stop = start + 3, stop - 3
    session.build_decay()
    outcome = session.fit()
    np.testing.assert_array_equal(session.decay, wiz.decay_of_current_file)
    assert outcome.x[0] == pytest.approx(wiz.tau_result, abs=6e-4)
    assert outcome.curves.data.size == wiz.fit_curves.data.size


def test_a_fit_without_an_irf_says_why():
    s = engine.MleSession()
    s.set_detectors(CHANNEL_SETTINGS["detectors"])
    assert s.fit() is None and "no IRF" in s.status


def test_pure_steps_have_the_wizards_edge_cases():
    assert engine.select_fit_range(None) is None
    assert engine.select_fit_range(np.zeros(8)) is None
    d = np.zeros(20)
    d[3:7] = 10
    d[13:17] = 10
    assert engine.select_fit_range(d) == (2, 8)
    assert engine.header_time_ns(None, 1) is None
    assert engine.window_bins(None, (5, 50), 2) == (5, 50, 5, 50)
    assert engine.window_bins([[0, 64], [64, 128]], (5, 50), 4) == (0, 16, 16, 32)
    arr = np.arange(16, dtype=float)
    rolled = engine.process_background(arr, 2, np.zeros(16))
    np.testing.assert_array_equal(rolled[8:], np.roll(arr[8:], 2))
    assert engine.process_background(None, 0, np.zeros(4)).tolist() == [0.0] * 4


def _tau_columns(rows):
    """Columns by name, rows ordered by file (the pool returns files in completion order) and kept in burst order within one."""
    ordered = sorted(enumerate(rows), key=lambda item: (str(item[1].get("First File")), item[0]))
    rows = [r for _i, r in ordered]
    return {
        key: np.array([r.get(key, np.nan) for r in rows], dtype=float)
        for key in sorted({k for r in rows for k in r if k.startswith("Tau (") or k.startswith("Number of Photons")})
    }


def test_the_batch_rows_equal_the_wizards_process_bursts(qapp_module, sample_copy):
    """Same burst table, IRF/background, windows and start values: every burst's fitted lifetime is the wizard's."""
    wiz = build_wizard(sample_copy)
    session = engine.MleSession()
    session.set_detectors(CHANNEL_SETTINGS["detectors"], CHANNEL_SETTINGS["file_type"])
    session.add_burst_files([sample_copy / BURST_TABLE])
    try:
        for det in ("green", "red"):
            wiz.comboBox_window.setCurrentText(det)
            session.current_detector = det
            wiz.auto_extract_irf_bg()
            session.auto_extract()
        seen = []
        session.run_batch(progress=lambda done, total: seen.append((done, total)))
        wiz.process_bursts(force=True)
        mine, theirs = _tau_columns(session.burst_results), _tau_columns(wiz.burst_results)
        assert sorted(mine) == sorted(theirs) and "Tau (green)" in mine and "Tau (red)" in mine
        for key in mine:
            np.testing.assert_allclose(mine[key], theirs[key], rtol=1e-9, atol=1e-12, equal_nan=True, err_msg=key)
        # the batch fitted the detector on screen with its live window (it used the 0..128 seed before the fix)
        assert wiz.channel_settings["red"]["micro_time_start"] == wiz.micro_time_range[0] != 0
        assert len(session.burst_results) == len(wiz.burst_results) == 2 * engine.row_count(session.df_bursts)
        assert seen and seen[-1][0] == seen[-1][1] == engine.row_count(session.df_bursts)
        finite = mine["Tau (green)"][np.isfinite(mine["Tau (green)"])]
        assert finite.size > 100 and 0.1 < np.median(finite) < 10.0
    finally:
        wiz.close()
