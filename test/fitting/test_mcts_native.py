"""Focused contracts for the callback-free ChiSurf/BFF model-search bridge."""

from __future__ import annotations

import numpy as np
import pytest

import chisurf.core.curve
import chisurf.core.data
import chisurf.core.fitting.fit as fitting
from chisurf.core.fitting.mcts.native import prepare_native_model_search
from chisurf.core.fitting.mcts.tcspc_lifetime import prepare_tcspc_lifetime_search
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


def test_lifetime_capability_builds_native_actions_without_mutating_the_fit():
    fit = _two_lifetime_fit()
    external_background = FittingParameter(name="external-bg", value=2.0, fixed=True)
    fit.model.generic._bg.link = external_background
    before = _state(fit)

    prepared = prepare_tcspc_lifetime_search(fit)

    assert prepared.supported, prepared.reasons
    assert _state(fit) == before
    assert fit.model.generic._bg.link is external_background
    assert all(not port.is_linked() for port in prepared.binding.ports)
    root = prepared.problem.get_initial_state()
    assert root.get_structure_key() == "lifetime:1"
    assert {
        (action.get_key(), action.get_predicted_state_key(), action.get_terminal())
        for action in prepared.problem.get_actions(root)
    } == {
        ("add-lifetime-2", "lifetime:2", False),
        ("terminate", "lifetime:1", True),
    }


def test_native_reward_has_the_existing_component_count_preference_and_applies_winner():
    fit = _two_lifetime_fit()
    prepared = prepare_tcspc_lifetime_search(fit)
    assert prepared.supported, prepared.reasons
    problem = prepared.problem
    root = problem.get_initial_state()
    add = next(action for action in problem.get_actions(root) if not action.get_terminal())

    two = problem.evaluate(root, add)

    assert two.get_structure_key() == "lifetime:2"
    assert problem.get_last_fit_status() in (1, 2, 3, 4)
    assert two.get_reward() > root.get_reward()
    original_second_tau = fit.model.lifetimes._lifetimes[1].value
    prepared.binding.apply_state(problem, two)
    assert not fit.model.lifetimes._lifetimes[1].fixed
    assert fit.model.lifetimes._lifetimes[1].value != pytest.approx(original_second_tau)
    assert fit.model.convolve._ts.fixed
    assert np.all(np.isfinite(fit.model.y))


def test_user_fixed_structure_is_refused_and_unchanged():
    fit = _two_lifetime_fit()
    fit.model.lifetimes._lifetimes[1].fixed = True
    before = _state(fit)

    prepared = prepare_tcspc_lifetime_search(fit)

    assert not prepared.supported
    assert prepared.reasons[0].code == "fixed_structural_parameter"
    assert _state(fit) == before


def test_none_native_objective_is_terminal_without_fallback(monkeypatch):
    fit = _two_lifetime_fit()
    # Obtain the family-owned declaration by intercepting only the final generic
    # preparation call; then exercise the generic bridge with a refused graph.
    declarations = []

    def capture(declaration):
        declarations.append(declaration)
        from chisurf.core.fitting.mcts.native import NativeSearchPreparation
        return NativeSearchPreparation(declaration.capability_id)

    monkeypatch.setattr(
        "chisurf.core.fitting.mcts.tcspc_lifetime.prepare_native_model_search", capture
    )
    prepare_tcspc_lifetime_search(fit)
    declaration = declarations[0]
    before = _state(fit)
    calls = []

    def no_graph(*args, **kwargs):
        calls.append((args, kwargs))
        return None

    monkeypatch.setattr("chisurf.core.fitting.minimizer.graph_objective", no_graph)
    prepared = prepare_native_model_search(declaration)

    assert len(calls) == 1
    assert not prepared.supported
    assert prepared.reasons[0].code == "native_objective_unrepresentable"
    assert _state(fit) == before
