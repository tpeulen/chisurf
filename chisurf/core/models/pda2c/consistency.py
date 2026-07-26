"""Kinetic consistency check for fitted PDA models (PRD-50, scope item 5).

A PDA fit answers "which parameters best describe the histogram", never
"*could* this scheme have produced the histogram at all". Those are different
questions: a two-state scheme forced onto a three-state system still returns a
best fit, and with enough bursts a barely-wrong model reaches a reduced
chi-squared far from one without that number meaning anything calibrated --
the 1D E-histogram bins are neither independent nor Gaussian (they are
projections of a sparse S1S2 matrix, with many low-count bins).

The consistency check answers the second question by **parametric bootstrap**.
Bursts are resampled from the *fitted* scheme, each resample is scored against
the fitted expectation with the same statistic the fit minimises, and the
measured score is placed in that empirical distribution. The resulting p-value
is calibrated by construction: it needs no assumption about the reference
distribution of the statistic, because the reference distribution is simulated.

This is the counterpart of the incumbent suite's "consistency check", and it
reuses the same forward model as the dynamic-PDA simulator -- bursts are drawn
from the photon-number distribution ``pF`` and split with the per-photon green
probabilities of the fitted amplitude spectrum.
"""

from __future__ import annotations

import numpy as np

#: 1D E-histogram settings used by the PDA residual (mirrors ``common``).
DEFAULT_HIST_KWARGS = {
    "x_max": 1.0,
    "x_min": 0.0,
    "log_x": False,
    "n_bins": 81,
    "n_min": 10,
}


def resample_s1s2(
        pF,
        amplitudes,
        probabilities,
        n_bursts: int,
        background_ch1: float = 0.0,
        background_ch2: float = 0.0,
        seed: int = 1,
        n_max: int | None = None,
) -> np.ndarray:
    """Draw a synthetic S1S2 histogram from a PDA amplitude spectrum.

    Implements the PDA forward model as a generator rather than as the
    probability convolution ``tttrlib.Pda`` evaluates: each burst draws a
    *signal* photon number from ``pF``, a species from ``amplitudes``, splits
    the signal binomially at that species' per-photon green probability, and
    adds independent Poisson background to each channel.

    Background is **added on top of** ``pF`` rather than carved out of it, which
    is the engine's convention: its mean total burst size is the mean of ``pF``
    plus ``background_ch1 + background_ch2``. Getting this backwards leaves a
    total-variation discrepancy of ~0.29 against the engine that no amount of
    sampling removes.

    Parameters
    ----------
    pF : array_like
        Signal photon-number distribution; ``pF[n]`` is the probability of a
        burst with ``n`` signal photons. Normalised internally.
    amplitudes : array_like
        Species weights of the fitted probability spectrum. Normalised
        internally.
    probabilities : array_like
        Per-photon channel-1 (green) probability of each species; same length
        as ``amplitudes``.
    n_bursts : int
        Number of bursts to draw.
    background_ch1, background_ch2 : float, optional
        Mean background photons per burst in each channel. Default 0.
    seed : int, optional
        Seed of the random generator. Default 1.
    n_max : int, optional
        Size of the returned matrix minus one. Defaults to ``len(pF) - 1``.

    Returns
    -------
    numpy.ndarray
        Counts of shape ``(n_max + 1, n_max + 1)`` indexed ``[green, red]``, in
        the same layout as the experimental ``data.pda['s1s2']``. Bursts falling
        outside the matrix are dropped, matching the engine's ``hist2d_nmax``.
    """
    pF = np.asarray(pF, dtype=float)
    amplitudes = np.asarray(amplitudes, dtype=float)
    probabilities = np.clip(np.asarray(probabilities, dtype=float), 0.0, 1.0)
    if pF.sum() <= 0.0 or amplitudes.sum() <= 0.0:
        raise ValueError("pF and amplitudes must have positive total weight")
    pF = pF / pF.sum()
    amplitudes = amplitudes / amplitudes.sum()

    if n_max is None:
        n_max = pF.size - 1
    n_bursts = int(n_bursts)
    rng = np.random.default_rng(int(seed))

    n_signal = rng.choice(pF.size, size=n_bursts, p=pF)
    species = rng.choice(amplitudes.size, size=n_bursts, p=amplitudes)
    p_green = probabilities[species]

    green_signal = rng.binomial(n_signal, p_green)
    green = green_signal + rng.poisson(max(0.0, float(background_ch1)), size=n_bursts)
    red = (n_signal - green_signal) + rng.poisson(max(0.0, float(background_ch2)), size=n_bursts)

    keep = (green <= n_max) & (red <= n_max)
    s1s2 = np.zeros((n_max + 1, n_max + 1), dtype=float)
    np.add.at(s1s2, (green[keep], red[keep]), 1.0)
    return s1s2


def _histogram_1d(pda_obj, s1s2, kw_hist) -> np.ndarray:
    """Return the 1D E-histogram of an S1S2 matrix via the engine."""
    _, y = pda_obj.get_1dhistogram(s1s2=np.asarray(s1s2, dtype=float).flatten(), **kw_hist)
    return np.asarray(y, dtype=float)


def _poisson_chi2(observed: np.ndarray, expected: np.ndarray) -> float:
    """Counting-noise chi-squared of an observed histogram against ``expected``.

    Uses the same ``(obs - exp) / sqrt(max(obs, 1))`` weighting as the PDA fit
    residual, so the statistic being bootstrapped is the one being minimised.
    """
    expected = np.asarray(expected, dtype=float)
    observed = np.asarray(observed, dtype=float)
    total = expected.sum()
    if total > 0.0:
        expected = expected * (observed.sum() / total)
    return float(np.sum(((observed - expected) / np.sqrt(np.maximum(observed, 1.0))) ** 2))


def kinetic_consistency_check(
        fit,
        n_resamples: int = 200,
        n_bursts: int | None = None,
        seed: int = 1,
        kw_hist: dict | None = None,
) -> dict:
    """Test whether measured bursts are consistent with a fitted PDA scheme.

    Resamples ``n_resamples`` synthetic burst datasets from the model's current
    (fitted) amplitude spectrum, scores each against the fitted expectation with
    :func:`_poisson_chi2`, and reports where the measured dataset falls in that
    empirical distribution.

    Call it on a fit that has already converged: the spectrum is read from the
    model as it currently stands.

    Parameters
    ----------
    fit : chisurf.core.fitting.fit.Fit
        A converged fit whose model is a PDA model (carries a ``pda`` engine).
    n_resamples : int, optional
        Number of bootstrap datasets. Default 200.
    n_bursts : int, optional
        Bursts per resample. Defaults to the measured burst count, so the
        resamples carry the same statistical weight as the data.
    seed : int, optional
        Base seed; resample ``i`` uses ``seed + i``. Default 1.
    kw_hist : dict, optional
        1D-histogram settings; defaults to :data:`DEFAULT_HIST_KWARGS`.

    Returns
    -------
    dict
        ``chi2_measured``, ``chi2_resampled`` (array), ``p_value``,
        ``consistent`` (``p_value >= 0.05``), ``n_bursts``, and the histograms
        ``hist_measured`` / ``hist_expected`` for plotting.

    Notes
    -----
    The p-value is the fraction of resamples scoring at least as badly as the
    data, computed with the usual ``(k + 1) / (n + 1)`` correction so it is
    never exactly zero -- with ``n_resamples`` draws nothing finer than
    ``1 / (n_resamples + 1)`` is resolvable, and reporting 0 would overstate
    what the bootstrap can support.
    """
    model = fit.model
    pda_obj = getattr(model, "pda", None)
    if pda_obj is None:
        raise TypeError(f"{type(model).__name__} is not a PDA model (no .pda engine)")
    pda_meta = getattr(fit.data, "pda", None)
    if not isinstance(pda_meta, dict) or pda_meta.get("s1s2") is None:
        raise ValueError("fit.data carries no PDA S1S2 histogram")

    kw_hist = dict(DEFAULT_HIST_KWARGS if kw_hist is None else kw_hist)

    # Make sure the engine reflects the current parameters, and that the
    # histogram callback the residual installs is in place.
    model.update()
    model.get_wres(fit)

    measured = np.asarray(pda_meta["s1s2"], dtype=float)
    n_bursts = int(measured.sum()) if n_bursts is None else int(n_bursts)

    expected_s1s2 = np.asarray(pda_obj.get_S1S2_matrix(), dtype=float)
    ny, nx = measured.shape
    expected_s1s2 = expected_s1s2[:ny, :nx]

    hist_expected = _histogram_1d(pda_obj, expected_s1s2, kw_hist)
    hist_measured = _histogram_1d(pda_obj, measured, kw_hist)
    chi2_measured = _poisson_chi2(hist_measured, hist_expected)

    amplitudes = np.asarray(pda_obj.get_amplitudes(), dtype=float)
    probabilities = np.asarray(pda_obj.get_probabilities_ch1(), dtype=float)
    pF = np.asarray(pda_obj.getPF(), dtype=float)

    chi2_resampled = np.empty(int(n_resamples), dtype=float)
    for i in range(int(n_resamples)):
        s1s2 = resample_s1s2(
            pF=pF,
            amplitudes=amplitudes,
            probabilities=probabilities,
            n_bursts=n_bursts,
            background_ch1=float(pda_obj.background_ch1),
            background_ch2=float(pda_obj.background_ch2),
            seed=int(seed) + i,
            n_max=ny - 1,
        )
        chi2_resampled[i] = _poisson_chi2(_histogram_1d(pda_obj, s1s2, kw_hist), hist_expected)

    n_worse = int(np.sum(chi2_resampled >= chi2_measured))
    p_value = (n_worse + 1) / (int(n_resamples) + 1)
    return {
        "chi2_measured": chi2_measured,
        "chi2_resampled": chi2_resampled,
        "p_value": p_value,
        "consistent": bool(p_value >= 0.05),
        "n_bursts": n_bursts,
        "hist_measured": hist_measured,
        "hist_expected": hist_expected,
    }
