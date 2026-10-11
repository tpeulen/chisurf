"""The Qt-free burst-MLE engine against the numbers the Qt wizard gave on the in-repository BH SPC-132 sample.

The wizard delegated its pure steps (burst indices, VV|VH histograms, IRF / background processing, header times,
binning and window selection) to ``engine``; ``MleSession`` composes the same steps without any widget. The wizard is
retired: what it produced on this sample (burst indices, decay, auto-selected binning and window, the IRF and
background patterns, the fitted parameters, the displayed curves, the per-burst lifetimes of the batch and the
exported tables) was recorded to ``qt_reference.json`` and is compared number for number. Real photons, nothing
generated.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.burst.burst_mle_analysis import engine

from .conftest import BURST_TABLE, CHANNEL_SETTINGS


def _a(values):
    """A recorded list as an array (``None`` is a recorded NaN)."""
    return np.array([np.nan if v is None else v for v in values], dtype=float)


@pytest.fixture(scope="module")
def session(sample_copy):
    """A session loaded with the sample's burst file and detectors (nothing fitted yet)."""
    s = engine.MleSession()
    s.set_detectors(CHANNEL_SETTINGS["detectors"], CHANNEL_SETTINGS["file_type"])
    s.add_burst_files([sample_copy / BURST_TABLE])
    s.current_detector = "green"
    return s


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


def test_burst_files_header_and_indices_equal_the_wizards(session, qt_reference):
    ref = qt_reference["bursts"]
    assert session.df_bursts is not None and engine.row_count(session.df_bursts) == ref["n_bursts"]
    indices = session.burst_indices()
    assert len(indices) == ref["n_indices"] and int(np.sum(indices)) == ref["indices_sum"]
    assert list(indices[:5]) == ref["indices_first"] and list(indices[-5:]) == ref["indices_last"]
    assert session.current_tttr() is not None
    # recorded at the binning of the green auto-extract, so the channel width is binning x header resolution
    binning = qt_reference["green"]["binning"]
    dt, period = engine.header_time_ns(session.current_tttr(), binning)
    assert (dt, period) == tuple(qt_reference["header_time_ns"])
    assert dt == pytest.approx(binning * engine.header_time_ns(session.current_tttr(), 1)[0])


def test_auto_extract_equals_the_wizards_one_click(session, qt_reference):
    ref = qt_reference["green"]
    session.auto_extract()
    assert session.outcome is not None
    assert session.settings.micro_time_binning == ref["binning"]
    assert list(session.micro_time_range) == ref["micro_time_range"]
    for det in ("green", "red"):
        np.testing.assert_array_equal(session.irf_np[det], _a(ref["irf_np"][det]))
        np.testing.assert_array_equal(session.bg_np[det], _a(ref["bg_np"][det]))
    np.testing.assert_array_equal(session.decay, _a(ref["decay"]))
    np.testing.assert_array_equal(session.irf(), _a(ref["irf"]))
    np.testing.assert_array_equal(session.background(), _a(ref["bg"]))
    # the fit: same optimum, same displayed curves
    assert session.outcome.names[0] == "tau"
    assert session.outcome.x[0] == pytest.approx(
        ref["tau"], abs=6e-4
    )  # the wizard showed 3 decimals
    assert session.outcome.two_istar == pytest.approx(ref["twoIstar"], abs=6e-4)
    for field in ("data", "model", "irf", "background", "residuals"):
        np.testing.assert_allclose(
            getattr(session.outcome.curves, field), _a(ref["curves"][field]), rtol=1e-9, atol=1e-12
        )
    assert 0.5 < session.outcome.x[0] < 5.0


def test_the_second_detector_and_a_changed_window_equal_the_wizard(session, qt_reference):
    session.current_detector = "red"
    session.auto_extract()
    assert session.outcome.x[0] == pytest.approx(qt_reference["red_tau"], abs=6e-4)
    assert session.outcome.two_istar == pytest.approx(qt_reference["red_twoIstar"], abs=6e-4)
    assert session.settings.micro_time_binning == qt_reference["red_binning"]
    assert list(session.micro_time_range) == qt_reference["red_range"]
    # narrow the window by hand
    ref = qt_reference["red_narrowed"]
    start, stop = ref["range"]
    session.settings.micro_time_start, session.settings.micro_time_stop = start, stop
    session.build_decay()
    outcome = session.fit()
    np.testing.assert_array_equal(session.decay, _a(ref["decay"]))
    assert outcome.x[0] == pytest.approx(ref["tau"], abs=6e-4)
    assert outcome.curves.data.size == ref["curves_size"]


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
        for key in sorted(
            {
                k
                for r in rows
                for k in r
                if k.startswith("Tau (") or k.startswith("Number of Photons")
            }
        )
    }


def test_the_batch_rows_equal_the_wizards_process_bursts(sample_copy, tmp_path, qt_reference):
    """Same burst table, IRF/background, windows and start values: every burst's fitted lifetime is the wizard's."""
    ref = qt_reference["batch"]
    session = engine.MleSession()
    session.set_detectors(CHANNEL_SETTINGS["detectors"], CHANNEL_SETTINGS["file_type"])
    import shutil

    own = tmp_path / "own"
    shutil.copytree(sample_copy, own)  # the session exports into its own copy
    session.add_burst_files([own / BURST_TABLE])
    for det in ("green", "red"):
        session.current_detector = det
        session.auto_extract()
    seen = []
    session.run_batch(progress=lambda done, total: seen.append((done, total)))
    mine = _tau_columns(session.burst_results)
    assert sorted(mine) == sorted(ref["columns"]) and "Tau (green)" in mine and "Tau (red)" in mine
    for key in mine:
        np.testing.assert_allclose(
            mine[key], _a(ref["columns"][key]), rtol=1e-9, atol=1e-12, equal_nan=True, err_msg=key
        )
    # the batch fitted the detector on screen with its live window (it used the 0..128 seed before the fix)
    assert (
        session.settings_of("red").micro_time_start
        == ref["red_micro_time_start_in_channel_settings"]
    )
    assert session.settings_of("red").micro_time_start == ref["wizard_micro_time_start"] != 0
    assert len(session.burst_results) == ref["n_rows"] == 2 * engine.row_count(session.df_bursts)
    assert seen and seen[-1][0] == seen[-1][1] == engine.row_count(session.df_bursts)
    # the exported b?4 tables: the same files, the same header and the same number of lines
    written = session.export_results()
    assert written and all(
        p.suffix in (".bg4", ".br4") for p in written if p.suffix.startswith(".b")
    )
    tables = {
        p.relative_to(own / BURST_TABLE.parent.parent).as_posix(): p
        for p in written
        if p.suffix in (".bg4", ".br4")
    }
    assert sorted(tables) == sorted(ref["exports"])
    for name, path in tables.items():
        lines = path.read_text().splitlines()
        assert lines[0] == ref["exports"][name]["header"], name
        assert len(lines) == ref["exports"][name]["n_lines"], name
    finite = mine["Tau (green)"][np.isfinite(mine["Tau (green)"])]
    assert finite.size > 100 and 0.1 < np.median(finite) < 10.0


def test_session_settings_round_trip():
    s = engine.MleSession()
    s.set_detectors(CHANNEL_SETTINGS["detectors"], "SPC-130")
    s.current_detector = "red"
    s.settings.tau, s.settings.fix_gamma, s.settings.micro_time_stop = 2.5, False, 99
    s.set_binning(16)
    other = engine.MleSession()
    other.apply_settings_payload(s.settings_payload())
    assert other.settings_of("red").tau == 2.5 and other.settings_of("red").fix_gamma is False
    assert (
        other.settings_of("red").micro_time_stop == 99 and other.template.micro_time_binning == 16
    )
    assert other.file_type == "SPC-130" and list(other.detectors) == ["green", "red"]
