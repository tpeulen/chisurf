"""Execution boundary for BFF-native fitting model search.

Capabilities describe a search problem and the GUI decides whether to accept
its winner.  This module owns the operation between those two points: it
configures and runs :class:`IMP.bff.ModelSearch`, including cooperative
cancellation.  It deliberately has no optimizer, score, or model-specific
fallback of its own.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NativeSearchSettings:
    """User-facing controls mapped directly onto ``bff.ModelSearchConfig``."""

    simulations: int = 400
    c_puct: float = 1.4
    reward_scale: float = 1.0
    dirichlet_alpha: float = 0.3
    dirichlet_fraction: float = 0.0
    seed: int = 7
    # The move policy weighting PUCT's priors: ``"shipped"`` is the
    # family-agnostic network bff ships, ``""`` (or ``b""``) searches on the
    # declared priors alone, and ``bytes`` are a ``bff.neural_net`` document
    # in msgpack, bff's network format.
    action_policy: str | bytes = "shipped"


def configure_action_space(problem: Any, search_fit_settings: bool) -> bool:
    """Search structures only, or structures and how each one is fitted.

    With ``search_fit_settings`` bff's fit-settings action space is switched
    on: a state is a structure fitted one particular way (optimiser
    tolerances, evaluation budget, start values, step bound), and a move may
    refit the same structure another way. Both are scored by the same reward,
    so a different way of fitting only wins by fitting better. Without it the
    problem is put back to structures only, which a live model needs because
    it keeps its problem between searches.

    Parameters
    ----------
    problem : IMP.bff.FittingModelSearchProblem
        The problem a search is about to run on.
    search_fit_settings : bool
        Whether to search fit settings too.

    Returns
    -------
    bool
        Whether the problem now searches what was asked; ``False`` when this
        bff build has no fit-settings action space and it was asked for.
    """
    import IMP.bff as bff

    if not hasattr(problem, "set_action_space"):
        return not search_fit_settings
    if search_fit_settings:
        problem.add_default_fit_settings_candidates()
        problem.set_action_space(bff.ACTION_SPACE_FIT_SETTINGS)
    elif problem.get_action_space() != bff.ACTION_SPACE_STRUCTURE:
        problem.set_action_space(bff.ACTION_SPACE_STRUCTURE)
    return True


def search_outcome(result: Any) -> tuple[str, tuple[str, ...]]:
    """How a search ended, and what it asks to be measured.

    Parameters
    ----------
    result : IMP.bff.ModelSearchResult
        A finished search.

    Returns
    -------
    tuple
        ``(outcome, missing)``: ``outcome`` is ``"selected"``,
        ``"request_information"`` or ``"cancelled"``; ``missing`` names the
        measurements a ``request_information`` outcome needs.
    """
    if hasattr(result, "get_outcome"):
        return str(result.get_outcome()), tuple(str(m) for m in result.get_missing_observables())
    return ("cancelled" if result.get_cancelled() else "selected"), ()


def run_native_search(
    problem: Any,
    settings: NativeSearchSettings,
    *,
    should_cancel: Callable[[], bool] | None = None,
) -> Any:
    """Run one already-prepared search entirely in BFF.

    ``ModelSearch.run`` is a blocking native call.  A tiny monitor forwards the
    task framework's cancellation flag to BFF's native cancellation flag; it
    never evaluates a candidate or touches the fitting model.
    """
    import IMP.bff as bff

    config = bff.ModelSearchConfig()
    config.set_number_of_simulations(max(1, int(settings.simulations)))
    config.set_c_puct(float(settings.c_puct))
    config.set_reward_scale(float(settings.reward_scale))
    config.set_dirichlet_alpha(float(settings.dirichlet_alpha))
    config.set_dirichlet_fraction(float(settings.dirichlet_fraction))
    config.set_seed(max(0, int(settings.seed)))

    search = bff.ModelSearch(problem)
    policy = settings.action_policy
    if policy == "shipped":
        # Only a fitting problem has residuals for a policy to read; a
        # pre-scored one searches on its declared priors.
        policy = bff.get_shipped_action_policy() if hasattr(problem, "set_action_policy") else ""
    if policy:
        problem.set_action_policy(policy)
    search.set_config(config)
    if should_cancel is None:
        return search.run()
    if should_cancel():
        search.request_cancel()
        return search.run()

    stopped = threading.Event()

    def forward_cancellation() -> None:
        while not stopped.wait(0.025):
            if should_cancel():
                search.request_cancel()
                return

    monitor = threading.Thread(
        target=forward_cancellation,
        name="chisurf-bff-search-cancellation",
        daemon=True,
    )
    monitor.start()
    try:
        return search.run()
    finally:
        stopped.set()
        monitor.join(timeout=0.1)
