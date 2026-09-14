"""Focused contracts for the callback-free ChiSurf/BFF model-search bridge."""

from __future__ import annotations

import numpy as np
import pytest

import chisurf.core.curve
import chisurf.core.data
import chisurf.core.fitting.fit as fitting
from chisurf.core.fitting.mcts.native import prepare_native_model_search
from chisurf.core.fitting.mcts.descriptions import prepare_lifetime_description_search
from chisurf.core.fitting.parameter import FittingParameter
from chisurf.core.models.tcspc.lifetime import LifetimeModel

N = 128
DT = 0.048


def _two_lifetime_fit(seed: int = 7):
    import tttrlib

    x = np.arange(N) * DT
    irf = 1000.0 * np.exp(-0.5 * ((x - 1.0) / 0.08) ** 2)
    clean = np.zeros(N)
    tttrlib.fconv_per_cs(
        clean,
        irf / irf.sum(),
        np.array([0.4, 0.9, 0.6, 3.2]),
        12.5,
        N - 1,
        N - 1,
        DT,
    )
    clean = clean / clean.max() * 4000.0 + 2.0
    y = np.random.default_rng(seed).poisson(clean).astype(float)
    data = chisurf.core.data.DataCurve(x=x, y=y, ey=np.sqrt(np.maximum(y, 1.0)))
    fit = fitting.Fit(model_class=LifetimeModel, data=data, noise_model="poisson")
    fit.xmin, fit.xmax = 0, N
    model = fit.model
    model.convolve._irf = chisurf.core.curve.Curve(x=x, y=irf.copy())
    model.convolve.dt = DT
    model.convolve.rep_rate = 80.0
    model.convolve.stop = N * DT
    # The user's instrument lock remains authoritative in every candidate.
    model.convolve._ts.fixed = True
    model.lifetimes._lifetimes[0].value = 3.0
    model.lifetimes.append(amplitude=0.3, lifetime=0.8)
    model.find_parameters()
    return fit


def _state(fit):
    def stable_value(parameter):
        value = float(parameter.value)
        return None if np.isnan(value) else value

    return tuple(
        (stable_value(p), bool(p.fixed), p.link, bool(getattr(p, "redundant", False)))
        for p in fit.model.parameters_all
    )


def test_lifetime_search_uses_bffs_description_without_mutating_the_fit():
    """The lattice is BFF's; ChiSurf only binds data and the user's choices."""
    fit = _two_lifetime_fit()
    external_background = FittingParameter(name="external-bg", value=2.0, fixed=True)
    fit.model.generic._bg.link = external_background
    before = _state(fit)

    prepared = prepare_lifetime_description_search(fit)

    assert prepared.supported, prepared.reasons
    assert _state(fit) == before
    assert fit.model.generic._bg.link is external_background
    root = prepared.problem.get_initial_state()
    assert root.get_structure_key() == "lifetime.components.1"
    # The ceiling is the rows the user allocated: two.
    assert set(prepared.problem.get_structure_keys()) == {
        "lifetime.components.1", "lifetime.components.2"}
    assert {a.get_key() for a in prepared.problem.get_actions(root)} == {
        "add-component", "stop"}


def test_the_winner_is_applied_to_the_users_model():
    fit = _two_lifetime_fit()
    prepared = prepare_lifetime_description_search(fit)
    assert prepared.supported, prepared.reasons
    problem = prepared.problem
    root = problem.get_initial_state()
    add = next(a for a in problem.get_actions(root) if a.get_key() == "add-component")

    two = problem.evaluate(root, add)

    assert two.get_structure_key() == "lifetime.components.2"
    assert problem.get_last_fit_status() in (1, 2, 3, 4)
    original_second_tau = fit.model.lifetimes._lifetimes[1].value
    prepared.binding.apply_state(problem, two)
    assert not fit.model.lifetimes._lifetimes[1].fixed
    assert fit.model.lifetimes._lifetimes[1].value != pytest.approx(original_second_tau)
    assert fit.model.convolve._ts.fixed  # the user's lock is theirs
    assert np.all(np.isfinite(fit.model.y))


def test_an_unused_row_is_zeroed_not_left_holding_a_seed():
    """Writing BFF's seed amplitude would add a component nobody fitted."""
    fit = _two_lifetime_fit()
    prepared = prepare_lifetime_description_search(fit)
    problem = prepared.problem
    root = problem.get_initial_state()
    prepared.binding.apply_state(problem, root)
    assert fit.model.lifetimes._amplitudes[1].value == 0.0
    assert fit.model.lifetimes._amplitudes[1].fixed


def test_user_fixed_structure_is_refused_and_unchanged():
    fit = _two_lifetime_fit()
    fit.model.lifetimes._lifetimes[1].fixed = True
    before = _state(fit)

    prepared = prepare_lifetime_description_search(fit)

    assert not prepared.supported
    assert prepared.reasons[0].code == "fixed_structural_parameter"
    assert _state(fit) == before


def test_what_the_description_does_not_carry_is_refused():
    fit = _two_lifetime_fit()
    fit.model.convolve.mode = "exp"
    prepared = prepare_lifetime_description_search(fit)
    assert not prepared.supported
    assert prepared.reasons[0].code == "non_periodic_convolution"


def test_the_description_reproduces_chisurfs_configured_decay():
    """Equivalence with the model the user configured, not with itself.

    Nothing is assigned after building: the route's own binding of the fit
    has to produce ChiSurf's curve. An earlier version wrote the parameters in
    afterwards, and a write to a fixed port is silently ignored -- which hid
    that the route never passed the user's lifetime rows at all, so the fixed
    first amplitude sat at a neutral seed and every fitted fraction was
    relative to the wrong reference.
    """
    from chisurf.core.fitting import minimizer

    fit = _two_lifetime_fit()
    built = minimizer.graph_objective(fit, fit.model)
    node = (built[0] if isinstance(built, tuple) else built)._decay
    node.update()
    reference = np.asarray(node.get_output_port("decay").value)

    prepared = prepare_lifetime_description_search(fit)
    key = "lifetime.components.2"
    prepared.problem.activate_structure(key)
    curve = np.asarray(prepared.problem.get_structure_output(key, f"{key}.decay"))
    assert curve == pytest.approx(reference, rel=1e-9, abs=1e-9)
