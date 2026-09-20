"""Contracts for the BFF-only model-search execution boundary."""

from __future__ import annotations

import threading

import pytest

# The execution boundary is BFF-only by design, so there is nothing here to
# test without it.  Skip rather than error at collection.
bff = pytest.importorskip("IMP.bff")

from chisurf.core.fitting.mcts.execution import (
    NativeSearchSettings,
    run_native_search,
)


def _problem():
    problem = bff.TabularModelSearchProblem()
    problem.add_state("root", 0.0, False)
    problem.add_state("winner", 3.0, True)
    problem.set_initial_state("root")
    problem.add_action("root", "improve", "winner", 1.0)
    problem.add_action("winner", "terminate", "winner", 1.0, True)
    return problem


def test_execution_uses_native_search_and_respects_run_settings():
    result = run_native_search(
        _problem(),
        NativeSearchSettings(simulations=23, seed=41, dirichlet_fraction=0.0),
    )

    assert result.get_best_state().get_structure_key() == "winner"
    assert result.get_number_of_simulations() == 23
    assert result.get_acceptable()


def test_preexisting_cancellation_reaches_bff_before_any_candidate():
    problem = _problem()
    result = run_native_search(
        problem,
        NativeSearchSettings(simulations=23),
        should_cancel=lambda: True,
    )

    assert result.get_cancelled()
    assert result.get_number_of_simulations() == 0
    assert problem.get_number_of_evaluations() == 0


def test_cancellation_during_native_run_is_forwarded(monkeypatch):
    cancelled = threading.Event()

    class Search:
        def __init__(self, problem):
            self.problem = problem

        def set_config(self, config):
            self.config = config

        def request_cancel(self):
            cancelled.set()

        def run(self):
            assert cancelled.wait(1.0)
            return "cancelled"

    checks = iter((False, True))
    monkeypatch.setattr(bff, "ModelSearch", Search)

    result = run_native_search(
        object(),
        NativeSearchSettings(),
        should_cancel=lambda: next(checks, True),
    )

    assert result == "cancelled"
    assert cancelled.is_set()


def test_residual_policy_is_forwarded_to_the_native_problem(monkeypatch):
    class Problem:
        configured = None

        def set_residual_action_policy(self, network, action_keys):
            self.configured = (network, tuple(action_keys))

    class Search:
        def __init__(self, problem):
            self.problem = problem

        def set_config(self, config):
            self.config = config

        def run(self):
            return self.problem.configured

    monkeypatch.setattr(bff, "ModelSearch", Search)
    result = run_native_search(
        Problem(),
        NativeSearchSettings(
            residual_action_policy="native-policy-json",
            residual_action_keys=("add-component", "fit-background"),
        ),
    )

    assert result == ("native-policy-json", ("add-component", "fit-background"))
