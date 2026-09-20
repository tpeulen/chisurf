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
    # Optional BFF-native policy.  The network sees the fitted, weighted
    # residual profile at each tree expansion; action keys name its outputs.
    residual_action_policy: str = ""
    residual_action_keys: tuple[str, ...] = ()


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
    if settings.residual_action_policy:
        configure_policy = getattr(problem, "set_residual_action_policy", None)
        if not callable(configure_policy):
            raise RuntimeError("this BFF model-search problem has no residual policy API")
        configure_policy(settings.residual_action_policy, list(settings.residual_action_keys))
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
