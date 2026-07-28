r"""Hidden-Markov-model analysis of binned time series (Qt-free).

The one place in ChiSurf where a binned trace is turned into states, dwell
times and a transition matrix. Everything above it -- the GUI tool, the RPC
service, the CLI, and the plugins that show intensity traces -- calls these
functions rather than driving :class:`chisurf.core.math.hmm.GaussianHMM`
themselves, so that state ordering, dwell-time definition and model selection
stay the same wherever states are reported.

Four conventions are fixed here, and they are the reason this module exists
rather than each tool calling the estimator itself:

1. **States are ordered by increasing total emission mean**, so state 0 is the
   dimmest. EM assigns labels arbitrarily; without the convention, "state 1"
   would mean something different in every fit, table and figure, and no two
   tools could be compared.
2. **A dwell is never continued across a sequence boundary.** Two traces that
   happen to end and start in the same state are two visits, not one -- the gap
   between them is not observed time.
3. **Rates are the short-bin limit** :math:`k_{ij} \approx A_{ij}/\Delta t`,
   reported with the diagonal set to the negative row sum so the result reads
   as a generator matrix. The approximation is documented on
   :func:`transition_rates`, including where it fails.
4. **The state count is chosen by AIC/BIC**, never by the likelihood, which
   always improves when a state is added.

Anything that needs states out of a measurement calls these functions; the
estimator (:mod:`chisurf.core.math.hmm`) stays free of analysis policy.
"""

from __future__ import annotations

import logging

import numpy as np

from chisurf.core.math.hmm import GaussianHMM

from ..api.models import HmmFit, HmmSettings, StateScan, StateSummary

__all__ = [
    "as_matrix",
    "dwell_times",
    "fit_traces",
    "scan_state_counts",
    "state_segments",
]

logger = logging.getLogger(__name__)


def as_matrix(traces) -> tuple[np.ndarray, list[int]]:
    """Normalise any accepted trace input into one matrix plus sequence lengths.

    Parameters
    ----------
    traces : array-like or sequence of array-like
        Either one ``(n_bins, n_features)`` matrix (a 1-D array is read as a
        single feature), or a sequence of such matrices to be fitted jointly as
        separate sequences.

    Returns
    -------
    X : numpy.ndarray
        Samples stacked row-wise, shape ``(total_bins, n_features)``.
    lengths : list of int
        Length of each sequence, summing to ``len(X)``.

    Raises
    ------
    ValueError
        If the sequences disagree on the number of features, or nothing was
        given.

    Notes
    -----
    ``[[1, 2], [3, 4]]`` is ambiguous -- two bins of two channels, or two
    single-channel sequences of two bins? It is resolved by *what the elements
    are*, which turns out to separate the two real callers cleanly:

    * a **list of arrays** means several sequences -- a caller holding traces
      holds arrays, and passing a list of them is how joint fitting is asked
      for;
    * a **nested list of numbers** means one matrix, rows being time bins --
      that is the JSON shape the RPC service receives.

    Getting this wrong is not a small error: three 1-D traces read as one matrix
    become three bins of six thousand channels, and the fit then quietly
    estimates millions of parameters from a handful of points. Passing 2-D
    arrays is unambiguous under either rule.
    """
    if isinstance(traces, np.ndarray):
        sequences = [traces]
    elif isinstance(traces, (list, tuple)) and len(traces):
        holds_arrays = any(isinstance(t, np.ndarray) for t in traces)
        if holds_arrays or np.ndim(traces[0]) >= 2:
            sequences = list(traces)
        else:
            try:
                sequences = [np.asarray(traces, dtype=float)]
            except ValueError:
                # Ragged nested lists can only be separate sequences.
                sequences = list(traces)
    else:
        sequences = [np.asarray(traces, dtype=float)]

    matrices = []
    for sequence in sequences:
        matrix = np.asarray(sequence, dtype=float)
        if matrix.ndim == 1:
            matrix = matrix[:, None]
        if matrix.ndim != 2:
            raise ValueError(f"a trace must be 1- or 2-dimensional, got shape {matrix.shape}")
        matrices.append(matrix)
    if not matrices or sum(len(m) for m in matrices) == 0:
        raise ValueError("no data to fit")
    n_features = matrices[0].shape[1]
    if any(m.shape[1] != n_features for m in matrices):
        raise ValueError("all traces must have the same number of features")
    total_bins = sum(len(m) for m in matrices)
    if n_features > total_bins:
        # Almost always a transposed trace: detection channels outnumber time
        # bins in no real measurement, and the fit that follows would estimate
        # far more parameters than there are data points.
        logger.warning(
            "%d features but only %d time bins -- is the trace transposed? "
            "Rows are time bins, columns are channels.",
            n_features,
            total_bins,
        )
    return np.concatenate(matrices), [len(m) for m in matrices]


def dwell_times(states, time_step: float = 1.0, lengths=None) -> dict[int, list[float]]:
    """Return the durations of every uninterrupted visit to each state.

    Parameters
    ----------
    states : array-like of int
        Decoded state per time bin.
    time_step : float
        Duration of one bin; the dwell times come back in these units.
    lengths : sequence of int, optional
        Sequence boundaries. A run is never continued across one -- two
        sequences that happen to end and start in the same state are two
        visits, not one.

    Returns
    -------
    dict
        State index to the list of its dwell times.
    """
    states = np.asarray(states, dtype=int)
    result: dict[int, list[float]] = {}
    if states.size == 0:
        return result
    bounds = np.cumsum(lengths) if lengths is not None else [len(states)]
    start = 0
    for end in bounds:
        segment = states[start:end]
        start = end
        if segment.size == 0:
            continue
        # A run ends wherever the label changes; the boundaries give the lengths.
        changes = np.flatnonzero(np.diff(segment)) + 1
        edges = np.concatenate([[0], changes, [len(segment)]])
        for begin, finish in zip(edges[:-1], edges[1:]):
            result.setdefault(int(segment[begin]), []).append((finish - begin) * time_step)
    return result


def state_segments(states, lengths=None) -> list[tuple[int, int, int]]:
    """Return the decoded path as ``(state, start_bin, stop_bin)`` runs.

    ``stop_bin`` is exclusive. This is what a trace plot needs to colour the
    path without drawing one item per bin.
    """
    states = np.asarray(states, dtype=int)
    if states.size == 0:
        return []
    bounds = np.cumsum(lengths) if lengths is not None else [len(states)]
    segments = []
    start = 0
    for end in bounds:
        segment = states[start:end]
        if segment.size:
            changes = np.flatnonzero(np.diff(segment)) + 1
            edges = np.concatenate([[0], changes, [len(segment)]])
            segments += [
                (int(segment[b]), int(start + b), int(start + f))
                for b, f in zip(edges[:-1], edges[1:])
            ]
        start = end
    return segments


def _build_model(settings: HmmSettings, n_states: int | None = None) -> GaussianHMM:
    """Return a :class:`GaussianHMM` configured from ``settings``."""
    return GaussianHMM(
        n_components=int(n_states or settings.n_states),
        covariance_type=settings.covariance_type,
        min_covar=settings.min_covar,
        algorithm=settings.decode,
        n_iter=settings.n_iter,
        tol=settings.tol,
        accelerate=settings.accelerate,
        random_state=settings.random_state,
    )


def _ordering(model: GaussianHMM) -> np.ndarray:
    """Return the permutation sorting the model's states by total emission mean."""
    return np.argsort(model.means_.sum(axis=1))


def fit_traces(traces, settings: HmmSettings | None = None) -> HmmFit:
    """Fit a Gaussian HMM to one or more binned traces and summarise it.

    Parameters
    ----------
    traces : array-like or sequence of array-like
        Binned trace(s); see :func:`as_matrix`.
    settings : HmmSettings, optional
        Fit settings; the defaults fit two states with full covariances.

    Returns
    -------
    HmmFit
        The fitted model, the decoded path and the derived per-state summaries,
        with states ordered from dimmest to brightest.

    Notes
    -----
    Several traces passed together are fitted **jointly as separate
    sequences**: they share one set of states and transitions, but no transition
    is counted across the seam between two of them. That is what repeats of one
    experiment need, and it is not the same as concatenating them.

    The returned object is complete enough to hand across a process boundary --
    :meth:`~...api.models.HmmFit.to_dict` is what the RPC service returns -- so
    a caller never needs the live model back to report a result.

    Examples
    --------
    >>> from chisurf.plugins.core.hmm.api import HmmSettings
    >>> fit = fit_traces(counts, HmmSettings(n_states=2, time_step=1e-3))  # doctest: +SKIP
    >>> fit.summaries[0].mean_dwell     # seconds in the dimmest state  # doctest: +SKIP
    >>> fit.transition_rates            # 1/s, rows summing to zero     # doctest: +SKIP
    """
    settings = settings or HmmSettings()
    X, lengths = as_matrix(traces)
    model = _build_model(settings)
    model.fit(X, lengths)

    order = _ordering(model)
    relabel = np.argsort(order)
    states = relabel[model.predict(X, lengths)]

    covars = model.covars_full_[order]
    variances = np.diagonal(covars, axis1=1, axis2=2)
    dwells = dwell_times(states, settings.time_step, lengths)
    occupancy = np.bincount(states, minlength=settings.n_states) / max(len(states), 1)

    summaries = []
    for index in range(model.n_components):
        durations = dwells.get(index, [])
        summaries.append(
            StateSummary(
                index=index,
                mean=model.means_[order][index].tolist(),
                std=np.sqrt(variances[index]).tolist(),
                occupancy=float(occupancy[index]),
                n_dwells=len(durations),
                mean_dwell=float(np.mean(durations)) if durations else 0.0,
            )
        )

    transmat = model.transmat_[np.ix_(order, order)]
    return HmmFit(
        settings=settings,
        n_states=model.n_components,
        log_likelihood=float(model.score(X, lengths)),
        aic=float(model.aic(X, lengths)),
        bic=float(model.bic(X, lengths)),
        converged=bool(model.monitor_.converged),
        n_iterations=int(model.monitor_.iter),
        startprob=model.startprob_[order].tolist(),
        transmat=transmat.tolist(),
        means=model.means_[order].tolist(),
        covars=np.asarray(model.covars_)[order].tolist()
        if model.covariance_type != "tied"
        else np.asarray(model.covars_).tolist(),
        states=states.tolist(),
        lengths=lengths,
        summaries=summaries,
        dwell_times=[dwells.get(i, []) for i in range(model.n_components)],
        transition_rates=transition_rates(transmat, settings.time_step).tolist(),
    )


def transition_rates(transmat, time_step: float = 1.0) -> np.ndarray:
    r"""Convert a per-bin transition matrix into a rate matrix.

    Parameters
    ----------
    transmat : array-like
        Row-stochastic transition probabilities per time bin.
    time_step : float
        Duration of one bin.

    Returns
    -------
    numpy.ndarray
        ``k[i, j] = P[i, j] / dt`` off the diagonal, with the diagonal set to
        the negative row sum so that the rows sum to zero, as a generator
        matrix does.

    Notes
    -----
    This is the short-bin approximation :math:`P \approx I + K\,\Delta t`,
    which holds while a state survives many bins. It becomes wrong once the
    off-diagonal probabilities are no longer small -- bin faster, or take the
    matrix logarithm, if a state turns over within a few bins.
    """
    transmat = np.asarray(transmat, dtype=float)
    rates = transmat / max(time_step, np.finfo(float).tiny)
    np.fill_diagonal(rates, 0.0)
    np.fill_diagonal(rates, -rates.sum(axis=1))
    return rates


def scan_state_counts(
    traces, settings: HmmSettings | None = None, min_states: int = 1, max_states: int = 6
) -> StateScan:
    """Fit a range of state counts and score each by AIC and BIC.

    Parameters
    ----------
    traces : array-like or sequence of array-like
        Binned trace(s); see :func:`as_matrix`.
    settings : HmmSettings, optional
        Fit settings; ``n_states`` is overridden by the scan.
    min_states, max_states : int
        Inclusive range of state counts to try.

    Returns
    -------
    StateScan
        The criteria per state count. Both criteria trade likelihood against
        parameter count; BIC charges more per parameter and so tends to pick
        the smaller model, which is usually what a kinetic interpretation
        wants.

    Notes
    -----
    Take the **minimum** of the criterion, not the elbow of the likelihood: the
    likelihood improves with every state added and can never choose. A fit that
    fails scores ``nan`` rather than aborting the scan, so one pathological
    state count does not cost the whole curve.

    A criterion still falling at the top of the range is evidence against the
    model rather than for many states -- bleaching, drift, or a continuum of
    states instead of discrete ones will all show up that way.
    """
    settings = settings or HmmSettings()
    X, lengths = as_matrix(traces)
    scan = StateScan()
    for n_states in range(int(min_states), int(max_states) + 1):
        scan.n_states.append(n_states)
        try:
            model = _build_model(settings, n_states)
            model.fit(X, lengths)
            scan.log_likelihood.append(float(model.score(X, lengths)))
            scan.aic.append(float(model.aic(X, lengths)))
            scan.bic.append(float(model.bic(X, lengths)))
        except Exception as exc:
            logger.warning("HMM fit with %d states failed: %s", n_states, exc)
            for values in (scan.log_likelihood, scan.aic, scan.bic):
                values.append(float("nan"))
    if scan.n_states:
        counts = np.asarray(scan.n_states)
        for name, values in (("best_bic", scan.bic), ("best_aic", scan.aic)):
            criterion = np.asarray(values, dtype=float)
            best = int(counts[np.nanargmin(criterion)]) if np.isfinite(criterion).any() else 0
            setattr(scan, name, best)
    return scan
