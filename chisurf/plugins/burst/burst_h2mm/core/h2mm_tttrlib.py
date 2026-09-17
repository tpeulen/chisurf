"""tttrlib-backed H2MM engine.

This adapter runs the Baum-Welch EM optimisation and Viterbi decoding through
the fast C++ :class:`tttrlib.HMM` engine while keeping the plugin's own
:class:`~.h2mm.BurstPhotons` / :class:`~.h2mm.H2mmModel` data types, so it is a
adapter over :class:`tttrlib.HMM`.

This is now the *only* H2MM engine. ChiSurf carried a second, in-tree
implementation until 2026-08-31 -- the C++ engine is a port of it -- and that
copy was deleted once it had become 44x slower for identical numbers; see
:mod:`.h2mm`. :data:`HAVE_TTTRLIB` therefore reports whether H2MM can run at
all, not which of two engines will; :mod:`.engines` turns a False into a
diagnosable error rather than a silent slow path.
"""

from __future__ import annotations

import numpy as np

from .h2mm import BurstPhotons, H2mmModel, factory_model

try:
    import tttrlib

    HAVE_TTTRLIB = hasattr(tttrlib, "HMM")
except Exception:  # pragma: no cover - tttrlib is optional
    tttrlib = None
    HAVE_TTTRLIB = False


def _to_engine(data: BurstPhotons) -> tttrlib.HMM:
    """Rebuild per-burst (times, streams) from CSR ``BurstPhotons`` and load them
    into a :class:`tttrlib.HMM` engine.

    ``BurstPhotons`` stores, per photon, the slot of the inter-photon Δt to the
    next photon (``gap_slot``, ``-1`` at a burst's last photon); the absolute
    macro-times are recovered by cumulative-summing ``unique_dt[gap_slot]`` within
    each burst (the absolute origin is irrelevant to H2MM — only the gaps matter).
    """
    offsets = np.asarray(data.burst_offsets)
    streams_all = np.asarray(data.streams)
    gap_slot = np.asarray(data.gap_slot)
    unique_dt = np.asarray(data.unique_dt)

    times: list[list[int]] = []
    strms: list[list[int]] = []
    for b in range(len(offsets) - 1):
        s, e = int(offsets[b]), int(offsets[b + 1])
        n = e - s
        if n <= 0:
            continue
        t = np.zeros(n, dtype=np.int64)
        if n > 1:
            slots = gap_slot[s : s + n - 1]
            dt = np.where(slots >= 0, unique_dt[np.clip(slots, 0, len(unique_dt) - 1)], 0)
            t[1:] = np.cumsum(dt.astype(np.int64))
        times.append([int(x) for x in t])
        strms.append([int(x) for x in streams_all[s:e]])

    eng = tttrlib.HMM()
    eng.set_bursts(times, strms, int(data.n_streams))
    return eng


def _to_engine_model(model: H2mmModel) -> tttrlib.HmmModel:
    return tttrlib.HmmModel(
        [float(x) for x in np.asarray(model.prior).ravel()],
        [float(x) for x in np.asarray(model.trans).ravel()],
        [float(x) for x in np.asarray(model.obs).ravel()],
    )


def _from_engine_model(fit: tttrlib.HmmModel, n_phot: int) -> H2mmModel:
    return H2mmModel(
        prior=np.asarray(fit.prior_np, dtype=np.float64),
        trans=np.asarray(fit.trans_np, dtype=np.float64),
        obs=np.asarray(fit.obs_np, dtype=np.float64),
        loglik=float(fit.loglik),
        n_iter=int(fit.n_iter),
        n_phot=int(n_phot),
        converged=bool(fit.converged),
    )


def optimize(
    model: H2mmModel,
    data: BurstPhotons,
    max_iter: int = 500,
    tol: float = 1e-7,
    min_trans: float = 1e-12,
    accelerate: bool = True,
    single_precision: bool = False,
    on_iter=None,
) -> H2mmModel:
    """EM optimisation via tttrlib. Reach it through :func:`~.engines.optimize`."""
    eng = _to_engine(data)
    fit = eng.optimize(
        _to_engine_model(model),
        int(max_iter),
        float(tol),
        float(min_trans),
        bool(accelerate),
        bool(single_precision),
    )
    out = _from_engine_model(fit, data.n_photons)
    if on_iter is not None:  # coarse progress: tttrlib EM is a single blocking call
        on_iter(out.n_iter, max(out.n_iter, 1))
    return out


def viterbi(model: H2mmModel, data: BurstPhotons) -> tuple[np.ndarray, float]:
    """Most-likely per-photon state path + ICL via tttrlib."""
    eng = _to_engine(data)
    path, icl = eng.viterbi(_to_engine_model(model))
    return np.asarray(path, dtype=np.int64), float(icl)


def posterior(model: H2mmModel, data: BurstPhotons) -> tuple[np.ndarray, int]:
    """Per-photon posterior state probabilities γ via tttrlib.

    Returns ``(gamma, n_underflow)`` with ``gamma`` of shape
    ``(n_photons, n_states)``, rows summing to 1. Unlike a Viterbi path this is a
    *distribution*: its column means are the unbiased state occupancy, which
    counting a decoded path is not.
    """
    eng = _to_engine(data)
    g, n_underflow = eng.gamma(_to_engine_model(model))
    return np.asarray(g, dtype=np.float32), int(n_underflow)


def sample_states(model: H2mmModel, data: BurstPhotons, seed: int = 0) -> tuple[np.ndarray, int]:
    """Draw each photon's state independently from its γ row (marginal draw)."""
    eng = _to_engine(data)
    path, n_underflow = eng.jitter_path(_to_engine_model(model), int(seed))
    return np.asarray(path, dtype=np.int64), int(n_underflow)


def sample_paths(
    model: H2mmModel, data: BurstPhotons, seed: int = 0, n_samples: int = 1
) -> np.ndarray:
    """Draw whole trajectories from ``P(path | data)`` (FFBS) via tttrlib."""
    eng = _to_engine(data)
    return np.asarray(
        eng.ffbs_paths(_to_engine_model(model), int(seed), int(n_samples)),
        dtype=np.int64,
    )


def fit_states(
    data: BurstPhotons,
    n_states: int,
    n_restarts: int = 1,
    max_iter: int = 500,
    tol: float = 1e-7,
    seed: int | None = 0,
    single_precision: bool = False,
    on_iter=None,
) -> H2mmModel:
    """Random-restart EM keeping the best fit — tttrlib backend."""
    eng = _to_engine(data)
    best: H2mmModel | None = None
    restarts = max(int(n_restarts), 1)
    for r in range(restarts):
        init = factory_model(n_states, data.n_streams, seed=None if seed is None else int(seed) + r)
        fit = eng.optimize(
            _to_engine_model(init), int(max_iter), float(tol), 1e-12, True, bool(single_precision)
        )
        cand = _from_engine_model(fit, data.n_photons)
        if best is None or cand.loglik > best.loglik:
            best = cand
        if on_iter is not None:
            on_iter((r + 1) * max_iter, restarts * max_iter)
    assert best is not None
    return best
