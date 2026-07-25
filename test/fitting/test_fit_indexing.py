from __future__ import annotations

import numpy as np
import pytest

import chisurf as cs
from chisurf.core.data import DataCurve, ExperimentDataCurveGroup
from chisurf.core.fitting import find_fit_idx
from chisurf.core.fitting.fit import FitGroup
from chisurf.core.models.tcspc.lifetime import LifetimeModel


@pytest.fixture
def fit_group() -> FitGroup:
    """Build a two-member :class:`FitGroup` over a decay-like curve group."""
    x = np.arange(64, dtype=np.float64)
    y = np.exp(-x / 8.0) * 1000.0
    data = ExperimentDataCurveGroup([DataCurve(x=x, y=y, name="a"), DataCurve(x=x, y=y, name="b")])
    return FitGroup(data=data, model_class=LifetimeModel)


def test_a_member_fit_resolves_to_the_index_of_its_group(fit_group):
    """A grouped fit is addressable by index, like the group itself.

    Only groups live in ``chisurf.fits``, so an identity-only search leaves
    every member fit without an index -- and the index is what the action
    layer and the server RPC address a fit by.
    """
    fits = [fit_group]
    assert find_fit_idx(fit_group, fits) == 0
    assert len(fit_group.grouped_fits) == 2
    for member in fit_group.grouped_fits:
        assert member is not fit_group
        assert find_fit_idx(member, fits) == 0


def test_the_group_index_is_reported_through_the_fit_property(fit_group, monkeypatch):
    """``Fit.fit_idx`` answers for a member fit, not only for the group."""
    other = FitGroup(
        data=ExperimentDataCurveGroup(
            [DataCurve(x=np.arange(8, dtype=np.float64), y=np.ones(8), name="c")]
        ),
        model_class=LifetimeModel,
    )
    monkeypatch.setattr(cs, "fits", [other, fit_group], raising=False)
    assert fit_group.fit_idx == 1
    for member in fit_group.grouped_fits:
        assert member.fit_idx == 1
    for member in other.grouped_fits:
        assert member.fit_idx == 0


def test_a_fit_outside_the_list_has_no_index(fit_group):
    """A fit that is in no list resolves to ``None`` -- explicitly, per the contract."""
    assert find_fit_idx(fit_group, []) is None
    assert find_fit_idx(fit_group.grouped_fits[0], []) is None
