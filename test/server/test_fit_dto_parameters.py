"""What a fit DTO says about its parameters.

The link menu, the Global View and every scripted client read parameters through
these DTOs, so an empty ``parameters_all`` here is not a cosmetic problem: it is
a fit that appears to have no parameters at all.
"""
from __future__ import annotations

import numpy as np

import chisurf.core.data as data
from chisurf.core.fitting.fit import FitGroup
from chisurf.core.models.tcspc.lifetime import LifetimeModel
from chisurf.server.services.fits import get_fit_info, list_fits
from chisurf.server.session import SessionState


def _fit(n_curves: int = 1) -> FitGroup:
    """Build a TCSPC fit group over *n_curves* synthetic decays."""
    curves = []
    for i in range(n_curves):
        x = np.arange(1, 64, dtype=np.float64)
        y = 1000.0 * np.exp(-x / 10.0) + 1.0
        curves.append(data.DataCurve(x=x, y=y, ey=np.sqrt(y), name=f"decay-{i}"))
    return FitGroup(
        data=data.DataCurveGroup(curves, name="decays"),
        model_class=LifetimeModel,
    )


def test_fresh_fit_lists_its_parameters():
    """A fit that has not been run or updated still reports its parameters."""
    state = SessionState(fits=[_fit()])
    dto = list_fits(state)["fits"][0]
    assert dto["parameter_count"] > 0
    assert len(dto["model"]["parameters_all"]) == dto["parameter_count"]


def test_parameter_entries_carry_uid_and_group():
    """Entries are addressable by UUID and know which sub-group they belong to."""
    state = SessionState(fits=[_fit()])
    params = get_fit_info(state, fit_index=0)["fit"]["model"]["parameters_all"]
    assert all(p["uid"] for p in params)
    assert len({p["uid"] for p in params}) == len(params)
    assert {p["group"] for p in params} - {""}


def test_detailed_dto_carries_the_group_members():
    """Each curve of a fit group is addressable, not only the selected one."""
    state = SessionState(fits=[_fit(n_curves=2)])
    fit_dto = get_fit_info(state, fit_index=0)["fit"]
    members = fit_dto["members"]
    assert [m["local_idx"] for m in members] == [0, 1]
    assert all(m["uid"] for m in members)
    for member in members:
        assert len(member["parameters_all"]) > 0
    # The two curves are separate fits: no parameter is shared between them.
    first, second = ({p["uid"] for p in m["parameters_all"]} for m in members)
    assert not (first & second)


def test_summary_dto_omits_the_members():
    """``fit.list`` stays lean — members ride along only with ``fit.get``."""
    state = SessionState(fits=[_fit(n_curves=2)])
    assert list_fits(state)["fits"][0]["members"] == []
