"""Burst MLE's IRF is the IRF Estimation tool's: one extraction, routed there, shown there.

On the simulated session of Burst Analysis (``burst_analysis/demo.py``: a Gaussian IRF of known
width, a measured water scatter and an Rh110 reference beside it) the IRF Burst MLE takes from the
reference dye is the tool's extraction (handed to it, the tool computes the identical IRF), and it
matches the measured scatter. The exact difference used before ``D[i] - a D[i-1]`` read the
rotation of the dye into the VH IRF: 82 ps late, TV 0.26 from the scatter.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.burst.burst_analysis import demo
from chisurf.plugins.burst.burst_mle_analysis import engine
from chisurf.plugins.fluorescence_decay.irf_estimator.gui.view_model import IRFViewModel


@pytest.fixture(scope="module")
def files(tmp_path_factory):
    return demo.make_demo(tmp_path_factory.mktemp("irf_tool_demo"))


@pytest.fixture(scope="module")
def session():
    s = engine.MleSession()
    s.set_definition(demo.SETUP)
    return s


def _tv(a, b) -> float:
    a, b = np.clip(a, 0, None), np.clip(b, 0, None)
    return 0.5 * float(np.abs(a / a.sum() - b / b.sum()).sum())


def test_the_reference_dye_irf_is_the_tools_and_matches_the_scatter(session, files):
    irf, text = session.irf_pattern("G|G", [files["reference"]])
    assert "Rh110" in text and "deconvolved" in text and "rotation" in text
    source = session.irf_inputs["G|G"]
    assert source["kind"] == "reference" and source["dye"] == "Rh110"

    # the tool, given what Burst MLE extracted from, extracts the same IRF
    tool = IRFViewModel()
    tool.receive_source(dict(source, detector="G|G", origin="Burst MLE"))
    assert tool.source == "reference" and tool.vv_vh
    tool.estimate()
    np.testing.assert_allclose(np.asarray(tool.result.irf), irf, atol=1e-12)
    assert tool.extraction.text == text

    # ... and it is the scatter measured beside it (the IRF of the simulation)
    scatter, scatter_text = session.irf_pattern("G|G", [files["irf"]])
    assert scatter_text.startswith("scatter")
    half = irf.size // 2
    for got, measured in ((irf[:half], scatter[:half]), (irf[half:], scatter[half:])):
        assert _tv(got, measured) < 0.12
        t = np.arange(half)
        centre = float((got * t).sum() / got.sum() - (measured * t).sum() / measured.sum())
        assert abs(centre) < 0.6  # bins (64 ps): the centre within ~40 ps


def test_auto_takes_the_dye_first_and_the_scatter_is_routed_too(session, files):
    irf, text = session.irf_pattern("G|G", [files["reference"], files["irf"]])
    assert "Rh110" in text and session.irf_inputs["G|G"]["kind"] == "reference"
    session.choose_irf("G|G", "measurement")
    irf = session.irf_np["G|G"]
    assert session.irf_inputs["G|G"]["kind"] == "scatter"
    tool = IRFViewModel()
    tool.receive_source(session.irf_inputs["G|G"])
    tool.estimate()
    np.testing.assert_allclose(np.asarray(tool.result.irf), irf, atol=1e-12)


def test_the_irf_tool_button_hands_the_source_to_the_irf_tool(session, files):
    """Burst MLE's **IRF tool** hands what the detector's IRF came from to IRF Estimation (the
    shell's hand-off), whose receive hook extracts the same IRF."""
    import json
    from pathlib import Path

    from chisurf.core.plugin import handoff
    from chisurf.plugins.burst.burst_mle_analysis.gui.native import MleNativeApp
    from chisurf.plugins.fluorescence_decay.irf_estimator.gui import app as tool_app

    manifest = json.loads((Path(tool_app.__file__).parents[1] / "manifest.json").read_text())

    class Host:
        def __init__(self):
            self.sent = []

        def accepts(self, plugin_id, kind):
            return handoff.accepted(plugin_id, kind, manifest) if plugin_id == "irf_estimator" else None

        def hand_off(self, plugin_id, kind, payload, **_extra):
            self.sent.append((plugin_id, kind, payload))

    window = MleNativeApp()
    host = Host()
    handoff.install_host(host)
    try:
        session.irf_pattern("G|G", [files["reference"]])
        window.model.session.irf_inputs["G|G"] = session.irf_inputs["G|G"]
        window.model.session.current_detector = "G|G"
        assert window.open_in_irf_tool()
        (plugin_id, kind, payload), = host.sent
        assert (plugin_id, kind) == ("irf_estimator", "irf_source")
        assert payload["irf_source"]["detector"] == "G|G" and payload["irf_source"]["origin"] == "Burst MLE"
        tool = tool_app.IRFEstimatorApp()
        try:
            tool_app.receive_irf_source(tool, payload)
            assert tool.future is not None
            tool.future.result(timeout=60)
        finally:
            tool.close()
        window.model.session.irf_inputs.pop("G|G")
        assert not window.open_in_irf_tool()  # nothing extracted from a measurement: said, not sent
        assert len(host.sent) == 1
    finally:
        handoff.uninstall_host(host)
        window.close()


def test_an_irf_tuned_in_the_irf_tool_comes_back_and_is_fitted(files):
    """The round trip: Burst MLE opens the IRF tool with its reference dye; the user changes the
    rotation there and estimates; that IRF (the same arrays) is Burst MLE's from then on, the
    selector says "IRF tool (tuned)", and another source takes over only once confirmed."""
    import json
    import time
    from pathlib import Path

    from chisurf.core.plugin import handoff
    from chisurf.plugins.burst.burst_mle_analysis.gui.native import MleNativeApp
    from chisurf.plugins.fluorescence_decay.irf_estimator.gui import app as tool_app

    manifest = json.loads((Path(tool_app.__file__).parents[1] / "manifest.json").read_text())
    tool = tool_app.IRFEstimatorApp()

    class Host:  # the shell: opens the tool and delivers the payload to its receive hook
        def accepts(self, plugin_id, kind):
            return handoff.accepted(plugin_id, kind, manifest) if plugin_id == "irf_estimator" else None

        def hand_off(self, plugin_id, kind, payload, **_extra):
            tool_app.receive_irf_source(tool, payload)

    def settle():
        end = time.monotonic() + 60
        while tool.future is not None and time.monotonic() < end:
            time.sleep(0.01)
            tool.poll()

    window = MleNativeApp()
    session = window.model.session
    session.set_definition(demo.SETUP)
    session.current_detector = "G|G"
    session.irf_pattern("G|G", [files["reference"]])
    session.apply_irf_choice("G|G")
    extracted = session.irf_np["G|G"].copy()
    host = Host()
    handoff.install_host(host)
    try:
        assert window.open_in_irf_tool()
        settle()
        np.testing.assert_allclose(np.asarray(tool.model.result.irf), extracted)
        window._take_tuned()
        assert not window.__dict__.get("_tuned_pending"), "opening the tool sends nothing back"
        assert window.model.irf_from == "auto"
        # the user tunes: another rotation, then Estimate
        tool.model.advanced = True
        tool.model.reference_rho_ns = 0.5
        assert tool.start_estimate()
        settle()
        tuned = np.asarray(tool.model.result.irf, dtype=float)
        assert not np.allclose(tuned, extracted)
        window._take_tuned()
        assert window.model.irf_from == "tuned"
        np.testing.assert_array_equal(session.irf_np["G|G"], tuned)
        assert window.model.irf_status().startswith("IRF tool (tuned)")
        assert session.irf_source["G|G"].startswith("IRF tool (tuned)")
        # another source: asked first, then the tuned IRF goes
        window.model.irf_from = "reference"
        assert window.model.irf_from == "tuned" and window.model.irf_confirm == "reference"
        window.model.confirm_irf_from(False)
        assert window.model.irf_from == "tuned"
        window.model.irf_from = "reference"
        window.model.confirm_irf_from(True)
        assert window.model.irf_from == "reference"
        np.testing.assert_allclose(session.irf_np["G|G"], extracted)
        assert "tuned" not in [k for k, _ in window.model.irf_from_choices()]
    finally:
        handoff.uninstall_host(host)
        tool.close()
        window.close()


def test_single_molecule_conditions_are_told_from_bulk():
    rng = np.random.default_rng(3)
    bulk = np.sort(rng.uniform(0, 10.0, 500_000))  # 50 kHz all the time
    background = rng.uniform(0, 10.0, 10_000)  # 1 kHz ...
    bursts = np.concatenate([c + rng.exponential(2e-4, 80) for c in rng.uniform(0, 10.0, 600)])
    sm = np.sort(np.concatenate([background, bursts]))  # ... and bright 1 ms bursts
    assert not engine.single_molecule(bulk)
    assert engine.single_molecule(sm)


def test_the_shift_is_calibrated_against_the_single_molecule_dye_first():
    """A reference dye measured at single-molecule conditions sets the IRF's time shift (it has
    the sample's count rates and pile-up); a bulk one only without it."""
    from test.fluorescence.test_irf_from_references import DT, _irf, _shifted_reference

    session = engine.MleSession()
    session.set_detectors({"G|G": {"chs": [0, 1], "micro_time_ranges": []}})
    irf = _irf()
    session.irf_np["G|G"] = np.hstack([irf / irf.sum(), irf / irf.sum()])
    settings = session.settings_of("G|G")
    settings.irf_threshold_vv = settings.irf_threshold_vh = 0.0

    def record(shift, sm, seed):
        vv, vh = _shifted_reference(shift, seed=seed)
        return {"path": f"Rh110_{'sm' if sm else 'bulk'}.ptu", "dye": "Rh110", "vv": vv, "vh": vh,
                "dt_ns": DT, "window": None, "single_molecule": sm, "tau_ns": 4.0,
                "tau_source": {"sources": [{"citation": "ISS"}]}}

    session.reference_records["G|G"] = [record(0.0, False, 1), record(1.25, True, 2)]
    found = session.calibrate_shift("G|G")
    assert found["single_molecule"] and found["source"] == "single-molecule reference dye"
    assert found["shift_vv"] == pytest.approx(1.25, abs=0.15)
    assert settings.shift_sp == found["shift_vv"] and settings.shift_ss == found["shift_vh"]
    session.reference_records["G|G"] = [record(0.0, False, 1)]
    found = session.calibrate_shift("G|G")
    assert not found["single_molecule"] and found["shift_vv"] == pytest.approx(0.0, abs=0.15)
    assert not found["warning"]  # no bursts to compare the rate with
    # a bulk reference at many times the bursts' count rate is warned of (SPAD timing moves
    # with the count rate); its rate and the bursts' go into the record
    bulk = record(0.0, False, 1)
    bulk["rate_khz"] = 400.0
    session.reference_records["G|G"] = [bulk]
    session.burst_count_rate_khz = lambda det: 20.0
    found = session.calibrate_shift("G|G")
    assert found["reference_rate_khz"] == 400.0 and found["burst_rate_khz"] == 20.0
    assert "bulk reference" in found["warning"] and "20x" in found["warning"]
    del session.burst_count_rate_khz
    session.shift_edits["G|G"] = {"shift_vv": 0.4, "shift_vh": -0.3, "source": "IRF tool"}  # wins
    found = session.calibrate_shift("G|G")
    assert (settings.shift_sp, settings.shift_ss) == (0.4, -0.3) and found["edit_source"] == "IRF tool"
    assert found["edited"] == ["shift_vh", "shift_vv"]
    assert found["calibrated_vv"] == pytest.approx(0.0, abs=0.15)  # the calibration is kept beside


def test_the_demo_irf_shift_is_calibrated_near_zero(session, files):
    """The demo's water scatter and Rh110 share the instrument: the scatter IRF calibrated against
    the dye needs no shift; the status says the shift was calibrated."""
    session.irf_pattern("G|G", [files["reference"], files["irf"]])
    session.choose_irf("G|G", "measurement")
    found = session.shift_calibration["G|G"]
    assert found["dye"] == "Rh110" and found["tau_known"] and found["tau_ns"] == 4.0
    assert abs(found["shift_vv"]) < 0.4 and abs(found["shift_vh"]) < 0.4


def test_the_shift_calibration_goes_into_the_calibration_report(session, files):
    from chisurf.plugins.burst.burst_analysis.calibration_report import build_report

    session.irf_pattern("G|G", [files["reference"]])
    report = build_report({}, {}, demo.SETUP, irf_shift=session.shift_calibration)
    entry = report["irf_shift"]["G|G"]
    assert entry["dye"] == "Rh110" and entry["tau_known"] and entry["tau_ns"] == 4.0
    assert "shift_vv" in entry and "shift_vh" in entry and entry["tau_citation"]
    # the reference fit: the dye fitted with its IRF and the burst model, its chi2_r and residuals
    assert entry["fit_chi2r"] > 0 and entry["fit_g_fitted"] > 0
    lo, hi = entry["fit_window"]
    residuals = entry["fit_residuals"]
    assert len(residuals) == 2 * len(session.reference_records["G|G"][0]["vv"])
    assert residuals[lo] is not None and (lo == 0 or residuals[0] is None)


def test_the_reference_dye_of_the_demo_fits_with_its_own_irf(session, files):
    """The demo's Rh110 fitted with the IRF deconvolved from it: about 1 with the G Data Selection
    computes (1.15, the simulation's); with the setup's 1.0 the fit says which G it asks for."""
    session.irf_pattern("G|G", [files["reference"]])
    session.choose_irf("G|G", "reference")
    wrong = dict(session.shift_calibration["G|G"])
    assert wrong["fit_g_fitted"] == pytest.approx(1.15, rel=0.03)
    assert "apply the G of Data Selection" in wrong["warning"]
    session.detectors["G|G"] = dict(session.detectors["G|G"], g_factor=1.15)
    found = session.calibrate_shift("G|G")
    assert found["fit_chi2r"] < 1.5, found["fit_text"]
    assert not found["warning"].startswith("the reference asks")
