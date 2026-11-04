"""The guided calibration workflow engine and the three shipped workflows.

Pins the contract the GUI will sit on: staged prerequisites, explicit user
confirmations, editable composition, step-specific transparent quality metrics
whose limits are the user's (a shipped workflow carries NO numeric thresholds),
and calibrations recorded as measured results with provenance. The power-diode
workflow pins the owner's gates: only verified-installed lasers, a verified
single-laser readback before capture, keyed calibrations, and no hardware
control anywhere in the backend.
"""

from __future__ import annotations

import calendar
import datetime
import json

import numpy as np
import pytest

from chisurf.plugins.core.acq.live import power_calibration
from chisurf.plugins.core.acq.live.calibration import library, workflow
from chisurf.plugins.core.acq.live.calibration.lasers import (
    AVAILABLE_LASERS_NM,
    LaserInventory,
)

# -- shared fixtures ------------------------------------------------------------------------------

EXPECTED_STEPS = [
    "instrument_setup",
    "water_irf",
    "buffer_background",
    "green_reference",
    "red_reference",
    "donor_only_crosstalk",
    "acceptor_only_direct",
    "dna_pie_gamma",
    "fret_summary",
]


@pytest.fixture()
def inventory() -> LaserInventory:
    inv = LaserInventory()
    inv.verify_installed(488, evidence="HW config: 488 head present, interlock OK")
    return inv


@pytest.fixture()
def wf() -> workflow.CalibrationWorkflow:
    return library.build_workflow("fret")


@pytest.fixture()
def hist(tmp_path):
    """A synthetic water-IRF histogram file (gaussian, sigma 0.15 ns) and a
    mono-exponential tail (tau 3.0 ns), both at 0.02 ns bins."""
    bin_ns = 0.02
    t = (np.arange(2000) + 0.5) * bin_ns
    irf = 10000.0 * np.exp(-0.5 * ((t - 20.0) / 0.15) ** 2)
    p_irf = tmp_path / "water_irf.npy"
    np.save(p_irf, irf)
    tail = 20000.0 * np.exp(-t / 3.0)
    p_tail = tmp_path / "rh110_tail.npy"
    np.save(p_tail, tail)
    p_red = tmp_path / "alexa647_tail.npy"
    np.save(p_red, 15000.0 * np.exp(-t / 1.8))
    return {"irf": p_irf, "green": p_tail, "red": p_red, "bin_ns": bin_ns}


def _set(wf, step_id, **values):
    for key, value in values.items():
        wf.set_value(step_id, key, value)


def _fret_plan(hist):
    """The FRET chain in order, with test-owned values (gamma truth: 0.8 at E 0.5)."""
    bin_ns = hist["bin_ns"]
    return [
        ("instrument_setup", dict(setup_name="MT200 PIE", setup_notes="488/640 pulsed")),
        ("water_irf", dict(file=str(hist["irf"]), micro_time_resolution_ns=bin_ns)),
        ("buffer_background", dict(photons=60000, acquisition_time_s=60.0, sample="50 mM Tris")),
        ("green_reference", dict(
            file=str(hist["green"]), micro_time_resolution_ns=bin_ns,
            tail_start_ns=10.0, tail_stop_ns=100.0, sample="Rh110 in buffer",
        )),
        ("red_reference", dict(
            file=str(hist["red"]), micro_time_resolution_ns=bin_ns,
            tail_start_ns=8.0, tail_stop_ns=60.0, sample="Alexa647 in buffer",
        )),
        ("donor_only_crosstalk", dict(
            i_dd=10000.0, i_ad_raw=300.0, sample="Alexa488 DNA, donor only",
        )),
        ("acceptor_only_direct", dict(
            i_aa=10000.0, i_ad_raw=500.0, sample="Alexa647 DNA, acceptor only",
        )),
        ("dna_pie_gamma", dict(
            i_dd=6250.0, i_ad_raw=5812.5, i_aa=12500.0,
            beta=1.25, stoichiometry_confirmed=True, sample="dsDNA 20 bp, 1:1",
        )),
        ("fret_summary", dict(note="accepted")),
    ]


def _confirm_fret(wf, hist, upto="fret_summary"):
    """Fill and confirm the FRET chain in order, stopping after `upto`."""
    for step_id, values in _fret_plan(hist):
        if step_id == "buffer_background":
            wf.configure_limits("buffer_background", "background_rate_khz", maximum=5.0)
        for key, value in values.items():
            wf.set_value(step_id, key, value)
        if step_id == "dna_pie_gamma":
            wf.adopt_suggestions(step_id)  # alpha and delta from the recorded results
        wf.confirm(step_id)
        if step_id == upto:
            return


# -- the library and its honesty -----------------------------------------------------------------

def test_the_three_workflows_exist_with_their_steps():
    fret = library.build_workflow("fret")
    assert [s.id for s in fret.steps] == EXPECTED_STEPS
    pol = library.build_workflow("polarization")
    assert [s.id for s in pol.steps] == [
        "instrument_setup", "water_irf", "buffer_background",
        "polarization_reference", "polarization_summary",
    ]
    power = library.build_workflow("power_diode", inventory=LaserInventory())
    assert [s.id for s in power.steps] == [
        "laser_selection", "verify_setup", "verify_single_laser", "dark_offset",
        "objective_meter_setup", "power_points", "power_summary",
    ]
    with pytest.raises(ValueError, match="kind"):
        library.build_workflow("raman")


def test_shipped_workflows_carry_no_numerical_thresholds():
    for kind in ("fret", "polarization", "power_diode"):
        wf = library.build_workflow(kind, inventory=LaserInventory())
        for step in wf.steps:
            for metric in step.metrics:
                assert metric.limits.minimum is None
                assert metric.limits.maximum is None


def test_the_optics_catalog_is_a_editable_skeleton_without_invented_numbers():
    cat = library.optics_catalog()
    dyes = {d["name"]: d for d in cat["dyes"]}
    for name in ("Alexa488", "Cy3", "Cy5", "Rh110", "Alexa647", "Atto655"):
        assert name in dyes, name
        assert dyes[name]["excitation_nm"] is None and dyes[name]["emission_nm"] is None
    assert cat["beam_splitters"], "at least named placeholders for the user's splitters"
    for bs in cat["beam_splitters"]:
        assert bs["cutoff_nm"] is None and bs["bands"] is None
    assert list(cat["lasers_nm"]) == list(AVAILABLE_LASERS_NM)


def test_the_calibration_backend_imports_no_hardware_module():
    import inspect
    from chisurf.plugins.core.acq.live import calibration

    pkg_dir = calibration.__path__[0]
    import pathlib

    for path in pathlib.Path(pkg_dir).glob("*.py"):
        src = path.read_text()
        for forbidden in (
            "from .devices", "from ..devices", "live.devices",
            "from .laser import", "from ..laser import", "live.laser",
            "from . import laser", "from . import devices",
        ):
            assert forbidden not in src, f"{path.name}: {forbidden}"


# -- staged prerequisites and confirmations ------------------------------------------------------

def test_later_steps_are_blocked_until_their_prerequisites_are_confirmed(wf):
    overview = wf.overview()
    assert overview["overall"] == "in progress"
    states = {s["id"]: s for s in overview["steps"]}
    assert states["instrument_setup"]["state"] == "ready"
    assert states["water_irf"]["state"] == "pending"
    assert "instrument_setup" in " ".join(states["water_irf"]["blockers"])


def test_confirm_refuses_and_names_the_missing_required_inputs(wf):
    ok, blockers = wf.can_confirm("instrument_setup")
    assert not ok
    joined = " ".join(blockers)
    assert "setup_name" in joined


def test_confirm_refuses_while_prerequisites_are_open(wf):
    _set(wf, "water_irf", file="nowhere.npy", micro_time_resolution_ns=0.02)
    ok, blockers = wf.can_confirm("water_irf")
    assert not ok
    assert any("instrument_setup" in b for b in blockers)


def test_a_file_input_must_exist_before_confirmation(wf, tmp_path):
    _set(wf, "instrument_setup", setup_name="MT200 PIE")
    wf.confirm("instrument_setup")
    _set(wf, "water_irf", file=str(tmp_path / "missing.npy"), micro_time_resolution_ns=0.02)
    ok, blockers = wf.can_confirm("water_irf")
    assert not ok
    assert any("missing.npy" in b for b in blockers)
    real = tmp_path / "irf.npy"
    np.save(real, np.ones(10))
    wf.set_value("water_irf", "file", str(real))
    ok, _ = wf.can_confirm("water_irf")
    assert ok


def test_values_cannot_change_after_confirmation_until_unconfirmed(wf):
    _set(wf, "instrument_setup", setup_name="MT200 PIE")
    wf.confirm("instrument_setup", note="locked")
    with pytest.raises(workflow.StepConfirmed):
        wf.set_value("instrument_setup", "setup_name", "other")
    wf.unconfirm("instrument_setup", note="need to fix the name")
    wf.set_value("instrument_setup", "setup_name", "MT200 PIE v2")
    assert wf.state["instrument_setup"].values["setup_name"] == "MT200 PIE v2"


def test_unconfirm_cascades_to_the_steps_that_depended_on_it(wf, hist):
    _confirm_fret(wf, hist, upto="dna_pie_gamma")
    assert wf.state["dna_pie_gamma"].confirmed
    wf.unconfirm("donor_only_crosstalk", note="wrong donor-only sample")
    assert not wf.state["dna_pie_gamma"].confirmed  # it consumed this stage's result
    assert wf.state["acceptor_only_direct"].confirmed  # an independent branch stays
    assert wf.state["buffer_background"].confirmed


def test_skip_records_a_reason_and_satisfies_prerequisites_until_unskipped(wf):
    _set(wf, "instrument_setup", setup_name="MT200 PIE")
    wf.confirm("instrument_setup")
    with pytest.raises(ValueError, match="reason"):
        wf.skip("water_irf", reason="   ")
    wf.skip("water_irf", reason="intensity-only FRET first; IRF measured next week")
    assert wf.state["water_irf"].state == "skipped"
    _set(wf, "buffer_background", photons=60000, acquisition_time_s=60.0)
    ok, _ = wf.can_confirm("buffer_background")
    assert ok
    wf.unskip("water_irf")
    assert wf.state["water_irf"].state == "ready"


def test_a_skipped_step_is_visible_as_skipped_with_its_reason(wf):
    _set(wf, "instrument_setup", setup_name="MT200 PIE")
    wf.confirm("instrument_setup")
    wf.skip("water_irf", reason="later")
    st = wf.status("water_irf")
    assert st["state"] == "skipped" and st["skip_reason"] == "later"


# -- transparent, configurable metrics -----------------------------------------------------------

def test_metric_verdicts_not_configured_within_outside_and_unavailable(wf, hist):
    _set(wf, "instrument_setup", setup_name="MT200 PIE")
    wf.confirm("instrument_setup")
    _set(wf, "water_irf", file=str(hist["irf"]), micro_time_resolution_ns=hist["bin_ns"])
    metrics = {mt["key"]: mt for mt in wf.status("water_irf")["metrics"]}
    assert metrics["irf_fwhm_ns"]["verdict"] == "not configured"
    assert metrics["irf_fwhm_ns"]["value"] == pytest.approx(2.3548 * 0.15, rel=0.02)

    wf.configure_limits("water_irf", "irf_fwhm_ns", maximum=1.0)
    metrics = {mt["key"]: mt for mt in wf.status("water_irf")["metrics"]}
    assert metrics["irf_fwhm_ns"]["verdict"] == "within bounds"

    wf.configure_limits("water_irf", "irf_fwhm_ns", maximum=0.1)
    metrics = {mt["key"]: mt for mt in wf.status("water_irf")["metrics"]}
    assert metrics["irf_fwhm_ns"]["verdict"] == "outside bounds"

    wf.clear_limits("water_irf", "irf_fwhm_ns")
    _set(wf, "water_irf", file="")
    metrics = {mt["key"]: mt for mt in wf.status("water_irf")["metrics"]}
    assert metrics["irf_fwhm_ns"]["verdict"] == "not computable"
    assert metrics["irf_fwhm_ns"]["detail"]

    wf.configure_limits("water_irf", "irf_fwhm_ns", maximum=1.0)
    with pytest.raises(ValueError, match="bounds"):
        wf.configure_limits("water_irf", "irf_fwhm_ns")
    with pytest.raises(KeyError):
        wf.configure_limits("water_irf", "no_such_metric", maximum=1.0)


def test_every_metric_documents_what_it_computes(wf):
    for step in wf.steps:
        for metric in step.metrics:
            assert metric.describe and metric.unit is not None
            assert metric.name


def test_confirmation_records_outside_limit_metrics_as_warnings_but_confirms(wf, hist):
    _set(wf, "instrument_setup", setup_name="MT200 PIE")
    wf.confirm("instrument_setup")
    wf.skip("water_irf", reason="background check only")
    _set(wf, "buffer_background", photons=600000, acquisition_time_s=60.0, sample="dirty buffer")
    wf.configure_limits("buffer_background", "background_rate_khz", maximum=5.0)
    verdicts = {mt["key"]: mt for mt in wf.status("buffer_background")["metrics"]}
    assert verdicts["background_rate_khz"]["verdict"] == "outside bounds"
    wf.confirm("buffer_background", note="user accepts a high background today")
    assert wf.state["buffer_background"].confirmed
    assert wf.state["buffer_background"].warnings == ["background_rate_khz"]


# -- the measured results ------------------------------------------------------------------------

def test_the_full_fret_workflow_records_its_calibrations_as_measured_results(wf, hist):
    _confirm_fret(wf, hist)
    assert wf.overview()["overall"] == "complete"
    summary = wf.summary()
    assert summary["alpha"]["value"] == pytest.approx(0.03)
    assert summary["delta"]["value"] == pytest.approx(0.05)
    assert summary["fret_efficiency_pie"]["value"] == pytest.approx(0.5)
    assert summary["gamma_pie"]["value"] == pytest.approx(0.8)
    assert summary["irf_fwhm_ns"]["unit"] == "ns"
    assert summary["background_rate_khz"]["value"] == pytest.approx(1.0)
    assert summary["lifetime_green_ns"]["value"] == pytest.approx(3.0, rel=0.01)
    assert summary["lifetime_red_ns"]["value"] == pytest.approx(1.8, rel=0.01)
    # provenance: every result says when, from which step, how it was obtained and on what sample
    for quantity in ("alpha", "gamma_pie", "lifetime_green_ns"):
        res = summary[quantity]
        assert res["measured_at"] and res["step_id"] and res["source"] in ("entered", "computed")
    assert summary["alpha"]["source"] == "computed"
    assert summary["alpha"]["sample"] == "Alexa488 DNA, donor only"
    assert summary["lifetime_green_ns"]["sample"] == "Rh110 in buffer"


def test_an_entered_fit_value_wins_over_the_computed_tail_fit(wf, hist):
    _set(wf, "instrument_setup", setup_name="MT200 PIE")
    wf.confirm("instrument_setup")
    _set(wf, "water_irf", file=str(hist["irf"]), micro_time_resolution_ns=hist["bin_ns"])
    wf.confirm("water_irf")
    _set(wf, "buffer_background", photons=60000, acquisition_time_s=60.0, sample="buffer")
    wf.confirm("buffer_background")
    _set(
        wf, "green_reference", file=str(hist["green"]), micro_time_resolution_ns=hist["bin_ns"],
        tail_start_ns=10.0, tail_stop_ns=100.0, lifetime_fit_ns=2.95, sample="Rh110",
    )
    wf.confirm("green_reference")
    res = wf.summary()["lifetime_green_ns"]
    assert res["value"] == pytest.approx(2.95)
    assert res["source"] == "entered"


def test_suggested_values_adopt_the_recorded_results_of_earlier_stages(wf, hist):
    _confirm_fret(wf, hist, upto="donor_only_crosstalk")
    _set(wf, "acceptor_only_direct", i_aa=10000.0, i_ad_raw=500.0, sample="acceptor only")
    wf.confirm("acceptor_only_direct")
    suggestions = wf.suggested_values("dna_pie_gamma")
    assert suggestions["alpha"] == pytest.approx(0.03)
    assert suggestions["delta"] == pytest.approx(0.05)
    wf.adopt_suggestions("dna_pie_gamma")
    assert wf.state["dna_pie_gamma"].values["alpha"] == pytest.approx(0.03)
    assert wf.state["dna_pie_gamma"].values["delta"] == pytest.approx(0.05)


def test_the_gamma_stage_refuses_without_the_stoichiometry_confirmation(wf, hist):
    _confirm_fret(wf, hist, upto="acceptor_only_direct")
    wf.adopt_suggestions("dna_pie_gamma")
    _set(wf, "dna_pie_gamma", i_dd=6250.0, i_ad_raw=5812.5, i_aa=12500.0, beta=1.25,
         stoichiometry_confirmed=False, sample="dsDNA")
    ok, blockers = wf.can_confirm("dna_pie_gamma")
    assert not ok and any("stoichiometry" in b.lower() for b in blockers)


def test_the_polarization_workflow_records_the_g_factor(inventory, hist):
    wf = library.build_workflow("polarization")
    _set(wf, "instrument_setup", setup_name="MT200 MFD", setup_notes="par/perp channels")
    wf.confirm("instrument_setup")
    _set(wf, "water_irf", file=str(hist["irf"]), micro_time_resolution_ns=hist["bin_ns"])
    wf.confirm("water_irf")
    _set(wf, "buffer_background", photons=60000, acquisition_time_s=60.0, sample="water")
    wf.confirm("buffer_background")
    _set(wf, "polarization_reference", i_par=2400.0, i_perp=1000.0, r_assumed=0.1,
         sample="Rh110 in water, fast rotation")
    wf.confirm("polarization_reference")
    assert wf.summary()["g_factor"]["value"] == pytest.approx(1.8)
    assert wf.summary()["g_factor"]["source"] == "computed"


# -- an editable composition ---------------------------------------------------------------------

def test_steps_can_be_added_moved_and_removed(wf, hist):
    gamma_spec = library.step_spec("dna_pie_gamma")
    wf.add_step(gamma_spec)  # a second construct
    second = [s.id for s in wf.steps if s.spec_id == "dna_pie_gamma"][1]
    assert second != "dna_pie_gamma"
    # prerequisites may name the base id: either instance satisfies them
    assert wf.state[second].state == "pending"

    wf.remove_step(second)
    assert [s.id for s in wf.steps] == EXPECTED_STEPS

    wf.move_step("green_reference", 2)  # measure the green reference right after the setup
    assert [s.id for s in wf.steps][2] == "green_reference"
    # the chain still holds: red reference needs its predecessors re-checked
    st = wf.status("red_reference")
    assert st["state"] == "pending"


def test_a_confirmed_step_cannot_be_removed_without_unconfirming(wf, hist):
    _confirm_fret(wf, hist, upto="instrument_setup")
    with pytest.raises(ValueError, match="unconfirm"):
        wf.remove_step("instrument_setup")
    wf.unconfirm("instrument_setup", note="restructure")
    wf.remove_step("instrument_setup")
    assert "instrument_setup" not in [s.id for s in wf.steps]


def test_removed_prerequisites_are_reported_as_blockers(wf):
    spec = library.step_spec("water_irf")
    wf.remove_step("water_irf")
    st = wf.status("buffer_background")
    assert st["state"] == "pending"
    assert any("water_irf" in b for b in st["blockers"])
    # and a removed step can be put back
    wf.add_step(spec, index=1)
    assert [s.id for s in wf.steps][1] == "water_irf"


# -- the power-diode workflow --------------------------------------------------------------------
#
# These tests pin the DELEGATION: the workflow stages walk the user through
# capturing what chisurf.plugins.core.acq.live.power_calibration demands, and
# the recorded result is that module's own document -- one owner of the
# conversion maths, not a re-implementation in the wizard.

HEADS = json.dumps({
    "heads": [
        {"name": "LDH-488", "wavelength_nm": 488.0, "serial": "488-1234"},
        {"name": "LDH-640", "wavelength_nm": 640.0, "serial": "640-5678"},
    ]
})
READBACK = "diode readback: LDH-488 on; LDH-640 dark; shutters verified"


def _emission(single=None):
    """Verified emission states: only `single` on, every state readback-verified."""
    return json.dumps([
        {"laser": "LDH-488", "on": single == "LDH-488", "verified": True},
        {"laser": "LDH-640", "on": single == "LDH-640", "verified": True},
    ])


CONDITIONS = dict(
    rep_rate_hz=40e6, mode="pulsed", pattern="20 MHz PIE pattern",
    optical_path="RDM455/532/640, dual detection",
)
POINTS = [
    {"drive": 5.0, "meter_uw": 12.0, "diode_raw": 8.0},
    {"drive": 10.0, "meter_uw": 24.0, "diode_raw": 16.0},
    {"drive": 20.0, "meter_uw": 48.0, "diode_raw": 32.0},
]


def _power_workflow(inventory):
    wf = library.build_workflow("power_diode", inventory=inventory)
    _set(wf, "laser_selection", laser_nm=488, laser_name="LDH-488")
    wf.confirm("laser_selection", note="verified installed")
    _set(wf, "verify_setup", config_heads=HEADS)
    wf.confirm("verify_setup", note="hardware configuration read")
    _set(wf, "verify_single_laser", all_other_lasers_off_confirmed=True,
         emission_states=_emission("LDH-488"), emission_state_readback=READBACK)
    wf.confirm("verify_single_laser", note="isolation verified from readback")
    _set(wf, "dark_offset", dark_raw=0.5, emission_states=_emission())
    wf.confirm("dark_offset", note="emission blocked, every laser verified off")
    _set(wf, "objective_meter_setup", meter_setup_confirmed=True,
         meter="N1913A at the objective", meter_calibrated="2026-08-01")
    wf.confirm("objective_meter_setup", note="meter in place")
    return wf


def test_only_a_verified_installed_laser_can_be_selected():
    wf = library.build_workflow("power_diode", inventory=LaserInventory())
    _set(wf, "laser_selection", laser_nm=488)
    ok, blockers = wf.can_confirm("laser_selection")
    assert not ok and any("verified" in b.lower() for b in blockers), blockers

    inv = LaserInventory()
    inv.verify_installed(488, evidence="HW config: 488 head present, interlock OK")
    wf = library.build_workflow("power_diode", inventory=inv)
    _set(wf, "laser_selection", laser_nm=488)
    ok, blockers = wf.can_confirm("laser_selection")
    assert ok, blockers


def test_the_single_laser_claim_needs_verified_emission_states(inventory):
    wf = library.build_workflow("power_diode", inventory=inventory)
    _set(wf, "laser_selection", laser_nm=488, laser_name="LDH-488")
    wf.confirm("laser_selection", note="488 verified installed")
    _set(wf, "verify_setup", config_heads=HEADS)
    wf.confirm("verify_setup")
    _set(wf, "verify_single_laser", all_other_lasers_off_confirmed=True)

    ok, blockers = wf.can_confirm("verify_single_laser")
    assert not ok and any("parse" in b for b in blockers), blockers

    _set(wf, "verify_single_laser", emission_states=_emission("LDH-640"))
    ok, blockers = wf.can_confirm("verify_single_laser")
    assert not ok and any("alone" in b for b in blockers), blockers

    _set(wf, "verify_single_laser", emission_states=json.dumps(
        [{"laser": "LDH-488", "on": True, "verified": False},
         {"laser": "LDH-640", "on": False, "verified": True}]))
    ok, blockers = wf.can_confirm("verify_single_laser")
    assert not ok and any("LDH-488" in b for b in blockers), blockers

    _set(wf, "verify_single_laser", emission_states=_emission("LDH-488"),
         emission_state_readback=READBACK)
    ok, blockers = wf.can_confirm("verify_single_laser")
    assert ok, blockers


def test_a_changed_configuration_between_verification_and_capture_aborts(inventory):
    wf = _power_workflow(inventory)
    # at capture the user pastes the CURRENT readback again; it differs from the
    # verification readback -> the configuration changed -> abort.
    _set(wf, "power_points", config_readback="diode readback: LDH-488 on; 640 head DISCONNECTED",
         measured_on="2026-10-30", **CONDITIONS)
    wf.set_points("power_points", "points", POINTS)
    ok, blockers = wf.can_confirm("power_points")
    assert not ok
    assert any("changed" in b.lower() and "abort" in b.lower() for b in blockers), blockers


def test_power_points_capture_with_matching_readback_and_valid_fit(inventory):
    wf = _power_workflow(inventory)
    _set(wf, "power_points", config_readback=READBACK, measured_on="2026-10-30", **CONDITIONS)
    wf.set_points("power_points", "points", POINTS)
    metrics = {mt["key"]: mt for mt in wf.status("power_points")["metrics"]}
    assert metrics["n_anchors"]["value"] == 4  # the dark zero plus the three references
    # dark 0.5 -> dark-corrected anchors (7.5, 12), (15.5, 24), (31.5, 48) plus the origin
    expected_slope = (0 + 12 * 7.5 + 24 * 15.5 + 48 * 31.5) / (0 + 7.5**2 + 15.5**2 + 31.5**2)
    assert metrics["slope_uw_per_raw"]["value"] == pytest.approx(expected_slope, rel=1e-3)
    assert metrics["max_residual_uw"]["value"] > 0  # honest residuals, not a perfect world
    ok, blockers = wf.can_confirm("power_points")
    assert ok, blockers
    wf.confirm("power_points")

    _set(wf, "power_summary", note="488 µW scale adopted")
    wf.confirm("power_summary")
    res = wf.summary()["power_calibration"]

    # the result IS the companion module's document -- no parallel schema
    cal = power_calibration.PowerCalibration.from_dict(res["extra"]["power_calibration"])
    assert cal.key.laser == "LDH-488" and cal.key.wavelength_nm == 488.0
    assert cal.validate() == [], cal.validate()
    assert res["extra"]["validations"] == []
    # three calendar months, the owner's policy, computed by that module
    today = datetime.date.today()
    m = today.month - 1 + 3
    y, m = today.year + m // 12, m % 12 + 1
    assert cal.expires_on() == datetime.date(y, m, min(today.day, calendar.monthrange(y, m)[1]))
    # ... and it applies, keyed, inside the measured range
    conv = cal.convert(
        16.0,
        conditions=power_calibration.LaserConditions(
            "LDH-488", 488.0,
            repetition_rate_hz=40e6, mode="pulsed",
            pattern="20 MHz PIE pattern", optical_path="RDM455/532/640, dual detection",
        ),
        emission=power_calibration.EmissionState.from_dict(json.loads(_emission("LDH-488"))),
        config=power_calibration.ConfigIdentity.from_dict(json.loads(HEADS)),
    )
    assert conv.valid and conv.status == "measured" and conv.uw == pytest.approx(48.0 / 2)


def test_the_adoption_refuses_an_incomplete_calibration(inventory):
    wf = _power_workflow(inventory)
    _set(wf, "power_points", config_readback=READBACK, measured_on="2026-10-30", **CONDITIONS)
    # a reference the meter did not actually read a power for cannot back a calibration
    wf.set_points("power_points", "points",
                  [{"drive": 5.0, "meter_uw": 0.0, "diode_raw": 8.0}])
    wf.confirm("power_points")
    ok, blockers = wf.can_confirm("power_summary")
    assert not ok and any("not complete" in b for b in blockers), blockers


def test_power_points_refuse_invalid_rows(inventory):
    wf = library.build_workflow("power_diode", inventory=inventory)
    with pytest.raises(ValueError, match="row"):
        wf.set_points("power_points", "points", [{"drive": 5.0, "meter_uw": "high", "diode_raw": 1.0}])
    with pytest.raises(ValueError, match="meter_uw"):
        wf.set_points("power_points", "points", [{"drive": 5.0, "diode_raw": 1.0}])


def test_the_power_workflow_names_its_gates_in_the_step_texts():
    step = {s.id: s for s in library.build_workflow("power_diode", inventory=LaserInventory()).steps}
    assert "OFF" in step["verify_single_laser"].instructions
    assert "readback" in step["verify_single_laser"].instructions.lower()
    assert "never" in step["verify_single_laser"].instructions.lower()  # never inferred from intent
    assert "objective" in step["objective_meter_setup"].instructions.lower()
    assert "measured" in step["power_points"].instructions.lower()
    assert "abort" in step["power_points"].instructions.lower()
    assert "cable" in step["laser_selection"].instructions.lower()  # manual exchange, user-confirmed
    assert "never" in step["laser_selection"].instructions.lower()  # never auto-switch
    assert "3 calendar months" in step["power_summary"].instructions
    assert "reference history" in step["power_summary"].instructions.lower()


def test_the_wizard_delegates_instead_of_reimplementing_the_conversion():
    import pathlib

    from chisurf.plugins.core.acq.live import calibration

    for path in pathlib.Path(calibration.__path__[0]).glob("*.py"):
        src = path.read_text()
        assert "class PowerCalibration" not in src, path.name
        assert "LIFETIME_MONTHS" not in src or "power_calibration" in src, path.name
        assert "def convert(" not in src, path.name


# -- persistence ----------------------------------------------------------------------------------

def test_save_and_load_round_trips_state_limits_and_results(wf, hist, tmp_path):
    _confirm_fret(wf, hist, upto="dna_pie_gamma")
    wf.configure_limits("buffer_background", "background_rate_khz", maximum=5.0)
    path = tmp_path / "fret_calibration.json"
    wf.save(path)
    loaded = workflow.CalibrationWorkflow.load(path)
    assert [s.id for s in loaded.steps] == [s.id for s in wf.steps]
    assert loaded.state["donor_only_crosstalk"].confirmed
    assert loaded.state["dna_pie_gamma"].values["i_dd"] == pytest.approx(6250.0)
    assert loaded.summary()["alpha"]["value"] == pytest.approx(0.03)
    step = {s.id: s for s in loaded.steps}
    assert step["water_irf"].metrics[0].compute is not None  # callables rebound from the library
    # and the loaded workflow continues
    _set(loaded, "fret_summary", note="accepted")
    loaded.confirm("fret_summary")
    assert loaded.summary()["gamma_pie"]["value"] == pytest.approx(0.8)


def test_loading_a_workflow_with_an_unknown_step_spec_names_it(tmp_path):
    doc = {"format": workflow.FORMAT, "version": 1, "kind": "fret", "name": "x",
           "steps": [{"id": "ghost_step", "spec_id": "ghost_step"}],
           "state": {}, "limits": {}, "results": []}
    path = tmp_path / "broken.json"
    path.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="ghost_step"):
        workflow.CalibrationWorkflow.load(path)


def test_the_owner_given_constants_are_what_the_owner_said():
    assert AVAILABLE_LASERS_NM == (488, 530, 640, 730)
    assert power_calibration.LIFETIME_MONTHS == 3  # stale after 3 calendar months
    assert tuple(int(w) for w in power_calibration.LASER_WAVELENGTHS_NM) == AVAILABLE_LASERS_NM
