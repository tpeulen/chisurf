"""Session-shared calibration pseudo-fit: cross-fit linking for global analysis."""

from __future__ import annotations

import chisurf as cs
from chisurf.core.fitting.parameter import FittingParameter
from chisurf.core.fluorescence.fret.calibration import (
    CalibrationFit,
    CalibrationParameters,
    link_to_calibration,
    register_calibration,
    unregister_calibration,
)


def test_register_exposes_calibration_as_a_fit():
    """A registered calibration appears in cs.fits with the expected factors."""
    calib = CalibrationParameters()
    calib.gamma = 1.7
    fit = register_calibration(calib, name="MyCalib")
    try:
        assert isinstance(fit, CalibrationFit)
        assert fit in cs.fits
        # enumeration mirrors what the parameter-link UI does
        found = next(f for f in cs.fits if getattr(f, "name", "") == "MyCalib")
        assert "gamma" in found.model.parameters_all_dict
        assert found.model.parameters_all_dict["gamma"].value == 1.7
        assert str(found.unique_identifier)
    finally:
        unregister_calibration(fit)
    assert fit not in cs.fits


def test_linked_parameter_follows_shared_calibration():
    """A fit parameter linked to the shared gamma tracks it (global analysis)."""
    calib = CalibrationParameters()
    calib.gamma = 1.4
    fit = register_calibration(calib)
    try:
        # two independent "fit" parameters both linked to the one calibration
        p1 = FittingParameter(value=1.0, name="gamma")
        p2 = FittingParameter(value=1.0, name="gamma")
        link_to_calibration(p1, calib, "gamma")
        link_to_calibration(p2, fit, "gamma")  # linking via the pseudo-fit works too
        assert p1.value == 1.4 and p2.value == 1.4
        assert p1.is_linked and p2.is_linked
        # refining the calibration once updates every linked fit
        calib.gamma = 1.9
        assert p1.value == 1.9 and p2.value == 1.9
    finally:
        unregister_calibration(fit)


def test_unregister_is_idempotent():
    """Unregistering a calibration twice does not raise."""
    calib = CalibrationParameters()
    fit = register_calibration(calib)
    unregister_calibration(fit)
    unregister_calibration(fit)  # no-op, no error
    assert fit not in cs.fits
