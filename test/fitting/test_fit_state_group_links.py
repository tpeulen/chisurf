"""Saving/restoring the parameter links of a grouped (global) fit.

A global fit links every follower to a parameter of the group's *first*
member, so the link target never lives in the model the group exposes unless
that first member happens to be selected. These tests pin that the saved state
finds the target for any selection, and that the round trip re-establishes it.
"""

from __future__ import annotations

import numpy as np
import pytest

import chisurf as cs
import chisurf.macros.core_fit as core_fit
from chisurf.core.data import DataCurve, DataGroup
from chisurf.core.fitting.fit import Fit, FitGroup
from chisurf.core.fitting.parameter import FittingParameter
from chisurf.core.models.model import ModelCurve
from chisurf.core.project.fit_state import apply_state_to_fit, fit_to_state


class DummyLinearModel(ModelCurve):
    """A constant model with a single free parameter ``p0``."""

    name = "DummyLinearModel"

    def __init__(self, fit: Fit, discover: bool = True, **kwargs):  # type: ignore[override]
        super().__init__(fit, **kwargs)
        self.p0 = FittingParameter(name="p0", value=1.0)
        if discover:
            self.find_parameters()

    def _update_model(self, **kwargs):  # type: ignore[override]
        x = self.fit.data.x
        self.x = x
        self.y = float(self.p0.value) * np.ones_like(x)


@pytest.fixture
def linked_group():
    """Build a three-member fit group with ``p0`` linked, registered in ``cs.fits``."""
    curves = [
        DataCurve(x=np.linspace(0.0, 1.0, 8, dtype=float), y=np.ones(8) * (i + 1), name=f"d{i}")
        for i in range(3)
    ]
    group = FitGroup(data=DataGroup(curves), model_class=DummyLinearModel)
    for local_fit in group.grouped_fits:
        local_fit.model.find_parameters()
    core_fit._auto_link_non_nuisance_group_parameters(group)

    cs.fits.append(group)
    try:
        yield group
    finally:
        cs.fits.remove(group)


def _p0(fit: Fit) -> FittingParameter:
    return fit.model.parameters_all_dict["p0"]


def _saved_link(fit: Fit) -> tuple:
    """Return the ``(link_target, link_target_fit_uid)`` saved for ``p0``."""
    state = fit_to_state(fit)
    for p_state in state["parameters"].values():
        if p_state["name"] == "p0":
            return p_state["link_target"], p_state["link_target_fit_uid"]
    raise AssertionError("p0 missing from the saved state")


@pytest.mark.parametrize("selected", [0, 1, 2])
def test_group_links_are_saved_for_any_selection(linked_group, selected):
    """The saved link must not depend on which curve of the group is shown."""
    linked_group.selected_fit = selected
    master_fit = linked_group.grouped_fits[0]
    master_uid = str(_p0(master_fit).unique_identifier)

    assert _saved_link(master_fit) == (None, None)
    for follower in linked_group.grouped_fits[1:]:
        # The *member's* uid is recorded, not the group's: the group resolves
        # to whichever member is selected and would restore the wrong model.
        assert _saved_link(follower) == (
            master_uid,
            str(master_fit.unique_identifier),
        )


@pytest.mark.parametrize("selected", [0, 1, 2])
def test_group_links_survive_a_round_trip(linked_group, selected):
    """Applying the saved state re-establishes the links dropped in between."""
    linked_group.selected_fit = selected
    master = _p0(linked_group.grouped_fits[0])
    states = [fit_to_state(f) for f in linked_group.grouped_fits]

    for local_fit in linked_group.grouped_fits:
        _p0(local_fit).link = None

    for local_fit, state in zip(linked_group.grouped_fits, states):
        apply_state_to_fit(local_fit, state)

    assert _p0(linked_group.grouped_fits[0]).link is None
    for follower in linked_group.grouped_fits[1:]:
        assert _p0(follower).link is master


def test_a_link_recorded_against_the_group_uid_still_restores(linked_group):
    """Projects saved before the members were addressed individually still load."""
    master = _p0(linked_group.grouped_fits[0])
    follower_fit = linked_group.grouped_fits[1]
    state = fit_to_state(follower_fit)
    for p_state in state["parameters"].values():
        if p_state["name"] == "p0":
            p_state["link_target_fit_uid"] = str(linked_group.unique_identifier)

    _p0(follower_fit).link = None
    apply_state_to_fit(follower_fit, state)

    assert _p0(follower_fit).link is master
