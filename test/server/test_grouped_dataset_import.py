"""Cached Simulator previews cross the actual dataset.load protocol atomically."""

from __future__ import annotations

import copy
import json

import numpy as np
import pytest

import chisurf as cs
from chisurf.core.api import ChiSurfAPI, _extract_curve_data
from chisurf.core.api._client import ChisurfClient, RemoteError
from chisurf.core.data import DataCurve
from chisurf.core.experiments.core.experiment import Experiment
from chisurf.core.experiments.tcspc.simulator import TCSPCSimulatorSetup
from chisurf.macros import core_data
from chisurf.server import protocol
from chisurf.server.app import ChiSurfServer
from chisurf.server.dispatcher import ServiceDispatcher
from chisurf.server.session import SessionState


class _ProtocolTransport:
    """Use real JSON-RPC encoding and app dispatch without opening an OS socket."""

    def __init__(self, state):
        self.server = ChiSurfServer.__new__(ChiSurfServer)
        self.server.dispatcher = ServiceDispatcher(state)
        self.server.dispatcher._build_default_registry()
        self.requests = []

    def call(self, method, params):
        """Round-trip the request through JSON, protocol, app, registry and service."""
        request = json.loads(json.dumps(protocol.encode_request(method, params, 1)))
        self.requests.append(request)
        method, params, request_id = protocol.decode_request(request)
        result = self.server._zmq_dispatch(method, params)
        if result.get("ok") is False:
            return protocol.encode_error(-32000, result["error"], request_id=request_id,
                                          data={"error_code": result.get("error_code")})
        return json.loads(json.dumps(protocol.encode_response(result, request_id)))


def _client(state):
    """Bind the generated client to the actual app/protocol transport seam."""
    client = ChisurfClient.__new__(ChisurfClient)
    client._client = _ProtocolTransport(state)
    return client


@pytest.fixture
def preview(monkeypatch):
    """Produce one real cached polarized simulation with non-default calibration."""
    monkeypatch.setattr(cs.core.base.Base, "_uuid_index", dict(cs.core.base.Base._uuid_index))
    experiment = Experiment(name="Lifetime")
    reader = TCSPCSimulatorSetup(experiment=experiment, n_tac=64, dt=0.1, p0=2500, add_noise=False,
                                 lifetime_spectrum=[1.0, 3.2], polarization="vv/vh")
    reader.g_factor, reader.l1, reader.l2, reader.vh_shift = 1.42, 0.04, 0.11, 0.7
    reader.rotation_spectrum = np.array([0.2, 1.3])
    irf = DataCurve(x=np.arange(64) * 0.1, y=np.eye(1, 64, 3).ravel(), name="measured IRF")
    reader.instrument_response_function = irf
    group = reader.read(name="cached")
    group.name = "cached pair"
    group.current_dataset = 1
    group.meta_data.update(note="cached without regeneration", axes=("time", "channel"),
                           calibration=np.array([reader.g_factor, reader.l1, reader.l2]))
    for index, member in enumerate(group):
        member.meta_data["channel"] = index
    def forbidden(*args, **kwargs):
        """No Add path may re-read the already cached photon/count realization."""
        raise AssertionError("cached preview was regenerated")
    monkeypatch.setattr(reader, "read", forbidden)
    monkeypatch.setattr(reader, "get_data", forbidden)
    return reader, group


def _assert_pair(actual, expected):
    """Compare every scientific/identity field, not merely the group's active curve."""
    assert len(actual) == len(expected) == 2
    assert actual.unique_identifier == expected.unique_identifier
    assert actual.name == expected.name and actual._current_dataset == expected._current_dataset
    assert actual.experiment.unique_identifier == expected.experiment.unique_identifier
    assert actual.experiment.name == expected.experiment.name
    assert actual.meta_data["axes"] == ("time", "channel")
    np.testing.assert_array_equal(actual.meta_data["calibration"], expected.meta_data["calibration"])
    for got, original in zip(actual, expected):
        assert got.experiment.unique_identifier == original.experiment.unique_identifier
        assert got.data_reader.experiment is got.experiment
        assert got.unique_identifier == original.unique_identifier and got.name == original.name
        for field in ("x", "y", "ex", "ey", "mask"):
            np.testing.assert_array_equal(getattr(got, field), getattr(original, field))
        assert got.meta_data["channel"] == original.meta_data["channel"]
        for field in ("g_factor", "l1", "l2", "vh_shift", "polarization", "is_vv_vh", "dt"):
            assert getattr(got.data_reader, field) == getattr(original.data_reader, field)
        np.testing.assert_array_equal(got.data_reader.instrument_response_function.y,
                                      original.data_reader.instrument_response_function.y)


def test_cached_pair_imports_once_through_actual_generated_client_and_service(preview):
    """A cached group arrives as one parent with both unchanged calibrated members."""
    reader, group = preview
    state = SessionState()
    client = _client(state)
    api = ChiSurfAPI(client=client, mode="server")
    result = api.load_dataset(experiment_reader=reader, dataset=group)
    assert result["ok"] and len(state.datasets) == 1
    _assert_pair(state.datasets[0], group)
    assert client._client.requests[0]["method"] == "dataset.load"


def test_cached_group_needs_no_reader_argument_to_cross_the_api(preview):
    """The supplied scientific object is sufficient; reader inference cannot drop it."""
    _, group = preview
    state = SessionState()
    api = ChiSurfAPI(client=_client(state), mode="server")
    assert api.load_dataset(dataset=group)["ok"]
    _assert_pair(state.datasets[0], group)


def test_explicit_local_state_receives_cached_pair_and_globals_remain_unchanged(preview, monkeypatch):
    """An injected isolated state owns its import instead of the live global container."""
    reader, group = preview
    globals_before = [DataCurve(x=np.arange(3), y=np.ones(3), name="unrelated")]
    monkeypatch.setattr(cs, "imported_datasets", globals_before)
    state = SessionState()
    api = ChiSurfAPI(mode="local", state=state)
    assert api.load_dataset(experiment_reader=reader, dataset=group)["ok"]
    assert len(state.datasets) == 1 and len(globals_before) == 1
    _assert_pair(state.datasets[0], group)
    assert all(got is old for got, old in zip(state.datasets[0], group))


def test_live_aliased_state_preserves_macro_history_route_and_cached_identity(preview, monkeypatch):
    """The existing GUI/history route imports the same members with the same group UID."""
    reader, group = preview
    monkeypatch.setattr(cs, "imported_datasets", [])
    monkeypatch.setattr(cs, "api", None, raising=False)
    monkeypatch.setattr(cs, "cs", None)
    recorded = []
    monkeypatch.setattr(core_data, "_record_history", lambda **kwargs: recorded.append(kwargs))
    api = ChiSurfAPI(mode="local")
    assert api.load_dataset(experiment_reader=reader, dataset=group)["ok"]
    assert api._state.datasets is cs.imported_datasets
    assert len(cs.imported_datasets) == 1
    _assert_pair(cs.imported_datasets[0], group)
    assert all(got is old for got, old in zip(cs.imported_datasets[0], group))
    assert recorded and recorded[-1]["action_type"] == "dataset_add"


def test_scalar_inline_contract_remains_valid_without_group_envelope():
    """Existing scalar callers keep their x/y/ex/ey payload and one result."""
    state = SessionState()
    client = _client(state)
    payload = {"x": [0.0, 1.0], "y": [3.0, 4.0], "ex": [0.0, 0.0], "ey": [1.0, 2.0]}
    result = client.dataset__load(curve_data=payload, name="scalar")
    assert result["ok"] and len(state.datasets) == 1
    assert state.datasets[0].name == "scalar"
    np.testing.assert_array_equal(state.datasets[0].y, [3, 4])


def test_real_vm_cached_group_keeps_single_member_identity(monkeypatch):
    """Magic-angle previews also keep their cached group/member UID across RPC."""
    monkeypatch.setattr(cs.core.base.Base, "_uuid_index", dict(cs.core.base.Base._uuid_index))
    reader = TCSPCSimulatorSetup(n_tac=64, dt=0.1, add_noise=False, lifetime_spectrum=[1.0, 3.0])
    group = reader.read(name="cached VM")
    state = SessionState()
    assert ChiSurfAPI(client=_client(state), mode="server").load_dataset(dataset=group)["ok"]
    assert len(state.datasets) == 1 and len(state.datasets[0]) == 1
    assert state.datasets[0].unique_identifier == group.unique_identifier
    assert state.datasets[0][0].unique_identifier == group[0].unique_identifier
    np.testing.assert_array_equal(state.datasets[0][0].y, group[0].y)


def test_invalid_second_member_fails_without_partial_import(preview):
    """Validate the complete transmitted group before adding its first valid curve."""
    _, group = preview
    payload = copy.deepcopy(_extract_curve_data(group))
    payload["members"][1]["arrays"]["y"]["values"].pop()
    state = SessionState()
    with pytest.raises(RemoteError):
        _client(state).dataset__load(curve_data=payload)
    assert not state.datasets


def test_invalid_cached_group_never_falls_back_to_reader_regeneration(preview):
    """A malformed cached object is rejected before transport or local mutation."""
    reader, group = preview
    group[1].y = np.full_like(group[1].y, np.nan)
    state = SessionState()
    result = ChiSurfAPI(mode="local", state=state).load_dataset(experiment_reader=reader, dataset=group)
    assert result["ok"] is False and not state.datasets


@pytest.mark.parametrize("fault", ["duplicate_uid", "metadata", "reader", "dependency",
                                  "reader_state", "irf_array"])
def test_malformed_group_identity_or_metadata_leaves_session_unchanged(preview, fault, monkeypatch):
    """Bad scientific identities/configuration are rejected before any object is imported."""
    _, group = preview
    payload = copy.deepcopy(_extract_curve_data(group))
    if fault == "duplicate_uid":
        payload["members"][1]["uid"] = payload["members"][0]["uid"]
    elif fault == "metadata":
        payload["members"][1]["metadata"]["unique_identifier"] = "contradictory"
    elif fault == "reader":
        payload["members"][1]["reader"]["module"] = "untrusted.arbitrary_module"
    elif fault == "reader_state":
        payload["members"][1]["reader"]["state"]["g_factor"] = 5.0
    elif fault == "irf_array":
        reader = payload["members"][1]["reader"]
        reader.pop("dependencies")
        payload["members"][1].pop("reader_inputs")
        reader["irf_array"] = {"dtype": "float64", "values": [[1.0]]}
    else:
        payload["members"][1]["reader_inputs"]["instrument_response_function"]["arrays"]["y"]["values"][0] = 17.0
    from chisurf.server.services import datasets

    constructed = []
    restore = datasets._restore_cached_dataset

    def record_construct(payload):
        """Record any premature domain object construction for an invalid packet."""
        constructed.append(payload)
        return restore(payload)

    monkeypatch.setattr(datasets, "_restore_cached_dataset", record_construct)
    state = SessionState()
    before = dict(cs.core.base.Base._uuid_index)
    with pytest.raises(RemoteError):
        _client(state).dataset__load(curve_data=payload)
    assert not state.datasets
    assert cs.core.base.Base._uuid_index == before
    assert not constructed


def test_explicit_state_rejects_an_empty_reader_result():
    """A reader without output must not append a null object to its session."""
    from types import SimpleNamespace

    state = SessionState()
    reader = SimpleNamespace(get_data=lambda **kwargs: None)
    assert ChiSurfAPI(mode="local", state=state).load_dataset(experiment_reader=reader)["ok"] is False
    assert not state.datasets


@pytest.mark.parametrize("isolated", [True, False])
def test_cached_actual_structure_group_keeps_local_owning_import(preview, monkeypatch, isolated):
    """A cached 148L Structure group imports unchanged without re-opening its file."""
    from pathlib import Path

    from chisurf.core.data import ExperimentDataGroup
    from chisurf.core.experiments.modelling.reader import StructureReader

    reader = StructureReader(experiment=Experiment(name="Structure"), record_provenance=False)
    group = reader.get_data(filename=str(Path("test/data/atomic_coordinates/pdb_files/148l.pdb").resolve()))
    assert isinstance(group, ExperimentDataGroup)
    structure = group[0]
    atoms = structure.atoms.copy()

    def forbidden(*args, **kwargs):
        """Keep the original molecular coordinates rather than re-opening the source."""
        raise AssertionError("cached structure was regenerated")

    monkeypatch.setattr(reader, "get_data", forbidden)
    monkeypatch.setattr(reader, "read", forbidden)
    monkeypatch.setattr(cs, "imported_datasets", [])
    monkeypatch.setattr(cs, "api", None, raising=False)
    monkeypatch.setattr(cs, "cs", None)
    monkeypatch.setattr(core_data, "_record_history", lambda **kwargs: None)
    state = SessionState() if isolated else None
    api = ChiSurfAPI(mode="local", state=state)
    assert api.load_dataset(experiment_reader=reader, dataset=group)["ok"]
    assert api._state.datasets[0] is group and group[0] is structure
    np.testing.assert_array_equal(group[0].atoms, atoms)
    assert structure.n_atoms == 1300 and structure.n_residues == 164
    assert len(cs.imported_datasets) == (0 if isolated else 1)


def test_cached_non_curve_group_is_explicitly_unsupported_by_curve_transport():
    """Other scientific group types are never flattened into an active-child curve."""
    from chisurf.core.base import Base
    from chisurf.core.data import ExperimentDataGroup

    group = ExperimentDataGroup([Base(name="non-curve")], name="other scientific group")
    state = SessionState()
    client = _client(state)
    result = ChiSurfAPI(client=client, mode="server").load_dataset(dataset=group)
    assert result["ok"] is False and not state.datasets and not client._client.requests


@pytest.mark.parametrize("polarization", ["vm", "vv/vh"])
def test_actual_cached_simulation_preserves_boolean_masks(polarization, monkeypatch):
    """DataCurve boolean selection masks survive cached VM and paired imports exactly."""
    monkeypatch.setattr(cs.core.base.Base, "_uuid_index", dict(cs.core.base.Base._uuid_index))
    reader = TCSPCSimulatorSetup(n_tac=64, dt=0.1, add_noise=False,
                                 lifetime_spectrum=[1.0, 3.0], polarization=polarization)
    group = reader.read(name="masked preview")
    for index, member in enumerate(group):
        member.mask = (np.arange(len(member.y)) % (index + 2)) != 0

    def forbidden(*args, **kwargs):
        """A selected cached realization must not be replaced by another simulation."""
        raise AssertionError("cached masked preview was regenerated")

    monkeypatch.setattr(reader, "read", forbidden)
    monkeypatch.setattr(reader, "get_data", forbidden)
    state = SessionState()
    result = ChiSurfAPI(client=_client(state), mode="server").load_dataset(
        experiment_reader=reader, dataset=group)
    assert result["ok"] and len(state.datasets) == 1
    assert len(state.datasets[0]) == len(group)
    for restored, original in zip(state.datasets[0], group):
        assert restored.mask.dtype == original.mask.dtype == np.dtype(bool)
        np.testing.assert_array_equal(restored.mask, original.mask)
        np.testing.assert_array_equal(restored.y, original.y)


@pytest.mark.parametrize("field", ["x", "y", "ex", "ey"])
def test_boolean_measurements_and_errors_are_not_selection_masks(preview, field):
    """Only a mask may be boolean; measurement/error arrays keep finite numeric types."""
    _, group = preview
    payload = _extract_curve_data(group)
    array = payload["members"][0]["arrays"][field]
    array["dtype"] = "bool"
    array["values"] = [True] * len(array["values"])
    state = SessionState()
    with pytest.raises(RemoteError):
        _client(state).dataset__load(curve_data=payload)
    assert not state.datasets
