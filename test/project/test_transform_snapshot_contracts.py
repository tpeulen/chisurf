"""Explicit shipped transforms and native output links survive scientific snapshots."""

import inspect
import json
import os
import subprocess
import sys

import numpy as np
import pytest

from chisurf.core.data import DataCurve
from chisurf.core.fitting.fit import Fit
from chisurf.core.models.parameter_transform.model import ParameterTransformModel
from chisurf.core.models.pda2c.simple import Pda2cSimpleModel
from chisurf.core.project.session import capture_session, restore_session
from chisurf.core.project.storage import load_file, save_file


def _transform():
    """Select the shipped FRET-to-PDA definition with nondefault optical controls."""
    data = DataCurve(x=np.arange(2.0), y=np.ones(2), load_filename_on_init=False)
    fit = Fit(data=data, model_class=ParameterTransformModel)
    fit.model.model_name = "FRET to PDA"
    for name, value in {"E": 0.37, "a": 0.045, "gp": 0.41, "phiA": 0.28, "phiD": 0.83}.items():
        fit.model.parameters_all_dict[name].value = value
    fit.model.update()
    return fit


def test_transform_snapshot_declares_selected_definition_and_native_node():
    """A transform snapshot contains a trusted definition identity and exact topology."""
    fit = _transform()
    state = fit.model.get_state()
    assert state["catalogue_name"] == "FRET to PDA"
    assert state["node_uid"] == fit.model._model._node.get_uid()
    assert state["input_names"] == ["E", "a", "gp", "phiA", "phiD"]
    assert state["input_port_uids"] == {
        name: port.get_uid() for name, port in fit.model._model._node.inputs.items()
    }
    assert state["output_names"] == ["p0"]
    assert "function" not in state and "code" not in state
    assert fit.model.parameters_all_dict["p0"].is_output
    assert fit.model.parameters_all_dict["p0"].fixed


def test_transform_rejects_archive_code_and_changed_shipped_definition():
    """Only a verified installed definition can create a restored callback."""
    fit = _transform()
    state = fit.model.get_state()
    with pytest.raises(ValueError, match="Invalid"):
        fit.model.set_state({**state, "code": "raise RuntimeError('archive code')"})
    with pytest.raises(ValueError, match="definition changed"):
        fit.model.set_state({**state, "definition_sha256": "0" * 64})


def test_transform_catalogue_initial_bounds_are_applied_to_native_inputs():
    """Structured catalogue initial declarations create the stated bounded inputs."""
    fit = _transform()
    parameter = fit.model.parameters_all_dict["E"]
    assert parameter.bounds_on and parameter.bounds == (0.0, 1.0)


def test_transform_restoration_constructs_only_saved_definition(monkeypatch):
    """Staged restoration never creates the identity or unrelated catalogue graph."""
    state = _transform().model.get_state()
    import chisurf.core.models

    decorator = chisurf.core.models.function_to_model_decorator
    constructed = []

    def selected_only(**kwargs):
        """Intercept graph creation, independently of cached Base property setters."""
        wrap_model = decorator(**kwargs)

        def construct(function):
            """Reject construction of any equation except the saved installed definition."""
            names = list(inspect.signature(function).parameters)
            assert names == ["E", "a", "gp", "phiA", "phiD"], "unrelated definition constructed"
            constructed.append(names)
            return wrap_model(function)

        return construct

    monkeypatch.setattr(chisurf.core.models, "function_to_model_decorator", selected_only)
    data = DataCurve(x=np.arange(2.0), y=np.ones(2), load_filename_on_init=False)
    restored = Fit(
        data=data, model_class=ParameterTransformModel, model_kw={"session_state": state}
    )
    assert restored.model.get_state() == state
    assert len(constructed) == 1


def test_default_transform_evaluates_scalar_native_inputs_without_constructor_warnings(caplog):
    """The initial shipped kinetics graph receives scalar rates, not length-one arrays."""
    data = DataCurve(x=np.arange(2.0), y=np.ones(2), load_filename_on_init=False)
    fit = Fit(data=data, model_class=ParameterTransformModel)
    fit.model.update()
    parameters = fit.model.parameters_all_dict
    assert sum(parameters[name].value for name in ("x1", "x2", "x3")) == pytest.approx(1.0)
    assert parameters["tR0"].value > 0 and parameters["tR1"].value > 0
    assert not [record for record in caplog.records if record.levelname == "WARNING"]


def test_transform_evaluation_failure_propagates_and_relocks_outputs(monkeypatch):
    """A failed native computation cannot silently leave a stale scientific output."""
    fit = _transform()

    def failed():
        """Expose the same failure an invalid runtime input would produce."""
        raise ValueError("scientific evaluation failed")

    monkeypatch.setattr(fit.model._model._node, "evaluate", failed)
    with pytest.raises(ValueError, match="scientific evaluation failed"):
        fit.model._update_model()
    assert all(port.fixed for port in fit.model._model._node.outputs.values())


def test_transform_local_and_duplicate_named_cross_fit_links_keep_exact_targets(tmp_path):
    """Local and cross-fit links identify ports, including duplicate-named sources."""
    first, second, target_fit = _transform(), _transform(), _transform()
    first.name = second.name = "duplicate-named transform"
    first.model.parameters_all_dict["E"].value = 0.21
    second.model.parameters_all_dict["E"].value = 0.66
    first.model.update()
    second.model.update()
    target_fit.model.parameters_all_dict["a"].link = target_fit.model.parameters_all_dict["gp"]
    target_fit.model.parameters_all_dict["E"].link = second.model.parameters_all_dict["p0"]
    target_fit.model.update()
    fits = [target_fit, first, second]
    project = capture_session([fit.data for fit in fits], fits)
    path = save_file(project, tmp_path / "linked-transform.cs.pto")
    restored = restore_session(load_file(path))
    target_fit, first, second = restored.fits
    target = target_fit.model.parameters_all_dict["E"]
    master = second.model.parameters_all_dict["p0"]
    assert target.link is master
    assert target._port.get_link().get_uid() == master._port.get_uid()
    assert (
        target_fit.model.parameters_all_dict["a"].link is target_fit.model.parameters_all_dict["gp"]
    )
    before = target_fit.model.parameters_all_dict["p0"].value
    second.model.parameters_all_dict["E"].value = 0.42
    second.model.update()
    target_fit.model.update()
    assert target_fit.model.parameters_all_dict["p0"].value != before
    target.link = None
    target.value = 0.31
    target.fixed = True
    target.bounds = (0.2, 0.8)
    target.error_estimate = 0.012
    target_fit.model.parameters_all_dict["a"].link = None
    target_fit.model.update()
    unlinked = capture_session(restored.datasets, restored.fits)
    path = save_file(unlinked, tmp_path / "unlinked-transform.cs.pto")
    target_fit = restore_session(load_file(path)).fits[0]
    target = target_fit.model.parameters_all_dict["E"]
    assert target.link is None and target.value == 0.31 and target.fixed
    assert target.bounds == (0.2, 0.8) and target.error_estimate == 0.012
    assert target_fit.model.parameters_all_dict["a"].link is None


def test_transform_native_output_link_survives_save_restore_edit_resave(tmp_path):
    """The restored native output drives a real PDA prediction and keeps exact identities."""
    from test.gui.test_pda2c_model_editor import _make_pda_data

    transform = _transform()
    consumer = Fit(data=_make_pda_data(nmax=24), model_class=Pda2cSimpleModel)
    target = consumer.model.pch0._pch0[0]
    output = transform.model.parameters_all_dict["p0"]
    efficiency = transform.model.parameters_all_dict["E"]
    efficiency.bounds = (0.1, 0.9)
    efficiency.error_estimate = 0.025
    transform.model.parameters_all_dict["phiD"].fixed = True
    target.link = output
    consumer.model.update()
    assert np.all(np.isfinite(consumer.model.y)) and np.sum(consumer.model.y) > 0
    fits = [transform, consumer]
    node_uid = transform.model._model._node.get_uid()
    port_uids = [p._port.get_uid() for p in transform.model.parameters_all]
    input_port_uids = transform.model.get_state()["input_port_uids"]
    for iteration in range(2):
        expected = consumer.model.y.copy()
        project = capture_session([fit.data for fit in fits], fits)
        path = save_file(project, tmp_path / f"transform-{iteration}.cs.pto")
        expected_path = tmp_path / f"expected-{iteration}.json"
        expected_path.write_text(json.dumps({"predictions": [None, expected.tolist()]}))
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "test.project.scientific_catalogue_probe",
                str(path),
                str(expected_path),
            ],
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        restored = restore_session(load_file(path))
        transform, consumer = fits = restored.fits
        assert transform.model.model_name == "FRET to PDA"
        assert transform.model._model._node.get_uid() == node_uid
        assert [p._port.get_uid() for p in transform.model.parameters_all] == port_uids
        assert transform.model.get_state()["input_port_uids"] == input_port_uids
        for name, port in transform.model._model._node.inputs.items():
            assert (
                port.get_link().get_uid()
                == transform.model.parameters_all_dict[name]._port.get_uid()
            )
        assert transform.model.parameters_all_dict["E"].bounds == (0.1, 0.9)
        assert transform.model.parameters_all_dict["E"].error_estimate == 0.025
        assert transform.model.parameters_all_dict["phiD"].fixed
        target = consumer.model.pch0._pch0[0]
        output = transform.model.parameters_all_dict["p0"]
        assert target.link is output
        assert target._port.get_link().get_uid() == output._port.get_uid()
        np.testing.assert_allclose(consumer.model.y, expected, rtol=1e-12, atol=1e-12)
        assert capture_session(restored.datasets, fits).fits == project.fits
        transform.model.parameters_all_dict["E"].value += 0.06
        transform.model.update()
        consumer.model.update()
        assert 0 < output.value < 1
        assert not np.allclose(consumer.model.y, expected)
