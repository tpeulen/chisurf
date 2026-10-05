"""Scientific-loss regressions from the project persistence follow-up review."""

import copy
import os
import subprocess
import sys

import numpy as np
import pytest

from chisurf.core.data import DataCurve, DataCurveGroup
from chisurf.core.fitting.fit import Fit, FitGroup
from chisurf.core.fitting.parameter import FittingParameter
from chisurf.core.models.model import ModelCurve
from chisurf.core.project import Project, SessionCodecError, capture_session, restore_session
from chisurf.core.project.pto import _validate_project_payload, write_project


class _LinearModel(ModelCurve):
    """A real parameter-backed model with an unambiguous prediction."""

    def __init__(self, fit, **kwargs):
        super().__init__(fit, **kwargs)
        self.slope = FittingParameter(name="slope", value=1.0)
        self.find_parameters()

    def _update_model(self, **kwargs):
        self.x = self.fit.data.x
        self.y = self.slope.value * self.x


def _curve(uid):
    """Return a measured curve with a stable identity."""
    x = np.arange(5.0)
    return DataCurve(x=x, y=x + 1, ey=np.ones(5), unique_identifier=uid)


def test_missing_codec_marker_cannot_publish_invalid_science(tmp_path, monkeypatch):
    """Validate before asking the transport to create a candidate file."""
    payload = Project(datasets={"bad": {"uid": "bad", "kind": "unsupported"}}).to_dict()

    def forbidden(*args):
        raise AssertionError("invalid science reached PTO transport")

    monkeypatch.setattr("chisurf.core.project.pto._temporary_path", forbidden)
    with pytest.raises(SessionCodecError):
        write_project(tmp_path / "invalid.cs.pto", payload)


def test_missing_codec_marker_still_validates_shared_database_payload():
    """The validation entrypoint used by MMFDB is unconditional too."""
    with pytest.raises(SessionCodecError):
        _validate_project_payload(Project(datasets={"bad": {"kind": "unsupported"}}).to_dict())


def test_invalid_unmarked_science_never_reaches_database_transport(monkeypatch):
    """Real storage's validator rejects science before accessing its transport."""
    from chisurf.core.project.storage import ProjectStorageError, save_database

    calls = []

    class ForbiddenTransport:
        def __getattr__(self, name):
            calls.append(name)
            raise AssertionError("invalid science reached database transport")

    monkeypatch.setattr("chisurf.core.project.storage.select_backend", lambda _: "mmfdb")
    with pytest.raises(ProjectStorageError, match="Invalid MMFDB project snapshot"):
        save_database(
            Project(datasets={"bad": {"kind": "unsupported"}}),
            mmfdb_settings={},
            client=ForbiddenTransport(),
        )
    assert calls == []


def test_invalid_unmarked_save_retains_previous_valid_portable_snapshot(tmp_path):
    """Real PTO publication preserves its prior scientific document on rejection."""
    curve = _curve("saved")
    project = capture_session([curve], [])
    path = write_project(tmp_path / "safe.cs.pto", project.to_dict())
    original = path.read_bytes()
    invalid = copy.deepcopy(project)
    invalid.metadata.pop("session_codec")
    invalid.datasets["saved"]["metadata"]["unique_identifier"] = "contradiction"
    with pytest.raises(SessionCodecError, match="metadata.*UID"):
        write_project(path, invalid.to_dict())
    assert path.read_bytes() == original
    restored = restore_session(Project.load(path))
    np.testing.assert_array_equal(restored.datasets[0].y, curve.y)


def test_aggregate_global_parameters_and_exact_links_survive_two_roundtrips():
    """Global and member parameters keep their own identities and link endpoints."""
    curves = DataCurveGroup([_curve("a"), _curve("b")])
    group = FitGroup(curves, model_class=_LinearModel)
    global_value = FittingParameter(name="global", value=7.0, fixed=True)
    global_value.bounds = (0, float("inf"))
    global_value.bounds_on = True
    global_value.error_estimate = 0.25
    follower = FittingParameter(name="follower", value=2.0)
    group._model.append_global_parameter(global_value)
    group._model.append_global_parameter(follower)
    follower.link = group.grouped_fits[1].model.slope
    group.grouped_fits[0].model.slope.link = global_value

    restored = restore_session(capture_session([curves], [group]))
    for _ in range(2):
        aggregate = restored.fits[0]._model
        assert len(aggregate.global_parameters_all) == 2
        value, linked = aggregate.global_parameters_all
        assert value.value == 7.0
        assert value.fixed is True
        assert value.error_estimate == 0.25
        assert value.bounds == (0, float("inf"))
        assert value.unique_identifier == global_value.unique_identifier
        assert restored.fits[0].grouped_fits[0].model.slope.link is value
        assert linked.link is restored.fits[0].grouped_fits[1].model.slope
        restored = restore_session(capture_session(restored.datasets, restored.fits))


def test_unlinked_aggregate_global_parameter_is_not_silently_lost():
    """Reproduce the review's successful capture that discarded a global value."""
    curves = DataCurveGroup([_curve("a"), _curve("b")])
    group = FitGroup(curves, model_class=_LinearModel)
    group._model.append_global_parameter(FittingParameter(name="global", value=7.0))
    restored = restore_session(capture_session([curves], [group]))
    assert len(restored.fits[0]._model.global_parameters_all) == 1
    assert restored.fits[0]._model.global_parameters_all[0].value == 7.0


@pytest.mark.parametrize("bounds", [(0, np.inf), (-np.inf, 10), (-np.inf, np.inf), (-3, 10)])
@pytest.mark.parametrize("enabled", [True, False])
def test_each_bound_endpoint_survives(bounds, enabled):
    """Preserve finite limits even when the other limit is infinite or disabled."""
    curve = _curve("curve")
    fit = Fit(model_class=_LinearModel, data=curve)
    fit.model.slope.bounds = bounds
    fit.model.slope.bounds_on = enabled
    saved = capture_session([curve], [fit])
    parameter = restore_session(saved).fits[0].model.slope
    assert parameter.bounds_on is enabled
    assert (parameter.lb, parameter.ub) == bounds


def test_null_input_parameter_fails_closed():
    """An incomplete input must not inherit the constructor's default value."""
    curve = _curve("curve")
    project = capture_session([curve], [Fit(model_class=_LinearModel, data=curve)])
    project.fits[0]["members"][0]["model"]["parameters"][0]["value"] = None
    with pytest.raises(SessionCodecError, match="parameter.*value"):
        restore_session(project)


def test_metadata_cannot_override_dataset_identity():
    """Reserved metadata is checked before any objects are reconstructed."""
    project = capture_session([_curve("a"), _curve("b")], [])
    project.datasets["b"]["metadata"]["unique_identifier"] = "a"
    with pytest.raises(SessionCodecError, match="metadata.*UID"):
        restore_session(project)


def test_capture_rejects_metadata_contradicting_explicit_identity():
    """A curve with an independently defined identity must agree with metadata."""

    class ExplicitIdentityCurve(DataCurve):
        @property
        def unique_identifier(self):
            return "explicit-identity"

    curve = ExplicitIdentityCurve(x=np.arange(3.0), y=np.arange(3.0))
    curve.meta_data["unique_identifier"] = "contradictory-metadata"
    with pytest.raises(SessionCodecError, match="metadata.*UID"):
        capture_session([curve], [])


def test_failed_detached_restore_keeps_live_registry_and_identity():
    """An adapter failure after construction cannot publish staged resources."""
    import IMP.bff as bff

    from chisurf.core.base import Base

    curve = _curve("live-on-failure")
    fit = Fit(model_class=_LinearModel, data=curve)
    project = capture_session([curve], [fit])
    live = bff.get_session()
    ports = {p.get_uid() for p in live.get_ports()}
    project.fits[0]["members"][0]["model"]["parameters"][0]["name"] = "missing-parameter"
    with pytest.raises(SessionCodecError, match="order/name changed"):
        restore_session(project)
    assert {p.get_uid() for p in live.get_ports()} == ports
    assert Base.find_by_uuid(curve.unique_identifier) is curve


def test_capture_rejects_distinct_dataset_groups_with_same_uid():
    """Distinct groups never publish the same scientific identity."""
    first = DataCurveGroup([_curve("a")], unique_identifier="duplicate")
    second = DataCurveGroup([_curve("b")], unique_identifier="duplicate")
    with pytest.raises(SessionCodecError, match="duplicate dataset.group UID"):
        capture_session([first, second], [])


def test_restore_rejects_duplicate_dataset_group_uid():
    """Layout records cannot restore two objects sharing one group identity."""
    project = capture_session([DataCurveGroup([_curve("a")], unique_identifier="group")], [])
    project.ui_state["dataset_layout"].append(copy.deepcopy(project.ui_state["dataset_layout"][0]))
    with pytest.raises(SessionCodecError, match="duplicate dataset.group UID"):
        restore_session(project)


def test_detached_restoration_does_not_register_ports_in_live_bff_session():
    """Successful detached validation never alters the active native registry."""
    import IMP.bff as bff

    curve = _curve("curve")
    fit = Fit(model_class=_LinearModel, data=curve)
    live = bff.get_session()

    def state():
        return {
            port.get_uid(): (
                port.name,
                np.asarray(port.value).tobytes(),
                repr(port.get_lower_bound()),
                repr(port.get_upper_bound()),
                port.get_is_bounded(),
            )
            for port in live.get_ports()
        }

    before = state()
    nodes = live.get_number_of_nodes()
    project = capture_session([curve], [fit])
    restore_session(project)
    assert bff.get_session() is live
    assert state() == before
    assert live.get_number_of_nodes() == nodes


def test_detached_restore_keeps_live_uid_lookup_and_structure_versions():
    """Staging objects does not redirect live identity lookups or invalidate caches."""
    from chisurf.core.base import Base
    from chisurf.core.fitting import factorgraph

    curve = _curve("identity-stays-live")
    fit = Fit(model_class=_LinearModel, data=curve)
    before = (factorgraph.structure_version(), factorgraph.window_version())
    project = capture_session([curve], [fit])
    restore_session(project)
    assert Base.find_by_uuid(curve.unique_identifier) is curve
    assert (factorgraph.structure_version(), factorgraph.window_version()) == before


def test_detached_construction_preserves_other_threads_live_registration(monkeypatch):
    """Private staging never clears registrations made by another live thread."""
    from concurrent.futures import ThreadPoolExecutor

    import IMP.bff as bff

    from chisurf.core.base import Base
    from chisurf.core.fitting import factorgraph

    curve = _curve("staged")
    fit = Fit(model_class=_LinearModel, data=curve)
    live = bff.get_session()
    count = live.get_number_of_ports()
    version = factorgraph.structure_version()
    registered = []
    original = _LinearModel.__init__

    def register_live():
        assert bff.get_session() is live
        parameter = FittingParameter(name="other", value=9)
        parameter.fixed = True
        registered.append((_curve("other-thread"), parameter))

    def construct(model, *args, **kwargs):
        original(model, *args, **kwargs)
        if not registered:
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(register_live).result(timeout=5)

    monkeypatch.setattr(_LinearModel, "__init__", construct)
    capture_session([curve], [fit])
    assert live.get_number_of_ports() == count + 1
    assert Base.find_by_uuid("other-thread") is registered[0][0]
    assert factorgraph.structure_version() > version


def test_unknown_type_in_builtin_namespace_is_rejected_before_import(monkeypatch):
    """An allowed package prefix is not permission to import an unknown type."""
    curve = _curve("curve")
    project = capture_session([curve], [Fit(model_class=_LinearModel, data=curve)])
    state = project.fits[0]["members"][0]["model"]
    state.update(model_module="chisurf.core.models.archive_controlled", model_class="Unknown")
    calls = []

    def forbidden(name):
        calls.append(name)
        raise AssertionError("unknown type reached import")

    monkeypatch.setattr("chisurf.core.project.session.importlib.import_module", forbidden)
    with pytest.raises(SessionCodecError, match="not registered or trusted"):
        restore_session(project)
    assert calls == []


def test_description_group_globals_restore_in_fresh_process(tmp_path):
    """Native lifetime models/global links reconstruct without a process registry."""
    from chisurf.core.models.description import tcspc_lifetime

    curves = DataCurveGroup([_curve("a"), _curve("b")])
    group = FitGroup(curves, model_class=tcspc_lifetime)
    value = FittingParameter(name="shared", value=7, fixed=True)
    value.bounds = (-np.inf, 10)
    value.bounds_on = True
    group._model.append_global_parameter(value)
    group.grouped_fits[0].model.parameters_all[0].link = value
    project = capture_session([curves], [group])
    path = project.save(tmp_path / "fresh.cs.pto")
    script = """
import sys
import numpy as np
from chisurf.core.project import Project, capture_session, restore_session
session = restore_session(Project.load(sys.argv[1]))
for _ in range(2):
    group = session.fits[0]
    parameter = group._model.global_parameters_all[0]
    assert parameter.value == 7
    assert parameter.bounds == (-np.inf, 10)
    assert parameter.fixed is True
    assert group.grouped_fits[0].model.parameters_all[0].link is parameter
    session = restore_session(capture_session(session.datasets, session.fits))
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(path)],
        env=os.environ.copy(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
