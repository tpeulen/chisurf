"""A FRET calibration belongs to the instrument, so it lives on the setup.

γ is fixed by the detection efficiencies and quantum yields, α by the filters,
δ by the excitation — properties of the microscope, not of one burst file.
Storing the measured factors on the detector setup is what lets every other tool
that already asks the user to pick a setup start from a real calibration instead
of typed-in defaults.
"""

from __future__ import annotations

import pathlib
import tempfile

import pytest

from chisurf.core.data_io.detector_setups import (
    get_setup_calibration,
    load_detector_setups,
    save_detector_setups,
    set_setup_calibration,
)
from chisurf.core.fluorescence.fret.calibration import (
    CalibrationParameters,
    calibration_from_setup,
    calibration_to_setup,
    setup_calibration_uncertainties,
    setup_calibration_values,
)

TRUTH = {"gamma": 0.65, "alpha": 0.08, "beta": 1.4, "delta": 0.06}


@pytest.fixture()
def setups_file():
    """A setups file holding one setup with real channel definitions."""
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "detector_setups.json"
        save_detector_setups(
            {
                "setups": {
                    "BS": {
                        "detectors": {"green": [0, 2], "red": [1, 3], "yellow": [4]},
                        "windows": {"prompt": [0, 4096]},
                    }
                },
                "last_used": "BS",
            },
            path,
        )
        yield path


def _calibrated():
    """A calibration group carrying the known factors."""
    calib = CalibrationParameters()
    for name, value in TRUTH.items():
        setattr(calib, name, value)
    calib.r0, calib.phi_a, calib.phi_d = 52.0, 0.32, 0.8
    return calib


def test_a_calibration_survives_the_round_trip_through_a_setup(setups_file):
    """What was measured is what comes back out."""
    assert set_setup_calibration("BS", calibration_to_setup(_calibrated()), setups_file)

    setup = load_detector_setups(setups_file)["setups"]["BS"]
    restored = calibration_from_setup(setup)
    for name, value in TRUTH.items():
        assert getattr(restored, name) == pytest.approx(value)
    assert restored.r0 == pytest.approx(52.0)
    assert restored.phi_a == pytest.approx(0.32)


def test_storing_a_calibration_does_not_disturb_the_channel_definitions(setups_file):
    """The setup's detectors and windows are what make it a setup.

    They are read back and rewritten wholesale on every store, so this asserts
    the one thing that must never be the casualty of annotating a setup.
    """
    before = load_detector_setups(setups_file)["setups"]["BS"]
    detectors, windows = dict(before["detectors"]), dict(before["windows"])

    set_setup_calibration("BS", calibration_to_setup(_calibrated()), setups_file)

    after = load_detector_setups(setups_file)
    assert after["setups"]["BS"]["detectors"] == detectors
    assert after["setups"]["BS"]["windows"] == windows
    assert after["last_used"] == "BS"


def test_uncertainties_ride_along_with_the_values(setups_file):
    """A factor without its error bar cannot be weighted by whoever reads it."""
    payload = calibration_to_setup(
        _calibrated(), uncertainties={"gamma": 0.006, "alpha": 0.0007, "beta": None}
    )
    set_setup_calibration("BS", payload, setups_file)

    setup = load_detector_setups(setups_file)["setups"]["BS"]
    sigmas = setup_calibration_uncertainties(setup)
    assert sigmas["gamma"] == pytest.approx(0.006)
    assert sigmas["alpha"] == pytest.approx(0.0007)
    assert "beta" not in sigmas  # a missing sigma is dropped, not stored as None


def test_an_uncalibrated_setup_yields_the_defaults(setups_file):
    """The normal case — a fresh setup — must not blow up or invent numbers."""
    setup = load_detector_setups(setups_file)["setups"]["BS"]
    fresh = CalibrationParameters()
    restored = calibration_from_setup(setup)
    assert restored.gamma == pytest.approx(fresh.gamma)
    assert setup_calibration_uncertainties(setup) == {}
    assert get_setup_calibration("BS", setups_file) == {}
    assert calibration_from_setup(None).gamma == pytest.approx(fresh.gamma)


def test_storing_on_an_unknown_setup_is_refused(setups_file):
    """This attaches a calibration to a setup; it must not invent one.

    Silently creating a setup named by a typo would produce a calibration that
    no tool ever finds.
    """
    assert not set_setup_calibration("typo", calibration_to_setup(_calibrated()), setups_file)
    assert set(load_detector_setups(setups_file)["setups"]) == {"BS"}


def test_non_finite_and_junk_values_are_ignored(setups_file):
    """A corrupt file must not push NaN into a factor every later fit uses."""
    setups = load_detector_setups(setups_file)["setups"]
    setups["BS"]["fret_calibration"] = {
        "values": {"gamma": float("nan"), "alpha": "not a number", "beta": None, "delta": 0.06}
    }
    restored = calibration_from_setup(setups["BS"])
    fresh = CalibrationParameters()
    assert restored.gamma == pytest.approx(fresh.gamma)
    assert restored.alpha == pytest.approx(fresh.alpha)
    assert restored.delta == pytest.approx(0.06)  # the one good value still lands


def test_a_tool_with_plain_scalar_fields_can_seed_itself(setups_file):
    """Most consumers keep plain floats, not a calibration group.

    They seed by attribute name, so the Förster radius has to answer to the
    spelling their field actually uses — otherwise every such tool needs its own
    ``r0`` → ``forster_radius`` lookup table and one of them will get it wrong.
    """
    calib = _calibrated()
    calib.r0 = 54.0
    set_setup_calibration("BS", calibration_to_setup(calib), setups_file)
    setup = load_detector_setups(setups_file)["setups"]["BS"]

    seed = setup_calibration_values(setup)
    assert seed["gamma"] == pytest.approx(TRUTH["gamma"])
    assert seed["beta"] == pytest.approx(TRUTH["beta"])
    assert seed["r0"] == pytest.approx(54.0)
    assert seed["forster_radius"] == pytest.approx(54.0)


def test_the_flat_seed_drops_what_it_cannot_use(setups_file):
    """A junk entry must stay out of a GUI field rather than become NaN in it."""
    setups = load_detector_setups(setups_file)["setups"]
    setups["BS"]["fret_calibration"] = {
        "values": {"gamma": float("inf"), "alpha": "junk", "delta": 0.06}
    }
    seed = setup_calibration_values(setups["BS"])
    assert seed == {"delta": pytest.approx(0.06)}
    assert setup_calibration_values(None) == {}


def test_a_legacy_field_still_seeds_but_the_calibration_wins(setups_file):
    """Setups predating the calibration field carry loose ``calibration`` dicts.

    They may hold values the calibration proper has no notion of (the G-factor,
    the laser period), so they are still read — but where both speak, the
    measured calibration is the answer.
    """
    setups = load_detector_setups(setups_file)["setups"]
    setups["BS"]["calibration"] = {"gamma": 0.5, "g_factor": 1.15}
    setups["BS"]["fret_calibration"] = {"values": {"gamma": 0.65}}
    seed = setup_calibration_values(setups["BS"])
    assert seed["gamma"] == pytest.approx(0.65)
    assert seed["g_factor"] == pytest.approx(1.15)


def test_the_factors_carry_a_typeset_label_and_keep_their_plain_name():
    """Crosslinking keys on the name; the reader sees the symbol.

    Both matter: a link stored against ``PhiA`` must not break because the label
    changed, and a parameter table reading ``PhiA`` helps nobody.
    """
    calib = CalibrationParameters()
    labels = {p.name: p.__dict__.get("label_text") for p in calib.parameters_all}
    assert labels["gamma"] == "&gamma;"
    assert labels["PhiA"] == "&Phi;<sub>A</sub>"
    assert labels["Bg_DD"] == "Bg<sub>DD</sub>"
    assert labels["R0"] == "R<sub>0</sub>"
    # the programmatic names are untouched — ndxplorer's mapping keys on them
    assert {"gamma", "alpha", "beta", "delta", "R0", "PhiA", "PhiD"} <= set(labels)
