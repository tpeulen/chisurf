"""Session-curve DTOs preserve parent indices and explicit child identities."""

from __future__ import annotations

import numpy as np
import pytest

import chisurf as cs
from chisurf.core.api import ChiSurfAPI
from chisurf.core.api._client import ChisurfClient
from chisurf.core.data import DataCurve, ExperimentDataCurveGroup
from chisurf.server.services import datasets
from chisurf.server.session import SessionState


@pytest.fixture
def curves(monkeypatch):
    """Two curves deliberately share names and filenames but have distinct UIDs."""
    monkeypatch.setattr(cs.core.base.Base, "_uuid_index", dict(cs.core.base.Base._uuid_index))
    members = [DataCurve(x=np.arange(3), y=np.full(3, value), name="same.dat", filename="same.dat",
                         unique_identifier=f"session-child-{index}")
               for index, value in enumerate((2.0, 9.0))]
    group = ExperimentDataCurveGroup(members, name="IRF group", unique_identifier="session-parent")
    group.current_dataset = 0
    unrelated = DataCurve(x=np.arange(3), y=np.full(3, 77.0), unique_identifier="unrelated-global")
    monkeypatch.setattr(cs, "imported_datasets", [unrelated])
    return group, members


@pytest.mark.parametrize("count", [1, 2])
def test_group_summaries_retain_outer_index_and_all_direct_members(curves, count):
    """A one-member group still carries an addressable member identity."""
    group, members = curves
    if count == 1:
        group.pop()
    state = SessionState(datasets=[group])
    local = ChiSurfAPI(mode="local", state=state).list_datasets()
    remote = datasets.list_datasets(state)["datasets"]
    assert local == remote
    assert local[0]["index"] == 0 and local[0]["uid"] == "session-parent"
    children = local[0]["members"]
    assert len(children) == count
    assert [child["member_index"] for child in children] == list(range(count))
    assert [child["uid"] for child in children] == [member.unique_identifier for member in members[:count]]
    assert all(child["index"] == 0 and child["parent_uid"] == "session-parent" for child in children)
    assert all(child["name"] == "same.dat" for child in children)


def test_explicit_state_drives_all_local_dataset_reads(curves):
    """An adopted state must not silently read a different global session."""
    group, _ = curves
    api = ChiSurfAPI(mode="local", state=SessionState(datasets=[group]))
    assert api.get_dataset_info(dataset_uid="session-parent")["dataset"]["uid"] == "session-parent"
    assert api.get_dataset_curve_data(dataset_index=0)["y"] == [2, 2, 2]


def test_child_uid_resolves_exact_curve_without_changing_active_member(curves):
    """The second IRF remains distinct despite duplicate filenames and first active member."""
    group, _ = curves
    state = SessionState(datasets=[group])
    api = ChiSurfAPI(mode="local", state=state)
    kwargs = {"dataset_uid": "session-parent", "member_uid": "session-child-1"}
    local = api.get_dataset_curve_data(**kwargs)
    remote = datasets.get_dataset_curve_data(state, **kwargs)
    assert local == remote
    assert local["y"] == [9, 9, 9]
    assert local["dataset_index"] == 0 and local["member_index"] == 1
    assert local["dataset_uid"] == "session-parent" and local["member_uid"] == "session-child-1"
    assert group._current_dataset == 0
    local_info = api.get_dataset_info(**kwargs)
    remote_info = datasets.get_dataset_info(state, **kwargs)
    assert local_info == remote_info
    assert local_info["dataset"]["uid"] == "session-child-1"
    assert local_info["dataset"]["index"] == 0
    assert local_info["dataset"]["parent_uid"] == "session-parent"
    assert group._current_dataset == 0


@pytest.mark.parametrize("owner", ["api", "service"])
@pytest.mark.parametrize("method", ["get_dataset_info", "get_dataset_curve_data"])
@pytest.mark.parametrize(("parent", "member"), [
    ("gone-parent", "session-child-1"), ("session-parent", "gone-member"),
])
def test_stale_parent_or_member_uid_never_falls_back_to_valid_index(curves, owner, method, parent, member):
    """Unknown explicit identities fail even when index zero is still valid."""
    group, _ = curves
    state = SessionState(datasets=[group])
    target = ChiSurfAPI(mode="local", state=state) if owner == "api" else datasets
    args = () if owner == "api" else (state,)
    result = getattr(target, method)(*args, dataset_index=0, dataset_uid=parent, member_uid=member)
    assert result["ok"] is False
    assert result["error_code"] == "NOT_FOUND"
    assert group._current_dataset == 0


def test_uid_lookup_reports_actual_outer_index_when_callers_index_is_stale(curves):
    """UID lookup reports its current parent index, rather than echoing a stale position."""
    group, _ = curves
    other = DataCurve(x=np.arange(3), y=np.ones(3), unique_identifier="first-other")
    state = SessionState(datasets=[other, group])
    info = datasets.get_dataset_info(state, dataset_index=0, dataset_uid="session-parent",
                                     member_uid="session-child-1")
    assert info["dataset"]["index"] == 1
    assert info["dataset"]["member_index"] == 1


@pytest.mark.parametrize("method", ["dataset__get", "dataset__curve_data"])
def test_generated_client_accepts_and_forwards_optional_member_uid(method):
    """Generated signatures must carry the new identity across the real transport boundary."""
    client = ChisurfClient.__new__(ChisurfClient)
    calls = []

    def call(name, params):
        """Record actual generated-method parameters without opening a socket."""
        calls.append((name, params))
        return {"ok": True, "dataset": {"uid": "session-child-1"}}

    client.call = call
    getattr(client, method)(dataset_index=0, dataset_uid="session-parent", member_uid="session-child-1")
    assert calls[0][1] == {"dataset_index": 0, "dataset_uid": "session-parent", "member_uid": "session-child-1"}
