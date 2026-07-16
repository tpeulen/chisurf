"""Threaded batch fitting for the ``fit2x`` estimators.

tttrlib's batch entry point (``DecayFit23.fit_matrix``) fits a whole matrix of
decays in one call with the Python GIL released for the *entire* loop.  That
makes in-process threading scale: several threads each fit a chunk of rows in
true parallel.  (Per-row fitting does **not** scale — each fit releases the GIL
for well under a millisecond, and the per-fit GIL handoff serialises the
threads.)

So throughput for large batches — pixel-wise FLIM images, big burst sets —
comes from a plain thread pool over row-chunks: no multiprocessing, hence no
``fork``/``spawn`` fragility and safe to call from inside a Qt GUI.  Each worker
thread owns its own :class:`Fit2x` (and therefore its own fit state), so the
fits are independent.
"""
from __future__ import annotations

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from .fit2x import Fit2x, Fit2xModel, Fit2xSettings


def fit_matrix_threaded(
    data: np.ndarray,
    rows: Sequence[int],
    settings: Fit2xSettings,
    x0: Sequence[float],
    fixed: Sequence[int],
    n_workers: int,
    model: Fit2xModel = Fit2xModel.FIT23,
) -> np.ndarray:
    """Fit selected rows of a decay matrix across threads via the batch fit.

    Parameters
    ----------
    data : numpy.ndarray
        ``(n_items, 2*window)`` matrix of VV/VH-format counting histograms.
    rows : sequence of int
        Row indices to fit (e.g. pixels above a photon threshold).
    settings : Fit2xSettings
        Shared instrument/acquisition settings for the fitter.
    x0, fixed : sequence
        Initial parameter vector and fixed-mask applied to every fit.
    n_workers : int
        Number of worker threads.  ``1`` fits the whole set in a single
        GIL-released batch call.
    model : Fit2xModel, optional
        Estimator to use (default ``FIT23``; only ``FIT23`` supports batching).

    Returns
    -------
    numpy.ndarray
        ``(len(rows), 5)`` array of ``[tau, gamma, r0, rho, 2I*]`` in the same
        order as ``rows``.
    """
    rows = np.asarray(rows)
    n = len(rows)
    params = np.empty((n, 5), dtype=np.float64)
    if n == 0:
        return params

    n_workers = max(1, int(n_workers))
    if n_workers == 1:
        fitter = Fit2x(settings, model=model)
        params[:] = fitter.fit_many(data[rows], x0, fixed)
        return params

    chunks = [c for c in np.array_split(rows, n_workers) if len(c)]
    offsets = np.cumsum([0] + [len(c) for c in chunks])
    fitters = [Fit2x(settings, model=model) for _ in range(len(chunks))]

    def work(i):
        params[offsets[i]:offsets[i + 1]] = fitters[i].fit_many(
            data[chunks[i]], x0, fixed
        )

    with ThreadPoolExecutor(len(chunks)) as pool:
        list(pool.map(work, range(len(chunks))))
    return params
