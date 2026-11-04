"""The wizard's laser inventory, and the delegation to the power-calibration backend.

The inventory answers only "which lasers are verified installed". Everything
else about a power calibration -- keying, the verified single-laser state, the
3-calendar-month expiry, the bounded conversion -- lives in
chisurf.plugins.core.acq.live.power_calibration, and the workflow records that
module's own document as its result. One owner of the conversion maths.
"""

import json

import pytest

from chisurf.plugins.core.acq.live import power_calibration
from chisurf.plugins.core.acq.live.calibration.lasers import (
    AVAILABLE_LASERS_NM,
    InstallationRecord,
    LaserInventory,
    NotInstalled,
)


# -- the inventory: available is NOT installed ----------------------------------------------------

def test_available_models_are_the_owner_s_four_lines():
    assert AVAILABLE_LASERS_NM == (488, 530, 640, 730)
    assert AVAILABLE_LASERS_NM == tuple(
        int(w) for w in power_calibration.LASER_WAVELENGTHS_NM
    )


def test_a_fresh_inventory_verifies_nothing():
    inv = LaserInventory()
    assert inv.installed() == ()
    assert not inv.is_verified(488)
    with pytest.raises(NotInstalled, match="verified"):
        inv.select(488)
    with pytest.raises(NotInstalled, match="verified installed"):
        inv.record(488)


def test_verification_needs_the_hardware_readback_as_evidence():
    inv = LaserInventory()
    with pytest.raises(ValueError, match="evidence"):
        inv.verify_installed(488, evidence="   ")
    with pytest.raises(ValueError, match="available"):
        inv.verify_installed(520, evidence="HW config shows a 520 head")
    rec = inv.verify_installed(488, evidence="HW config: 488 head present, interlock OK")
    assert isinstance(rec, InstallationRecord)
    assert rec.evidence.startswith("HW config")
    assert inv.installed() == (488,)
    assert inv.select(488) == 488  # now the wizard may offer and select it


def test_availability_does_not_imply_installation():
    inv = LaserInventory()
    inv.verify_installed(640, evidence="HW config: only the 640 head connected")
    for nm in (488, 530, 730):  # available, but nobody verified them installed
        assert nm in AVAILABLE_LASERS_NM
        with pytest.raises(NotInstalled):
            inv.select(nm)


def test_an_exchange_is_manual_and_logged():
    inv = LaserInventory()
    inv.verify_installed(488, evidence="HW config: 488 head present")
    inv.unverify_installed(488, note="user disconnected the 488 head by hand")
    assert inv.installed() == ()
    assert inv.exchange_log and inv.exchange_log[0]["wavelength_nm"] == 488
    with pytest.raises(NotInstalled):
        inv.select(488)
    with pytest.raises(NotInstalled):
        inv.unverify_installed(488, note="again")


def test_the_inventory_survives_a_round_trip(tmp_path):
    inv = LaserInventory()
    inv.verify_installed(488, evidence="HW config: 488 head present", note="main head")
    inv.verify_installed(640, evidence="HW config: 640 head present")
    inv.unverify_installed(640, note="swapped for the 730")
    path = tmp_path / "inventory.json"
    inv.save(path)
    loaded = LaserInventory.load(path)
    assert loaded.installed() == (488,)
    assert loaded.record(488).note == "main head"
    assert loaded.exchange_log == inv.exchange_log


# -- the delegation: one owner of the conversion maths --------------------------------------------

def test_the_companion_module_owns_the_calibration_lifecycle():
    # the names the workflow delegates to exist there, with the owner's policy
    for name in ("PowerCalibration", "CalibrationSet", "EmissionState", "ConfigIdentity",
                 "ReferencePoint", "DarkOffset", "LIFETIME_MONTHS"):
        assert hasattr(power_calibration, name), name
    assert power_calibration.LIFETIME_MONTHS == 3


def test_a_workflow_result_round_trips_through_the_companion_module(tmp_path):
    """End-to-end: the wizard's recorded result IS a PowerCalibration document."""
    from chisurf.plugins.core.acq.live.calibration import library

    inv = LaserInventory()
    inv.verify_installed(488, evidence="HW config: 488 head present, interlock OK")
    wf = library.build_workflow("power_diode", inventory=inv)
    wf.set_value("laser_selection", "laser_nm", 488)
    wf.set_value("laser_selection", "laser_name", "LDH-488")
    wf.confirm("laser_selection", note="verified installed")
    wf.set_value("verify_setup", "config_heads", json.dumps({"heads": [
        {"name": "LDH-488", "wavelength_nm": 488.0, "serial": "488-1234"}]}))
    wf.confirm("verify_setup")
    emission = json.dumps([{"laser": "LDH-488", "on": True, "verified": True}])
    all_off = json.dumps([{"laser": "LDH-488", "on": False, "verified": True}])
    wf.set_value("verify_single_laser", "all_other_lasers_off_confirmed", True)
    wf.set_value("verify_single_laser", "emission_states", emission)
    wf.set_value("verify_single_laser", "emission_state_readback", "readback: only 488 on")
    wf.confirm("verify_single_laser", note="isolation verified")
    wf.set_value("dark_offset", "dark_raw", 0.5)
    wf.set_value("dark_offset", "emission_states", all_off)
    wf.confirm("dark_offset", note="emission blocked")
    wf.set_value("objective_meter_setup", "meter_setup_confirmed", True)
    wf.set_value("objective_meter_setup", "meter", "N1913A at the objective")
    wf.confirm("objective_meter_setup")
    wf.set_value("power_points", "config_readback", "readback: only 488 on")
    wf.set_value("power_points", "measured_on", "2026-10-30")
    wf.set_value("power_points", "rep_rate_hz", 40e6)
    wf.set_value("power_points", "mode", "pulsed")
    wf.set_value("power_points", "pattern", "20 MHz PIE pattern")
    wf.set_value("power_points", "optical_path", "RDM455/532/640")
    wf.set_points("power_points", "points", [
        {"drive": 5.0, "meter_uw": 12.0, "diode_raw": 8.0},
        {"drive": 10.0, "meter_uw": 24.0, "diode_raw": 16.0},
        {"drive": 20.0, "meter_uw": 48.0, "diode_raw": 32.0},
    ])
    wf.confirm("power_points")
    wf.set_value("power_summary", "note", "adopted")
    wf.confirm("power_summary")

    doc = wf.summary()["power_calibration"]["extra"]["power_calibration"]
    cal = power_calibration.PowerCalibration.from_dict(doc)
    assert cal.validate() == []
    conv = cal.convert(
        16.0,
        conditions=power_calibration.LaserConditions(
            "LDH-488", 488.0, repetition_rate_hz=40e6, mode="pulsed",
            pattern="20 MHz PIE pattern", optical_path="RDM455/532/640"),
        emission=power_calibration.EmissionState.from_dict(json.loads(emission)),
        config=power_calibration.ConfigIdentity.from_dict(
            json.loads(json.dumps({"heads": [
                {"name": "LDH-488", "wavelength_nm": 488.0, "serial": "488-1234"}]}))),
    )
    assert conv.valid and conv.uw == pytest.approx(24.0)
    # and the companion store accepts the document unchanged
    store = power_calibration.CalibrationSet()
    store.add(cal)
    path = tmp_path / "calibrations.json"
    store.save(path)
    reloaded = power_calibration.CalibrationSet.load(path)
    assert reloaded.calibrations[0].key == cal.key
