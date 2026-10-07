"""IRF action callbacks preserve parent/member identity and the owning fit."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

import chisurf as cs
from chisurf.core.data import DataCurve, ExperimentDataCurveGroup
from chisurf.macros import model as macros


@pytest.fixture
def group(monkeypatch):
    """Duplicate curve names cannot substitute for distinct member UIDs."""
    monkeypatch.setattr(cs.core.base.Base, "_uuid_index", dict(cs.core.base.Base._uuid_index))
    curves = [DataCurve(x=np.arange(3), y=np.full(3, value), name="same.dat", filename="same.dat",
                       unique_identifier=f"irf-member-{index}")
              for index, value in enumerate((1.0, 8.0))]
    parent = ExperimentDataCurveGroup(curves, unique_identifier="irf-parent")
    monkeypatch.setattr(cs, "imported_datasets", [parent])
    monkeypatch.setattr(macros, "_sync_editors", lambda fit: None)
    return parent, curves


def test_explicit_member_identity_precedes_legacy_selector_and_duplicate_names(group):
    """An explicit member never resolves through a filtered selector or a name suffix."""
    parent, members = group
    selector = SimpleNamespace(datasets=[members[0]])
    selected = macros._resolve_selected_curve(0, "same.dat", selector=selector,
                                              dataset_uid="irf-parent", member_uid="irf-member-1")
    assert selected is members[1]
    assert parent._current_dataset == 0


@pytest.mark.parametrize(("parent_uid", "member_uid"), [
    ("gone-parent", "irf-member-1"), ("irf-parent", "gone-member"),
])
def test_bad_identity_never_falls_back_to_valid_legacy_selection(group, parent_uid, member_uid):
    """A valid index or matching filename cannot rescue an invalid explicit UID."""
    _, members = group
    selector = SimpleNamespace(datasets=[members[0]])
    assert macros._resolve_selected_curve(0, "same.dat", selector=selector,
                                          dataset_uid=parent_uid, member_uid=member_uid) is None


class _Fit:
    """A bounded fit target exposing the actual action/macro contracts."""

    def __init__(self):
        self.selected_fit_index = 0
        self.updated = 0
        self.datasets = []
        self.model = SimpleNamespace(convolve=SimpleNamespace(_irf=None),
                                     set_dataset=lambda slot, curve: self.datasets.append((slot, curve)))

    def __getitem__(self, key):
        """Return the targeted fit member for the macro's usual slice."""
        return [self][key]

    def update(self):
        """Observe that only the selected owning fit was updated."""
        self.updated += 1


def test_irf_action_targets_owning_fit_and_selected_child(group, monkeypatch):
    """The original top index/name/fit index accompany additive stable identities."""
    from chisurf.core.actions import model_actions  # noqa: F401 - register actual actions

    parent, members = group
    fits = [_Fit(), _Fit(), _Fit()]
    monkeypatch.setattr(cs, "fits", fits)
    cs.core.actions.dispatch(name="model.change_irf", payload={
        "irf_idx": 0, "irf_name": "same.dat", "fit_index": 2,
        "dataset_uid": "irf-parent", "member_uid": "irf-member-1",
    })
    assert fits[0].model.convolve._irf is None and fits[1].model.convolve._irf is None
    np.testing.assert_array_equal(fits[2].model.convolve._irf.y, members[1].y)
    assert fits[2].model.convolve._irf.name == members[1].name
    assert fits[2].updated == 1 and parent._current_dataset == 0


def test_generic_curve_action_preserves_fixed_slot_and_fit_index(group, monkeypatch):
    """Fixed action payload remains intact when the chosen group member is added."""
    from chisurf.core.actions import model_actions  # noqa: F401 - register actual actions

    _, members = group
    fits = [_Fit(), _Fit(), _Fit()]
    monkeypatch.setattr(cs, "fits", fits)
    cs.core.actions.dispatch(name="model.set_dataset", payload={
        "slot": "response", "idx": 0, "name": "same.dat", "fit_index": 2,
        "dataset_uid": "irf-parent", "member_uid": "irf-member-1",
    })
    assert fits[2].datasets == [("response", members[1])]
    assert not fits[0].datasets and not fits[1].datasets
