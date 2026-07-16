"""Multiprocessing helper to fit many decays with a ``fit2x`` estimator.

The tttrlib ``Fit23``/``Fit24``/``Fit25`` maximum-likelihood fit is correct
under Python threads but does not scale in-process (the C++ fit serialises on
per-thread state access), so throughput for large batches — pixel-wise FLIM
images, big burst sets — comes from **separate processes**.

Workers are started with the ``fork`` start method: the children inherit the
parent's already-imported modules, so there is no re-import of the (heavy,
sometimes subprocess-hostile) plugin/GUI package chain and no per-worker import
cost.  The per-decay histograms are shared through a single ``shared_memory``
block (no per-task pickling of the data matrix); each worker builds one
:class:`Fit2x` and fits its assigned rows.

``fork`` is safe here because the fits run headless (no Qt event loop is being
forked); it is the same start method the modelling plugins use for their
compute pools.
"""

from __future__ import annotations

from collections.abc import Sequence
from multiprocessing import get_context, shared_memory
from typing import Any

import numpy as np

from .fit2x import Fit2x, Fit2xModel, Fit2xSettings

# Worker-process state, populated by :func:`_init` in each spawned worker.
_W: dict[str, Any] = {}


def _settings_kwargs(s: Fit2xSettings) -> dict:
    """Picklable kwargs to rebuild a :class:`Fit2xSettings` in a worker."""
    return dict(
        dt=s.dt,
        period=s.period,
        irf=np.ascontiguousarray(s.irf, dtype=np.float64),
        background=(
            None if s.background is None else np.ascontiguousarray(s.background, dtype=np.float64)
        ),
        g_factor=s.g_factor,
        l1=s.l1,
        l2=s.l2,
        convolution_stop=s.convolution_stop,
        p2s_twoIstar=s.p2s_twoIstar,
        soft_bifl_scatter=s.soft_bifl_scatter,
    )


def _init(shm_name, shape, dtype_str, settings_kw, model, x0, fixed):
    """Pool initialiser: attach shared data + build one reusable fitter."""
    shm = shared_memory.SharedMemory(name=shm_name)
    _W["shm"] = shm
    _W["arr"] = np.ndarray(shape, dtype=np.dtype(dtype_str), buffer=shm.buf)
    _W["fit"] = Fit2x(Fit2xSettings(**settings_kw), model=Fit2xModel(model))
    _W["x0"] = np.asarray(x0, dtype=np.float64)
    _W["fixed"] = np.asarray(fixed, dtype=np.int16)


def _fit_rows(rows):
    """Fit a chunk of matrix rows; returns ``(rows, params[len(rows), 5])``."""
    arr = _W["arr"]
    fit = _W["fit"]
    x0 = _W["x0"]
    fixed = _W["fixed"]
    out = np.empty((len(rows), 5), dtype=np.float64)
    for m, r in enumerate(rows):
        res = fit.fit(arr[r].astype(np.float64), x0, fixed)
        out[m, 0] = res.x[0]
        out[m, 1] = res.x[1]
        out[m, 2] = res.x[2]
        out[m, 3] = res.x[3]
        out[m, 4] = res.twoIstar
    return rows, out


def fit_matrix_parallel(
    data: np.ndarray,
    rows: Sequence[int],
    settings: Fit2xSettings,
    x0: Sequence[float],
    fixed: Sequence[int],
    n_workers: int,
    model: Fit2xModel = Fit2xModel.FIT23,
) -> np.ndarray:
    """Fit selected rows of a decay matrix across worker processes.

    Parameters
    ----------
    data : numpy.ndarray
        ``(n_items, 2*window)`` matrix of Jordi-format counting histograms.
    rows : sequence of int
        Row indices to fit (e.g. pixels above a photon threshold).
    settings : Fit2xSettings
        Shared instrument/acquisition settings for the fitter.
    x0, fixed : sequence
        Initial parameter vector and fixed-mask passed to every fit.
    n_workers : int
        Number of worker processes.
    model : Fit2xModel, optional
        Estimator to use (default ``FIT23``).

    Returns
    -------
    numpy.ndarray
        ``(len(rows), 5)`` array of ``[tau, gamma, r0, rho, 2I*]`` in the same
        order as ``rows``.
    """
    rows = np.asarray(rows)
    settings_kw = _settings_kwargs(settings)
    shm = shared_memory.SharedMemory(create=True, size=data.nbytes)
    try:
        arr = np.ndarray(data.shape, dtype=data.dtype, buffer=shm.buf)
        arr[:] = data
        chunks = [c.tolist() for c in np.array_split(rows, n_workers * 3) if len(c)]
        params = np.empty((len(rows), 5), dtype=np.float64)
        index_of = {int(r): i for i, r in enumerate(rows)}
        ctx = get_context("fork")
        model_name = model.value if isinstance(model, Fit2xModel) else str(model)
        with ctx.Pool(
            n_workers,
            initializer=_init,
            initargs=(
                shm.name,
                data.shape,
                str(data.dtype),
                settings_kw,
                model_name,
                list(x0),
                list(fixed),
            ),
        ) as pool:
            for chunk_rows, chunk_out in pool.map(_fit_rows, chunks):
                for m, r in enumerate(chunk_rows):
                    params[index_of[int(r)]] = chunk_out[m]
        return params
    finally:
        shm.close()
        shm.unlink()
