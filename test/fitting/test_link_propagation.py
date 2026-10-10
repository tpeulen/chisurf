"""An edit of a linked master refreshes the fits that follow it.

A follower pulls its master's value only when its own model evaluates, so the
edit has to be pushed: the ``fit.update`` service the GUI calls after a value
edit refreshes every fit linked to the edited one (directly or through a chain),
once each, and leaves unrelated fits alone.
"""

from __future__ import annotations

import numpy as np

import chisurf.core.data
import chisurf.core.fitting.fit
import chisurf.core.models.parse
from chisurf.core.fitting.link_propagation import link_followers
from chisurf.server.services.fits import fit_update
from chisurf.server.services.parameters import set_parameter_value
from chisurf.server.session import SessionState


def _fit(name: str):
    x = np.linspace(0.0, 5.0, 32)
    curve = chisurf.core.data.DataCurve(x=x, y=1.0 + x**2, ey=np.full_like(x, 0.1))
    fit = chisurf.core.fitting.fit.FitGroup(
        data=chisurf.core.data.DataGroup([curve]),
        model_class=chisurf.core.models.parse.ParseModel,
    )
    fit.name = name
    for local in fit:
        local.fit_range = 0, len(local.model.y)
        local.model.func = "c+a*x**2"
        local.model.find_parameters()
    fit._model.find_parameters()
    fit.update()
    return fit


def _parameter(fit, name):
    (local,) = list(fit)
    return local.model.parameters_all_dict[name]


def _prediction(fit):
    (local,) = list(fit)
    return np.array(local.model.y, dtype=float).copy()


def _counting_updates(fit):
    (local,) = list(fit)
    calls = []
    original = local.update

    def update():
        calls.append(1)
        original()

    local.update = update
    return calls


def test_editing_a_master_refreshes_its_follower_without_its_own_update():
    a, b, unrelated = _fit("A"), _fit("B"), _fit("C")
    _parameter(b, "c").link = _parameter(a, "c")
    b.update()
    state = SessionState(fits=[a, b, unrelated])

    old_c = _parameter(a, "c").value
    before_b = _prediction(b)
    before_unrelated = _prediction(unrelated)
    b_updates = _counting_updates(b)
    unrelated_updates = _counting_updates(unrelated)

    # What the GUI's value editor sends: the value, then the owning fit's update.
    assert set_parameter_value(state, "c", 7.5, fit_uid=a.unique_identifier, local_idx=0)["ok"]
    assert fit_update(state, fit_uid=a.unique_identifier)["ok"]

    after_b = _prediction(b)
    assert not np.allclose(after_b, before_b), "the follower kept its stale prediction"
    assert np.allclose(after_b - before_b, 7.5 - old_c)
    assert len(b_updates) == 1, "the follower must be refreshed exactly once"
    assert unrelated_updates == [], "an unlinked fit must not be recomputed"
    assert np.array_equal(_prediction(unrelated), before_unrelated)


def test_followers_are_found_transitively_once_each_and_in_dependency_order():
    a, b, c, d = _fit("A"), _fit("B"), _fit("C"), _fit("D")
    # C follows B, which follows A; D follows C and A.
    _parameter(b, "c").link = _parameter(a, "c")
    _parameter(c, "a").link = _parameter(b, "a")
    _parameter(d, "a").link = _parameter(c, "c")
    _parameter(d, "c").link = _parameter(a, "a")
    # Out of session order on purpose: the order must come from the links.
    fits = [d, c, b, a]

    (lb,), (lc,), (ld,) = list(b), list(c), list(d)
    followers = link_followers(fits, a)
    assert [id(f) for f in followers] == [id(lb), id(lc), id(ld)]
    # Editing C reaches only D; editing D reaches nothing.
    assert [id(f) for f in link_followers(fits, c)] == [id(ld)]
    assert link_followers(fits, d) == []


def test_a_link_cycle_between_fits_terminates():
    a, b = _fit("A"), _fit("B")
    _parameter(b, "c").link = _parameter(a, "c")
    _parameter(a, "a").link = _parameter(b, "a")
    (lb,) = list(b)
    assert [id(f) for f in link_followers([a, b], a)] == [id(lb)]
