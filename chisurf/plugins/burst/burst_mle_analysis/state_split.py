"""Burst MLE split by H2MM state, without a toolkit: the per-state global fit and its seeding of the burst fits.

A burst analysed by H2MM carries one state per photon. Splitting the burst-MLE fit by state widens each burst's row
(``Tau S0 (green)`` beside ``Tau (green)``, see :func:`.engine.state_result_columns`) and adds one global fit per
``(detector, state)``: the decay of every photon the measurement assigned to that state, pooled over all bursts. That
pooled lifetime is the number to quote (one burst's state holds tens of photons) and the start value of every
per-burst fit of the state.

These functions were methods of the Qt ``MLELifetimeAnalysisWizard``; the wizard and the Qt-free
:class:`.engine.MleSession` both call them now, so the two give the same numbers.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

import numpy as np

from chisurf.core.datastore import store_from_rows, write_csv_table

logger = logging.getLogger(__name__)


def load_state_arrays(
    analysis_dir: Path | None, tttrs: dict[str, Any]
) -> tuple[dict[str, np.ndarray], int, str]:
    """Per-photon H2MM states of the loaded measurements.

    Returns ``({stem: int8 array}, n_states, message)``; ``({}, 0, reason)`` when the folder has no usable H2MM run,
    so a missing upstream analysis turns the split off rather than failing the batch.
    """
    from chisurf.core.fio.fluorescence import burst_states

    if analysis_dir is None:
        return {}, 0, "Split by state: no analysis folder - skipped."
    sizes = {}
    for stem, tttr in (tttrs or {}).items():
        try:
            sizes[str(stem)] = int(np.asarray(tttr.routing_channels).size)
        except Exception:  # noqa: BLE001 - an unreadable file has no states; the rest still do
            continue
    try:
        arrays, n_states = burst_states.state_arrays(analysis_dir, sizes)
    except (FileNotFoundError, ValueError) as exc:
        return {}, 0, f"Split by state: {exc}"
    if n_states < 1:
        return {}, 0, "Split by state: the H2MM run resolved no states."
    labelled = sum(int((a >= 0).sum()) for a in arrays.values())
    return (
        arrays,
        int(n_states),
        f"Split by state: {n_states} states, {labelled:,} photons labelled.",
    )


def pool_state_decays(
    jobs: list,
    det_order: list[str],
    ctx: Any,
    max_workers: int,
    *,
    should_stop: Callable[[], bool] | None = None,
    on_file: Callable[[int, int], None] | None = None,
) -> dict[str, np.ndarray]:
    """Sum every burst's photons into one decay per ``(detector, state)``, over every file.

    Runs the binning-only pass of :func:`._mp_worker.pool_states_worker` over the same jobs (and the same shared
    memory) the fit pass uses. *should_stop* is read between files; *on_file(done, total)* reports progress.

    Returns ``{detector: ndarray(n_states, 2, half_len)}``, empty when there is nothing to pool or it was stopped.
    """
    from concurrent.futures import ProcessPoolExecutor, as_completed

    from ._mp_worker import pool_states_worker

    pool_jobs = [
        (
            bursts,
            rc_name,
            rc_shape,
            rc_dtype,
            mt_name,
            mt_shape,
            mt_dtype,
            det_order,
            perdet_cfg,
            state_info,
        )
        for (
            _fname,
            bursts,
            rc_name,
            rc_shape,
            rc_dtype,
            mt_name,
            mt_shape,
            mt_dtype,
            _det_order,
            perdet_cfg,
            _shift,
            state_info,
        ) in jobs
    ]
    totals: dict[str, np.ndarray] = {}
    done = 0
    with ProcessPoolExecutor(max_workers=max_workers, mp_context=ctx) as ex:
        futures = [ex.submit(pool_states_worker, j) for j in pool_jobs]
        for fut in as_completed(futures):
            # Read the stop *here*: after the loop it is read once every future has been joined.
            if should_stop is not None and should_stop():
                for pending in futures:
                    pending.cancel()
                return {}
            try:
                part = fut.result()
            except Exception as exc:  # noqa: BLE001 - one unreadable file must not cost the pooled fit
                logger.warning("Pooled state decays: a file failed (%s)", exc)
                part = None
            for det, arr in (part or {}).items():
                if det in totals:
                    totals[det] += arr
                else:
                    totals[det] = np.asarray(arr, dtype=np.int64).copy()
            done += 1
            if on_file is not None:
                on_file(done, len(pool_jobs))
    return totals


def fit_pooled_state_decays(
    pooled: dict, det_order: list[str], perdet_cfg: dict, shift: int
) -> dict:
    """Fit each pooled ``(detector, state)`` decay: the state's global lifetime.

    The window and the perpendicular-channel shift are applied here, once, to the sum rather than per burst: both are
    linear, so the result is identical and the pass that produced the sum stays a plain bin count.

    Returns ``{detector: {state: {"x": ndarray, "two_istar": float, "cp": int, "cs": int}}}``; a state below the
    detector's photon floor is recorded with ``x=None`` rather than dropped, so the table says which state could not
    be fitted.
    """
    from ._mp_worker import _build_fitter, _copy_shifted

    out: dict[str, dict[int, dict]] = {}
    do_shift = int(shift or 0)
    for det in det_order:
        arr = pooled.get(det)
        cfg = perdet_cfg.get(det)
        if arr is None or cfg is None:
            continue
        n = int(cfg["half_len"])
        s0 = max(0, int(cfg["sb"]))
        s1 = min(n, int(cfg["eb"]))
        fitter = _build_fitter(cfg)
        per_state: dict[int, dict] = {}
        for state in range(arr.shape[0]):
            cp = np.asarray(arr[state, 0], dtype=np.uint32)
            cs_ = np.asarray(arr[state, 1], dtype=np.uint32)
            cp_sum, cs_sum = int(cp.sum()), int(cs_.sum())
            entry = {"x": None, "two_istar": float("nan"), "cp": cp_sum, "cs": cs_sum}
            if (cp_sum + cs_sum) < int(cfg["min_photons"]) or s1 <= s0:
                per_state[state] = entry
                continue
            d = np.zeros(2 * n, dtype=np.float64)
            d[s0:s1] = cp[s0:s1]
            if do_shift:
                _copy_shifted(cs_, d, n, s0, s1, do_shift, n)
            else:
                d[n + s0 : n + s1] = cs_[s0:s1]
            try:
                res = fitter(data=d, initial_values=cfg["x0"], fixed=cfg["fixed"])
            except Exception as exc:  # noqa: BLE001 - recorded as unfitted
                logger.warning("Pooled fit failed for %s state %s: %s", det, state, exc)
                per_state[state] = entry
                continue
            entry["x"] = np.asarray(res.x, dtype=np.float64)
            entry["two_istar"] = float(res.twoIstar)
            per_state[state] = entry
        out[det] = per_state
    return out


def state_lifetime_rows(fits: dict, model: str, param_names) -> list[dict]:
    """The pooled per-state fits as plain rows, one per ``(detector, state)``."""
    rows: list[dict] = []
    for det, per_state in fits.items():
        for state in sorted(per_state):
            entry = per_state[state]
            x = entry["x"]

            def g(i, x=x):
                try:
                    return float(x[i])
                except (TypeError, IndexError):
                    return float("nan")

            row = {
                "Detector": det,
                "Colour": det.lower(),
                "State": int(state),
                "Photons (parallel)": entry["cp"],
                "Photons (perpendicular)": entry["cs"],
                "Photons": entry["cp"] + entry["cs"],
                "Tau": g(0),
                "2I*": entry["two_istar"],
            }
            if model == "fit23":
                row["gamma"] = g(1)
                row["r0"] = g(2)
                row["rho"] = g(3)
            else:
                for i, nm in enumerate(param_names or ()):
                    row[nm] = g(i)
            rows.append(row)
    return rows


def seed_state_fits(jobs: list, fits: dict) -> int:
    """Write each state's pooled lifetime into the jobs as the start value of that state's burst fits.

    Returns the largest number of states seeded for one detector.
    """
    seeded = 0
    for job in jobs:
        cfgs = job[9]
        for det, per_state in fits.items():
            cfg = cfgs.get(det)
            if cfg is None:
                continue
            seeds = {}
            for state, entry in per_state.items():
                x = entry["x"]
                if x is None or not np.isfinite(x[0]) or float(x[0]) <= 0.0:
                    continue  # nothing was fitted; leave the panel's guess
                start = np.asarray(cfg["x0"], dtype=np.float64).copy()
                start[0] = float(x[0])
                seeds[int(state)] = start
            if seeds:
                cfg["state_x0"] = seeds
                seeded = max(seeded, len(seeds))
    return seeded


def pooled_state_fits(
    jobs: list,
    det_order: list[str],
    ctx: Any,
    max_workers: int,
    model: str,
    param_names,
    shift: int,
    *,
    should_stop: Callable[[], bool] | None = None,
    on_file: Callable[[int, int], None] | None = None,
) -> tuple[list[dict], int, str]:
    """Pool, fit and seed: the whole global-lifetime step. Returns ``(rows, seeded, status message)``."""
    pooled = pool_state_decays(
        jobs, det_order, ctx, max_workers, should_stop=should_stop, on_file=on_file
    )
    if not pooled:
        return [], 0, "Pooled state lifetimes: nothing to pool."
    # Every job carries the same per-detector configuration; a file without its raw measurement carries an empty one
    # and can be first, so take the first real one.
    shared_cfg = next((j[9] for j in jobs if j[9]), {})
    fits = fit_pooled_state_decays(pooled, det_order, shared_cfg, shift)
    rows = state_lifetime_rows(fits, model, param_names)
    seeded = seed_state_fits(jobs, fits)
    taus = ", ".join(
        f"S{r['State']} {r['Colour']} {r['Tau']:.2f} ns" for r in rows if np.isfinite(r["Tau"])
    )
    message = (
        f"Pooled state lifetimes ({seeded} seeded): {taus}"
        if taus
        else "Pooled state lifetimes: none could be fitted."
    )
    return rows, seeded, message


def write_state_lifetimes(rows: list[dict], analysis_dirs) -> list[Path]:
    """Write the pooled per-state lifetimes to ``<analysis>/Info/state_lifetimes.csv`` for each analysis folder.

    Beside the analysis, not as a companion: a companion carries one row per burst and is merged by position, this
    table has one row per state.
    """
    if not rows:
        return []
    written: list[Path] = []
    for root in sorted({Path(r) for r in analysis_dirs}):
        info = root / "Info"
        try:
            info.mkdir(parents=True, exist_ok=True)
            target = info / "state_lifetimes.csv"
            write_csv_table(target, store_from_rows(rows), delimiter=",")
        except OSError as exc:
            logger.warning("Could not write %s: %s", info, exc)
            continue
        written.append(target)
    return written


__all__ = [
    "fit_pooled_state_decays",
    "load_state_arrays",
    "pool_state_decays",
    "pooled_state_fits",
    "seed_state_fits",
    "state_lifetime_rows",
    "write_state_lifetimes",
]
