"""Behavioral tests for the detached project session codec."""

import numpy as np
import pytest

from chisurf.core.data import DataCurve, DataCurveGroup
from chisurf.core.fitting.fit import Fit, FitGroup
from chisurf.core.fitting.parameter import FittingParameter
from chisurf.core.models.model import ModelCurve
from chisurf.core.project import Project, SessionCodecError, capture_session, restore_session


class _TwoParameterModel(ModelCurve):
    """Small real ModelCurve used to exercise the complete codec contract."""

    def __init__(self, fit, **kwargs):
        super().__init__(fit, **kwargs)
        self.amplitude = FittingParameter(name="value", value=1.0)
        self.offset = FittingParameter(name="value", value=0.0)
        self.find_parameters()

    def _update_model(self, **kwargs):
        self.x = self.fit.data.x
        self.y = self.amplitude.value * self.x + self.offset.value


def test_curve_roundtrip_preserves_uid_arrays_metadata_and_is_detached():
    curve = DataCurve(
        x=np.array([0.0, 1.0, 2.0]),
        y=np.array([4.0, 5.0, 6.0]),
        ex=np.array([0.1, 0.1, 0.1]),
        ey=np.array([1.0, 2.0, 3.0]),
        name="measured",
        unique_identifier="dataset-stable",
    )
    curve.meta_data["sample"] = "A"

    project = capture_session([curve], [], name="experiment")
    restored = restore_session(project)

    assert restored.datasets[0] is not curve
    assert restored.datasets[0].unique_identifier == "dataset-stable"
    np.testing.assert_array_equal(restored.datasets[0].y, curve.y)
    assert restored.datasets[0].meta_data["sample"] == "A"


def test_future_and_legacy_formats_fail_closed():
    with pytest.raises(ValueError, match="requires v5"):
        Project.from_dict({"project_format_version": 6})
    with pytest.raises(SessionCodecError, match="format v5"):
        restore_session(Project(project_format_version=4))


def _curve(uid, offset=0.0):
    x = np.arange(8.0)
    return DataCurve(
        x=x,
        y=x + offset,
        ex=np.full_like(x, 0.1),
        ey=np.ones_like(x),
        name=f"curve-{uid}",
        unique_identifier=uid,
    )


def test_fit_group_links_ranges_errors_and_two_save_reload_roundtrip():
    first, second = _curve("data-a"), _curve("data-b", 2.0)
    group = FitGroup(
        DataCurveGroup([first, second], name="measurements"), model_class=_TwoParameterModel
    )
    group.unique_identifier = "fit-group"
    group.selected_fit = 1
    group.grouped_fits[0].fit_range = (1, 7)
    group.grouped_fits[1].fit_range = (2, 6)
    source, target = group.grouped_fits
    source.model.amplitude.value = 4.25
    source.model.amplitude.error_estimate = float("nan")
    source.model.amplitude.fixed = True
    source.model.offset.bounds = (-3.0, 9.0)
    source.model.offset.bounds_on = True
    target.model.amplitude.link = source.model.amplitude

    data_group = DataCurveGroup([first, second], name="measurements")
    data_group.current_dataset = 1
    project = capture_session([data_group], [group], name="roundtrip")
    restored = restore_session(project)
    restored_group = restored.fits[0]
    assert isinstance(restored_group, FitGroup)
    assert restored_group.selected_fit_index == 1
    assert restored_group.grouped_fits[0].data is restored.datasets[0][0]
    assert restored_group.grouped_fits[1].fit_range == (2, 6)
    assert restored_group.grouped_fits[0].model.amplitude.fixed is True
    assert np.isnan(restored_group.grouped_fits[0].model.amplitude.error_estimate)
    assert (
        restored_group.grouped_fits[1].model.amplitude.link
        is restored_group.grouped_fits[0].model.amplitude
    )

    second_project = capture_session(restored.datasets, restored.fits, name="roundtrip")
    second_restored = restore_session(second_project)
    np.testing.assert_array_equal(
        second_restored.fits[0].grouped_fits[0].model.y, restored_group.grouped_fits[0].model.y
    )


def test_restore_rejects_malformed_array_without_touching_any_live_objects():
    curve = _curve("safe")
    project = capture_session([curve], [])
    project.datasets["safe"]["arrays"]["y"]["values"] = [1.0, 2.0]
    with pytest.raises(SessionCodecError, match="different lengths"):
        restore_session(project)
    assert curve.unique_identifier == "safe"
    np.testing.assert_array_equal(curve.y, np.arange(8.0))


def test_restore_rejects_non_model_import_and_dangling_link():
    curve = _curve("bad")
    fit = Fit(model_class=_TwoParameterModel, data=curve)
    project = capture_session([curve], [fit])
    state = project.fits[0]["members"][0]["model"]
    state["model_module"] = "json"
    state["model_class"] = "loads"
    with pytest.raises(SessionCodecError, match="not registered or trusted"):
        restore_session(project)


def test_real_tcspc_lifetime_group_roundtrip_keeps_dynamic_state_and_curves():
    from chisurf.core.models.description import tcspc_lifetime as LifetimeModel

    first, second = _curve("tcspc-a"), _curve("tcspc-b", 3.0)
    irf, background = _curve("irf"), _curve("background", 0.25)
    data_group = DataCurveGroup([first, second], name="decays")
    fit_group = FitGroup(data_group, model_class=LifetimeModel)
    fit_group.unique_identifier = "tcspc-group"
    fit_group.selected_fit = 1
    model = fit_group.grouped_fits[0].model
    model.generic.background_curve = background
    model.convolve._irf = irf
    model.change_components("lifetime", 2)
    model.parameters_all[0].value = 0.42
    model.parameters_all[0].fixed = True
    model.update()
    expected = np.array(model.y, copy=True)

    project = capture_session([data_group, irf, background], [fit_group], name="tcspc")
    restored = restore_session(project)
    restored_model = restored.fits[0].grouped_fits[0].model
    assert len(restored_model.parameters_all) == len(model.parameters_all)
    assert restored_model.generic.background_curve.unique_identifier == "background"
    assert restored_model.convolve._irf.unique_identifier == "irf"
    assert restored_model.parameters_all[0].fixed is True
    np.testing.assert_allclose(restored_model.y, expected)

    restored_twice = restore_session(
        capture_session(restored.datasets, restored.fits, name="tcspc")
    )
    np.testing.assert_allclose(restored_twice.fits[0].grouped_fits[0].model.y, expected)


def test_real_fcs_model_roundtrip_keeps_prediction_and_objective():
    from chisurf.core.models.fcs.mdf import MdfFCSModel

    x = np.logspace(-3, 2, 48)
    curve = DataCurve(
        x=x,
        y=np.ones_like(x),
        ex=np.zeros_like(x),
        ey=np.full_like(x, 0.05),
        unique_identifier="fcs-data",
    )
    fit = Fit(model_class=MdfFCSModel, data=curve, noise_model="poisson")
    fit.model.parameters_all[0].value = 2.5
    fit.model.update()
    expected = np.array(fit.model.y, copy=True)

    restored = restore_session(capture_session([curve], [fit])).fits[0]

    assert restored.noise_model == "poisson"
    np.testing.assert_allclose(restored.model.y, expected, rtol=1e-12, atol=1e-12)
