"""The empirical-Bayes analysis loop of ebFRET's main window, without the window.

``MainWindow/run_ebayes.m`` alternates two steps for one number of states:
``run_vbayes`` fits every series' posterior against the shared prior (in
batches of 24, redrawing the plots between batches), then ``h_step``
re-estimates the prior from all posteriors and their statistics. It stops
when the summed lower bound improves by less than ``precision * |L|``, when
the iteration limit is exceeded, or when the user presses *Stop*.

Both are ported here as **generators**: they do the work in place on a
:class:`~chisurf.plugins.burst.burst_ebfret.core.model.Analysis` and yield an
event after every batch and every iteration. That is where the reference
refreshes its plots and checks the *Stop* button, so a caller -- a worker
thread, the backend service, a test -- gets the same points to redraw and to
stop at, and the loop itself knows nothing about who is watching.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence

import numpy as np

from . import hmm
from .model import Analysis

__all__ = ["run_ebayes", "run_vbayes"]


def _grow(analysis: Analysis, n_series: int) -> None:
    """Make the per-series fields of ``analysis`` at least ``n_series`` long.

    Parameters
    ----------
    analysis : Analysis
        Analysis to extend in place.
    n_series : int
        Number of series.
    """
    for name in ("posterior", "expect", "viterbi"):
        values = getattr(analysis, name)
        if len(values) < n_series:
            values.extend([None] * (n_series - len(values)))
    if analysis.lowerbound.size < n_series:
        analysis.lowerbound = np.concatenate(
            [analysis.lowerbound, np.zeros(n_series - analysis.lowerbound.size)]
        )
    if analysis.restart.size < n_series:
        analysis.restart = np.concatenate(
            [analysis.restart, np.zeros(n_series - analysis.restart.size, dtype=int)]
        )


def run_vbayes(
    analysis: Analysis,
    signals: Sequence,
    *,
    restarts: int,
    threshold: float,
    series: Sequence[int] | None = None,
    rng: np.random.Generator | None = None,
    should_stop: Callable[[], bool] = lambda: False,
    batch_size: int = 24,
    vb_threshold: float = 1e-5,
    vb_max_iter: int = 100,
) -> Iterator[list[int]]:
    """Fit the posterior of every series against the prior (``run_vbayes.m``).

    Parameters
    ----------
    analysis : Analysis
        Updated in place: ``posterior``, ``expect``, ``viterbi``,
        ``lowerbound`` and ``restart`` of each fitted series.
    signals : sequence of array_like or None
        Cropped, clipped signal per series; ``None`` or empty for an excluded
        series, which is skipped and left untouched.
    restarts : int
        The *Restarts* control.
    threshold : float
        The *Precision* control (used to pick between restarts).
    series : sequence of int, optional
        0-based series to fit; all by default.
    rng : numpy.random.Generator, optional
        Random source for restarts drawn from the prior.
    should_stop : callable
        Polled before each batch; ``True`` ends the generator early.
    batch_size : int
        Series per batch (24 in the reference).
    vb_threshold, vb_max_iter : float, int
        Per-series VBEM convergence controls (the reference uses ``vbayes``'s
        defaults).

    Yields
    ------
    list of int
        The 0-based series of each batch that were stored.

    Raises
    ------
    ValueError
        When ``analysis.prior`` is not set.
    """
    if analysis.prior is None:
        raise ValueError("the analysis has no prior; initialise it before running")
    rng = np.random.default_rng() if rng is None else rng
    n_series = len(signals)
    series = list(range(n_series)) if series is None else list(series)
    _grow(analysis, n_series)
    u = analysis.prior
    for start in range(0, len(series), batch_size):
        if should_stop():
            return
        batch = series[start : start + batch_size]
        stored = []
        for n in batch:
            x = signals[n]
            if x is None or np.size(x) == 0:
                continue
            fit = hmm.vbayes_series(
                x,
                u,
                analysis.posterior[n],
                restarts,
                threshold,
                rng,
                vb_threshold=vb_threshold,
                vb_max_iter=vb_max_iter,
            )
            analysis.posterior[n] = fit["posterior"]
            analysis.expect[n] = fit["expect"]
            analysis.viterbi[n] = fit["viterbi"]
            analysis.lowerbound[n] = fit["lowerbound"]
            analysis.restart[n] = fit["restart"]
            stored.append(n)
        yield stored


def run_ebayes(
    analysis: Analysis,
    signals: Sequence,
    *,
    restarts: int = 2,
    precision: float = 1e-3,
    max_iter: int = 100,
    rng: np.random.Generator | None = None,
    should_stop: Callable[[], bool] = lambda: False,
    vb_threshold: float = 1e-5,
    vb_max_iter: int = 100,
):
    """Empirical-Bayes iterations for one number of states (``run_ebayes.m``).

    Each iteration runs :func:`run_vbayes` over all series, sums the lower
    bound over the included ones, and -- unless the loop ends -- replaces the
    prior by :func:`~chisurf.plugins.burst.burst_ebfret.core.hmm.h_step` of
    their posteriors and statistics.

    Parameters
    ----------
    analysis : Analysis
        Updated in place, prior included.
    signals : sequence of array_like or None
        Cropped, clipped signal per series; ``None``/empty when excluded.
    restarts : int
        The *Restarts* control.
    precision : float
        The *Precision* control: VBEM restart threshold and relative
        convergence threshold of the summed lower bound.
    max_iter : int
        The loop stops once ``it > max_iter``.
    rng : numpy.random.Generator, optional
        Random source for restarts.
    should_stop : callable
        The *Stop* button; polled between batches and before each h-step.
    vb_threshold, vb_max_iter : float, int
        Per-series VBEM controls.

    Yields
    ------
    dict
        ``{"kind": "batch", "series": [...]}`` after each batch and
        ``{"kind": "iteration", "it": it, "L": L, "dL": dL}`` after each
        iteration (``dL`` is the relative change, ``NaN`` on the first).

    Returns
    -------
    list of float
        Summed lower bound per iteration (the generator's return value).
    """
    if analysis.prior is None:
        raise ValueError("the analysis has no prior; initialise it before running")
    rng = np.random.default_rng() if rng is None else rng
    included = [n for n, x in enumerate(signals) if x is not None and np.size(x) > 0]
    L: list[float] = []
    it = 1
    while True:
        for batch in run_vbayes(
            analysis,
            signals,
            restarts=restarts,
            threshold=precision,
            rng=rng,
            should_stop=should_stop,
            vb_threshold=vb_threshold,
            vb_max_iter=vb_max_iter,
        ):
            yield {"kind": "batch", "series": batch}
        L.append(float(np.sum(analysis.lowerbound[included])))
        # MATLAB prints NaN/Inf here for a zero bound (e.g. every fit invalid)
        dL = float("nan") if it == 1 or L[-1] == 0 else (L[-1] - L[-2]) / abs(L[-1])
        yield {"kind": "iteration", "it": it, "L": L[-1], "dL": dL}
        if it > max_iter:
            break
        if it > 1 and (L[-1] - L[-2]) < precision * abs(L[-1]):
            break
        if should_stop():
            return L
        posteriors = [analysis.posterior[n] for n in included if analysis.posterior[n] is not None]
        expect = [analysis.expect[n] for n in included]
        analysis.prior = hmm.h_step(posteriors, analysis.prior, expect=expect)
        it += 1
    return L
