"""Real native transform publication follows concrete owner transactions."""

import copy

import IMP.bff as bff
import numpy as np
import pytest

from chisurf.core.base import Base
from chisurf.core.project.session import capture_session, owned_scientific_objects, restore_session
from chisurf.core.project.transition import OwnerTransaction, replace_project
from chisurf.server.session import SessionState
from test.project.test_transform_snapshot_contracts import _transform


def _same_port(first, second):
    """Use native shared-pointer deduplication, rather than SWIG proxy identity."""
    probe = bff.GraphSession()
    probe.add_port(first)
    probe.add_port(second)
    return len(probe.get_ports()) == 1


def _assert_node(graph, key, expected):
    """Check the original native topology under the exact registered key."""
    actual = graph.get_nodes()[key]
    assert actual.get_uid() == expected.get_uid()
    actual_ports, expected_ports = actual.get_ports(), expected.get_ports()
    assert set(actual_ports) == set(expected_ports)
    assert expected_ports
    assert all(_same_port(actual_ports[name], port) for name, port in expected_ports.items())


def _owner():
    """Build a concrete owner with a real nonempty shipped transform graph."""
    fit = _transform()
    return SessionState(datasets=[fit.data], fits=[fit])


def _node(owner):
    """Return the concrete selected transform node."""
    return owner.fits[0].model._model._node


def test_temporary_parameter_lists_cannot_hide_later_owned_parameters():
    """Repeated multi-model walks must retain every concrete parameter identity."""
    from test.project.test_spec_science_uid import scientific_state

    owner = SessionState()
    for _ in range(6):
        state = scientific_state()
        owner.datasets.extend(state.datasets)
        owner.fits.extend(state.fits)
    expected = {p.unique_identifier: p for fit in owner.fits for p in fit.model.parameters_all}
    for _ in range(20):
        objects = owned_scientific_objects(owner)
        assert all(objects.get(uid) is parameter for uid, parameter in expected.items())


def test_transform_retirement_keeps_peer_keys_and_rollback_graph_identity():
    """Tentative replacement and retirement preserve peer nodes and free ports."""
    owner = _owner()
    project = capture_session(owner.datasets, owner.fits)
    replace_project(project, owner=owner)
    original = _node(owner)
    previous = bff.get_session()
    previous.add_node("owned-key-is-not-uid", original)
    peer = _transform()
    peer_node = peer.model._model._node
    previous.add_node("peer-key-is-not-uid", peer_node)
    peers = []

    def reject(*args):
        staged = _node(owner)
        _assert_node(bff.get_session(), staged.get_uid(), staged)
        assert "owned-key-is-not-uid" not in bff.get_session().get_nodes()
        assert not _same_port(staged.get_ports()["E"], original.get_ports()["E"])
        _assert_node(bff.get_session(), "peer-key-is-not-uid", peer_node)
        peers.append(_transform())
        bff.get_session().add_node("during-presentation", peers[0].model._model._node)
        raise RuntimeError("reject native graph")

    with pytest.raises(RuntimeError, match="reject native graph"):
        replace_project(project, owner=owner, present=reject)
    assert bff.get_session() is previous
    assert _node(owner) is original
    _assert_node(previous, original.get_uid(), original)
    _assert_node(previous, "owned-key-is-not-uid", original)
    _assert_node(previous, "peer-key-is-not-uid", peer_node)
    _assert_node(previous, "during-presentation", peers[0].model._model._node)
    for parameter in peers[0].model.parameters_all:
        assert any(_same_port(port, parameter._port) for port in previous.get_ports())
    replace_project(capture_session([], []), owner=owner)
    assert original.get_uid() not in bff.get_session().get_nodes()
    assert "owned-key-is-not-uid" not in bff.get_session().get_nodes()
    _assert_node(bff.get_session(), "peer-key-is-not-uid", peer_node)


@pytest.mark.parametrize("same_uid", [False, True])
@pytest.mark.parametrize("peer_commit", [False, True])
def test_interleaved_transform_rollback_preserves_peer_native_objects(same_uid, peer_commit):
    """Interleaved owners retain exact current mappings or the original graph."""
    first = _owner()
    project = capture_session(first.datasets, first.fits)
    replace_project(project, owner=first)
    original = _node(first)
    graph_before = bff.get_session()
    second = SessionState() if same_uid else _owner()
    project_b = project if same_uid else capture_session(second.datasets, second.fits)
    original_b = None if same_uid else _node(second)
    a = OwnerTransaction(first, project)
    a.begin()
    early_peer = _transform()
    early_node = early_peer.model._model._node
    bff.get_session().add_node("peer-before-interleave", early_node)
    b = OwnerTransaction(second, project_b)
    b.begin()
    staged_b = _node(second)
    peer = _transform()
    peer_node = peer.model._model._node
    bff.get_session().add_node("peer-after-interleave", peer_node)
    if peer_commit:
        b.finish(commit=True)
        late_peer = _transform()
        bff.get_session().add_node("peer-after-commit", late_peer.model._model._node)
    a.finish(commit=False)
    expected = staged_b if same_uid else original
    _assert_node(bff.get_session(), expected.get_uid(), expected)
    _assert_node(bff.get_session(), "peer-after-interleave", peer_node)
    _assert_node(bff.get_session(), "peer-before-interleave", early_node)
    if not peer_commit:
        b.finish(commit=False)
        assert bff.get_session() is graph_before
        _assert_node(graph_before, original.get_uid(), original)
        _assert_node(graph_before, "peer-after-interleave", peer_node)
        _assert_node(graph_before, "peer-before-interleave", early_node)
        if original_b is not None:
            _assert_node(graph_before, original_b.get_uid(), original_b)
    else:
        _assert_node(bff.get_session(), staged_b.get_uid(), staged_b)
        _assert_node(bff.get_session(), "peer-after-commit", late_peer.model._model._node)
        active = second.fits[0].model.parameters_all_dict["E"]
        assert Base.find_by_uuid(active.unique_identifier) is active
    for parameter in peer.model.parameters_all + early_peer.model.parameters_all:
        assert any(_same_port(port, parameter._port) for port in bff.get_session().get_ports())


@pytest.mark.parametrize("same_uid", [False, True])
def test_peer_rollback_before_owner_rollback_keeps_late_native_registration(same_uid):
    """Peer objects registered after an interleaved rollback reach the original graph."""
    first = _owner()
    project = capture_session(first.datasets, first.fits)
    original = _node(first)
    previous = bff.get_session()
    second = SessionState() if same_uid else _owner()
    project_b = project if same_uid else capture_session(second.datasets, second.fits)
    a = OwnerTransaction(first, project)
    a.begin()
    b = OwnerTransaction(second, project_b)
    b.begin()
    b.finish(commit=False)
    peer = _transform()
    peer_node = peer.model._model._node
    bff.get_session().add_node("peer-after-rollback", peer_node)
    a.finish(commit=False)
    assert bff.get_session() is previous
    _assert_node(previous, original.get_uid(), original)
    _assert_node(previous, "peer-after-rollback", peer_node)
    for parameter in peer.model.parameters_all:
        assert any(_same_port(port, parameter._port) for port in previous.get_ports())


def test_tentative_peer_replacement_under_existing_key_and_port_uid_survives_rollback():
    """Registration identity, rather than equal native UID, distinguishes peer writes."""
    owner = _owner()
    project = capture_session(owner.datasets, owner.fits)
    previous = bff.get_session()
    peer_before = _transform()
    previous.add_node("replaceable-peer-key", peer_before.model._model._node)
    peer_port = peer_before.model.parameters_all_dict["E"]._port
    peers = []

    def reject(*args):
        peers.append(_transform())
        node = peers[0].model._model._node
        port = peers[0].model.parameters_all_dict["E"]._port
        port.set_uid(peer_port.get_uid())
        bff.get_session().add_node("replaceable-peer-key", node)
        raise RuntimeError("keep peer replacement")

    with pytest.raises(RuntimeError, match="keep peer replacement"):
        replace_project(project, owner=owner, present=reject)
    assert bff.get_session() is previous
    _assert_node(previous, "replaceable-peer-key", peers[0].model._model._node)
    replacement = peers[0].model.parameters_all_dict["E"]._port
    matches = [port for port in previous.get_ports() if port.get_uid() == replacement.get_uid()]
    assert any(_same_port(port, replacement) for port in matches)
    assert any(_same_port(port, peer_port) for port in matches)


@pytest.mark.parametrize("interleave", ["none", "commit", "rollback"])
def test_peer_port_with_staged_native_uid_cannot_keep_discarded_port(interleave):
    """Rollback merges raw peer registrations without retaining its cancelled stage."""
    from chisurf.core.fitting.parameter import FittingParameter

    first = _owner()
    project = capture_session(first.datasets, first.fits)
    original = first.fits[0].model.parameters_all_dict["E"]._port
    a = OwnerTransaction(first, project)
    a.begin()
    discarded = first.fits[0].model.parameters_all_dict["E"]._port
    peer = FittingParameter(name="peer-with-same-native-uid", value=8.0)
    peer._port.set_uid(discarded.get_uid())
    if interleave != "none":
        second = _owner()
        b = OwnerTransaction(second, capture_session(second.datasets, second.fits))
        b.begin()
        if interleave == "commit":
            b.finish(commit=True)
    a.finish(commit=False)
    if interleave == "rollback":
        b.finish(commit=False)
    ports = [p for p in bff.get_session().get_ports() if p.get_uid() == original.get_uid()]
    assert len(ports) == 2
    assert any(_same_port(p, original) for p in ports)
    assert any(_same_port(p, peer._port) for p in ports)
    assert not any(_same_port(p, discarded) for p in ports)


def test_clearing_same_uid_transform_owner_cannot_retire_committed_peer_node():
    """A stale owner's detached native graph conveys no authority over a peer."""
    first = _owner()
    project = capture_session(first.datasets, first.fits)
    replace_project(project, owner=first)
    second = SessionState()
    replace_project(project, owner=second)
    committed = _node(second)
    replace_project(capture_session([], []), owner=first)
    _assert_node(bff.get_session(), committed.get_uid(), committed)


def test_general_fcs_declared_inactive_parameters_have_concrete_owner_and_registry():
    """Catalogue restore and publication preserve every inactive preset parameter."""
    from chisurf.core.fitting.fit import Fit
    from chisurf.server.services.parameters import set_parameter_value
    from test.project.test_all_model_catalogue_roundtrip import CATALOGUE, _data, _resolve

    entry = next(item for item in CATALOGUE if item["configured_path"].endswith(".GeneralFCSModel"))
    cls = _resolve(entry["configured_path"])
    data = _data(entry, cls)
    fit = Fit(data=data, model_class=cls, xmin=0, xmax=len(data.y))
    fit.model.diffusion_mode = "two_focus"
    fit.model.two_focus._diam.value = 375.0
    fit.model.mdf_physical._D.value = 123.0
    fit.model.mdf_physical._D.bounds = (10.0, 500.0)
    fit.model.mdf_physical._D.fixed = True
    fit.model.update()
    project = capture_session([data], [fit])
    restored = restore_session(project)
    assert capture_session(restored.datasets, restored.fits).fits == project.fits
    records = project.fits[0]["members"][0]["model"]["parameters"]
    declared = restored.fits[0].model.get_session_parameters()
    objects = owned_scientific_objects(restored)
    assert {p.unique_identifier for p in declared} == {record["uid"] for record in records}
    assert all(objects[p.unique_identifier] is p for p in declared)
    state = SessionState()
    replace_project(project, owner=state)
    for parameter in state.fits[0].model.get_session_parameters():
        assert state.registry.get_parameter(parameter.unique_identifier) is parameter
    inactive = state.fits[0].model.mdf_physical._D
    peer_owner = SessionState()
    replace_project(project, owner=peer_owner)
    peer_inactive = peer_owner.fits[0].model.mdf_physical._D
    assert Base.find_by_uuid(inactive.unique_identifier) is peer_inactive
    prediction = state.fits[0].model.y.copy()
    result = set_parameter_value(state, parameter_uid=inactive.unique_identifier, value=124.0)
    assert result["ok"], result
    assert inactive.value == 124.0
    assert peer_inactive.value == 123.0
    np.testing.assert_array_equal(state.fits[0].model.y, prediction)
    expected = copy.deepcopy(project.fits)
    next(
        record
        for record in expected[0]["members"][0]["model"]["parameters"]
        if record["uid"] == inactive.unique_identifier
    )["value"] = 124.0
    assert capture_session(state.datasets, state.fits).fits == expected
    container = state.registry._parameters
    original_index = dict(container)

    def reject(*args):
        for parameter in state.fits[0].model.get_session_parameters():
            assert state.registry.get_parameter(parameter.unique_identifier) is parameter
        raise RuntimeError("restore inactive preset registry")

    with pytest.raises(RuntimeError, match="restore inactive preset registry"):
        replace_project(project, owner=state, present=reject)
    assert state.registry._parameters is container
    assert set(container) == set(original_index)
    assert all(container[uid] is obj for uid, obj in original_index.items())
    assert capture_session(state.datasets, state.fits).fits == expected
