"""Contracts for the BFF-only model-search execution boundary."""

from __future__ import annotations

import threading

import pytest

# The execution boundary is BFF-only by design, so there is nothing here to
# test without it.  Skip rather than error at collection.
bff = pytest.importorskip("IMP.bff")

from chisurf.core.fitting.mcts.execution import (
    NativeSearchSettings,
    configure_action_space,
    run_native_search,
    search_outcome,
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


class _PolicyProblem:
    configured = None

    def set_action_policy(self, network):
        self.configured = network


class _EchoSearch:
    def __init__(self, problem):
        self.problem = problem

    def set_config(self, config):
        self.config = config

    def run(self):
        return self.problem.configured


def test_an_explicit_policy_is_forwarded_to_the_native_problem(monkeypatch):
    monkeypatch.setattr(bff, "ModelSearch", _EchoSearch)
    result = run_native_search(
        _PolicyProblem(), NativeSearchSettings(action_policy=b"native-policy")
    )
    assert result == b"native-policy"


def test_the_shipped_policy_is_the_default_and_none_means_declared_priors(monkeypatch):
    monkeypatch.setattr(bff, "ModelSearch", _EchoSearch)
    monkeypatch.setattr(bff, "get_shipped_action_policy", lambda: b"shipped")
    assert run_native_search(_PolicyProblem(), NativeSearchSettings()) == b"shipped"
    assert run_native_search(_PolicyProblem(), NativeSearchSettings(action_policy="")) is None


class _SpaceProblem:
    """A fitting problem as far as the action space is concerned."""

    def __init__(self):
        self.space = 0
        self.candidates = 0

    def set_action_space(self, space):
        self.space = space

    def get_action_space(self):
        return self.space

    def add_default_fit_settings_candidates(self):
        self.candidates += 1


@pytest.mark.skipif(
    not hasattr(bff, "ACTION_SPACE_FIT_SETTINGS"),
    reason="this IMP.bff has no fit-settings action space",
)
def test_the_action_space_follows_the_flag_every_time():
    problem = _SpaceProblem()
    assert configure_action_space(problem, True)
    assert problem.space == bff.ACTION_SPACE_FIT_SETTINGS and problem.candidates == 1
    # A live model keeps its problem between searches: off puts it back.
    assert configure_action_space(problem, False)
    assert problem.space == bff.ACTION_SPACE_STRUCTURE


def test_a_problem_without_fit_settings_refuses_only_when_asked():
    assert configure_action_space(_problem(), False)
    assert not configure_action_space(_problem(), True)


def test_the_outcome_of_a_search():
    result = run_native_search(_problem(), NativeSearchSettings(simulations=5))
    assert search_outcome(result) == ("selected", ())
