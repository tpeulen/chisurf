"""Hyperparameter optimisation of the burst-MLE settings (the wizard's "Opt"), Qt-free.

The tunables are the settings that shape how the IRF and the decay meet: the integer and sub-bin shifts of the
perpendicular IRF, the IRF window and the IRF thresholds. Each trial writes the settings, refits the current decay
and is scored by its fit quality 2I* (1 for a decay the model describes; a diverged fit, 2I* < 0, never wins). The
search is a Latin-hypercube exploration (70 % of the budget) followed by a coordinate line search around the best
trial. The starting configuration is the first trial, so the result is never worse than what the user had.

The fit window is *not* searched unless the caller passes bounds for ``micro_time_start`` / ``micro_time_stop``: a
narrower window leaves out the bins the model describes badly, which lowers 2I* without improving the fit.
"""

from __future__ import annotations

import copy
from typing import Any, Callable

import numpy as np

#: Tunable -> kind.
TUNABLES: dict[str, str] = {
    "shift": "int",
    "shift_sp": "float",
    "shift_ss": "float",
    "irf_start": "int",
    "irf_stop": "int",
    "irf_threshold_vv": "float",
    "irf_threshold_vh": "float",
}


def default_bounds(session: Any) -> dict[str, tuple[float, float, str]]:
    """Search ranges around the current settings, clamped to the binned histogram."""
    s = session.settings
    irf = session.irf_np.get(session.current_detector)
    n_bins = max(4, int(np.asarray(irf).size // 2)) if irf is not None else 64
    peak = 0
    if irf is not None and np.asarray(irf).size:
        half = np.asarray(irf, dtype=float)[: n_bins]
        peak = int(np.argmax(half))
    start_cur = int(s.irf_start)
    stop_cur = int(s.irf_stop)
    start = (0, max(0, peak)) if start_cur < 0 else (max(0, start_cur - 10), min(n_bins - 2, start_cur + 10))
    stop = (min(n_bins - 1, peak + 1), n_bins - 1) if stop_cur < 0 else (max(1, stop_cur - 10), min(n_bins - 1, stop_cur + 10))
    shift = int(s.shift)
    return {
        "shift": (shift - 5, shift + 5, "int"),
        "shift_sp": (-0.9, 0.9, "float"),
        "shift_ss": (-5.0, 5.0, "float"),
        "irf_start": (*start, "int"),
        "irf_stop": (*stop, "int"),
        "irf_threshold_vv": (0.0, 0.5, "float"),
        "irf_threshold_vh": (0.0, 0.5, "float"),
    }


def _apply(session: Any, cfg: dict) -> None:
    for key, value in cfg.items():
        kind = TUNABLES.get(key) or ("int" if key.startswith("micro_time") else "float")
        setattr(session.settings, key, int(round(value)) if kind == "int" else float(value))
    if "micro_time_start" in cfg or "micro_time_stop" in cfg:
        session.build_decay()


def _loss(session: Any) -> float:
    outcome = session.fit()
    if outcome is None:
        return float("inf")
    value = float(outcome.two_istar)
    return value if np.isfinite(value) and value >= 0.0 else float("inf")


def optimize_hyperparameters(
    session: Any,
    n_iter: int = 40,
    *,
    bounds: dict | None = None,
    seed: int | None = 0,
    should_stop: Callable[[], bool] | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> dict:
    """Search the tunables for the lowest 2I* of the current decay and apply the best configuration.

    Parameters
    ----------
    session : MleSession
        Session with a decay, IRF and background for its current detector.
    n_iter : int
        Number of fits (the budget).
    bounds : dict, optional
        ``{name: (low, high, "int"|"float")}`` overrides of :func:`default_bounds`.
    seed : int, optional
        Seed of the Latin-hypercube exploration.
    should_stop : callable, optional
        Returns True to stop; the settings are then restored to what they were.
    progress : callable, optional
        Called with ``(fits done, budget)``.

    Returns
    -------
    dict
        ``config`` (applied), ``loss`` (its 2I*), ``start_loss`` (2I* before), ``evaluations`` and ``stopped``.
    """
    reason = session.blocked_reason()
    if reason is not None:
        raise ValueError(f"Cannot optimise: {reason}")
    entry = copy.deepcopy(session.settings)
    use = {**default_bounds(session), **(bounds or {})}
    for key, (lo, hi, kind) in list(use.items()):
        lo, hi = float(min(lo, hi)), float(max(lo, hi))
        use[key] = (int(np.floor(lo)), int(np.ceil(hi)), kind) if kind == "int" else (lo, hi, kind)
    keys = list(use)
    budget = max(1, int(n_iter))
    rng = np.random.default_rng(seed)

    def constrain(cfg: dict) -> dict:
        out = {}
        for k in keys:
            lo, hi, kind = use[k]
            v = min(hi, max(lo, cfg[k]))
            out[k] = int(round(v)) if kind == "int" else float(v)
        for a, b in (("micro_time_start", "micro_time_stop"), ("irf_start", "irf_stop")):
            if a in out and b in out and out[b] <= out[a]:
                out[b] = min(use[b][1], out[a] + 1)
                if out[b] <= out[a]:
                    out[a] = max(use[a][0], out[b] - 1)
        return out

    cache: dict[tuple, float] = {}
    best = {"cfg": None, "loss": float("inf")}
    state = {"stopped": False}

    def evaluate(cfg: dict) -> float:
        cfg = constrain(cfg)
        key = tuple(round(float(cfg[k]), 6) for k in keys)
        if key in cache:
            return cache[key]
        if should_stop is not None and should_stop():
            state["stopped"] = True
            return float("inf")
        _apply(session, cfg)
        value = _loss(session)
        cache[key] = value
        if value < best["loss"]:
            best["cfg"], best["loss"] = cfg, value
        if progress is not None:
            progress(min(len(cache), budget), budget)
        return value

    start_cfg = {}
    for k in keys:
        current = getattr(entry, k)
        if k in ("irf_start", "irf_stop") and int(current) < 0:  # unset: no clip is the n_bins edge
            current = use[k][0] if k == "irf_start" else use[k][1]
        start_cfg[k] = current
    start_loss = evaluate(start_cfg)
    explore = min(budget, max(8, int(0.7 * budget))) - 1
    strata = (np.arange(max(explore, 0)) + rng.random(max(explore, 0))) / max(explore, 1)
    grid = np.zeros((max(explore, 0), len(keys)))
    for j in range(len(keys)):
        grid[:, j] = rng.permutation(strata)
    for row in grid:
        if state["stopped"] or len(cache) >= budget:
            break
        cfg = {}
        for j, k in enumerate(keys):
            lo, hi, kind = use[k]
            cfg[k] = lo + int(np.floor(row[j] * (hi - lo + 1))) if kind == "int" else lo + row[j] * (hi - lo)
        evaluate(cfg)
    step = {k: 1 if use[k][2] == "int" else 0.25 * (use[k][1] - use[k][0]) for k in keys}
    quiet = 0
    while best["cfg"] is not None and not state["stopped"] and len(cache) < budget and quiet < 3:
        improved = False
        for k in keys:
            for sign in (-1, 1):
                if state["stopped"] or len(cache) >= budget:
                    break
                before = best["loss"]
                trial = dict(best["cfg"])
                trial[k] = trial[k] + sign * step[k]
                evaluate(trial)
                improved |= best["loss"] < before
        if not improved:
            quiet += 1
            for k in keys:
                step[k] = max(1, step[k] // 2) if use[k][2] == "int" else step[k] * 0.5
        else:
            quiet = 0
    if state["stopped"] or best["cfg"] is None:
        session.det_settings[session.current_detector] = entry
        session.fit()
        if not state["stopped"]:
            raise ValueError("No valid configuration: every trial diverged; settings restored.")
        return {"config": None, "loss": float("nan"), "start_loss": start_loss,
                "evaluations": len(cache), "stopped": True}
    _apply(session, best["cfg"])
    session.fit()
    return {"config": best["cfg"], "loss": best["loss"], "start_loss": start_loss,
            "evaluations": len(cache), "stopped": False}
