"""Native model-search composition for global and heterogeneous fits."""

from __future__ import annotations

import numpy as np
import pytest

import chisurf.core.data
import chisurf.core.fitting.fit
import chisurf.core.models.parse
from chisurf.core.fitting.mcts.global_fit import prepare_global_model_search
from chisurf.core.fitting.mcts.native import (
    NativeAction,
    NativeParameterGroup,
    NativeScore,
    NativeSearchDeclaration,
    NativeStructure,
    unsupported,
)

N = 48
SIGMA = 0.02


def _group(*, bad_second: bool = False):
    rng = np.random.default_rng(14)
    x = np.linspace(0.1, 8.0, N)
    curves = []
    for amplitude in (2.0, 5.0):
        y = amplitude * np.exp(-x / 3.0) + rng.normal(0.0, SIGMA, N)
        curves.append(
            chisurf.core.data.DataCurve(
                x=x, y=y, ey=np.full(N, SIGMA), name=f"a={amplitude}"
            )
        )
    fit = chisurf.core.fitting.fit.FitGroup(
        data=chisurf.core.data.DataGroup(curves),
        model_class=chisurf.core.models.parse.ParseModel,
    )
    for member in fit:
        member.xmin, member.xmax = 0, N - 1
        member.mask = None
        member.model.func = "a*exp(-x/t)"
        member.model.find_parameters()
        member.model.parameters_all_dict["a"].value = 1.0
        member.model.parameters_all_dict["t"].value = 1.0
    owner = fit[0].model.parameters_all_dict["t"]
    fit[1].model.parameters_all_dict["t"].link = owner
    for member in fit:
        member.model.find_parameters()
    fit._model.find_parameters()
    if bad_second:
        fit[1].model._expression = None
    return fit


def _declaration(member):
    parameters = member.model.parameters_all_dict
    amplitude = parameters["a"]
    lifetime = parameters["t"]
    return NativeSearchDeclaration(
        capability_id="test.parse.exponential.v1",
        fit=member,
        objective_model=member.model,
        live_parameters=tuple(member.model.parameters_all),
        groups=(
            NativeParameterGroup("amplitude", (amplitude,)),
            # Deliberately retain the follower in the member declaration. The
            # global composer must replace it by the owner and declare one port.
            NativeParameterGroup("lifetime", (lifetime,), (2.0,), (1.0,)),
        ),
        structures=(
            NativeStructure("fixed-lifetime", ("amplitude",)),
            NativeStructure("free-lifetime", ("amplitude", "lifetime")),
        ),
        actions=(
            NativeAction(
                "fixed-lifetime", "release-lifetime", "free-lifetime"
            ),
            NativeAction("fixed-lifetime", "terminate", "fixed-lifetime", terminal=True),
            NativeAction("free-lifetime", "terminate", "free-lifetime", terminal=True),
        ),
        initial_structure="fixed-lifetime",
        score=NativeScore(complexity_penalty=0.01),
    )


def _live_state(fit):
    def stable_value(parameter):
        value = float(parameter.value)
        return None if np.isnan(value) else value

    return tuple(
        (stable_value(parameter), bool(parameter.fixed), parameter.link)
        for parameter in fit._model.parameters_all
    )


def test_global_search_uses_one_joint_problem_and_one_shared_owner_port():
    import IMP.bff as bff

    fit = _group()
    before = _live_state(fit)
    prepared = prepare_global_model_search(fit, _declaration)

    assert prepared.supported, prepared.reasons
    assert _live_state(fit) == before
    keys = list(prepared.problem.get_parameter_group_keys())
    assert sum(key.startswith("shared:") for key in keys) == 1
    assert sum(key.startswith("member:") for key in keys) == 2
    assert len(prepared.binding.ports) == 3
    assert all(not port.is_linked() for port in prepared.binding.ports)

    root = prepared.problem.get_initial_state()
    moves = [
        action
        for action in prepared.problem.get_actions(root)
        if not action.get_terminal()
    ]
    # Releasing a linked structural parameter in only one member is illegal;
    # the sole move coordinates both declarations.
    assert len(moves) == 1
    assert "member-1:release-lifetime" in moves[0].get_key()
    assert "member-2:release-lifetime" in moves[0].get_key()

    config = bff.ModelSearchConfig()
    config.set_number_of_simulations(20)
    config.set_dirichlet_fraction(0.0)
    config.set_seed(9)
    search = bff.ModelSearch(prepared.problem)
    search.set_config(config)
    result = search.run()
    assert result.get_best_state().get_structure_key() == moves[0].get_predicted_state_key()
    prepared.binding.apply_state(prepared.problem, result.get_best_state())

    owner = fit[0].model.parameters_all_dict["t"]
    follower = fit[1].model.parameters_all_dict["t"]
    assert owner.value == pytest.approx(3.0, abs=0.03)
    assert follower.value == pytest.approx(owner.value)
    assert not owner.fixed
    assert follower.is_linked
    assert all(np.all(np.isfinite(member.model.y)) for member in fit)


def test_one_refused_member_refuses_the_whole_group_before_graph_build(monkeypatch):
    fit = _group()
    before = _live_state(fit)
    calls = []

    def declarer(member):
        if member is fit[1]:
            return unsupported(
                "test.unsupported", "unsupported_member", "no native equation"
            )
        return _declaration(member)

    def graph_was_called(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("a partial global objective must not be built")

    monkeypatch.setattr(
        "chisurf.core.fitting.minimizer.graph_objective", graph_was_called
    )
    prepared = prepare_global_model_search(fit, declarer)

    assert not prepared.supported
    assert prepared.reasons[0].code == "unsupported_member"
    assert prepared.reasons[0].feature == "member:2"
    assert calls == []
    assert _live_state(fit) == before


def test_unrepresentable_member_refuses_joint_objective_and_restores_live_state():
    fit = _group(bad_second=True)
    before = _live_state(fit)

    prepared = prepare_global_model_search(fit, _declaration)

    assert not prepared.supported
    assert prepared.reasons[0].code == "native_objective_unrepresentable"
    assert _live_state(fit) == before


def test_shared_initial_activity_must_match_across_members():
    fit = _group()

    def mismatched(member):
        declaration = _declaration(member)
        if member is fit[1]:
            return NativeSearchDeclaration(
                capability_id=declaration.capability_id,
                fit=declaration.fit,
                objective_model=declaration.objective_model,
                live_parameters=declaration.live_parameters,
                groups=declaration.groups,
                structures=declaration.structures,
                actions=declaration.actions,
                initial_structure="free-lifetime",
                score=declaration.score,
            )
        return declaration

    prepared = prepare_global_model_search(fit, mismatched)

    assert not prepared.supported
    assert prepared.reasons[0].code == "shared_initial_structure_mismatch"


def test_different_member_model_classes_share_one_native_joint_objective():
    import IMP.bff as bff

    class LinearMemberModel(chisurf.core.models.parse.ParseModel):
        pass

    fit = _group()
    x = np.asarray(fit[1].data.x, dtype=float)
    fit[1].data.y = 4.0 + 1.5 * x
    fit[1].data.ey = np.full(x.size, SIGMA)
    fit[1].model = LinearMemberModel(fit[1])
    fit[1].model.func = "b+c*x"
    fit[1].model.find_parameters()
    fit[1].model.parameters_all_dict["b"].value = 1.0
    fit[1].model.parameters_all_dict["c"].value = 1.0
    # This fixture checks heterogeneous composition, independently of the
    # linked-owner fixture above.
    fit[0].model.parameters_all_dict["t"].link = None
    fit._model.find_parameters()

    def fixed_structure(member):
        owners = tuple(
            parameter
            for parameter in member.model.parameters_all
            if not parameter.fixed and not parameter.is_linked
        )
        return NativeSearchDeclaration(
            capability_id=f"test.{type(member.model).__name__}.v1",
            fit=member,
            objective_model=member.model,
            live_parameters=tuple(member.model.parameters_all),
            groups=(NativeParameterGroup("user-free", owners),),
            structures=(
                NativeStructure("initialized", ("user-free",)),
                NativeStructure("refined", ("user-free",)),
            ),
            actions=(NativeAction("initialized", "refine", "refined"),),
            initial_structure="initialized",
        )

    prepared = prepare_global_model_search(fit, fixed_structure)
    assert prepared.supported, prepared.reasons

    config = bff.ModelSearchConfig()
    config.set_number_of_simulations(20)
    config.set_dirichlet_fraction(0.0)
    search = bff.ModelSearch(prepared.problem)
    search.set_config(config)
    result = search.run()
    prepared.binding.apply_state(prepared.problem, result.get_best_state())

    first = fit[0].model.parameters_all_dict
    second = fit[1].model.parameters_all_dict
    assert first["t"].value == pytest.approx(3.0, abs=0.03)
    assert second["b"].value == pytest.approx(4.0, abs=0.03)
    assert second["c"].value == pytest.approx(1.5, abs=0.03)


def test_common_dispatcher_routes_a_multi_member_fit_to_the_joint_capability():
    from chisurf.core.fitting.mcts.dispatcher import prepare_model_search

    fit = _group()
    prepared = prepare_model_search(fit)

    assert prepared.supported, prepared.reasons
    assert prepared.binding.declaration.objective_model is fit._model
    assert len(prepared.binding.ports) == 3
    assert sum(
        key.startswith("shared:")
        for key in prepared.problem.get_parameter_group_keys()
    ) == 1


def test_native_tcspc_members_are_refused_whole_until_joint_builder_supports_them():
    from chisurf.core.fitting.mcts.dispatcher import prepare_model_search
    from chisurf.core.models.description import tcspc_lifetime as LifetimeModel

    x = np.arange(32, dtype=float) * 0.05
    y = 1000.0 * np.exp(-x / 2.0) + 1.0
    curves = [
        chisurf.core.data.DataCurve(x=x, y=y, ey=np.sqrt(y)) for _ in range(2)
    ]
    fit = chisurf.core.fitting.fit.FitGroup(
        data=chisurf.core.data.DataGroup(curves), model_class=LifetimeModel
    )
    for member in fit:
        member.noise_model = "poisson"
        member.xmin, member.xmax = 0, len(x) - 1
        member.mask = None
        member.model.find_parameters()
    fit._model.find_parameters()
    before = _live_state(fit)

    prepared = prepare_model_search(fit)

    assert not prepared.supported
    assert prepared.reasons[0].code == "native_objective_unrepresentable"
    assert _live_state(fit) == before
