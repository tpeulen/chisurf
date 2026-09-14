"""Contracts for model-independent, callback-free native fit refinement."""

from __future__ import annotations

import numpy as np
import pytest

import chisurf as cs
import chisurf.core.data
import chisurf.core.fitting.fit as fitting
from chisurf.core.fitting.mcts.fixed_structure import (
    build_fixed_structure_declaration,
    prepare_fixed_structure_search,
)
from chisurf.core.fitting.mcts.native import NativeParameterGroup
from chisurf.core.models.fcs.general import GeneralFCSModel
from chisurf.core.models.fcs.parse import ParseFCSModel
from chisurf.core.models.parse import ParseModel
from chisurf.core.models.pcf.parse import ParsePCFModel
from chisurf.core.models.stopped_flow.parse import ParseStoppedFlowModel


def _parse_fit():
    x = np.linspace(0.1, 12.0, 192)
    y = 2.5 * np.exp(-x / 3.1) + 0.4
    data = cs.core.data.DataCurve(x=x, y=y, ey=np.full(x.size, 0.02))
    fit = fitting.Fit(model_class=ParseModel, data=data)
    fit.model.func = "a*exp(-x/t)+b"
    for name, value in (("a", 1.0), ("t", 1.0), ("b", 0.0)):
        fit.model.parameters_all_dict[name].value = value
    fit.xmin, fit.xmax = 0, x.size
    return fit


def _parameter_state(fit):
    def stable_value(parameter):
        value = float(parameter.value)
        return None if np.isnan(value) else value

    return tuple(
        (
            id(parameter),
            stable_value(parameter),
            bool(parameter.fixed),
            parameter.link,
            bool(getattr(parameter, "redundant", False)),
        )
        for parameter in fit.model.parameters_all
    )


def test_parse_fit_refines_entirely_on_the_native_graph_and_applies_the_winner():
    fit = _parse_fit()
    fit.model.parameters_all_dict["b"].fixed = True
    fit.model.parameters_all_dict["b"].value = 0.4
    fit.model.find_parameters()
    before = _parameter_state(fit)

    prepared = prepare_fixed_structure_search(fit)

    assert prepared.supported, prepared.reasons
    assert _parameter_state(fit) == before
    assert list(prepared.problem.get_parameter_group_keys()) == ["user-free"]
    root = prepared.problem.get_initial_state()
    actions = prepared.problem.get_actions(root)
    assert {(action.get_key(), action.get_terminal()) for action in actions} == {
        ("refine", False),
        ("terminate", True),
    }

    refined = prepared.problem.evaluate(
        root, next(action for action in actions if action.get_key() == "refine")
    )
    assert refined.get_structure_key() == "refined"
    # The initial state is scored after its own fit, so refining the same free
    # set reaches the same optimum: never worse, and not measurably better.
    assert refined.get_reward() == pytest.approx(root.get_reward(), rel=1e-9, abs=1e-9)
    prepared.binding.apply_state(prepared.problem, refined)
    assert fit.model.parameters_all_dict["a"].value == pytest.approx(2.5, rel=1e-5)
    assert fit.model.parameters_all_dict["t"].value == pytest.approx(3.1, rel=1e-5)
    assert fit.model.parameters_all_dict["b"].value == pytest.approx(0.4)
    assert fit.model.parameters_all_dict["b"].fixed


def test_declared_groups_are_preserved_and_must_cover_every_user_free_owner():
    fit = _parse_fit()
    parameters = fit.model.parameters_all_dict
    groups = (
        NativeParameterGroup("scale", (parameters["a"], parameters["b"])),
        NativeParameterGroup("shape", (parameters["t"],)),
    )

    declaration = build_fixed_structure_declaration(fit, parameter_groups=groups)

    assert declaration.groups == groups
    assert declaration.structures[0].free_groups == ("scale", "shape")

    refused = build_fixed_structure_declaration(
        fit, parameter_groups=(groups[0],)
    )
    assert not refused.supported
    assert refused.reasons[0].code == "incomplete_parameter_groups"


def test_general_fcs_mode_uses_the_same_fixed_structure_capability():
    tau = np.logspace(-4.0, 2.5, 192)
    data = cs.core.data.DataCurve(
        x=tau, y=np.ones_like(tau), ey=np.full(tau.size, 1e-3)
    )
    fit = fitting.Fit(model_class=GeneralFCSModel, data=data)
    fit.xmin, fit.xmax = 0, tau.size
    model = fit.model
    model.gauss._N.value = 2.5
    model.gauss._D.value = 150.0
    model.gauss._w_r.fixed = True
    model.gauss._w_z.fixed = True
    model.gauss._b.fixed = True
    model.find_parameters()
    model.update()
    fit.data.y = np.asarray(model.y, dtype=float).copy()
    model.gauss._N.value = 1.5
    model.gauss._D.value = 400.0
    model.find_parameters()
    before = _parameter_state(fit)

    prepared = prepare_fixed_structure_search(fit)

    assert prepared.supported, prepared.reasons
    assert _parameter_state(fit) == before
    root = prepared.problem.get_initial_state()
    refine = next(
        action
        for action in prepared.problem.get_actions(root)
        if action.get_key() == "refine"
    )
    refined = prepared.problem.evaluate(root, refine)
    # Scored after its own fit, the root already sits at the optimum.
    assert refined.get_reward() == pytest.approx(root.get_reward(), rel=1e-9, abs=1e-9)
    prepared.binding.apply_state(prepared.problem, refined)
    assert model.gauss.N == pytest.approx(2.5, rel=2e-4)
    assert model.gauss.D == pytest.approx(150.0, rel=2e-4)


@pytest.mark.parametrize("mode", ["gauss", "two_focus", "species", "mdf"])
def test_every_native_general_fcs_mode_prepares_without_changing_live_state(mode):
    tau = np.logspace(-4.0, 2.0, 64)
    data = cs.core.data.DataCurve(
        x=tau, y=np.ones_like(tau), ey=np.ones(tau.size)
    )
    fit = fitting.Fit(model_class=GeneralFCSModel, data=data)
    fit.xmin, fit.xmax = 0, tau.size
    fit.model.diffusion_mode = mode
    fit.model.find_parameters()
    before = _parameter_state(fit)

    prepared = prepare_fixed_structure_search(fit)

    assert prepared.supported, prepared.reasons
    assert _parameter_state(fit) == before


@pytest.mark.parametrize(
    "model_class", [ParseModel, ParseFCSModel, ParsePCFModel, ParseStoppedFlowModel]
)
def test_non_tcspc_parse_families_share_the_native_capability(model_class):
    x = np.linspace(0.1, 5.0, 64)
    data = cs.core.data.DataCurve(x=x, y=np.ones_like(x), ey=np.ones(x.size))
    fit = fitting.Fit(model_class=model_class, data=data)
    fit.model.func = "a*exp(-x/t)+b"
    fit.model.find_parameters()
    fit.xmin, fit.xmax = 0, x.size
    before = _parameter_state(fit)

    prepared = prepare_fixed_structure_search(fit)

    assert prepared.supported, prepared.reasons
    assert _parameter_state(fit) == before


def test_missing_native_graph_is_a_terminal_refusal_without_mutation(monkeypatch):
    fit = _parse_fit()
    before = _parameter_state(fit)
    calls = []

    def no_graph(*args, **kwargs):
        calls.append((args, kwargs))
        return None

    def forbidden_fallback(*args, **kwargs):
        raise AssertionError("the Python/director minimizer must not be invoked")

    monkeypatch.setattr("chisurf.core.fitting.minimizer.graph_objective", no_graph)
    monkeypatch.setattr("chisurf.core.fitting.minimizer.minimize", forbidden_fallback)

    prepared = prepare_fixed_structure_search(fit)

    assert len(calls) == 1
    assert not prepared.supported
    assert prepared.reasons[0].code == "native_objective_unrepresentable"
    assert _parameter_state(fit) == before
