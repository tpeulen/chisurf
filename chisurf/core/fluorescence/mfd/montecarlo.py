"""The 2D-MFD histogram by simulating bursts, rather than by summing over them.

A transcription of the forward model in Sim2D (Seidel lab, C#), which produced
published 2D-MFD analyses for years and whose physics core is about a hundred
lines. Its shape is worth stating plainly, because the brevity is the point:

    draw a burst's duration and photon budget from the *measured* distribution;
    walk the kinetic scheme through that duration; hand the photons out over the
    states in proportion to the time spent in each; let every photon choose a
    channel and, if it is a donor photon, a delay; histogram what comes out.

There is no approximation anywhere in that list. The analytic path in
:mod:`~chisurf.core.fluorescence.mfd.histogram` computes the same expectation in
closed form — a nested Poisson/binomial sum for the channel counts, a Gaussian
moment kernel for the mean delay, a transfer-matrix propagator for the occupation
times — and is much faster per evaluation, but each of those three is an
approximation with a regime where it frays. This module is the second opinion
that says which, and by how much.

What is shared and what is not. The two paths share what a *state* is — the same
``species_properties`` and the same IRF-convolved micro-time patterns — so they
cannot disagree about the photophysics, only about what happens to a burst. That
is deliberate: the question here is the burst-level treatment.

Faithfulness, and its limits. The multinomial-over-states followed by a per-state
Bernoulli is Sim2D's construction, kept even though thinning a multinomial is
provably an ordinary binomial on the averaged probability, because the whole
value of a second implementation is that it does not assume the first one's
algebra. What is *not* carried over: Sim2D's LFSR generator, its ``log(u+1)``
exponential offset, its roulette wheel that walks off the end of a probability
vector summing to ``1 − ε``, and its rate matrix being dimensionless (only the
product ``k·T`` was ever defined there). Rates here are Hz, in chisurf's
``K[target, source]`` convention.
"""

from __future__ import annotations

import numpy as np

from chisurf.core.fluorescence.kinetics import (
    equilibrium_populations,
    occupation_time_fractions_reference,
)
from chisurf.core.fluorescence.mfd.patterns import donor_lifetime_spectrum_of_state

__all__ = ["monte_carlo_histogram", "DEFAULT_MC_BURSTS"]

#: Simulated bursts per evaluation. Enough that the sampling scatter of a 41x41
#: histogram sits below the deviance differences a fit is asked to resolve.
DEFAULT_MC_BURSTS = 200_000


def _component_patterns(model, data) -> tuple[np.ndarray, np.ndarray]:
    """Return each component's acceptor probability and donor micro-time pattern.

    Component 0 is the donor-only species; the rest are the exchanging states, in
    the model's order. The patterns come from the measurement's own green
    response, so they carry its IRF and the wrap-around of the laser period.

    Parameters
    ----------
    model : MfdModel
        The model to evaluate.
    data : MfdData
        The measurement, for its channel responses.

    Returns
    -------
    p_red, patterns : numpy.ndarray
        ``(n_components,)`` and ``(n_components, n_micro_channels)``.
    """
    green_response = data.responses[data.channels[0]]
    _, p_red, _, _ = model.species_properties(data)

    patterns = []
    for has_acceptor, state in model._species()[1]:
        if has_acceptor:
            amplitudes, lifetimes = donor_lifetime_spectrum_of_state(
                state, model.optics, n_points=model.n_distance_samples
            )
        else:
            amplitudes = np.array([1.0])
            lifetimes = np.array([model.optics.tau_d0])
        patterns.append(np.asarray(green_response.pattern(amplitudes, lifetimes)))
    return np.asarray(p_red, dtype=float), np.asarray(patterns, dtype=float)


def _sampled_channel_sums(rng, counts: np.ndarray, patterns: np.ndarray,
                          n_bursts: int) -> np.ndarray:
    """Return the summed micro-time channel of each burst's donor photons.

    Every photon is drawn individually from its component's pattern — the thing
    the Gaussian moment kernel approximates — and the draws are grouped by
    component so the whole measurement costs one categorical sample per component
    rather than one per photon.

    Parameters
    ----------
    rng : numpy.random.Generator
        Source of randomness.
    counts : numpy.ndarray
        ``(n_bursts, n_components)`` donor photons per burst and component.
    patterns : numpy.ndarray
        ``(n_components, n_channels)`` micro-time densities, each summing to one.
    n_bursts : int
        Number of bursts, for the output length.

    Returns
    -------
    numpy.ndarray
        ``(n_bursts,)`` summed channel index.
    """
    total = np.zeros(n_bursts, dtype=np.int64)
    cumulative = np.cumsum(patterns, axis=1)
    for component in range(counts.shape[1]):
        per_burst = counts[:, component]
        n = int(per_burst.sum())
        if n == 0:
            continue
        # searchsorted on the pattern's CDF is the categorical draw; np.repeat
        # carries each photon's burst index so the sums land in the right rows.
        edges = np.clip(cumulative[component], 0.0, 1.0)
        edges[-1] = 1.0
        channels = np.searchsorted(edges, rng.random(n), side="right")
        owner = np.repeat(np.arange(n_bursts), per_burst)
        total += np.bincount(owner, weights=channels, minlength=n_bursts).astype(np.int64)
    return total


def _sample_background_channels(rng, response, n: int,
                                n_channels: int) -> np.ndarray:
    """Return micro-time channels for *n* background photons of a channel.

    Uses the response's measured background distribution where there is one, and
    a flat draw otherwise. Non-burst photons are mostly sub-threshold
    fluorescence rather than dark counts, so assuming flat puts their mean delay
    at half the laser period and biases the whole lifetime axis.

    Parameters
    ----------
    rng : numpy.random.Generator
        Source of randomness.
    response : ChannelResponse
        The channel's response, for its background pattern.
    n : int
        Number of background photons.
    n_channels : int
        Micro-time channels in one period.

    Returns
    -------
    numpy.ndarray
        ``(n,)`` channel indices.
    """
    pattern = getattr(response, "background_pattern", None)
    if pattern is None:
        return rng.integers(0, n_channels, size=n)
    weights = np.asarray(pattern, dtype=float)
    total = weights.sum()
    if total <= 0.0:
        return rng.integers(0, n_channels, size=n)
    edges = np.cumsum(weights / total)
    edges[-1] = 1.0
    return np.searchsorted(edges, rng.random(n), side="right")


def monte_carlo_histogram(model, data, *, n_bursts: int = DEFAULT_MC_BURSTS,
                          seed: int = 0, binned=None) -> np.ndarray:
    """Return the model 2D histogram by simulating bursts.

    Drop-in for :func:`~chisurf.core.fluorescence.mfd.histogram.model_histogram`:
    same axes, same green-photon cut, same meaning. Bursts are drawn from the
    measurement's own nuisance measure, so the simulated and observed histograms
    share their burst-size and duration distributions by construction rather than
    by a matching step.

    The seed is fixed by default and *must* stay fixed across the iterations of a
    fit: with common random numbers the objective is a deterministic function of
    the parameters, and without them an optimiser differentiates sampling scatter.

    Parameters
    ----------
    model : MfdModel
        The model to evaluate. ``rate_matrix`` (Hz, ``K[target, source]``) makes
        the states exchange during the burst; ``None`` leaves them static.
    data : MfdData
        The measurement, supplying the axes, the nuisance measure and the
        instrument responses.
    n_bursts : int
        Simulated bursts. Sampling scatter falls as its square root.
    seed : int
        Common-random-number seed.
    binned : tuple, optional
        A pre-binned nuisance measure; ``data.binned`` otherwise. Kinetics use each
        cell's mean duration, as the analytic path does, so that a comparison
        between the two isolates the burst treatment rather than the binning. Pass
        a finer grid to price the binning itself.

    Returns
    -------
    numpy.ndarray
        ``(n_ratio, n_micro_time)`` expected counts, normalised to *n_bursts*.
    """
    rng = np.random.default_rng(int(seed))
    axes = data.axes
    green_response = data.responses[data.channels[0]]
    red_response = data.responses[data.channels[1]]
    dt = float(green_response.dt)
    n_micro_channels = int(np.asarray(green_response.irf).size)

    species_weights, _, _, _ = model.species_properties(data)
    p_red, patterns = _component_patterns(model, data)
    donor_only = float(species_weights[0])
    state_weights = np.asarray(species_weights[1:], dtype=float)
    if state_weights.sum() > 0:
        state_weights = state_weights / state_weights.sum()

    rate_matrix = getattr(model, "rate_matrix", None)
    if rate_matrix is not None:
        rate_matrix = np.asarray(rate_matrix, dtype=float)

    weights, signal, spans = binned if binned is not None else data.binned
    weights = np.asarray(weights, dtype=float)
    occupied = np.nonzero(weights > 0)[0]
    if occupied.size == 0:
        return np.zeros(axes.shape)
    per_cell = rng.multinomial(int(n_bursts), weights[occupied] / weights[occupied].sum())

    n_components = patterns.shape[0]
    ratios, means = [], []
    for cell, n_cell in zip(occupied, per_cell):
        if n_cell == 0:
            continue
        total_signal = int(round(float(signal[cell])))
        if total_signal <= 0:
            continue
        window = float(spans[-1][cell])

        # Background is part of the burst's photon budget, not added to it — the
        # same split the nested sum makes, so the two paths mean the same S.
        b_green = rng.poisson(float(green_response.background_rate) * float(spans[0][cell]),
                              size=n_cell)
        b_red = rng.poisson(float(red_response.background_rate) * float(spans[1][cell]),
                            size=n_cell)
        n_signal = np.clip(total_signal - b_green - b_red, 0, None)

        # Which component each burst's photons come from. A donor-only molecule has
        # no FRET state to be in, so it never exchanges.
        fractions = np.zeros((n_cell, n_components))
        is_donor_only = rng.random(n_cell) < donor_only
        fractions[is_donor_only, 0] = 1.0
        exchanging = ~is_donor_only
        n_exchanging = int(exchanging.sum())
        if n_exchanging:
            if rate_matrix is None or not np.any(rate_matrix):
                picked = rng.choice(state_weights.size, size=n_exchanging,
                                    p=state_weights)
                fractions[np.flatnonzero(exchanging), 1 + picked] = 1.0
            else:
                sampled = occupation_time_fractions_reference(
                    rate_matrix, window, n_exchanging,
                    seed=int(seed) + int(cell) + 1,
                )
                fractions[exchanging, 1:] = sampled

        # Sim2D's construction: hand the photons out over the states by occupancy,
        # then let each choose its channel. Kept rather than collapsed to a single
        # binomial on f.p, because assuming the analytic path's algebra is exactly
        # what a second implementation must not do.
        counts = rng.multinomial(n_signal, fractions)
        red = rng.binomial(counts, np.broadcast_to(p_red, counts.shape))
        green = counts - red

        n_red = b_red + red.sum(axis=1)
        n_green = b_green + green.sum(axis=1)
        detected = n_green + n_red
        keep = (n_green >= int(data.min_green_photons)) & (detected > 0)
        if not np.any(keep):
            continue

        channel_sum = _sampled_channel_sums(rng, green, patterns, n_cell)
        # Background photons follow the channel's measured background shape, and
        # fall back to flat only where none was measured — the same rule the
        # analytic path applies through ``ChannelResponse.background_moments``. The
        # two must agree about what background *is*, or a comparison between them
        # measures that disagreement instead of the burst treatment.
        n_background = int(b_green.sum())
        if n_background:
            drawn = _sample_background_channels(
                rng, green_response, n_background, n_micro_channels
            )
            owner = np.repeat(np.arange(n_cell), b_green)
            channel_sum += np.bincount(owner, weights=drawn,
                                       minlength=n_cell).astype(np.int64)

        ratios.append(n_red[keep] / detected[keep])
        means.append(channel_sum[keep] / n_green[keep] * dt)

    if not ratios:
        return np.zeros(axes.shape)
    counts, _, _ = np.histogram2d(
        np.concatenate(ratios), np.concatenate(means),
        bins=(axes.ratio_edges, axes.micro_time_edges),
    )
    return counts
