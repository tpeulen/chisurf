r"""Photon-by-photon Hidden Markov Model (H2MM) — data types.

The **compute** lives in the photon library (:class:`tttrlib.HMM`); this module
holds the types it is driven with and the two things that make one: the CSR
packing of per-burst photons, and a random model to start from.

It used to carry a second, in-tree implementation of the algorithm as well —
a numba port kept as a fallback. That copy was deleted once it had nothing
left to offer: after numba was retired from the package it ran as interpreted
Python at **44×** the compiled engine's time (302.3 ms against 6.8 ms for the
same 50-map EM) while agreeing with it to 1e-15, so it was neither a faster
path nor an independent check — only a slower way to get the same number, and
one that four call sites had been reaching for by accident. Route every fit
through :mod:`.engines`.

Model
-----
A model :math:`\lambda = \{\pi, A, B\}` over ``n_states`` hidden states and
``n_streams`` photon streams (detector categories):

* ``prior`` — ``(n_states,)`` initial-state probabilities, sums to 1.
* ``trans`` — ``(n_states, n_states)`` **row-stochastic** transition matrix for
  **one base time unit** (``trans[i, j] = P(state j at t+1 | state i at t)``).
* ``obs`` — ``(n_states, n_streams)`` **row-stochastic** emission matrix
  (``obs[i, k] = P(photon stream k | state i)``).

Variable inter-photon times
---------------------------
Photons arrive at integer macro-times ``t_1 < t_2 < ...``. Between two
consecutive photons the hidden state performs :math:`\Delta t` unobserved
transitions, so wherever a standard HMM uses ``A`` the engine uses
``A**Δt``. :class:`BurstPhotons` is laid out for that: it stores, per photon,
the *slot* of the gap to the next one, and the sorted table of unique gaps
those slots index — so the engine can cache one matrix power per distinct
interval and cost scales with the number of *photons* rather than of clock
ticks.

The algorithm is that of Pirchi *et al.* (J. Phys. Chem. B 2016, 120, 13065)
and the reference ``H2MM_C`` library by P. D. Harris.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np


@dataclass
class H2mmModel:
    """An H2MM model plus its optimisation diagnostics.

    Attributes
    ----------
    prior : numpy.ndarray
        Initial-state probabilities, shape ``(n_states,)``.
    trans : numpy.ndarray
        One-step row-stochastic transition matrix, shape
        ``(n_states, n_states)``.
    obs : numpy.ndarray
        Row-stochastic emission matrix, shape ``(n_states, n_streams)``.
    loglik : float
        Log-likelihood of the data under the model (``-inf`` if not scored).
    n_iter : int
        Number of EM iterations performed.
    n_phot : int
        Total number of photons the model was scored on.
    converged : bool
        Whether the EM loop met the convergence criterion.
    """

    prior: np.ndarray
    trans: np.ndarray
    obs: np.ndarray
    loglik: float = -np.inf
    n_iter: int = 0
    n_phot: int = 0
    converged: bool = False

    @property
    def n_states(self) -> int:
        """Number of hidden states."""
        return int(self.prior.shape[0])

    @property
    def n_streams(self) -> int:
        """Number of photon streams (detector categories)."""
        return int(self.obs.shape[1])

    @property
    def n_free(self) -> int:
        """Number of free parameters ``k`` (used by BIC/ICL)."""
        n, p = self.n_states, self.n_streams
        return n * n + (p - 1) * n - 1

    @property
    def bic(self) -> float:
        """Bayesian information criterion ``-2·logL + k·ln(N_phot)``."""
        if not math.isfinite(self.loglik) or self.n_phot <= 0:
            return np.inf
        return -2.0 * self.loglik + self.n_free * math.log(self.n_phot)

    def normalize(self) -> H2mmModel:
        """Renormalise ``prior``, and the rows of ``trans`` and ``obs``."""
        self.prior = _row_normalize(self.prior.reshape(1, -1)).ravel()
        self.trans = _row_normalize(self.trans)
        self.obs = _row_normalize(self.obs)
        return self

    def copy(self) -> H2mmModel:
        """Return a deep copy of the model."""
        return H2mmModel(
            self.prior.copy(),
            self.trans.copy(),
            self.obs.copy(),
            self.loglik,
            self.n_iter,
            self.n_phot,
            self.converged,
        )


def _row_normalize(a: np.ndarray) -> np.ndarray:
    """Return ``a`` with every row rescaled to sum to 1 (zero rows → uniform)."""
    a = np.asarray(a, dtype=np.float64)
    out = a.copy()
    s = out.sum(axis=1)
    for i in range(out.shape[0]):
        if s[i] > 0:
            out[i] /= s[i]
        else:
            out[i] = 1.0 / out.shape[1]
    return out


# ---------------------------------------------------------------------------
# Burst-photon data container
# ---------------------------------------------------------------------------


@dataclass
class BurstPhotons:
    """Photon streams for a set of bursts in engine-ready (CSR) layout.

    Attributes
    ----------
    streams : numpy.ndarray
        Concatenated per-photon stream index of length ``N``, in the narrowest
        signed int that fits (``int8`` for ≤127 streams) to keep the hot-loop
        read small.
    gap_slot : numpy.ndarray
        For each photon ``n``, the cache slot of ``Δt`` between photon ``n``
        and ``n+1`` (``-1`` for the last photon of every burst); ``int16`` for
        up to 32767 unique Δt, else ``int32``.
    burst_offsets : numpy.ndarray
        CSR offsets, ``int64`` of length ``n_bursts + 1``.
    unique_dt : numpy.ndarray
        Sorted unique inter-photon ``Δt`` values, ``int64``.  ``0`` is a slot
        like any other (coincident macro times propagate with the identity).
    n_streams : int
        Number of photon streams.
    """

    streams: np.ndarray
    gap_slot: np.ndarray
    burst_offsets: np.ndarray
    unique_dt: np.ndarray
    n_streams: int

    @property
    def n_bursts(self) -> int:
        """Number of bursts."""
        return int(self.burst_offsets.shape[0] - 1)

    @property
    def n_photons(self) -> int:
        """Total number of photons across all bursts."""
        return int(self.streams.shape[0])


def prepare_bursts(
    times: Sequence[np.ndarray],
    streams: Sequence[np.ndarray],
    n_streams: int,
) -> BurstPhotons:
    """Pack per-burst photon arrays into the engine's CSR layout.

    Parameters
    ----------
    times : sequence of numpy.ndarray
        One monotonically non-decreasing integer macro-time array per burst.
    streams : sequence of numpy.ndarray
        Matching per-burst photon stream indices in ``[0, n_streams)``.
    n_streams : int
        Number of photon streams.

    Returns
    -------
    BurstPhotons
        Concatenated arrays, burst offsets, and the unique-``Δt`` table.
    """
    if len(times) != len(streams):
        raise ValueError("times and streams must have the same number of bursts")

    kept_times: list[np.ndarray] = []
    kept_streams: list[np.ndarray] = []
    for t, s in zip(times, streams):
        t = np.asarray(t).astype(np.int64, copy=False)
        s = np.asarray(s).astype(np.int32, copy=False)
        if t.shape[0] != s.shape[0]:
            raise ValueError("each burst needs equal-length times and streams")
        if t.shape[0] == 0:
            continue
        kept_times.append(t)
        kept_streams.append(s)

    if not kept_times:
        raise ValueError("no non-empty bursts provided")

    offsets = np.zeros(len(kept_times) + 1, dtype=np.int64)
    offsets[1:] = np.cumsum([t.shape[0] for t in kept_times])
    # The stream index is tiny (0..n_streams-1); store it in the narrowest int so
    # the per-photon read stays small in the memory-bound E-step hot loop.
    stream_dtype = np.int8 if int(n_streams) <= 127 else np.int16
    streams_concat = np.concatenate(kept_streams).astype(stream_dtype)

    # Inter-photon Δt per photon (0 at the last photon of each burst).
    all_dt: list[np.ndarray] = []
    for t in kept_times:
        if t.shape[0] > 1:
            all_dt.append(np.diff(t))
    if all_dt:
        unique_dt = np.unique(np.concatenate(all_dt)).astype(np.int64)
        # ``Δt == 0`` is a legitimate gap (the input is only non-*decreasing*, and
        # coarse macro-time scaling makes ties common) and gets its own slot: the
        # propagator of a zero interval is the identity, ``ρ(0) = 0``.  Dropping it
        # would make every tie resolve to slot 0, i.e. the smallest *positive* Δt.
        unique_dt = unique_dt[unique_dt >= 0]
    else:
        unique_dt = np.zeros(0, dtype=np.int64)

    # gap_slot indexes unique_dt (plus a -1 sentinel); int16 covers up to 32767
    # unique Δt values, otherwise widen to int32.
    slot_dtype = np.int16 if unique_dt.shape[0] < 32767 else np.int32
    gap_slot = np.full(streams_concat.shape[0], -1, dtype=slot_dtype)
    for b, t in enumerate(kept_times):
        if t.shape[0] < 2:
            continue
        start = offsets[b]
        dt = np.diff(t)
        slots = np.searchsorted(unique_dt, dt).astype(slot_dtype)
        gap_slot[start : start + dt.shape[0]] = slots

    return BurstPhotons(
        streams=streams_concat,
        gap_slot=gap_slot,
        burst_offsets=offsets,
        unique_dt=unique_dt,
        n_streams=int(n_streams),
    )


# ---------------------------------------------------------------------------
# A^Δt and ρ caches (associative pair-power)
# ---------------------------------------------------------------------------


def factory_model(
    n_states: int,
    n_streams: int,
    trans_scale: float = 1e-4,
    seed: int | None = None,
) -> H2mmModel:
    """Build a reasonable initial model for EM.

    Parameters
    ----------
    n_states : int
        Number of hidden states.
    n_streams : int
        Number of photon streams.
    trans_scale : float
        Off-diagonal transition probability of the initial ``trans`` matrix.
    seed : int, optional
        Seed for the small random spread applied to the emission matrix so
        states are not degenerate.

    Returns
    -------
    H2mmModel
        A row-stochastic initial model.
    """
    rng = np.random.default_rng(seed)
    prior = np.full(n_states, 1.0 / n_states)

    trans = np.full((n_states, n_states), trans_scale)
    for i in range(n_states):
        trans[i, i] = 1.0 - trans_scale * (n_states - 1)
    trans = _row_normalize(trans)

    # Spread emission profiles across the stream axis so states are distinct.
    obs = np.full((n_states, n_streams), 1.0 / n_streams)
    if n_states > 1 and n_streams > 1:
        for i in range(n_states):
            frac = (i + 1) / (n_states + 1)
            profile = np.linspace(1.0 - frac, frac, n_streams)
            profile = np.clip(profile + 0.05 * rng.standard_normal(n_streams), 1e-3, None)
            obs[i] = profile
    obs = _row_normalize(obs)

    return H2mmModel(prior=prior, trans=trans, obs=obs)


def simulate_bursts(
    model: H2mmModel,
    burst_times: Sequence[np.ndarray],
    seed: int | None = None,
) -> list[np.ndarray]:
    """Monte-Carlo sample photon streams from a model along given time axes.

    The hidden chain is advanced tick-by-tick with the one-step ``trans``
    matrix (so it exercises the exact ``A**Δt`` propagation the engine
    caches), and each photon emits a stream drawn from ``obs``.

    Parameters
    ----------
    model : H2mmModel
        The generative model.
    burst_times : sequence of numpy.ndarray
        One monotonically increasing integer macro-time array per burst.
    seed : int, optional
        Random seed.

    Returns
    -------
    list of numpy.ndarray
        Per-burst photon stream indices, matching ``burst_times`` in shape.
    """
    times = [np.asarray(t).astype(np.int64) for t in burst_times]

    # The compiled engine walks the same chain tick by tick. It is not a second
    # implementation kept for comparison -- it is the one that already existed,
    # and this loop was the copy.
    try:
        import tttrlib

        from .h2mm_tttrlib import HAVE_TTTRLIB, _to_engine_model

        if HAVE_TTTRLIB:
            out = tttrlib.HMM.simulate_bursts(
                _to_engine_model(model),
                [[int(v) for v in t] for t in times],
                -1 if seed is None else int(seed),
            )
            return [np.asarray(s, dtype=np.int32) for s in out]
    except Exception:  # pragma: no cover
        pass

    rng = np.random.default_rng(seed)
    n_states = model.n_states
    streams_out: list[np.ndarray] = []
    for t in times:
        m = t.shape[0]
        s = np.empty(m, dtype=np.int32)
        state = rng.choice(n_states, p=model.prior)
        for n in range(m):
            if n > 0:
                for _ in range(int(t[n] - t[n - 1])):
                    state = rng.choice(n_states, p=model.trans[state])
            s[n] = rng.choice(model.n_streams, p=model.obs[state])
        streams_out.append(s)
    return streams_out
