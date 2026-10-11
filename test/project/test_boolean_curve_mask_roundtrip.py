"""Boolean inclusion masks survive the owning session codec without numeric casts."""

from __future__ import annotations

import json

import numpy as np
import pytest

from chisurf.core.data import DataCurve
from chisurf.core.experiments.tcspc.simulator import TCSPCSimulatorSetup
from chisurf.core.fitting.fit import Fit
from chisurf.core.models.description import tcspc_lifetime
from chisurf.core.project import Project, SessionCodecError, capture_session, restore_session


@pytest.mark.parametrize("polarization", ["vm", "vv/vh"])
def test_actual_simulator_curve_and_fit_boolean_masks_roundtrip(polarization):
    """JSON snapshots restore real count arrays, boolean selections and model predictions."""
    reader = TCSPCSimulatorSetup(
        n_tac=64, dt=0.1, add_noise=False, lifetime_spectrum=[1.0, 3.0], polarization=polarization
    )
    group = reader.read(name="masked simulation")
    for index, curve in enumerate(group):
        curve.mask = (np.arange(len(curve.y)) % (index + 2)) != 0
    fit = Fit(data=group[0], model_class=tcspc_lifetime)
    fit.fit_range = (0, 64)
    fit.mask = np.arange(64) % 3 != 0
    fit.model.update()
    expected_prediction = fit.model.y.copy()
    project = capture_session([group], [fit])
    restored = restore_session(Project.from_dict(json.loads(json.dumps(project.to_dict()))))
    assert len(restored.datasets[0]) == len(group)
    for actual, original in zip(restored.datasets[0], group):
        assert actual.mask.dtype == original.mask.dtype == np.dtype(bool)
        np.testing.assert_array_equal(actual.mask, original.mask)
        for field in ("x", "y", "ex", "ey"):
            np.testing.assert_array_equal(getattr(actual, field), getattr(original, field))
    assert restored.fits[0].mask.dtype == fit.mask.dtype == np.dtype(bool)
    np.testing.assert_array_equal(restored.fits[0].mask, fit.mask)
    np.testing.assert_allclose(
        restored.fits[0].model.y, expected_prediction, rtol=1e-12, atol=1e-12
    )


@pytest.mark.parametrize("field", ["x", "y", "ex", "ey"])
def test_boolean_measurement_arrays_are_rejected_by_capture_and_restore(field):
    """A boolean mask exception cannot admit boolean coordinates, counts or uncertainties."""
    curve = DataCurve(x=np.arange(4.0), y=np.arange(4.0) + 2.0)
    project = capture_session([curve], [])
    record = project.datasets[curve.unique_identifier]["arrays"][field]
    record.update(dtype="bool", values=[True, False, True, False])
    with pytest.raises(SessionCodecError):
        restore_session(project)
    # Curve coerces x/y to float at its public setter; uncertainties retain
    # ndarray dtype and exercise capture rejection without bypassing that API.
    if field in {"ex", "ey"}:
        setattr(curve, field, np.array([True, False, True, False]))
        with pytest.raises(SessionCodecError):
            capture_session([curve], [])
