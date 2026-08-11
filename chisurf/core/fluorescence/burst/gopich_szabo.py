r"""Photon-by-photon maximum likelihood for interconverting FRET states.

The Gopich–Szabo likelihood asks a question no histogram can: given a burst of
photons with their **individual arrival times and colours**, how probable is a
particular kinetic scheme? Because it never bins, it resolves exchange that is
faster than any bin you could choose — down to the mean interphoton time.

How it differs from H2MM
------------------------
Both are photon-by-photon and both come out of the same literature, but they
parameterise time differently, and the difference is not cosmetic:

- **H2MM** (:mod:`chisurf.plugins.burst.burst_h2mm.core.h2mm`) is a
  *discrete-time* hidden Markov model on macro-time ticks. Its free parameter is
  a transition **probability** matrix :math:`A` per tick, propagated as
  :math:`A^{\Delta t}`. Rates come out only after dividing by the tick period,
  and the answer depends on what you chose as a tick.
- **This module** is *continuous-time*. The free parameter is the rate matrix
  :math:`K` itself, in s\ :sup:`-1`, propagated as :math:`e^{K\Delta t}` for the
  exact real-valued gap between two photons. There is no tick and no binning
  convention to defend.

The two agree where both apply, which is worth exploiting: fitting the same
photons both ways is the sharpest available check that either is right, and
:func:`chisurf.plugins.burst.burst_gs` does exactly that.

The recursion
-------------
Write :math:`\Phi_c = \mathrm{diag}(p_{c})` for the probability that a photon
emitted from each state carries colour :math:`c` (for two colours,
:math:`p_a = E` and :math:`p_d = 1 - E`). Then the likelihood of a burst is a
matrix product alternating emission and propagation,

.. math::

    L = \mathbf{1}^{T}\,
        \Phi_{c_N} e^{K \Delta t_N} \cdots \Phi_{c_2} e^{K \Delta t_1}
        \Phi_{c_1}\, \mathbf{p}_{\mathrm{eq}},

one factor per photon. Diagonalising :math:`K = U \Lambda U^{-1}` once and
working in the eigenbasis turns every :math:`e^{K\Delta t}` into an elementwise
:math:`e^{\lambda \Delta t}`, which is what makes the per-photon cost a handful
of flops rather than a matrix exponential.

The product underflows within a few hundred photons, so it is renormalised at
every photon and the discarded magnitude accumulated in the log — the standard
HMM scaling trick, and the reason the result is stable for bursts of any length.

Any number of colours
---------------------
The emission matrix is ``(n_states, n_colors)`` and row-stochastic, so two- and
three-colour FRET are the same code path: three-colour simply has three
probabilities per state instead of :math:`(1-E, E)`. This matters because
three-colour is where the method earns its keep — it is genuinely sensitive to
which of two distances changed, and there is no binned equivalent.

Complex spectra
---------------
A rate matrix obeying detailed balance has a real spectrum, and then everything
below is real. A **non-reversible cycle** (three or more states with a net
circulation) has a genuinely complex conjugate pair, and the reference
implementation this follows takes the real part of the transformed emission
matrices while keeping the eigenvalues complex — an inconsistency that is
harmless for a reversible scheme and wrong for a circulating one. Here the
arithmetic stays complex throughout and the real part is taken only once, of the
final scalar, where it is exact. The cost is a factor of a few on matrices this
small; the alternative is silently wrong answers on exactly the schemes that are
interesting.

Reference: Gopich & Szabo, *Theory of the statistics of kinetic transitions with
application to single-molecule enzyme catalysis*, J. Chem. Phys. 124, 154712
(2006), and *Decoding the pattern of photon colors in single-molecule FRET*,
J. Phys. Chem. B 113, 10965 (2009). Used as documented prior art and
reimplemented here, not copied.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from collections.abc import Sequence

import numpy as np

from chisurf.core.fluorescence.kinetics import (
    equilibrium_populations,
    generator_from_rate_matrix,
    rate_matrix_from_rates,
    rates_from_rate_matrix,
)

def _engine(rate_matrix, emission):
    r"""Return a configured ``tttrlib.GopichSzabo``, or say why it cannot be had.

    The likelihood and the Viterbi path are both the photon library's. They were
    compiled here with numba until 2026-08-11, and the copy was kept as a
    fallback for a library defect that rejected any scheme with a repeated zero
    eigenvalue -- the no-exchange limit, or a state that does not exchange with
    the rest. That defect is fixed: verified on four such schemes (connected,
    ``k = 0``, one-way, and a 3-state with an isolated state), agreeing with the
    deleted kernels to 6.8e-13 - 2.8e-10 in log-likelihood and on **every**
    Viterbi state across 3040 photons.

    Raising rather than falling back is deliberate. A silent second
    implementation is the thing this work exists to remove, and a fallback that
    is never exercised is a fallback nobody knows is broken.

    Parameters
    ----------
    rate_matrix : array_like
        ``(n_states, n_states)`` with ``[target, source]`` rates in s\ :sup:`-1`.
    emission : array_like
        ``(n_states, n_colors)`` row-stochastic emission probabilities.

    Returns
    -------
    tttrlib.GopichSzabo

    Raises
    ------
    RuntimeError
        If the photon library is missing or predates the engine.
    ValueError
        If the engine refuses the scheme.
    """
    try:
        import tttrlib
    except ImportError as exc:  # pragma: no cover - tttrlib is a hard dependency
        raise RuntimeError(
            "the Gopich-Szabo engine is provided by tttrlib, which could not be "
            "imported"
        ) from exc
    if not hasattr(tttrlib, "GopichSzabo"):
        raise RuntimeError(
            "tttrlib does not expose GopichSzabo; rebuild it (the compiled "
            "engine carries the burst likelihood and the Viterbi path)"
        )
    rate_matrix = np.asarray(rate_matrix, dtype=float)
    emission = _validate_emission(emission)
    engine = tttrlib.GopichSzabo()
    ok = engine.set_scheme(
        rate_matrix.flatten().tolist(), emission.flatten().tolist(),
        int(rate_matrix.shape[0]), int(emission.shape[1]),
    )
    if not ok:
        raise ValueError(
            f"the compiled Gopich-Szabo engine refused a "
            f"{int(rate_matrix.shape[0])}-state scheme"
        )
    return engine


__all__ = [
    "GsFitResult",
    "PhotonBursts",
    "emission_from_efficiencies",
    "fit",
    "log_likelihood",
    "log_likelihood_multi",
    "rate_matrix_from_rates",
    "rates_from_rate_matrix",
    "transition_state_model",
    "transition_time_scan",
    "viterbi",
]

#: Condition number of the eigenvector matrix above which the spectral
#: propagator is not trustworthy. Mirrors the guard in the H2MM engine.
_MAX_COND = 1e8


# ──────────────────────────────────────────────────────────────────────────────
# Photon container
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class PhotonBursts:
    """Bursts of coloured photons in the flat layout the kernels consume.

    Times are **seconds** and rates are s\\ :sup:`-1` throughout this module.
    Storing every burst in one flat array with an offset table (rather than a
    list of arrays) is what lets the likelihood run as a single parallel numba
    loop over bursts.

    Attributes
    ----------
    times : numpy.ndarray
        ``(n_photons,)`` float64 arrival times in seconds, concatenated over
        bursts and non-decreasing within each burst.
    colors : numpy.ndarray
        ``(n_photons,)`` int32 colour index in ``[0, n_colors)``.
    offsets : numpy.ndarray
        ``(n_bursts + 1,)`` int64 start indices, so burst ``b`` occupies
        ``times[offsets[b]:offsets[b + 1]]``.
    n_colors : int
        Number of distinct photon colours.
    """

    times: np.ndarray
    colors: np.ndarray
    offsets: np.ndarray
    n_colors: int

    @classmethod
    def from_lists(
        cls,
        times: Sequence[np.ndarray],
        colors: Sequence[np.ndarray],
        n_colors: int | None = None,
        min_photons: int = 2,
    ) -> "PhotonBursts":
        """Build from per-burst arrays, dropping bursts that are too short.

        Parameters
        ----------
        times : sequence of numpy.ndarray
            Per-burst arrival times in seconds.
        colors : sequence of numpy.ndarray
            Per-burst colour indices, same lengths as *times*.
        n_colors : int, optional
            Number of colours; inferred as ``max + 1`` when omitted.
        min_photons : int
            Bursts shorter than this carry no kinetic information (a single
            photon has no gap) and are dropped.

        Returns
        -------
        PhotonBursts

        Raises
        ------
        ValueError
            If the two sequences disagree in length, or nothing survives the
            ``min_photons`` filter.
        """
        if len(times) != len(colors):
            raise ValueError("times and colors must have the same number of bursts")
        keep_t: list[np.ndarray] = []
        keep_c: list[np.ndarray] = []
        for t, c in zip(times, colors):
            t = np.asarray(t, dtype=np.float64).ravel()
            c = np.asarray(c, dtype=np.int32).ravel()
            if t.shape != c.shape:
                raise ValueError("a burst has different numbers of times and colors")
            if t.size < max(int(min_photons), 2):
                continue
            keep_t.append(t)
            keep_c.append(c)
        if not keep_t:
            raise ValueError("no burst has enough photons to carry kinetic information")
        lengths = np.array([t.size for t in keep_t], dtype=np.int64)
        offsets = np.zeros(lengths.size + 1, dtype=np.int64)
        np.cumsum(lengths, out=offsets[1:])
        flat_c = np.concatenate(keep_c).astype(np.int32)
        n = int(n_colors) if n_colors is not None else int(flat_c.max()) + 1
        if flat_c.min() < 0 or flat_c.max() >= n:
            raise ValueError(f"colour indices must lie in [0, {n})")
        return cls(
            times=np.concatenate(keep_t).astype(np.float64),
            colors=flat_c,
            offsets=offsets,
            n_colors=n,
        )

    def __len__(self) -> int:
        """Return the number of bursts."""
        return int(self.offsets.size - 1)

    @property
    def n_photons(self) -> int:
        """Total number of photons across all bursts."""
        return int(self.times.size)


# ──────────────────────────────────────────────────────────────────────────────
# Rate-matrix helpers
# ──────────────────────────────────────────────────────────────────────────────
def emission_from_efficiencies(efficiencies) -> np.ndarray:
    """Return the two-colour emission matrix for per-state FRET efficiencies.

    Parameters
    ----------
    efficiencies : array_like
        ``(n_states,)`` apparent FRET efficiency of each state, in ``[0, 1]``.

    Returns
    -------
    numpy.ndarray
        ``(n_states, 2)`` with column 0 the donor probability ``1 - E`` and
        column 1 the acceptor probability ``E``. Colour 0 is therefore the
        donor and colour 1 the acceptor.
    """
    e = np.asarray(efficiencies, dtype=float).ravel()
    return np.column_stack([1.0 - e, e])


def transition_state_model(k_forward: float, k_backward: float, transit_time: float,
                           efficiencies, transit_efficiency=None):
    """Return the three-state scheme that gives transitions a finite duration.

    A two-state fit assumes transitions are instantaneous. They are not, and
    whether the finite crossing time is *detectable* is a real physical question
    — for a folding barrier it is the transition-path time. The test is to
    insert an explicit intermediate that the molecule must pass through and see
    whether the likelihood prefers a non-zero duration.

    The intermediate is entered from either side and leaves to either side with
    equal probability, so escaping it takes on average ``2 / k_transit`` and the
    entry rates are **doubled** to keep the effective two-state exchange rates
    at ``k_forward`` and ``k_backward``. The crossing time is therefore
    ``transit_time = 1 / (2 * k_transit)``.

    Parameters
    ----------
    k_forward, k_backward : float
        Effective ``1 -> 2`` and ``2 -> 1`` rates in s\\ :sup:`-1`.
    transit_time : float
        Mean time spent crossing, in seconds. Must be positive; zero is the
        instantaneous two-state model, which this function will not build.
    efficiencies : array_like
        ``(2,)`` FRET efficiencies of the two end states.
    transit_efficiency : float, optional
        Efficiency of the intermediate. Defaults to the mean of the two end
        states, which is the assumption of the reference implementation and is
        a *choice*, not a derivation — a real transition path need not sit
        halfway. Set it explicitly when the geometry says otherwise.

    Returns
    -------
    rate_matrix : numpy.ndarray
        ``(3, 3)``, states ordered ``[1, intermediate, 2]``.
    efficiencies : numpy.ndarray
        ``(3,)`` matching efficiencies.

    Raises
    ------
    ValueError
        If *transit_time* is not positive.
    """
    if not np.isfinite(transit_time) or transit_time <= 0.0:
        raise ValueError("transit_time must be positive; use the two-state model for zero")
    k_transit = 1.0 / (2.0 * float(transit_time))
    e = np.asarray(efficiencies, dtype=float).ravel()
    if e.size != 2:
        raise ValueError("the transition-state model is built on two end states")
    middle = float(np.mean(e)) if transit_efficiency is None else float(transit_efficiency)
    matrix = np.zeros((3, 3), dtype=float)
    matrix[1, 0] = 2.0 * float(k_forward)   # 1 -> intermediate
    matrix[1, 2] = 2.0 * float(k_backward)  # 2 -> intermediate
    matrix[0, 1] = k_transit                # intermediate -> 1
    matrix[2, 1] = k_transit                # intermediate -> 2
    return matrix, np.array([e[0], middle, e[1]], dtype=float)


# ──────────────────────────────────────────────────────────────────────────────
# Spectral decomposition
# ──────────────────────────────────────────────────────────────────────────────
def _spectral(rate_matrix, emission):
    """Return the eigenbasis quantities the likelihood kernel needs.

    Returns ``(eigenvalues, phi, p0, u_row)`` with ``phi[c] = U^-1 diag(p_c) U``,
    ``p0 = U^-1 p_eq`` and ``u_row = 1^T U``, all complex128; or ``None`` when
    the decomposition is too ill-conditioned to propagate through.
    """
    generator = generator_from_rate_matrix(rate_matrix)
    emission = np.asarray(emission, dtype=float)
    n = generator.shape[0]
    if emission.shape[0] != n:
        raise ValueError(
            f"emission has {emission.shape[0]} rows but the rate matrix has {n} states"
        )

    eigenvalues, eigenvectors = np.linalg.eig(generator)
    if np.linalg.cond(eigenvectors) > _MAX_COND:
        # Degenerate or near-degenerate spectrum: the spectral propagator is
        # not usable and a likelihood computed from it would be noise.
        return None
    try:
        inverse = np.linalg.inv(eigenvectors)
    except np.linalg.LinAlgError:  # pragma: no cover - caught by the cond test
        return None

    # exp(K t) has non-positive real exponents for a generator; a positive real
    # part is round-off and would overflow on a long gap.
    eigenvalues = eigenvalues.astype(np.complex128)
    eigenvalues.real = np.minimum(eigenvalues.real, 0.0)

    populations = equilibrium_populations(rate_matrix)
    phi = np.empty((emission.shape[1], n, n), dtype=np.complex128)
    for c in range(emission.shape[1]):
        phi[c] = inverse @ np.diag(emission[:, c]) @ eigenvectors
    p0 = (inverse @ populations).astype(np.complex128)
    u_row = eigenvectors.sum(axis=0).astype(np.complex128)
    return eigenvalues, phi, p0, u_row


def _validate_emission(emission) -> np.ndarray:
    """Return *emission* as a validated ``(n_states, n_colors)`` array."""
    emission = np.asarray(emission, dtype=float)
    if emission.ndim != 2:
        raise ValueError("emission must be (n_states, n_colors)")
    if np.any(emission < -1e-12):
        raise ValueError("emission probabilities cannot be negative")
    sums = emission.sum(axis=1)
    if not np.allclose(sums, 1.0, atol=1e-8):
        raise ValueError(
            "each state's colour probabilities must sum to one; "
            f"got row sums {np.array2string(sums, precision=4)}"
        )
    return emission


# ──────────────────────────────────────────────────────────────────────────────
# Kernels
# ──────────────────────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
# Public likelihood
# ──────────────────────────────────────────────────────────────────────────────
def log_likelihood(bursts: PhotonBursts, rate_matrix, emission) -> float:
    """Return the total log-likelihood of a kinetic scheme given the photons.

    Delegates to tttrlib's C++ GopichSzabo engine when available (~1.5x faster
    than the numba implementation), falling back to the Python kernel otherwise.

    Parameters
    ----------
    bursts : PhotonBursts
        Photon arrival times (seconds) and colours.
    rate_matrix : array_like
        ``(n_states, n_states)`` with ``[target, source]`` rates in
        s\\ :sup:`-1`; the diagonal is rebuilt, so it may be anything.
    emission : array_like
        ``(n_states, n_colors)`` row-stochastic probability that a photon from
        each state carries each colour. Use
        :func:`emission_from_efficiencies` for the two-colour case.

    Returns
    -------
    float
        Summed log-likelihood over bursts. ``-inf`` when the scheme cannot have
        produced the data, or when the rate matrix is too degenerate to
        diagonalise — both of which an optimiser reads as "back off", which is
        the desired behaviour.

    Raises
    ------
    ValueError
        If *emission* is not row-stochastic or its shape disagrees with the
        rate matrix, or if a colour index exceeds the emission matrix.
    """
    emission = _validate_emission(emission)
    if emission.shape[1] < bursts.n_colors:
        raise ValueError(
            f"the photons use {bursts.n_colors} colours but emission has "
            f"{emission.shape[1]} columns"
        )
    # `-inf` is reserved for a model that genuinely has no likelihood: a
    # defective generator, whose repeated eigenvalue leaves the spectral
    # propagator undefined. That is what backs an optimiser off, and it is
    # decided HERE rather than by the engine, because a *setup* failure is a
    # different thing and conflating the two is how the no-exchange limit once
    # came to report "forbidden".
    if _spectral(rate_matrix, emission) is None:
        return float("-inf")
    # Everything else is the library's. This used to fall back to an in-tree
    # numba copy kept for a library defect that rejected disconnected schemes;
    # that defect is fixed, so the copy is gone and a refusal now raises.
    return float(_engine(rate_matrix, emission).log_likelihood(
        bursts.times, bursts.colors, bursts.offsets
    ))


def log_likelihood_multi(datasets: Sequence[tuple[PhotonBursts, np.ndarray]],
                         rate_matrix) -> float:
    """Return the log-likelihood of several photon sets sharing one rate matrix.

    This is how a three-colour measurement is fitted: the two-colour photons
    (say green excitation) and the three-colour photons (blue excitation) are
    different colour models of the **same** molecule, so they constrain one
    kinetic scheme jointly. Splitting them is not a convenience — the two
    excitation periods genuinely see different emission probabilities.

    Parameters
    ----------
    datasets : sequence of (PhotonBursts, array_like)
        Each entry pairs a photon set with its own ``(n_states, n_colors)``
        emission matrix. All must have the same number of states.
    rate_matrix : array_like
        The shared ``(n_states, n_states)`` rate matrix.

    Returns
    -------
    float
        Sum of the per-dataset log-likelihoods, or ``-inf`` if any is.
    """
    total = 0.0
    for bursts, emission in datasets:
        value = log_likelihood(bursts, rate_matrix, emission)
        if not np.isfinite(value):
            return float("-inf")
        total += value
    return float(total)


def viterbi(bursts: PhotonBursts, rate_matrix, emission):
    """Return the most likely state of every photon.

    The likelihood integrates over all state paths; this picks the single best
    one, which is what you plot under a burst to see *when* it switched.

    .. warning::

       A Viterbi path is a point estimate with no error bar, and it will happily
       draw transitions in a burst that contains no evidence for any. Read it as
       an illustration of a fitted model, never as a measurement.

    Parameters
    ----------
    bursts : PhotonBursts
        Photon arrival times and colours.
    rate_matrix : array_like
        ``(n_states, n_states)`` rates in s\\ :sup:`-1`.
    emission : array_like
        ``(n_states, n_colors)`` row-stochastic emission probabilities.

    Returns
    -------
    numpy.ndarray
        ``(n_photons,)`` int32 state index per photon, in the same flat order
        as ``bursts.times``.

    Raises
    ------
    ValueError
        If the rate matrix is too degenerate to diagonalise, or the emission
        matrix is invalid.
    """
    # `offsets` is the whole point. Without burst boundaries the concatenated
    # array decodes as ONE burst and the previous burst's evidence leaks across
    # the dark gap. Measured upstream at tau = 250 s: an entire 30-photon burst
    # was still being dragged at a gap of 5e5 s -- two thousand relaxation times
    # -- because Viterbi maximises a path rather than marginalising, so the
    # accumulated log-likelihood competes with a transition term decaying only
    # as exp(-dt/tau). "Our bursts are well separated" is not a defence.
    return np.asarray(
        _engine(rate_matrix, emission).viterbi(
            bursts.times, bursts.colors, bursts.offsets
        ),
        dtype=np.int32,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Fitting
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class GsFitResult:
    """Outcome of a Gopich–Szabo maximum-likelihood fit.

    Attributes
    ----------
    rate_matrix : numpy.ndarray
        ``(n_states, n_states)`` fitted rates in s\\ :sup:`-1`.
    efficiencies : numpy.ndarray
        ``(n_states,)`` fitted FRET efficiencies (two-colour fits only; empty
        for a general emission matrix).
    emission : numpy.ndarray
        ``(n_states, n_colors)`` fitted emission matrix.
    log_likelihood : float
        Log-likelihood at the optimum.
    n_photons : int
        Photons that entered the fit.
    n_bursts : int
        Bursts that entered the fit.
    n_parameters : int
        Free parameters, for information criteria.
    success : bool
        Whether the optimiser reported convergence.
    message : str
        Optimiser message.
    """

    rate_matrix: np.ndarray
    efficiencies: np.ndarray
    emission: np.ndarray
    log_likelihood: float
    n_photons: int
    n_bursts: int
    n_parameters: int
    success: bool = True
    message: str = ""
    #: Relaxation times ``-1 / Re(lambda)`` of the non-zero eigenvalues, seconds.
    relaxation_times: np.ndarray = field(default_factory=lambda: np.zeros(0))

    @property
    def bic(self) -> float:
        """Bayesian information criterion; lower is better."""
        return float(self.n_parameters * np.log(max(self.n_photons, 1)) - 2.0 * self.log_likelihood)

    @property
    def aic(self) -> float:
        """Akaike information criterion; lower is better."""
        return float(2.0 * self.n_parameters - 2.0 * self.log_likelihood)

    def to_dict(self) -> dict:
        """Return a JSON-compatible summary."""
        return {
            "rate_matrix": self.rate_matrix.tolist(),
            "rates": rates_from_rate_matrix(self.rate_matrix).tolist(),
            "efficiencies": np.asarray(self.efficiencies, dtype=float).tolist(),
            "emission": np.asarray(self.emission, dtype=float).tolist(),
            "log_likelihood": float(self.log_likelihood),
            "relaxation_times": np.asarray(self.relaxation_times, dtype=float).tolist(),
            "n_photons": int(self.n_photons),
            "n_bursts": int(self.n_bursts),
            "n_parameters": int(self.n_parameters),
            "bic": self.bic,
            "aic": self.aic,
            "success": bool(self.success),
            "message": str(self.message),
        }


def _relaxation_times(rate_matrix) -> np.ndarray:
    """Return ``-1 / Re(lambda)`` for the non-zero eigenvalues, in seconds."""
    eigenvalues = np.linalg.eigvals(generator_from_rate_matrix(rate_matrix))
    nonzero = eigenvalues[np.abs(eigenvalues) > 1e-12 * max(np.abs(eigenvalues).max(), 1.0)]
    if nonzero.size == 0:
        return np.zeros(0)
    return np.sort(-1.0 / np.real(nonzero))[::-1]


def fit(
    bursts: PhotonBursts,
    n_states: int = 2,
    initial_rates=None,
    initial_efficiencies=None,
    fix_efficiencies: bool = False,
    rate_bounds: tuple[float, float] = (1.0, 1e6),
    method: str = "nelder-mead",
    max_iterations: int = 2000,
    progress=None,
) -> GsFitResult:
    """Fit rates and per-state FRET efficiencies to coloured photons.

    Rates are optimised in **log space**, efficiencies in linear space. That is
    not cosmetic: exchange rates plausibly span four decades and an optimiser
    stepping linearly through them either crawls at the bottom of the range or
    steps straight past the optimum at the top. Efficiencies live on ``[0, 1]``
    and want no transform.

    Parameters
    ----------
    bursts : PhotonBursts
        Two-colour photons (colour 0 donor, colour 1 acceptor).
    n_states : int
        Number of kinetic states.
    initial_rates : array_like, optional
        ``n_states * (n_states - 1)`` starting rates in s\\ :sup:`-1`; see
        :func:`rate_matrix_from_rates` for the order. Defaults to 1 ms\\
        :sup:`-1` throughout, which is the middle of the accessible range.
    initial_efficiencies : array_like, optional
        ``(n_states,)`` starting efficiencies. Defaults to values spread evenly
        over ``[0.2, 0.8]``.
    fix_efficiencies : bool
        Hold the efficiencies at their starting values and fit only the rates.
        Worth doing when the efficiencies are known from a static measurement:
        it removes the strongest correlation in the problem.
    rate_bounds : tuple of float
        Lower and upper bound on every rate, s\\ :sup:`-1`. The lower bound
        matters — a rate free to reach zero makes a state absorbing and the
        likelihood surface flat.
    method : str
        ``"nelder-mead"`` (the reference's choice, robust and derivative-free)
        or ``"l-bfgs-b"`` (faster, but relies on finite differences of a
        likelihood that is only piecewise smooth in the eigen-decomposition).
    max_iterations : int
        Optimiser iteration cap.
    progress : callable, optional
        Called as ``progress(fraction, message)`` during the fit.

    Returns
    -------
    GsFitResult

    Raises
    ------
    ValueError
        If the photons are not two-coloured or *n_states* is below two.
    """
    from scipy.optimize import minimize

    n_states = int(n_states)
    if n_states < 2:
        raise ValueError("a kinetic fit needs at least two states")
    if bursts.n_colors != 2:
        raise ValueError(
            "fit() is the two-colour entry point; build the emission matrix "
            "yourself and call log_likelihood_multi for more colours"
        )

    n_rates = n_states * (n_states - 1)
    if initial_rates is None:
        initial_rates = np.full(n_rates, 1e3)
    initial_rates = np.clip(np.asarray(initial_rates, dtype=float).ravel(), *rate_bounds)
    if initial_efficiencies is None:
        initial_efficiencies = np.linspace(0.2, 0.8, n_states)
    initial_efficiencies = np.clip(
        np.asarray(initial_efficiencies, dtype=float).ravel(), 1e-6, 1.0 - 1e-6
    )

    log_lo, log_hi = np.log(rate_bounds[0]), np.log(rate_bounds[1])
    calls = {"n": 0}

    def unpack(vector):
        """Split the optimiser vector into a rate matrix and efficiencies."""
        rates = np.exp(np.clip(vector[:n_rates], log_lo, log_hi))
        if fix_efficiencies:
            efficiencies = initial_efficiencies
        else:
            efficiencies = np.clip(vector[n_rates:], 1e-9, 1.0 - 1e-9)
        return rate_matrix_from_rates(rates, n_states), efficiencies

    def objective(vector):
        """Negative log-likelihood; the optimiser minimises this."""
        matrix, efficiencies = unpack(vector)
        value = log_likelihood(bursts, matrix, emission_from_efficiencies(efficiencies))
        calls["n"] += 1
        if progress is not None and calls["n"] % 20 == 0:
            progress(
                min(calls["n"] / float(max_iterations), 0.99),
                f"logL = {value:,.1f} after {calls['n']} evaluations",
            )
        # A finite penalty rather than -inf: Nelder-Mead cannot order infinities
        # and would stall on its first reflection into a forbidden region.
        return -value if np.isfinite(value) else 1e12

    start = list(np.log(initial_rates))
    bounds = [(log_lo, log_hi)] * n_rates
    if not fix_efficiencies:
        start += list(initial_efficiencies)
        bounds += [(0.0, 1.0)] * n_states
    start = np.asarray(start, dtype=float)

    key = method.lower().replace("_", "-")
    if key == "l-bfgs-b":
        outcome = minimize(
            objective, start, method="L-BFGS-B", bounds=bounds,
            options={"maxiter": int(max_iterations)},
        )
    else:
        outcome = minimize(
            objective, start, method="Nelder-Mead", bounds=bounds,
            options={"maxiter": int(max_iterations), "fatol": 1e-4, "xatol": 1e-4},
        )

    matrix, efficiencies = unpack(np.asarray(outcome.x, dtype=float))
    value = log_likelihood(bursts, matrix, emission_from_efficiencies(efficiencies))
    n_parameters = n_rates + (0 if fix_efficiencies else n_states)
    if progress is not None:
        progress(1.0, "done")
    return GsFitResult(
        rate_matrix=matrix,
        efficiencies=efficiencies,
        emission=emission_from_efficiencies(efficiencies),
        log_likelihood=float(value),
        n_photons=bursts.n_photons,
        n_bursts=len(bursts),
        n_parameters=int(n_parameters),
        success=bool(outcome.success),
        message=str(getattr(outcome, "message", "")),
        relaxation_times=_relaxation_times(matrix),
    )


def transition_time_scan(
    bursts: PhotonBursts,
    k_forward: float,
    k_backward: float,
    efficiencies,
    transit_times=None,
    transit_efficiency=None,
):
    """Scan the log-likelihood against the duration of a transition.

    The two-state model says a molecule switches instantaneously. Inserting an
    explicit intermediate (:func:`transition_state_model`) and scanning its
    lifetime asks the data whether it prefers a finite crossing time. The
    baseline is the instantaneous model, so the returned curve is a **log-
    likelihood difference**: positive means the data support a transition of
    that duration.

    Interpret it conservatively. The curve is flat and slightly negative for
    every duration well below the mean interphoton time, because a crossing
    faster than the photon rate leaves no trace whatever — an upper bound is
    usually all such a scan can deliver, and a peak needs an accompanying
    likelihood-ratio test before it means anything.

    Parameters
    ----------
    bursts : PhotonBursts
        Two-colour photons.
    k_forward, k_backward : float
        Fitted effective exchange rates, s\\ :sup:`-1`.
    efficiencies : array_like
        ``(2,)`` fitted efficiencies of the two end states.
    transit_times : array_like, optional
        Crossing times to scan, in seconds. Defaults to 50 points
        logarithmically spaced over 1 µs to 1 ms, the range of the reference
        implementation.
    transit_efficiency : float, optional
        Efficiency of the intermediate; see :func:`transition_state_model`.

    Returns
    -------
    transit_times : numpy.ndarray
        The scanned durations, seconds.
    delta_log_likelihood : numpy.ndarray
        Log-likelihood relative to the instantaneous two-state model.
    baseline : float
        Log-likelihood of the instantaneous model itself.
    """
    if transit_times is None:
        transit_times = np.logspace(-6.0, -3.0, 50)
    transit_times = np.asarray(transit_times, dtype=float).ravel()
    efficiencies = np.asarray(efficiencies, dtype=float).ravel()

    baseline = log_likelihood(
        bursts,
        rate_matrix_from_rates([k_forward, k_backward], 2),
        emission_from_efficiencies(efficiencies),
    )
    out = np.full(transit_times.size, np.nan)
    for i, transit in enumerate(transit_times):
        try:
            matrix, three = transition_state_model(
                k_forward, k_backward, float(transit), efficiencies, transit_efficiency
            )
        except ValueError:
            continue
        out[i] = log_likelihood(bursts, matrix, emission_from_efficiencies(three))
    return transit_times, out - baseline, float(baseline)
