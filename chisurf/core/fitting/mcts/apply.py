"""Bridge between a live ChiSurf fit and the MCTS model selector.

The search itself never touches the GUI's fit object — it runs on a private
fit built from the same data by the existing
:func:`~chisurf.core.fluorescence.decay_fit_model.build_lifetime_fit`, so it
is safe to run off the GUI thread. This module extracts that private
environment from a live fit and transfers the winning state back: parameter
values, the fix/free mask, everything the user would have set by hand.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Tuple

import numpy as np

from chisurf.core.fitting.mcts.environment import EnvConfig, FitEnv, FitState

logger = logging.getLogger(__name__)


def fit_is_tcspc(fit: Any) -> bool:
    """Whether a fit carries the lifetime-model groups MCTS can drive.

    Anything without ``convolve``, ``generic`` and ``lifetimes`` groups (an
    FCS fit, a PDA fit, …) is not something the TCSPC selector applies to.
    """
    model = getattr(fit, "model", None)
    return all(
        getattr(model, name, None) is not None
        for name in ("convolve", "generic", "lifetimes")
    )


def environment_from_fit(
    fit: Any,
    config: Optional[EnvConfig] = None,
    donor_reference: Optional[Any] = None,
) -> FitEnv:
    """The model-selection environment *on the user's own fit*.

    No private copy is built and nothing is transferred afterwards — the
    environment mutates the user's model (its fix/free mask), refines with
    the fit's own ``run()``, and the search's final
    :meth:`~chisurf.core.fitting.mcts.environment.FitEnv.apply_best` leaves
    the user's fit in the winning state. A FRET model yields the
    :class:`~chisurf.core.fitting.mcts.environment.FretEnv`; its donor
    reference is the user's linked fit, a fit supplied via
    ``donor_reference``, or — when neither exists — asked for through the
    caller's message box (see :class:`~chisurf.core.fitting.mcts.
    environment.AgentQuestion`).
    """
    from chisurf.core.fitting.mcts.environment import (
        FretEnv, FretEnvConfig, N_TOGGLE_SLOTS,
    )

    if getattr(fit.model, "fret_parameters", None) is not None:
        fret_config = config if isinstance(config, FretEnvConfig) else FretEnvConfig(
            max_components=config.max_components if config else 4,
            obs_length=config.obs_length if config else 128,
        )
        return FretEnv(fit=fit, donor_fit=donor_reference, config=fret_config)
    return FitEnv(fit=fit, config=config)


def transfer_state_to_fit(
    state: FitState,
    fit: Any,
    config: Optional[EnvConfig] = None,
) -> None:
    """Write a searched state (values + fix/free mask) into a live fit.

    For a FRET model this also aligns the Gaussian states (mean, sigma,
    amplitude per active state; the rest fixed at zero amplitude) and the
    FRET nuisance parameters (``xDOnly``, ``tauD0``).
    """
    from chisurf.core.fitting.mcts.environment import FretEnvConfig

    config = config if config is not None else EnvConfig()
    model = fit.model
    lifetimes = model.lifetimes
    lo, hi = config.tau_bounds

    while len(lifetimes) < len(state.structure.active):
        lifetimes.append(lower_bound_lifetime=lo, upper_bound_lifetime=hi)

    active = list(state.structure.active)
    while len(active) < len(lifetimes):
        active.append(False)
    k = 0
    for i, (tau_p, amp_p) in enumerate(
        zip(lifetimes._lifetimes, lifetimes._amplitudes)
    ):
        if active[i]:
            tau_p.value = float(np.clip(state.lifetimes[k], lo, hi))
            amp_p.value = float(state.amplitudes[k])
            tau_p.fixed = False
            amp_p.fixed = False
            k += 1
        else:
            amp_p.value = 0.0
            tau_p.fixed = True
            amp_p.fixed = True

    ts = model.convolve._ts
    sc = model.generic._sc
    bg = model.generic._bg
    # A search that leaves the shift "off" has no opinion about it — the
    # user's current colour shift survives untouched.
    original_ts = float(ts.value)
    ts.value = float(state.irf_shift) if state.structure.fit_irf_shift else original_ts
    ts.fixed = not state.structure.fit_irf_shift
    sc.value = float(state.scatter) if state.structure.fit_scatter else 0.0
    sc.fixed = not state.structure.fit_scatter
    bg.value = float(state.background) if state.structure.fit_background else 0.0
    bg.fixed = not state.structure.fit_background

    if getattr(model, "fret_parameters", None) is not None and state.distances.size:
        gaussians = model.gaussians
        r_lo, r_hi = ((config.distance_bounds if isinstance(config, FretEnvConfig)
                       else (10.0, 120.0)))
        while len(gaussians) < len(state.structure.fret_states):
            gaussians.append(50.0, 6.0, 1.0 / max(len(gaussians), 1))
        j = 0
        for mean_p, sigma_p, amp_p in zip(
            gaussians._gaussianMeans, gaussians._gaussianSigma,
            gaussians._gaussianAmplitudes,
        ):
            if j < len(state.structure.fret_states) and state.structure.fret_states[j]:
                mean_p.value = float(np.clip(state.distances[j], r_lo, r_hi))
                sigma_p.value = float(state.sigmas[j])
                amp_p.value = float(state.fractions[j])
                mean_p.fixed = False
                amp_p.fixed = False
                sigma_p.fixed = not state.structure.fit_state_width
                j += 1
            else:
                amp_p.value = 0.0
                mean_p.fixed = True
                amp_p.fixed = True
                sigma_p.fixed = True
        fp = model.fret_parameters
        fp._xDonly.value = float(state.donor_only_fraction) \
            if state.structure.fit_donor_only else 0.0
        fp._xDonly.fixed = not state.structure.fit_donor_only

    # The generic registry decisions reach the live fit too: a parameter the
    # search freed (or pinned) is addressed by name through the same
    # discovery the environment used, so slot i means the same thing.
    if state.toggle_names:
        from chisurf.core.fitting.mcts.environment import nuisance_registry_for_model

        target = {
            name: p for name, p in nuisance_registry_for_model(
                model, model.lifetimes, tuple(config.frozen_parameters),
            )
        }
        for name, value, free in zip(
                state.toggle_names, state.toggle_values, state.toggles):
            parameter = target.get(name)
            if parameter is None:
                continue
            parameter.value = float(value)
            parameter.fixed = not free

    try:
        model.find_parameters()
    except Exception:  # pragma: no cover - defensive
        logger.exception("parameter discovery failed after transferring MCTS state")
    try:
        model.update()
        if hasattr(fit, "update"):
            fit.update()
    except Exception:
        logger.exception("model update failed after transferring MCTS state")
