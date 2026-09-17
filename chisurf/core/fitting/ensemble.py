r"""Ensemble MCMC samplers: affine-invariant stretch and ensemble slice.

An *ensemble* sampler advances many walkers at once and proposes a move for one
walker out of the positions of the others. The ensemble therefore learns the
scale and the correlations of the target by itself, which is what makes these
samplers usable on a posterior nobody has tuned a proposal for. Two are
implemented here, sharing all bookkeeping:

:class:`EnsembleSampler`
    The **stretch move** of Goodman & Weare. For walker :math:`x_k` a partner
    :math:`x_j` is drawn from the complementary half of the ensemble and the
    proposal is

    .. math::

        y = x_j + z\,(x_k - x_j),

    with the stretch factor drawn from :math:`g(z) \propto z^{-1/2}` on
    :math:`[1/a, a]`, which satisfies :math:`g(1/z) = z\,g(z)`. The proposal is
    accepted with probability
    :math:`\min\!\left(1, z^{\,n-1}\,p(y)/p(x_k)\right)`; the :math:`z^{n-1}`
    factor is what makes the chain reversible. One log-probability evaluation
    per walker per step, and a single knob (:math:`a`) that rarely needs
    touching.

:class:`EnsembleSliceSampler`
    **Ensemble slice sampling** after Karamanis & Beutler. A direction is drawn
    from the complementary half of the ensemble -- as a difference of two of its
    walkers, or from its covariance -- and the walker is then moved by
    one-dimensional *slice* sampling along that direction: a slice height
    :math:`y \sim \mathcal{U}(0, p(x))` is drawn, an interval around the current
    point is stepped out until both ends fall below :math:`y`, and points are
    drawn from it and the interval shrunk until one lands above :math:`y`. There
    is no accept/reject and no step size: every walker moves at every step, and
    the length scale adapts from the expansion/contraction statistics. It costs
    several log-probability evaluations per walker per step and buys a much
    longer move, which pays off when the posterior is strongly correlated or
    badly scaled.

Both are *affine invariant*: they perform identically on :math:`p(x)` and on any
linear reparameterisation of it, so a posterior whose parameters are strongly
correlated or scaled very differently costs no tuning. That is the property a
diagonal random walk lacks and the reason these are worth having next to
:func:`chisurf.core.fitting.sample.walk_mcmc`.

Walkers are updated in two halves ("red-blue"): one half is moved using only the
other, then the roles swap. Within a half the proposals are independent, so a
whole half is evaluated in one vectorised call (or through a process pool), and
the ensemble as a whole still satisfies detailed balance. Because the walkers
interact by construction they are **not** independent chains, so an
:math:`\hat{R}` computed across walkers is optimistic -- see
:mod:`chisurf.core.fitting.diagnostics`.

Both samplers are self-contained -- no external MCMC package is required -- and
store the chain as a plain numpy array.

References
----------
Goodman, J. & Weare, J. *Ensemble samplers with affine invariance.*
Communications in Applied Mathematics and Computational Science **5**, 65 (2010).

Foreman-Mackey, D., Hogg, D. W., Lang, D. & Goodman, J. *emcee: the MCMC
hammer.* Publications of the Astronomical Society of the Pacific **125**, 306
(2013) -- the parallel red-blue split.

Karamanis, M. & Beutler, F. *Ensemble slice sampling.* Statistics and Computing
**31**, 61 (2021).

Neal, R. M. *Slice sampling.* Annals of Statistics **31**, 705 (2003).

Examples
--------
Sample a two-dimensional Gaussian with either sampler and recover its mean:

>>> import numpy as np
>>> from chisurf.core.fitting.ensemble import EnsembleSampler, EnsembleSliceSampler
>>> def log_prob(x):
...     return -0.5 * float(np.sum(x ** 2))
>>> p0 = np.random.default_rng(0).standard_normal((16, 2))
>>> for cls in (EnsembleSampler, EnsembleSliceSampler):
...     sampler = cls(16, 2, log_prob, seed=1)
...     _ = sampler.run_mcmc(p0, 400)
...     chain = sampler.get_chain(flat=True, discard=100)
...     bool(np.all(np.abs(chain.mean(axis=0)) < 0.25))
True
True
"""

from __future__ import annotations

import typing

import numpy as np

__all__ = [
    "EnsembleSampler",
    "EnsembleSliceSampler",
    "EnsembleState",
    "DifferentialMove",
    "CovarianceMove",
    "AdaptiveCovarianceMove",
    "walkers_independent",
]


class EnsembleState:
    """Position of every walker plus the values cached with it.

    Parameters
    ----------
    coords : array_like or EnsembleState
        Walker positions, shape ``(nwalkers, ndim)``, or a state to copy.
    log_prob : numpy.ndarray, optional
        Log-probability of each walker at ``coords``. Computed on demand when
        not given.
    blobs : numpy.ndarray, optional
        Per-walker metadata returned alongside the log-probability.
    """

    __slots__ = ("coords", "log_prob", "blobs")

    def __init__(self, coords, log_prob=None, blobs=None):
        if isinstance(coords, EnsembleState):
            log_prob = coords.log_prob if log_prob is None else log_prob
            blobs = coords.blobs if blobs is None else blobs
            coords = coords.coords
        self.coords = np.atleast_2d(np.array(coords, dtype=np.float64))
        self.log_prob = None if log_prob is None else np.array(log_prob, dtype=np.float64)
        self.blobs = None if blobs is None else np.array(blobs)

    def __repr__(self) -> str:
        """Return a short representation naming the ensemble shape."""
        return f"EnsembleState(nwalkers={self.coords.shape[0]}, ndim={self.coords.shape[1]})"


def walkers_independent(coords: np.ndarray) -> bool:
    """Test whether the walkers span the parameter space.

    An ensemble move can only ever explore the affine subspace spanned by its
    walkers. If the initial positions are (nearly) linearly dependent -- all
    walkers on a line, or two walkers identical -- the chain stays trapped in
    that subspace and the run silently returns nonsense rather than failing.

    Parameters
    ----------
    coords : numpy.ndarray
        Walker positions, shape ``(nwalkers, ndim)``.

    Returns
    -------
    bool
        ``True`` when the column-normalised, mean-subtracted positions have a
        condition number below ``1e8``.
    """
    coords = np.asarray(coords, dtype=np.float64)
    if not np.all(np.isfinite(coords)):
        return False
    c = coords - np.mean(coords, axis=0)[None, :]
    col_max = np.amax(np.abs(c), axis=0)
    if np.any(col_max == 0):
        return False
    c = c / col_max
    col_norm = np.sqrt(np.sum(c**2, axis=0))
    if np.any(col_norm == 0):
        return False
    c = c / col_norm
    return bool(np.linalg.cond(c) <= 1e8)


class _CallWithArgs:
    """Bind ``args``/``kwargs`` to a log-probability function.

    A module-level class rather than a closure so that the bound callable stays
    picklable and can therefore be shipped to a ``multiprocessing`` pool.

    Parameters
    ----------
    f : callable
        Log-probability function.
    args : sequence or None
        Extra positional arguments.
    kwargs : dict or None
        Extra keyword arguments.
    """

    __slots__ = ("f", "args", "kwargs")

    def __init__(self, f, args, kwargs):
        self.f = f
        self.args = tuple(args) if args else ()
        self.kwargs = dict(kwargs) if kwargs else {}

    def __call__(self, x):
        """Evaluate the wrapped function at ``x``."""
        return self.f(x, *self.args, **self.kwargs)


class _EnsembleSamplerBase:
    """Storage, log-probability evaluation and the driver loop of an ensemble.

    Subclasses implement :meth:`_step`, which advances every walker once.

    Parameters
    ----------
    nwalkers : int
        Number of walkers.
    ndim : int
        Number of sampled dimensions.
    log_prob_fn : callable
        ``log_prob_fn(x, *args, **kwargs)`` returning the log-posterior (up to
        a constant) at position ``x``. It may return the log-probability alone,
        or a tuple ``(log_prob, *blobs)`` whose trailing entries are stored
        alongside the chain. With ``vectorize=True`` it instead receives an
        ``(n, ndim)`` array and returns ``n`` log-probabilities.
    args : sequence, optional
        Extra positional arguments for ``log_prob_fn``.
    kwargs : dict, optional
        Extra keyword arguments for ``log_prob_fn``.
    pool : object, optional
        Anything with a ``map`` method, used to evaluate a half-ensemble in
        parallel. Ignored when ``vectorize`` is set.
    vectorize : bool, optional
        Call ``log_prob_fn`` once per half-ensemble with all positions at once.
    seed : int or numpy.random.Generator, optional
        Seed or generator; pass one for a reproducible run.

    Attributes
    ----------
    iteration : int
        Number of stored steps.
    n_evaluations : int
        Number of log-probability evaluations performed, which is the honest
        currency for comparing samplers: a slice step moves further than a
        stretch step but costs several evaluations.
    """

    def __init__(
        self,
        nwalkers: int,
        ndim: int,
        log_prob_fn: typing.Callable,
        args: typing.Sequence = None,
        kwargs: dict = None,
        pool=None,
        vectorize: bool = False,
        seed=None,
    ):
        self.nwalkers = int(nwalkers)
        self.ndim = int(ndim)
        if self.nwalkers < 4:
            raise ValueError(
                f"an ensemble of {self.nwalkers} walkers is too small to be split into two "
                f"halves that propose from each other; use at least 4"
            )
        self.log_prob_fn = _CallWithArgs(log_prob_fn, args, kwargs)
        self.pool = pool
        self.vectorize = bool(vectorize)
        self.random = seed if isinstance(seed, np.random.Generator) else np.random.default_rng(seed)
        self._previous_state: EnsembleState | None = None
        self.reset()

    # ------------------------------------------------------------------ store

    def reset(self) -> None:
        """Discard the stored chain and all bookkeeping."""
        self.iteration = 0
        self.n_evaluations = 0
        self.accepted = np.zeros(self.nwalkers, dtype=np.float64)
        self._chain = np.empty((0, self.nwalkers, self.ndim), dtype=np.float64)
        self._log_prob = np.empty((0, self.nwalkers), dtype=np.float64)
        self._blobs: np.ndarray | None = None
        self._previous_state = None

    @property
    def shape(self) -> tuple:
        """Return the ensemble shape ``(nwalkers, ndim)``."""
        return self.nwalkers, self.ndim

    @property
    def acceptance_fraction(self) -> np.ndarray:
        """Return the fraction of steps in which each walker moved."""
        if self.iteration <= 0:
            return np.full(self.nwalkers, np.nan)
        return self.accepted / float(self.iteration)

    def _grow(self, ngrow: int, blobs: np.ndarray | None) -> None:
        """Make room for ``ngrow`` further stored steps.

        Parameters
        ----------
        ngrow : int
            Number of additional steps to store.
        blobs : numpy.ndarray or None
            Current blob array, used for its dtype and per-walker shape.
        """
        n_extra = ngrow - (len(self._chain) - self.iteration)
        if n_extra > 0:
            self._chain = np.concatenate(
                (self._chain, np.empty((n_extra, self.nwalkers, self.ndim), dtype=np.float64)),
                axis=0,
            )
            self._log_prob = np.concatenate(
                (self._log_prob, np.empty((n_extra, self.nwalkers), dtype=np.float64)), axis=0
            )
        if blobs is None:
            if self._blobs is not None:
                raise ValueError("the log-probability stopped returning blobs mid-run")
            return
        blobs = np.asarray(blobs)
        dt = np.dtype((blobs.dtype, blobs.shape[1:]))
        if self._blobs is None:
            if self.iteration > 0:
                raise ValueError("the log-probability started returning blobs mid-run")
            self._blobs = np.empty((len(self._chain), self.nwalkers), dtype=dt)
        elif len(self._blobs) < len(self._chain):
            pad = np.empty((len(self._chain) - len(self._blobs), self.nwalkers), dtype=dt)
            self._blobs = np.concatenate((self._blobs, pad), axis=0)

    def _save_step(self, state: EnsembleState, accepted: np.ndarray) -> None:
        """Append one state to the stored chain.

        Parameters
        ----------
        state : EnsembleState
            Ensemble state to store.
        accepted : numpy.ndarray
            Boolean per-walker flags saying which walkers moved.
        """
        self._chain[self.iteration] = state.coords
        self._log_prob[self.iteration] = state.log_prob
        if state.blobs is not None:
            self._blobs[self.iteration] = state.blobs
        self.accepted += accepted
        self.iteration += 1

    def get_value(self, name: str, flat: bool = False, thin: int = 1, discard: int = 0):
        """Read a stored quantity, optionally thinned, burnt in and flattened.

        Parameters
        ----------
        name : {"chain", "log_prob", "blobs"}
            Quantity to read.
        flat : bool, optional
            Merge the step and walker axes into one.
        thin : int, optional
            Keep only every ``thin``-th stored step.
        discard : int, optional
            Drop the first ``discard`` stored steps as burn-in.

        Returns
        -------
        numpy.ndarray or None
            The requested slice, or ``None`` for ``blobs`` when the
            log-probability returned none.
        """
        if self.iteration <= 0:
            raise AttributeError("the sampler has not stored a step yet")
        store = {"chain": self._chain, "log_prob": self._log_prob, "blobs": self._blobs}
        if name not in store:
            raise KeyError(f"unknown stored quantity {name!r}")
        v = store[name]
        if v is None:
            return None
        v = v[discard + thin - 1 : self.iteration : thin]
        if flat:
            s = list(v.shape[1:])
            s[0] = int(np.prod(v.shape[:2]))
            return v.reshape(s)
        return v

    def get_chain(self, **kwargs) -> np.ndarray:
        """Return the stored positions, shaped ``(n_steps, nwalkers, ndim)``.

        Parameters
        ----------
        **kwargs
            ``flat``, ``thin`` and ``discard``, see :meth:`get_value`.

        Returns
        -------
        numpy.ndarray
            Walker positions.
        """
        return self.get_value("chain", **kwargs)

    def get_log_prob(self, **kwargs) -> np.ndarray:
        """Return the stored log-probabilities, shaped ``(n_steps, nwalkers)``.

        Parameters
        ----------
        **kwargs
            ``flat``, ``thin`` and ``discard``, see :meth:`get_value`.

        Returns
        -------
        numpy.ndarray
            Log-probability of each stored walker position.
        """
        return self.get_value("log_prob", **kwargs)

    def get_blobs(self, **kwargs):
        """Return the stored blobs, or ``None`` if there are none.

        Parameters
        ----------
        **kwargs
            ``flat``, ``thin`` and ``discard``, see :meth:`get_value`.

        Returns
        -------
        numpy.ndarray or None
            Per-step, per-walker metadata.
        """
        return self.get_value("blobs", **kwargs)

    def get_last_sample(self) -> EnsembleState:
        """Return the most recently stored state.

        Returns
        -------
        EnsembleState
            The last stored ensemble position with its log-probability and
            blobs.
        """
        if self.iteration <= 0:
            raise AttributeError("the sampler has not stored a step yet")
        it = self.iteration
        blobs = self.get_blobs(discard=it - 1)
        return EnsembleState(
            self.get_chain(discard=it - 1)[0],
            log_prob=self.get_log_prob(discard=it - 1)[0],
            blobs=None if blobs is None else blobs[0],
        )

    # ----------------------------------------------------------- probability

    def compute_log_prob(self, coords: np.ndarray) -> tuple:
        """Evaluate the log-probability for a set of walker positions.

        Parameters
        ----------
        coords : numpy.ndarray
            Positions, shape ``(n, ndim)``.

        Returns
        -------
        log_prob : numpy.ndarray
            One log-probability per position.
        blobs : numpy.ndarray or None
            Stacked trailing return values of ``log_prob_fn``, or ``None`` when
            it returned the log-probability alone.

        Raises
        ------
        ValueError
            If a position is not finite or a returned log-probability is NaN.
        """
        p = np.asarray(coords, dtype=np.float64)
        if not np.all(np.isfinite(p)):
            raise ValueError("a walker moved to a non-finite position")
        self.n_evaluations += len(p)

        if self.vectorize:
            results = self.log_prob_fn(p)
        elif self.pool is not None:
            results = list(self.pool.map(self.log_prob_fn, p))
        else:
            results = [self.log_prob_fn(x) for x in p]

        log_prob, blobs = _split_blobs(results)
        if np.any(np.isnan(log_prob)):
            raise ValueError("the log-probability returned NaN")
        return log_prob, blobs

    # ---------------------------------------------------------------- driver

    def _halves(self) -> list:
        """Split the walkers into two randomly assigned complementary halves.

        Returns
        -------
        list of tuple
            ``[(active, complement), (complement, active)]`` as index arrays,
            so every walker is moved exactly once per step using only walkers
            that are not being moved with it.
        """
        order = self.random.permutation(self.nwalkers)
        half = self.nwalkers // 2
        first, second = order[:half], order[half:]
        return [(first, second), (second, first)]

    def _step(self, state: EnsembleState) -> tuple:
        """Advance every walker once.

        Parameters
        ----------
        state : EnsembleState
            Current state; updated in place.

        Returns
        -------
        state : EnsembleState
            The updated state.
        accepted : numpy.ndarray
            Boolean per-walker flags saying which walkers moved.
        """
        raise NotImplementedError

    def sample(
        self,
        initial_state,
        iterations: int = 1,
        thin_by: int = 1,
        store: bool = True,
        skip_initial_state_check: bool = False,
    ) -> typing.Iterator[EnsembleState]:
        """Advance the ensemble, yielding the state every ``thin_by`` steps.

        Parameters
        ----------
        initial_state : EnsembleState or array_like
            Starting positions, shape ``(nwalkers, ndim)``, or a state returned
            by an earlier call.
        iterations : int, optional
            Number of *stored* states to generate; ``iterations * thin_by``
            steps are taken per walker.
        thin_by : int, optional
            Keep only every ``thin_by``-th step.
        store : bool, optional
            Append the yielded states to the stored chain.
        skip_initial_state_check : bool, optional
            Skip the :func:`walkers_independent` test of the initial positions.

        Yields
        ------
        EnsembleState
            The ensemble state after each kept step.
        """
        state = EnsembleState(initial_state)
        if state.coords.shape != (self.nwalkers, self.ndim):
            raise ValueError(
                f"initial state has shape {state.coords.shape}, "
                f"expected {(self.nwalkers, self.ndim)}"
            )
        if not skip_initial_state_check and not walkers_independent(state.coords):
            raise ValueError(
                "Initial state has a large condition number. The walkers span less than "
                "the full parameter space, so the chain cannot explore it -- spread them out."
            )
        if state.log_prob is None:
            state.log_prob, state.blobs = self.compute_log_prob(state.coords)
        if np.shape(state.log_prob) != (self.nwalkers,):
            raise ValueError("the supplied log-probability does not have one entry per walker")
        if np.any(np.isnan(state.log_prob)):
            raise ValueError("the initial log-probability was NaN")

        thin_by = int(thin_by)
        if thin_by <= 0:
            raise ValueError("thin_by must be a positive integer")
        iterations = int(iterations)
        if store:
            self._grow(iterations, state.blobs)

        for _ in range(iterations):
            for _ in range(thin_by):
                state, accepted = self._step(state)
            if store:
                self._save_step(state, accepted)
            yield state

    def run_mcmc(self, initial_state, nsteps: int, **kwargs) -> EnsembleState:
        """Run :meth:`sample` to completion and return the final state.

        Parameters
        ----------
        initial_state : EnsembleState, array_like or None
            Starting positions. ``None`` resumes where the previous call left
            off.
        nsteps : int
            Number of *stored* states to generate.
        **kwargs
            Passed to :meth:`sample`.

        Returns
        -------
        EnsembleState
            The final state, ready to be handed back in to continue the run.
        """
        if initial_state is None:
            if self._previous_state is None:
                raise ValueError("run_mcmc has never been called, so there is nothing to resume")
            initial_state = self._previous_state
        result = None
        for result in self.sample(initial_state, iterations=int(nsteps), **kwargs):
            pass
        self._previous_state = result
        return result


class EnsembleSampler(_EnsembleSamplerBase):
    """Affine-invariant ensemble sampler using the stretch move.

    One log-probability evaluation per walker per step. See the module
    docstring for the move and its acceptance rule.

    Parameters
    ----------
    nwalkers : int
        Number of walkers. The move needs at least ``2 * ndim`` walkers to span
        the space; fewer raises unless ``live_dangerously`` is set.
    ndim : int
        Number of sampled dimensions.
    log_prob_fn : callable
        Log-probability function, see :class:`_EnsembleSamplerBase`.
    stretch_scale : float, optional
        The stretch parameter :math:`a`; larger values propose bolder moves.
        The default of ``2.0`` is the standard choice and gives an acceptance
        fraction near 0.3 on well-scaled targets.
    live_dangerously : bool, optional
        Skip the ``nwalkers >= 2 * ndim`` requirement.
    **kwargs
        ``args``, ``kwargs``, ``pool``, ``vectorize`` and ``seed``, see
        :class:`_EnsembleSamplerBase`.

    Notes
    -----
    ``run_mcmc`` counts ``nsteps`` in *stored* states: with ``thin_by=k`` it
    takes ``nsteps * k`` steps per walker and keeps every ``k``-th.
    """

    def __init__(
        self,
        nwalkers: int,
        ndim: int,
        log_prob_fn: typing.Callable,
        stretch_scale: float = 2.0,
        live_dangerously: bool = False,
        **kwargs,
    ):
        self.stretch_scale = float(stretch_scale)
        self.live_dangerously = bool(live_dangerously)
        super().__init__(nwalkers, ndim, log_prob_fn, **kwargs)
        if self.nwalkers < 2 * self.ndim and not self.live_dangerously:
            raise ValueError(
                f"an ensemble of {self.nwalkers} walkers cannot span {self.ndim} dimensions; "
                f"use at least {2 * self.ndim} walkers"
            )

    def _step(self, state: EnsembleState) -> tuple:
        """Propose one stretch move per walker and accept or reject each.

        Parameters
        ----------
        state : EnsembleState
            Current state; updated in place for accepted moves.

        Returns
        -------
        state : EnsembleState
            The updated state.
        accepted : numpy.ndarray
            Boolean per-walker acceptance flags.
        """
        a = self.stretch_scale
        accepted = np.zeros(self.nwalkers, dtype=bool)

        for active, complement in self._halves():
            s = state.coords[active]
            c = state.coords[complement]
            n_s = len(active)
            # z ~ g(z) ∝ 1/sqrt(z) on [1/a, a], drawn by inverting its CDF.
            z = ((a - 1.0) * self.random.random(n_s) + 1.0) ** 2 / a
            partners = c[self.random.integers(len(c), size=n_s)]
            q = partners - (partners - s) * z[:, None]
            factors = (self.ndim - 1.0) * np.log(z)

            new_log_prob, new_blobs = self.compute_log_prob(q)
            with np.errstate(invalid="ignore"):
                # A NaN difference (both ends at -inf) compares False, i.e. rejects.
                take = (factors + new_log_prob - state.log_prob[active]) > np.log(
                    self.random.random(n_s)
                )

            idx = active[take]
            state.coords[idx] = q[take]
            state.log_prob[idx] = new_log_prob[take]
            if new_blobs is not None:
                if state.blobs is None:
                    raise ValueError(
                        "a state supplied with a log-probability must also carry its blobs"
                    )
                state.blobs[idx] = new_blobs[take]
            accepted[idx] = True

        return state, accepted


class DifferentialMove:
    """Directions drawn as differences between two complementary walkers.

    The cheapest direction proposal that is still affine invariant, and the
    right default while the ensemble is still spread out over the posterior.

    Parameters
    ----------
    scale : float, optional
        Multiplies the difference vector.
    """

    name = "differential"

    def __init__(self, scale: float = 1.0):
        self.scale = float(scale)

    def get_direction(self, complement: np.ndarray, n: int, random) -> np.ndarray:
        """Return ``n`` direction vectors built from the complementary half.

        Parameters
        ----------
        complement : numpy.ndarray
            Positions of the walkers not being moved, shape ``(m, ndim)``.
        n : int
            Number of directions to return.
        random : numpy.random.Generator
            Random generator to draw from.

        Returns
        -------
        numpy.ndarray
            Directions, shape ``(n, ndim)``.
        """
        m = len(complement)
        i = random.integers(m, size=n)
        j = random.integers(m - 1, size=n)
        # Map j into "any index except i" so the pair is never degenerate.
        j = j + (j >= i)
        return self.scale * (complement[i] - complement[j])


class CovarianceMove:
    """Directions drawn from the covariance of the complementary walkers.

    A whole-ensemble Gaussian direction: it points along the posterior's
    principal axes rather than at another walker, which moves further on a
    strongly correlated target than a single difference vector does.

    Parameters
    ----------
    epsilon : float, optional
        Ridge added to the covariance diagonal for numerical stability.
    """

    name = "covariance"

    def __init__(self, epsilon: float = 1e-6):
        self.epsilon = float(epsilon)

    def _factor(self, cov: np.ndarray) -> np.ndarray:
        """Return a matrix ``L`` with ``L L^T = cov``.

        Parameters
        ----------
        cov : numpy.ndarray
            Covariance estimate, shape ``(ndim, ndim)``.

        Returns
        -------
        numpy.ndarray
            Cholesky factor, or an eigenvalue-clipped square root when the
            covariance is not positive definite (which it is not whenever there
            are fewer walkers than dimensions).
        """
        try:
            return np.linalg.cholesky(cov)
        except np.linalg.LinAlgError:
            vals, vecs = np.linalg.eigh(cov)
            return vecs @ np.diag(np.sqrt(np.maximum(vals, self.epsilon)))

    def _covariance(self, complement: np.ndarray) -> np.ndarray:
        """Return the regularised covariance of the complementary walkers.

        Parameters
        ----------
        complement : numpy.ndarray
            Positions of the walkers not being moved.

        Returns
        -------
        numpy.ndarray
            Covariance with a ridge on the diagonal.
        """
        centred = complement - np.mean(complement, axis=0)
        cov = centred.T @ centred / max(1, len(complement) - 1)
        return cov + np.eye(complement.shape[1]) * self.epsilon

    def get_direction(self, complement: np.ndarray, n: int, random) -> np.ndarray:
        """Return ``n`` Gaussian directions with the complement's covariance.

        Parameters
        ----------
        complement : numpy.ndarray
            Positions of the walkers not being moved, shape ``(m, ndim)``.
        n : int
            Number of directions to return.
        random : numpy.random.Generator
            Random generator to draw from.

        Returns
        -------
        numpy.ndarray
            Directions, shape ``(n, ndim)``.
        """
        factor = self._factor(self._covariance(complement))
        return random.standard_normal((n, complement.shape[1])) @ factor.T


class AdaptiveCovarianceMove(CovarianceMove):
    """Covariance directions from an exponentially weighted running estimate.

    The plain :class:`CovarianceMove` re-estimates the covariance from one half
    of the ensemble at every step, which is noisy when the walkers are few.
    Averaging that estimate over the run trades a little adaptivity for a much
    steadier direction.

    Parameters
    ----------
    alpha : float, optional
        Weight kept from the previous estimate at each update.
    epsilon : float, optional
        Ridge added to the covariance diagonal for numerical stability.
    """

    name = "adaptive_covariance"

    def __init__(self, alpha: float = 0.9, epsilon: float = 1e-6):
        super().__init__(epsilon=epsilon)
        self.alpha = float(alpha)
        self.cov: np.ndarray | None = None

    def _covariance(self, complement: np.ndarray) -> np.ndarray:
        """Update and return the exponentially weighted covariance.

        Parameters
        ----------
        complement : numpy.ndarray
            Positions of the walkers not being moved.

        Returns
        -------
        numpy.ndarray
            The running covariance estimate.
        """
        current = super()._covariance(complement)
        if self.cov is None or self.cov.shape != current.shape:
            self.cov = current
        else:
            self.cov = self.alpha * self.cov + (1.0 - self.alpha) * current
        return self.cov


class EnsembleSliceSampler(_EnsembleSamplerBase):
    """Ensemble slice sampler with an adaptive length scale.

    Every walker moves at every step: a direction comes from the complementary
    half of the ensemble and the walker is then slice-sampled along it, so there
    is no accept/reject and no step size to set. The length scale ``mu`` is
    tuned from the ratio of interval expansions to contractions towards the
    value that makes stepping-out and shrinking equally frequent. See the module
    docstring for the algorithm and the reference.

    This costs several log-probability evaluations per walker per step, which
    :attr:`n_evaluations` reports -- compare samplers by effective samples per
    evaluation, not per step.

    Parameters
    ----------
    nwalkers : int
        Number of walkers.
    ndim : int
        Number of sampled dimensions.
    log_prob_fn : callable
        Log-probability function, see :class:`_EnsembleSamplerBase`.
    moves : object or list, optional
        Direction proposal(s): a single move, a list of moves, or a list of
        ``(move, weight)`` pairs. Defaults to a :class:`DifferentialMove` and a
        :class:`CovarianceMove` in equal measure, which covers both a
        walker-to-walker difference and the ensemble's principal axes.
    tune : bool, optional
        Adapt the length scale ``mu``. Adaptation stops on its own once the
        expansion ratio has settled, so the chain is asymptotically valid; the
        tuning steps are still best discarded as burn-in.
    max_steps : int, optional
        Budget of stepping-out expansions per side, which bounds the cost of a
        single walker update.
    max_iter : int, optional
        Hard cap on the number of shrinking iterations, after which a walker
        stays where it is.
    tolerance, patience : float, int, optional
        Tuning stops after ``patience`` consecutive steps whose expansion ratio
        is within ``tolerance`` of one half.
    **kwargs
        ``args``, ``kwargs``, ``pool``, ``vectorize`` and ``seed``, see
        :class:`_EnsembleSamplerBase`.

    Attributes
    ----------
    mu : float
        Current length scale multiplying every proposed direction.
    tuning : bool
        Whether the length scale is still being adapted.
    """

    def __init__(
        self,
        nwalkers: int,
        ndim: int,
        log_prob_fn: typing.Callable,
        moves=None,
        tune: bool = True,
        max_steps: int = 50,
        max_iter: int = 1000,
        tolerance: float = 0.1,
        patience: int = 5,
        **kwargs,
    ):
        self._moves, self._weights = _parse_moves(moves)
        self.tuning = bool(tune)
        self.max_steps = int(max_steps)
        self.max_iter = int(max_iter)
        self.tolerance = float(tolerance)
        self.patience = int(patience)
        self.mu = 1.0
        self._settled = 0
        super().__init__(nwalkers, ndim, log_prob_fn, **kwargs)

    def _step(self, state: EnsembleState) -> tuple:
        """Slice-sample every walker once along an ensemble direction.

        Parameters
        ----------
        state : EnsembleState
            Current state; updated in place.

        Returns
        -------
        state : EnsembleState
            The updated state.
        moved : numpy.ndarray
            Boolean per-walker flags; ``False`` only for a walker that
            exhausted ``max_iter`` without finding a point on its slice.
        """
        move = self._moves[self.random.choice(len(self._moves), p=self._weights)]
        moved = np.zeros(self.nwalkers, dtype=bool)
        n_expand = n_contract = 0

        for active, complement in self._halves():
            n = len(active)
            directions = self.mu * move.get_direction(state.coords[complement], n, self.random)
            x0 = state.coords[active]
            # Slice height: uniform under the density, i.e. exponential below
            # the log-density.
            height = state.log_prob[active] - self.random.exponential(size=n)

            left = -self.random.random(n)
            right = left + 1.0
            n_expand += self._step_out(x0, directions, height, left, right)
            new_x, new_lp, new_blobs, found, contractions = self._shrink(
                x0, directions, height, left, right
            )
            n_contract += contractions

            idx = active[found]
            state.coords[idx] = new_x[found]
            state.log_prob[idx] = new_lp[found]
            if new_blobs is not None:
                if state.blobs is None:
                    raise ValueError(
                        "a state supplied with a log-probability must also carry its blobs"
                    )
                state.blobs[idx] = new_blobs[found]
            moved[idx] = True

        self._tune(n_expand, n_contract)
        return state, moved

    def _step_out(self, x0, directions, height, left, right) -> int:
        """Expand the interval until both ends fall below the slice height.

        ``left`` and ``right`` are modified in place.

        Parameters
        ----------
        x0 : numpy.ndarray
            Current positions of the walkers being moved.
        directions : numpy.ndarray
            Direction vectors, one per walker.
        height : numpy.ndarray
            Log-density level of each walker's slice.
        left, right : numpy.ndarray
            Interval bounds in units of ``directions``.

        Returns
        -------
        int
            Number of successful expansions, which the tuning weighs against
            the number of contractions.
        """
        n = len(x0)
        # Split the expansion budget randomly between the two sides, as in
        # Karamanis & Beutler: the total cost per walker is then bounded.
        budget_left = np.floor(self.max_steps * self.random.random(n))
        budget_right = (self.max_steps - 1) - budget_left
        open_left = np.ones(n, dtype=bool)
        open_right = np.ones(n, dtype=bool)
        n_expand = 0

        for _ in range(self.max_iter):
            grow_left = open_left & (budget_left > 0)
            grow_right = open_right & (budget_right > 0)
            if not np.any(grow_left) and not np.any(grow_right):
                break
            # The *current* endpoint is probed, and the interval grows while it
            # is still inside the slice. Probing the prospective endpoint
            # instead would leave the interval one step short of covering the
            # slice, truncating its tails and reporting a posterior that is
            # systematically too narrow.
            probe = np.concatenate(
                (
                    x0[grow_left] + directions[grow_left] * left[grow_left][:, None],
                    x0[grow_right] + directions[grow_right] * right[grow_right][:, None],
                )
            )
            log_prob, _ = self.compute_log_prob(probe)
            n_left = int(np.count_nonzero(grow_left))
            lp_left, lp_right = log_prob[:n_left], log_prob[n_left:]

            i_left = np.flatnonzero(grow_left)
            inside = lp_left > height[i_left]
            left[i_left[inside]] -= 1.0
            budget_left[i_left[inside]] -= 1
            open_left[i_left[~inside]] = False
            n_expand += int(np.count_nonzero(inside))

            i_right = np.flatnonzero(grow_right)
            inside = lp_right > height[i_right]
            right[i_right[inside]] += 1.0
            budget_right[i_right[inside]] -= 1
            open_right[i_right[~inside]] = False
            n_expand += int(np.count_nonzero(inside))

        return n_expand

    def _shrink(self, x0, directions, height, left, right) -> tuple:
        """Draw from the interval, shrinking it, until a point is on the slice.

        Parameters
        ----------
        x0 : numpy.ndarray
            Current positions of the walkers being moved.
        directions : numpy.ndarray
            Direction vectors, one per walker.
        height : numpy.ndarray
            Log-density level of each walker's slice.
        left, right : numpy.ndarray
            Interval bounds from :meth:`_step_out`; modified in place.

        Returns
        -------
        new_x : numpy.ndarray
            Accepted positions (the old position where none was found).
        new_log_prob : numpy.ndarray
            Log-probability at ``new_x``.
        blobs : numpy.ndarray or None
            Blobs at ``new_x``, or ``None`` if the log-probability returns none.
        found : numpy.ndarray
            Boolean flags marking the walkers that landed on their slice.
        n_contract : int
            Number of interval contractions, used for tuning.
        """
        n = len(x0)
        pending = np.ones(n, dtype=bool)
        new_x = np.array(x0, dtype=np.float64)
        new_log_prob = np.array(height, dtype=np.float64)
        blobs = None
        n_contract = 0

        for _ in range(self.max_iter):
            if not np.any(pending):
                break
            idx = np.flatnonzero(pending)
            u = self.random.uniform(left[idx], right[idx])
            probe = x0[idx] + directions[idx] * u[:, None]
            log_prob, probe_blobs = self.compute_log_prob(probe)
            if probe_blobs is not None and blobs is None:
                blobs = np.zeros((n,) + probe_blobs.shape[1:], dtype=probe_blobs.dtype)

            on_slice = log_prob > height[idx]
            hit = idx[on_slice]
            new_x[hit] = probe[on_slice]
            new_log_prob[hit] = log_prob[on_slice]
            if probe_blobs is not None:
                blobs[hit] = probe_blobs[on_slice]
            pending[hit] = False

            miss = idx[~on_slice]
            u_miss = u[~on_slice]
            shrink_left = u_miss < 0
            left[miss[shrink_left]] = u_miss[shrink_left]
            right[miss[~shrink_left]] = u_miss[~shrink_left]
            n_contract += int(len(miss))

        found = ~pending
        if blobs is not None and np.any(pending):
            # Walkers that never landed keep their previous blobs; the caller
            # only writes back the ones that moved.
            blobs[pending] = 0
        return new_x, new_log_prob, blobs, found, n_contract

    def _tune(self, n_expand: int, n_contract: int) -> None:
        """Adapt the length scale from the expansion/contraction balance.

        Parameters
        ----------
        n_expand : int
            Successful stepping-out expansions in this step.
        n_contract : int
            Interval contractions in this step.
        """
        if not self.tuning:
            return
        total = n_expand + n_contract
        if total <= 0:
            return
        ratio = max(1, n_expand) / float(total)
        self.mu = float(np.clip(self.mu * 2.0 * ratio, 1e-3, 1e3))
        if abs(ratio - 0.5) < self.tolerance:
            self._settled += 1
        else:
            self._settled = 0
        if self._settled > self.patience:
            self.tuning = False


def _parse_moves(moves) -> tuple:
    """Normalise a move specification into parallel move and weight lists.

    Parameters
    ----------
    moves : None, object, or list
        A single move, a list of moves, or a list of ``(move, weight)`` pairs.
        ``None`` selects the default mixture.

    Returns
    -------
    moves : list
        The move objects.
    weights : numpy.ndarray
        Their normalised selection probabilities.
    """
    if moves is None:
        moves = [DifferentialMove(), CovarianceMove()]
    if not isinstance(moves, (list, tuple)):
        return [moves], np.ones(1)
    if moves and isinstance(moves[0], (list, tuple)):
        items, weights = zip(*moves)
        items = list(items)
        weights = np.asarray(weights, dtype=np.float64)
    else:
        items = list(moves)
        weights = np.ones(len(items), dtype=np.float64)
    if not items:
        raise ValueError("at least one move is required")
    total = float(np.sum(weights))
    if total <= 0:
        raise ValueError("move weights must sum to a positive number")
    return items, weights / total


def _split_blobs(results) -> tuple:
    """Separate log-probabilities from any trailing blob values.

    Parameters
    ----------
    results : sequence or numpy.ndarray
        Return values of the log-probability function, one per walker: a scalar
        each, a tuple ``(log_prob, *blobs)`` each, or -- in the vectorised case
        -- a single array of log-probabilities.

    Returns
    -------
    log_prob : numpy.ndarray
        Log-probability per walker.
    blobs : numpy.ndarray or None
        Blob values, shape ``(n_walkers, n_blobs)``, or ``None``.
    """
    if isinstance(results, np.ndarray) and results.dtype != object:
        return np.asarray(results, dtype=np.float64).ravel(), None

    results = list(results)
    if not results:
        return np.empty(0, dtype=np.float64), None
    first = results[0]
    if np.isscalar(first) or (isinstance(first, np.ndarray) and first.ndim == 0):
        return np.array([float(r) for r in results], dtype=np.float64), None

    try:
        log_prob = np.array([float(np.asarray(r[0]).item()) for r in results], dtype=np.float64)
        raw = [tuple(r[1:]) for r in results]
    except (TypeError, IndexError, ValueError):
        return np.array([float(np.asarray(r).item()) for r in results], dtype=np.float64), None

    if not raw or not len(raw[0]):
        return log_prob, None
    try:
        blobs = np.array(raw, dtype=np.float64)
    except (TypeError, ValueError):
        blobs = np.array(raw, dtype=object)
    return log_prob, blobs
