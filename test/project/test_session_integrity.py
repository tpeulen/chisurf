"""Fail-closed integrity contracts for the detached session codec."""

from __future__ import annotations

import copy
import sys

import numpy as np
import pytest

from chisurf.core.data import DataCurve, DataCurveGroup
from chisurf.core.experiments.core.experiment import Experiment
from chisurf.core.fitting.fit import Fit
from chisurf.core.fitting.parameter import FittingParameter
from chisurf.core.models.model import ModelCurve
from chisurf.core.project import SessionCodecError, capture_session, restore_session


class _StatefulModel(ModelCurve):
    """Small model with an explicit structural adapter."""

    def __init__(self, fit, **kwargs):
        super().__init__(fit, **kwargs)
        self.amplitude = FittingParameter(name="amplitude", value=1.0)
        self.scale = 1.0
        self.find_parameters()

    def get_state(self):
        return {"scale": self.scale}

    def set_state(self, state):
        self.scale = float(state["scale"])

    def _update_model(self, **kwargs):
        self.x = self.fit.data.x
        self.y = self.scale * self.amplitude.value * self.x


class _BrokenAdapterModel(_StatefulModel):
    """Prediction state deliberately omitted by a broken adapter."""

    def get_state(self):
        return {}

    def set_state(self, state):
        return None


def _curve(uid="curve"):
    x = np.arange(5.0)
    return DataCurve(
        x=x,
        y=x + 1.0,
        ex=np.zeros(5, dtype=np.float32),
        ey=np.ones(5, dtype=np.float32),
        mask=np.array([1, 0, 1, 1, 0], dtype=np.uint8),
        unique_identifier=uid,
    )


def test_curve_mask_dtype_experiment_and_nested_values_are_detached():
    experiment = Experiment(name="FCS", hidden=True)
    curve = _curve()
    curve.experiment = experiment
    curve.meta_data["nested"] = {"values": [1, 2]}
    ui = {"nested": {"selection": [1]}}
    experiments = {"active": {"settings": ["a"]}}

    project = capture_session(
        [DataCurveGroup([curve], name="curves")], [], ui_state=ui, experiments=experiments
    )
    restored = restore_session(project)
    restored_curve = restored.datasets[0][0]

    assert isinstance(restored.datasets[0], DataCurveGroup)
    np.testing.assert_array_equal(restored_curve.mask, curve.mask)
    assert restored_curve.mask.dtype == curve.mask.dtype
    assert restored_curve.experiment.name == "FCS"
    assert restored_curve.experiment.hidden is True
    restored_curve.meta_data["nested"]["values"].append(3)
    restored.ui_state["nested"]["selection"].append(2)
    restored.experiments["active"]["settings"].append("b")
    assert curve.meta_data["nested"]["values"] == [1, 2]
    assert ui["nested"]["selection"] == [1]
    assert experiments["active"]["settings"] == ["a"]


def test_noise_model_and_adapter_state_roundtrip_independently_of_defaults(monkeypatch):
    curve = _curve()
    fit = Fit(model_class=_StatefulModel, data=curve, noise_model="poisson")
    fit.model.scale = 3.5
    fit.model.amplitude.value = 2.0
    fit.model.update()
    expected = np.array(fit.model.y, copy=True)
    project = capture_session([curve], [fit])
    monkeypatch.setattr("chisurf.core.fitting.default_noise_model", lambda *_: "default")

    restored = restore_session(project).fits[0]

    assert restored.noise_model == "poisson"
    assert restored.model.scale == 3.5
    np.testing.assert_allclose(restored.model.y, expected, rtol=1e-12, atol=1e-12)


def test_builtin_tcspc_reader_roundtrips_configuration_without_reading_files(monkeypatch):
    from chisurf.core.experiments.tcspc.reader import TCSPCReader

    experiment = Experiment(name="TCSPC")
    experiment.add_model_class(_StatefulModel)
    reader = TCSPCReader(
        experiment=experiment,
        dt=0.123,
        rep_rate=42.0,
        g_factor=1.4,
        l1=0.07,
        l2=0.09,
        rebin=(2, 4),
        matrix_columns=(1, 3),
        skiprows=7,
        use_header=False,
        reading_routine="csv",
        name="my-reader",
        record_provenance=False,
    )
    reader.col_x, reader.col_y, reader.dt_scaled = 1, 3, True
    first, second = _curve("first"), _curve("second")
    for curve in (first, second):
        curve.data_reader = reader
        curve.experiment = experiment

    def forbidden_read(*args, **kwargs):
        raise AssertionError("restoration reread the original measurement")

    monkeypatch.setattr(TCSPCReader, "read", forbidden_read)
    restored = restore_session(capture_session([first, second], []))
    restored_reader = restored.datasets[0].data_reader
    assert restored_reader is restored.datasets[1].data_reader
    assert restored.datasets[0].experiment is restored.datasets[1].experiment
    assert restored_reader.experiment is restored.datasets[0].experiment
    assert restored_reader.experiment.model_classes == [_StatefulModel]
    assert isinstance(restored_reader, TCSPCReader)
    for attr in (
        "dt",
        "rep_rate",
        "g_factor",
        "l1",
        "l2",
        "rebin",
        "matrix_columns",
        "skiprows",
        "use_header",
        "reading_routine",
        "col_x",
        "col_y",
        "dt_scaled",
        "record_provenance",
        "name",
    ):
        assert getattr(restored_reader, attr) == getattr(reader, attr), attr
    assert restored_reader.unique_identifier == reader.unique_identifier
    assert restored_reader.db is None


def test_builtin_global_fit_placeholder_is_restored_with_its_reader():
    from chisurf.core.experiments.globalfit.reader import GlobalFitSetup

    experiment = Experiment(name="Global fit", hidden=True)
    reader = GlobalFitSetup(experiment=experiment, name="Global-fit")
    curve = reader.read()
    curve.data_reader = reader
    curve.experiment = experiment
    restored = restore_session(capture_session([curve], [])).datasets[0]
    assert isinstance(restored.data_reader, GlobalFitSetup)
    assert restored.data_reader.record_provenance is False
    assert restored.experiment.name == "Global fit"
    np.testing.assert_array_equal(restored.x, curve.x)
    np.testing.assert_array_equal(restored.y, curve.y)


@pytest.mark.parametrize(
    "group_name", ["DataGroup", "DataCurveGroup", "ExperimentDataGroup", "ExperimentDataCurveGroup"]
)
def test_builtin_dataset_group_types_preserve_members_and_selection(group_name):
    import chisurf.core.data as data

    cls = getattr(data, group_name)
    group = cls([_curve("a"), _curve("b")], name="measurements", unique_identifier="group")
    group.current_dataset = 1
    restored = restore_session(capture_session([group], [])).datasets[0]
    assert type(restored) is cls
    assert restored.current_dataset is restored[1]
    assert restored.name == group.name
    assert restored.unique_identifier == group.unique_identifier


def test_archive_reader_module_is_rejected_before_import(monkeypatch):
    curve = _curve()
    project = capture_session([curve], [])
    project.datasets["curve"]["reader"] = {
        "module": "archive_controlled_reader",
        "class": "BadReader",
        "state": {},
    }
    calls = []

    def forbidden_import(name, *args, **kwargs):
        calls.append(name)
        raise AssertionError("archive-controlled reader import attempted")

    monkeypatch.setattr("importlib.import_module", forbidden_import)
    with pytest.raises(SessionCodecError, match="reader.*not trusted"):
        restore_session(project)
    assert calls == []


def test_broken_adapter_is_rejected_during_capture():
    curve = _curve()
    fit = Fit(model_class=_BrokenAdapterModel, data=curve)
    fit.model.scale = 7.0
    fit.model.update()

    with pytest.raises(SessionCodecError, match="prediction|reconstruct"):
        capture_session([curve], [fit])


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda p: p.fits.append(copy.deepcopy(p.fits[0])), "duplicate fit UID"),
        (
            lambda p: p.fits[0]["members"].append(copy.deepcopy(p.fits[0]["members"][0])),
            "duplicate fit-member UID",
        ),
        (
            lambda p: p.fits[0]["members"][0]["model"]["parameters"].append(
                copy.deepcopy(p.fits[0]["members"][0]["model"]["parameters"][0])
            ),
            "duplicate parameter UID",
        ),
        (lambda p: p.fits[0].__setitem__("kind", "mystery"), "invalid fit kind"),
        (
            lambda p: p.fits[0]["members"][0].__setitem__("fit_range", [-1, 99]),
            "fit range",
        ),
        (
            lambda p: p.ui_state.__setitem__("dataset_layout", [{"kind": "mystery"}]),
            "dataset layout",
        ),
        (
            lambda p: p.datasets["curve"].__setitem__("kind", "mystery"),
            "invalid dataset UID/record",
        ),
        (
            lambda p: p.fits[0]["members"][0].__setitem__("dataset_uid", "missing"),
            "missing dataset",
        ),
        (
            lambda p: p.fits[0]["members"][0]["model"]["parameters"][0].__setitem__(
                "bounds", [2.0, 1.0]
            ),
            "parameter bounds",
        ),
        (
            lambda p: p.fits[0]["members"][0].__setitem__("noise_model", "archive-choice"),
            "noise model",
        ),
    ],
)
def test_malformed_identity_ranges_and_layouts_fail_closed(mutate, message):
    curve = _curve()
    fit = Fit(model_class=_StatefulModel, data=curve)
    project = capture_session([curve], [fit])
    mutate(project)

    with pytest.raises(SessionCodecError, match=message):
        restore_session(project)


def test_explicit_empty_layout_does_not_fallback_flat():
    project = capture_session([_curve()], [])
    project.ui_state["dataset_layout"] = []
    with pytest.raises(SessionCodecError, match="dataset layout"):
        restore_session(project)


def test_archive_module_is_rejected_before_import(monkeypatch):
    curve = _curve()
    fit = Fit(model_class=_StatefulModel, data=curve)
    project = capture_session([curve], [fit])
    state = project.fits[0]["members"][0]["model"]
    state["model_module"] = "archive_controlled_payload"
    state["model_class"] = "Payload"
    calls = []

    def forbidden_import(name, *args, **kwargs):
        calls.append(name)
        raise AssertionError("archive-controlled import attempted")

    monkeypatch.setattr("importlib.import_module", forbidden_import)
    sys.modules.pop("archive_controlled_payload", None)
    with pytest.raises(SessionCodecError, match="not registered|not trusted"):
        restore_session(project)
    assert calls == []


def test_parameter_link_cycle_is_rejected():
    curve = _curve()
    fit = Fit(model_class=_StatefulModel, data=curve)
    project = capture_session([curve], [fit])
    parameter = project.fits[0]["members"][0]["model"]["parameters"][0]
    parameter["link_target"] = {
        "fit_uid": project.fits[0]["uid"],
        "member_uid": project.fits[0]["members"][0]["uid"],
        "parameter_uid": parameter["uid"],
    }
    with pytest.raises(SessionCodecError, match="cycle"):
        restore_session(project)
