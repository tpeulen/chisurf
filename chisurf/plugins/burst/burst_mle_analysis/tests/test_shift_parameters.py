"""The detector's three time shifts: what each does, where its start comes from, and the table.

* IRF shift VV / VH (``shift_sp`` / ``shift_ss``): the IRF moved against the VV / VH data, sub-bin;
* Shift VV/VH (``shift``): the VH decay moved against the VV decay, whole bins (data and IRF).

Their start is the calibration on the reference dye of the detector's *detection pair*: the red
detectors under green excitation (``R|G``) are the red detectors of ``R|R`` -- the G factor, the
IRF's shape and the SPAD timing are the detection side's -- so ``R|G`` takes ``R|R``'s
calibration on Alexa 647, its IRF placed at the green pulse by the setup's PIE windows. They are
rows of the Fit parameters table, fixed by default; an edit refits, is kept with the step and is
reset to the calibration.
"""

from __future__ import annotations

import copy

import numpy as np
import pytest

from chisurf.plugins.burst.burst_analysis import demo
from chisurf.plugins.burst.burst_mle_analysis import engine


@pytest.fixture(autouse=True)
def _packaged_dye_database(monkeypatch):
    from chisurf.core.fluorescence import dyes

    monkeypatch.setattr(dyes, "_entries_from_database", lambda: None)
    dyes.reference_dyes(refresh=True)
    yield
    monkeypatch.undo()
    dyes.reference_dyes(refresh=True)


@pytest.fixture(scope="module")
def red(tmp_path_factory):
    folder = tmp_path_factory.mktemp("pie_red")
    demo.make_demo(folder)
    return demo.make_red_reference(folder)


def _centre(part: np.ndarray) -> float:
    t = np.arange(part.size)
    return float((part * t).sum() / part.sum())


# -- what each shift does ------------------------------------------------------------------- #
def test_the_irf_shifts_move_the_irf_against_vv_and_vh_each():
    session = engine.MleSession()
    session.set_detectors({"G|G": {"chs": [0, 1], "micro_time_ranges": []}})
    t = np.arange(256)
    peak = np.exp(-0.5 * ((t - 100.0) / 3.0) ** 2)
    session.irf_np["G|G"] = np.hstack([peak, peak])
    settings = session.settings
    base = session.irf()
    settings.shift_sp = 0.5
    moved = session.irf()
    assert _centre(moved[:256]) - _centre(base[:256]) == pytest.approx(0.5, abs=0.02)
    assert _centre(moved[256:]) == pytest.approx(_centre(base[256:]), abs=1e-9)
    settings.shift_sp, settings.shift_ss = 0.0, -0.75
    moved = session.irf()
    assert _centre(moved[256:]) - _centre(base[256:]) == pytest.approx(-0.75, abs=0.02)
    assert _centre(moved[:256]) == pytest.approx(_centre(base[:256]), abs=1e-9)


def test_the_vv_vh_shift_moves_the_vh_data_and_the_vh_irf_in_whole_bins():
    import tttrlib

    n = 2000
    micro = np.full(n, 100, dtype=np.uint16)
    channel = np.tile(np.array([0, 1], dtype=np.int8), n // 2)
    stream = tttrlib.TTTR(np.arange(n, dtype=np.uint64), micro, channel, np.zeros(n, dtype=np.int8))
    stream.header.set_number_of_micro_time_channels(256)
    plain = np.asarray(engine.vv_vh_histogram(stream, [0, 1], (0, 0), 1, shift=0, normalize_counts=0))
    rolled = np.asarray(engine.vv_vh_histogram(stream, [0, 1], (0, 0), 1, shift=2, normalize_counts=0))
    half = plain.size // 2
    assert int(np.argmax(rolled[:half])) == int(np.argmax(plain[:half])) == 100  # VV stays
    assert int(np.argmax(rolled[half:])) == int(np.argmax(plain[half:])) + 2  # VH moves
    peak = np.zeros(256)
    peak[50] = 1.0
    irf = engine.process_irf(np.hstack([peak, peak]), micro_time_range=(0, 0), binning=1, shift=2)
    assert int(np.argmax(irf[:256])) == 50 and int(np.argmax(irf[256:])) == 52


# -- R|G is calibrated on R|R: one detection pair --------------------------------------------- #
def test_r_g_takes_the_red_detectors_calibration_placed_at_the_green_window(red):
    session = engine.MleSession()
    session.set_definition(copy.deepcopy(demo.SETUP_PIE))
    session.irf_one_for_all = False
    # Data Selection's G of the red detector pair, written to both (the detection side's)
    session.detectors["R|R"]["g_factor"] = demo.TRUTH_RED["g_factor"]
    session.detectors["R|G"]["g_factor"] = 1.0  # not used: R|G is calibrated with R|R's G
    for det in ("R|R", "R|G"):
        assert session.set_pattern_files("irf", det, [red]) == [det]
    assert session.detection_siblings("R|G") == ["R|G", "R|R"]
    binning = demo.SETUP_PIE["tttr_reading"]["micro_time_binning"]
    offset = session.window_offset("R|G", "R|R")
    assert offset == -512 // binning
    record = session.reference_records["R|G"][0]
    assert record["detector"] == "R|R" and record["offset_bins"] == offset
    # the IRF: R|R's, at the green pulse (the green prompt is at 2.0 ns, the red one 18.4 ns)
    half = session.irf_np["R|G"].size // 2
    np.testing.assert_allclose(session.irf_np["R|G"][:half], np.roll(session.irf_np["R|R"][:half], offset))
    dt = demo.MICRO_S * 1e9 * binning
    assert int(np.argmax(session.irf_np["R|G"][:half])) * dt == pytest.approx(demo.TRUTH["prompt_ns"], abs=0.2)
    # the shifts and the reference fit: R|R's, with R|R's G -- one red calibration
    rr, rg = session.shift_calibration["R|R"], session.shift_calibration["R|G"]
    assert rg["calibrated_on"] == "R|R" and rg["dye"] == "Alexa647"
    assert rg["shift_vv"] == pytest.approx(rr["shift_vv"], abs=1e-9)
    assert rg["shift_vh"] == pytest.approx(rr["shift_vh"], abs=1e-9)
    assert rg["fit_chi2r"] == pytest.approx(rr["fit_chi2r"]) and rg["fit_g"] == pytest.approx(demo.TRUTH_RED["g_factor"])
    assert rr["fit_chi2r"] < 1.6, rr["fit_text"]
    # G|G sees no red dye: no reference, no calibration from it
    assert session.set_pattern_files("irf", "G|G", [red]) == []


# -- the Fit parameters table ----------------------------------------------------------------- #
@pytest.fixture
def example():
    from chisurf.plugins.burst.burst_mle_analysis.gui.model import MleViewModel

    model = MleViewModel()
    model.load_example()
    model.session.auto_extract()
    model.refit()
    return model


def _row(model, name):
    return next(r for r in model.parameter_records() if r["name"] == name)


def test_the_shifts_are_rows_edited_refitted_kept_and_reset(example):
    model = example
    det = model.session.current_detector
    rows = {r["name"]: r for r in model.shift_records()}
    assert list(rows) == ["IRF shift VV", "IRF shift VH", "Shift VV/VH"]
    assert all(r["fixed"] for r in rows.values())  # fixed by default
    assert "not calibrated" in rows["IRF shift VV"]["tip"]  # the example has no reference dye
    assert model.parameter_cell_editable(rows["IRF shift VV"], "start")
    assert not model.shifts_edited

    model.edit_parameter(rows["IRF shift VV"], "start", 0.3)  # an edit refits at once
    assert model.session.settings.shift_sp == pytest.approx(0.3)
    assert _row(model, "IRF shift VV")["start"] == 0.3 and _row(model, "IRF shift VV")["result"] == "0.30"
    assert model.session.outcome is not None and model.shifts_edited
    assert "set by hand" in _row(model, "IRF shift VV")["tip"]
    model.edit_parameter(_row(model, "Shift VV/VH"), "start", 1)
    assert model.session.settings.shift == 1

    # kept with the step's settings (the hub's) and in a settings file
    from chisurf.plugins.burst.burst_mle_analysis.gui.native import MleNativeApp

    app = MleNativeApp(model)
    state = app.export_settings()
    assert state["shift_edits"][det]["shift_vv"] == 0.3 and state["shift_edits"][det]["shift"] == 1
    assert model.session.settings_payload()["shift_edits"][det]["shift_vv"] == 0.3
    from chisurf.plugins.burst.burst_mle_analysis.gui.model import MleViewModel

    other = MleNativeApp(MleViewModel())
    other.restore_settings(state)
    assert other.model.session.shift_edits[det]["shift_vv"] == 0.3

    model.reset_shifts()  # back to the calibration (none here: 0)
    assert not model.shifts_edited
    assert (model.session.settings.shift_sp, model.session.settings.shift) == (0.0, 0)
    assert model.session.outcome is not None


def test_an_unfixed_shift_is_refined_by_the_fit_within_its_bound(example):
    model = example
    fixed = model.two_istar
    model.edit_parameter(_row(model, "IRF shift VV"), "start", 0.4)
    displaced = model.two_istar
    model.edit_parameter(_row(model, "IRF shift VV"), "fixed", False)
    used = model.session.settings.shift_sp
    assert abs(used - 0.4) <= engine.SHIFT_BOUNDS["shift_sp"] + 1e-9
    assert model.two_istar <= displaced + 1e-9
    assert _row(model, "IRF shift VV")["start"] == 0.4  # the start stays; Result is what was used
    assert _row(model, "IRF shift VV")["result"] == f"{used:.2f}"
    assert np.isfinite(fixed)
