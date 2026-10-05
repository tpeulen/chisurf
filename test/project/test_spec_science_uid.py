"""Active scientific identities must belong to the addressed runtime owner."""

import numpy as np
import pytest

from chisurf.core.base import Base
from chisurf.core.data import DataCurve
from chisurf.core.fitting.fit import Fit
from chisurf.core.models.parse.parse import ParseModel
from chisurf.core.project.session import capture_session, restore_session
from chisurf.core.project.transition import replace_project
from chisurf.server.services.parameters import set_parameter_value
from chisurf.server.session import SessionState


def scientific_state():
    """Build a real equation fit whose coefficients affect predictions."""
    x = np.arange(1.0, 12.0)
    curve = DataCurve(x=x, y=2 * x + 3, ey=np.ones_like(x))
    fit = Fit(data=curve, model_class=ParseModel)
    fit.model.func = "a*x+b"
    fit.fit_range = (0, len(x))
    fit.model.update()
    return SessionState(datasets=[curve], fits=[fit])


def test_uid_publication_and_owned_parameter_prediction():
    """Published UIDs address the replacement and update its real model."""
    state = scientific_state()
    original = state.fits[0].model.parameters_all_dict["a"]
    uid = original.unique_identifier
    project = capture_session(state.datasets, state.fits)
    staged = restore_session(project)
    assert Base.find_by_uuid(uid) is original
    replace_project(project, owner=state)
    active = state.fits[0].model.parameters_all_dict["a"]
    assert Base.find_by_uuid(uid) is active
    assert staged.fits[0] is not state.fits[0]
    result = set_parameter_value(state, value=9.0, parameter_uid=uid)
    assert result["ok"] is True
    assert active.value == 9.0
    assert original.value == 1.0
    np.testing.assert_allclose(state.fits[0].model.y, 9 * state.fits[0].data.x + 1)
    state.fits[0].run()
    np.testing.assert_allclose(
        [p.value for p in state.fits[0].model.parameters_all], [2, 3], atol=1e-4
    )


def test_uid_rollback_keeps_original_lookup_by_identity():
    """A failed presentation restores every replaced mapping by identity."""
    state = scientific_state()
    original = state.fits[0].model.parameters_all_dict["a"]
    project = capture_session(state.datasets, state.fits)

    def fail(*args):
        assert Base.find_by_uuid(original.unique_identifier) is not original
        raise RuntimeError("presentation failed")

    with pytest.raises(RuntimeError, match="presentation failed"):
        replace_project(project, owner=state, present=fail)
    assert state.fits[0].model.parameters_all_dict["a"] is original
    assert Base.find_by_uuid(original.unique_identifier) is original


def test_same_uids_in_two_sessions_resolve_within_owner():
    """Global lookup order never decides which server session is mutated."""
    first = scientific_state()
    project = capture_session(first.datasets, first.fits)
    second = SessionState()
    replace_project(project, owner=second)
    first_parameter = first.fits[0].model.parameters_all_dict["a"]
    second_parameter = second.fits[0].model.parameters_all_dict["a"]
    assert set_parameter_value(first, value=4, parameter_uid=first_parameter.unique_identifier)[
        "ok"
    ]
    assert first_parameter.value == 4
    assert second_parameter.value == 1
    foreign = scientific_state().fits[0].model.parameters_all_dict["a"]
    assert not set_parameter_value(first, value=7, parameter_uid=foreign.unique_identifier)["ok"]
    assert foreign.value == 1


def test_native_uid_publication_retains_peer_ports_and_rollback_identity():
    """The default BFF graph publishes canonical ports and restores by identity."""
    import IMP.bff as bff

    from chisurf.core.fitting.parameter import FittingParameter

    state = scientific_state()
    parameter = state.fits[0].model.parameters_all_dict["a"]
    native_uid = parameter._port.get_uid()
    peer = FittingParameter(name="peer", value=8)
    previous = bff.get_session()
    project = capture_session(state.datasets, state.fits)

    def reject(*args):
        active = state.fits[0].model.parameters_all_dict["a"]
        assert active._port.get_uid() == native_uid
        ports = {p.get_uid(): p for p in bff.get_session().get_ports()}
        assert np.asarray(ports[native_uid].value).reshape(-1)[0] == active.value
        assert np.asarray(ports[peer._port.get_uid()].value).reshape(-1)[0] == 8
        assert set_parameter_value(state, value=5, parameter_uid=active.unique_identifier)["ok"]
        assert np.asarray(ports[native_uid].value).reshape(-1)[0] == 5
        assert parameter.value == 1
        raise RuntimeError("rollback native")

    with pytest.raises(RuntimeError, match="rollback native"):
        replace_project(project, owner=state, present=reject)
    assert bff.get_session() is previous
    assert parameter._port.get_uid() == native_uid


def test_additive_fit_import_is_resolved_in_current_owner():
    """Imported fit UIDs work without clearing existing or unrelated mappings."""
    state = scientific_state()
    incoming = scientific_state()
    restored = restore_session(capture_session(incoming.datasets, incoming.fits))
    state.datasets.extend(restored.datasets)
    state.fits.extend(restored.fits)
    parameter = restored.fits[0].model.parameters_all_dict["a"]
    result = set_parameter_value(state, value=6, parameter_uid=parameter.unique_identifier)
    assert result["ok"], result
    assert parameter.value == 6
    assert incoming.fits[0].model.parameters_all_dict["a"].value == 1
    np.testing.assert_allclose(restored.fits[0].model.y, 6 * restored.fits[0].data.x + 1)


def test_base_uid_setter_reindexes_only_its_owned_entry():
    """A scientific UID reassignment never leaves a stale alias in Base."""
    curve = DataCurve(x=[0.0], y=[1.0])
    old = curve.unique_identifier
    curve.unique_identifier = "explicit-new-owned-uid"
    assert Base.find_by_uuid("explicit-new-owned-uid") is curve
    assert Base.find_by_uuid(old) is None


def test_owned_plugin_parameters_work_and_foreign_link_targets_fail():
    """Plugin groups participate through explicit session ownership only."""
    from chisurf.core.fitting.parameter import FittingParameter, FittingParameterGroup
    from chisurf.server.services.parameters import parameter_link

    group = FittingParameterGroup()
    group.slope = FittingParameter(name="slope", value=3)
    group.find_parameters()
    state = scientific_state()
    state.plugins["owned_model"] = group
    assert set_parameter_value(state, value=4, parameter_uid=group.slope.unique_identifier)["ok"]
    active = state.fits[0].model.parameters_all_dict["a"]
    assert parameter_link(
        state,
        parameter_uid=active.unique_identifier,
        target_parameter_uid=group.slope.unique_identifier,
    )["ok"]
    assert active.link is group.slope
    foreign = FittingParameter(name="foreign", value=20)
    result = parameter_link(
        state,
        parameter_uid=active.unique_identifier,
        target_parameter_uid=foreign.unique_identifier,
    )
    assert not result["ok"]
    assert active.link is group.slope


def test_duplicate_native_uid_is_rejected_without_registry_pollution():
    """Two distinct coefficients cannot overwrite one native identity."""
    state = scientific_state()
    original = state.fits[0].model.parameters_all_dict["a"]
    project = capture_session(state.datasets, state.fits)
    parameters = project.fits[0]["members"][0]["model"]["parameters"]
    parameters[1]["native_uid"] = parameters[0]["native_uid"]
    with pytest.raises(ValueError, match="native.*UID"):
        replace_project(project, owner=state)
    assert Base.find_by_uuid(original.unique_identifier) is original


def test_owner_registry_replacement_and_rollback_retain_containers():
    """The session registry's exact owned mappings follow its scientific graph."""
    state = scientific_state()
    fit = state.fits[0]
    parameter = fit.model.parameters_all_dict["a"]
    state.registry.register_fit(fit.unique_identifier, fit)
    state.registry.register_parameter(parameter.unique_identifier, parameter)
    parameters = state.registry._parameters
    lock = state.registry._lock
    project = capture_session(state.datasets, state.fits)

    def reject(*args):
        assert (
            state.registry.get_parameter(parameter.unique_identifier)
            is state.fits[0].model.parameters_all_dict["a"]
        )
        assert state.registry.get_fit(fit.unique_identifier) is state.fits[0]
        raise RuntimeError("registry rollback")

    with pytest.raises(RuntimeError, match="registry rollback"):
        replace_project(project, owner=state, present=reject)
    assert state.registry._parameters is parameters
    assert state.registry._lock is lock
    assert state.registry.get_parameter(parameter.unique_identifier) is parameter
    assert state.registry.get_fit(fit.unique_identifier) is fit


def test_fresh_process_repeated_uid_publication_is_stable(tmp_path):
    """Fresh canonical loads preserve native/Python UIDs and real predictions."""
    import os
    import subprocess
    import sys

    state = scientific_state()
    from chisurf.core.project.storage import save_file

    path = save_file(capture_session(state.datasets, state.fits), tmp_path / "initial.cs.pto")
    script = """
import importlib.abc
import sys
import numpy as np
class BlockMMFDB(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'mmfdb' or fullname.startswith('mmfdb.'):
            raise AssertionError('MMFDB imported')
sys.meta_path.insert(0, BlockMMFDB())
import IMP.bff as bff
from chisurf.core.base import Base
from chisurf.core.project.storage import load_file, save_file
from chisurf.core.project.session import capture_session
from chisurf.core.project.transition import replace_project
from chisurf.server.session import SessionState
from chisurf.server.services.parameters import set_parameter_value
state = SessionState()
project = load_file(sys.argv[1])
expected = [p['uid'] for p in project.fits[0]['members'][0]['model']['parameters']]
native_expected = [p['native_uid'] for p in project.fits[0]['members'][0]['model']['parameters']]
count = None
for iteration in range(4):
    replace_project(project, owner=state)
    parameters = state.fits[0].model.parameters_all
    assert [p.unique_identifier for p in parameters] == expected
    assert [p._port.get_uid() for p in parameters] == native_expected
    assert all(Base.find_by_uuid(p.unique_identifier) is p for p in parameters)
    ports = bff.get_session().get_ports()
    if count is not None:
        assert len(ports) == count, (len(ports), count)
    count = len(ports)
    assert set_parameter_value(state, value=iteration+2, parameter_uid=expected[0])['ok']
    np.testing.assert_allclose(state.fits[0].model.y, (iteration+2)*state.datasets[0].x+parameters[1].value)
    state.fits[0].run()
    np.testing.assert_allclose([p.value for p in parameters], [2,3], atol=1e-4)
    project = capture_session(state.datasets, state.fits)
    save_file(project, sys.argv[1])
    project = load_file(sys.argv[1])
print('four fresh canonical file/owner/UID edits/refits; native ports stable:', count)
assert not any(n == 'mmfdb' or n.startswith('mmfdb.') for n in sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(path)],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    (tmp_path / "uid-readback.txt").write_text(result.stdout)


def test_rollback_keeps_unrelated_thread_native_registration():
    """Rollback must not discard a peer port registered during presentation."""
    from concurrent.futures import ThreadPoolExecutor

    import IMP.bff as bff

    from chisurf.core.fitting.parameter import FittingParameter

    state = scientific_state()
    project = capture_session(state.datasets, state.fits)
    native_before = bff.get_session()
    peers = []

    def publish_peer():
        peers.append(FittingParameter(name="concurrent-peer", value=8))

    def reject(*args):
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(publish_peer).result(timeout=5)
        raise RuntimeError("peer rollback")

    with pytest.raises(RuntimeError, match="peer rollback"):
        replace_project(project, owner=state, present=reject)
    assert bff.get_session() is native_before
    peer = peers[0]
    assert Base.find_by_uuid(peer.unique_identifier) is peer
    assert peer._port.get_uid() in {p.get_uid() for p in bff.get_session().get_ports()}


def test_interleaved_owner_transactions_keep_native_owner_mappings():
    """A rollback after a peer commit restores only its own native identities."""
    import IMP.bff as bff

    from chisurf.core.project.transition import OwnerTransaction

    first, second = scientific_state(), scientific_state()
    project_a = capture_session(first.datasets, first.fits)
    project_b = capture_session(second.datasets, second.fits)
    original = first.fits[0].model.parameters_all_dict["a"]
    original.value = 4
    a = OwnerTransaction(first, project_a)
    a.begin()
    b = OwnerTransaction(second, project_b)
    b.begin()
    active_b = second.fits[0].model.parameters_all_dict["a"]
    assert set_parameter_value(second, value=8, parameter_uid=active_b.unique_identifier)["ok"]
    b.finish(commit=True)
    a.finish(commit=False)
    assert Base.find_by_uuid(original.unique_identifier) is original
    assert Base.find_by_uuid(active_b.unique_identifier) is active_b
    ports = {p.get_uid(): p for p in bff.get_session().get_ports()}
    assert np.asarray(ports[original._port.get_uid()].value).reshape(-1)[0] == 4
    assert np.asarray(ports[active_b._port.get_uid()].value).reshape(-1)[0] == 8


def test_overlapping_same_uid_rollbacks_never_republish_discarded_stage():
    """Rollback predecessors remain live when two sessions load identical science."""
    import IMP.bff as bff

    from chisurf.core.project.transition import OwnerTransaction

    first = scientific_state()
    project = capture_session(first.datasets, first.fits)
    original = first.fits[0].model.parameters_all_dict["a"]
    original.value = 4
    native_before = bff.get_session()
    a = OwnerTransaction(first, project)
    a.begin()
    second = SessionState()
    b = OwnerTransaction(second, project)
    b.begin()
    a.finish(commit=False)
    b.finish(commit=False)
    assert first.fits[0].model.parameters_all_dict["a"] is original
    assert second.fits == []
    assert Base.find_by_uuid(original.unique_identifier) is original
    assert bff.get_session() is native_before
    ports = {p.get_uid(): p for p in bff.get_session().get_ports()}
    assert np.asarray(ports[original._port.get_uid()].value).reshape(-1)[0] == 4


def test_clearing_old_same_uid_owner_keeps_committed_peer_native_ports():
    """Only the current owner's native mappings may be retired by replacement."""
    import IMP.bff as bff

    first = scientific_state()
    project = capture_session(first.datasets, first.fits)
    second = SessionState()
    replace_project(project, owner=second)
    active = second.fits[0].model.parameters_all_dict["a"]
    replace_project(capture_session([], []), owner=first)
    assert Base.find_by_uuid(active.unique_identifier) is active
    assert active._port.get_uid() in {p.get_uid() for p in bff.get_session().get_ports()}
    assert set_parameter_value(second, value=9, parameter_uid=active.unique_identifier)["ok"]
    ports = {p.get_uid(): p for p in bff.get_session().get_ports()}
    assert np.asarray(ports[active._port.get_uid()].value).reshape(-1)[0] == 9
