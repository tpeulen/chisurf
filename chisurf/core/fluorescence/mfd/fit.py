"""Tying it together: a burst folder, an instrument, a set of states, a score.

This is the layer a fitting model, a CLI or a script talks to. It holds the two
halves apart on purpose:

* :class:`MfdData` is everything that comes from the measurement and never moves —
  the prepared bursts, the nuisance measure, the observed histogram on raw axes, and
  the per-channel instrument response with its background rate. Built once.
* :class:`MfdModel` is everything that is fitted — the optics and the states — and
  it produces a predicted histogram for that data.

The instrument response and the background rate come from the measurement's own
**non-burst photons** (:mod:`chisurf.core.fluorescence.burst.irf_bg`): in a confocal
single-molecule experiment most of the acquisition has no molecule in the focus, and
those photons are exactly the scattered excitation light and dark counts the model
needs. So a burst folder is self-sufficient — no separate scatter measurement, and
no IRF taken on a different day at a different alignment.
"""

from __future__ import annotations

import pathlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from chisurf.core.fluorescence.mfd.histogram import (
    DEFAULT_MIN_GREEN_PHOTONS,
    HistogramAxes,
    MfdHistogram,
    model_histogram,
    observed_histogram,
)
from chisurf.core.fluorescence.mfd.moments import mixture_moments
from chisurf.core.fluorescence.mfd.patterns import (
    ChannelResponse,
    FretState,
    Optics,
    donor_lifetime_spectrum_of_state,
    red_probability,
    state_efficiency,
)
from chisurf.core.fluorescence.mfd.prepare import (
    BurstPreparation,
    NuisanceMeasure,
    nuisance_measure,
    prepare_burst_folder,
)
from chisurf.core.fluorescence.mfd.sources import ScoreResult, histogram_residuals

__all__ = [
    "MfdData",
    "MfdKineticModel",
    "MfdModel",
    "bootstrap_uncertainties",
    "burstwise_log_probabilities",
    "estimate_responses",
    "load_mfd_data",
    "pooled_decay_score",
]


def estimate_responses(
    preparation: BurstPreparation,
    *,
    channels: Sequence[str] = ("green", "red"),
    min_photons: int = 60,
    photon_window: int = 10,
    time_window: float = 1e-3,
) -> dict[str, ChannelResponse]:
    """Estimate each channel's response and background from the non-burst photons.

    Most of a single-molecule acquisition has nothing in the focus. Those photons
    are scattered excitation light — whose shape *is* the instrument response — and
    uncorrelated dark counts, whose rate is the background the forward model needs.
    Summed over every measurement in the folder, because one file rarely has enough
    scatter to define a response and the alignment does not change between them.

    Parameters
    ----------
    preparation : BurstPreparation
        Must carry its photons (``with_photons=True``).
    channels : sequence of str
        Detector names to build responses for.
    min_photons, photon_window, time_window
        Burst-search parameters defining what counts as *not* a burst; see
        :func:`chisurf.core.fluorescence.burst.irf_bg.non_burst_mask`.

    Returns
    -------
    dict
        Detector name to :class:`~chisurf.core.fluorescence.mfd.patterns.ChannelResponse`.

    Raises
    ------
    ValueError
        If the preparation carries no photons, or a channel yields no scatter at
        all — an all-zero response would silently make every pattern the decay
        itself, which is a real IRF-free fit masquerading as an IRF-corrected one.
    """
    from chisurf.core.fluorescence.burst.irf_bg import extract_irf_background

    tttrs = preparation.summary.get("_tttrs")
    if not tttrs:
        raise ValueError(
            "responses come from the photon streams; prepare the folder with "
            "with_photons=True"
        )
    preparation.require_verified(channels)

    by_name = {s.name: s for s in preparation.streams}
    detectors = {
        name: {
            "chs": list(by_name[name].channels),
            "micro_time_ranges": list(by_name[name].micro_time_ranges),
        }
        for name in channels
    }

    accumulated: dict[str, np.ndarray] = {}
    background: dict[str, list[tuple[float, float]]] = {name: [] for name in channels}
    dt_ns = 0.0
    for tttr in tttrs.values():
        estimates = extract_irf_background(
            tttr,
            detectors,
            min_photons=min_photons,
            photon_window=photon_window,
            time_window=time_window,
        )
        for name, estimate in estimates.items():
            if name not in accumulated:
                accumulated[name] = np.zeros_like(estimate.irf_raw)
            accumulated[name] += estimate.irf_raw
            # Weight each file's background rate by the photons it contributed, so
            # a short file cannot outvote a long one.
            background[name].append(
                (float(estimate.background_khz), float(estimate.n_background_photons))
            )
            if dt_ns <= 0.0 and estimate.time_ns.size > 1:
                dt_ns = float(estimate.time_ns[1] - estimate.time_ns[0])

    responses: dict[str, ChannelResponse] = {}
    for name in channels:
        raw = accumulated.get(name)
        if raw is None or raw.sum() <= 0:
            raise ValueError(
                f"the {name} channel has no non-burst photons, so its instrument "
                "response cannot be estimated from this measurement"
            )
        # Subtract the flat dark-count floor; what remains is scatter, i.e. the
        # response. The quantile is the same robust choice irf_bg makes.
        baseline = float(np.quantile(raw, 0.2))
        irf = np.clip(raw - baseline, 0.0, None)
        if irf.sum() <= 0:
            raise ValueError(
                f"the {name} channel's non-burst micro times are flat: there is no "
                "scatter prompt to take an instrument response from"
            )
        rates, photons = zip(*background[name])
        total = sum(photons) or 1.0
        rate_khz = sum(r * n for r, n in zip(rates, photons)) / total
        responses[name] = ChannelResponse(
            irf=irf, dt=dt_ns, background_rate=rate_khz * 1e3
        )
    return responses


@dataclass
class MfdData:
    """Everything about the measurement that a fit does not change.

    Attributes
    ----------
    preparation : BurstPreparation
        The bursts, as read.
    nuisance : NuisanceMeasure
        The empirical ``P(S, t_G, t_R)``.
    binned : tuple
        The nuisance measure on a grid, computed once so a fit loop never rebins.
    observed : MfdHistogram
        The data histogram, on raw axes, built once and never moved.
    responses : dict
        Per-channel instrument response and background rate.
    channels : tuple of str
        ``(green, red)`` detector names.
    """

    preparation: BurstPreparation
    nuisance: NuisanceMeasure
    binned: tuple
    observed: MfdHistogram
    responses: dict[str, ChannelResponse]
    channels: tuple[str, str]

    @property
    def axes(self) -> HistogramAxes:
        """Return the histogram's bin edges."""
        return self.observed.axes

    @property
    def min_green_photons(self) -> int:
        """Return the green-photon cut the observed histogram applied."""
        return int(self.observed.summary["min_green_photons"])

    def report(self) -> str:
        """Return a human-readable account of what was loaded and excluded."""
        green, red = self.channels
        lines = [
            self.preparation.report(),
            f"nuisance: {len(self.nuisance)} bursts, "
            f"{self.nuisance.summary['n_excluded_low_signal']} below the signal cut",
            f"histogram: {self.observed.n_used} bursts "
            f"({self.observed.summary['excluded_fraction']:.1%} excluded, cut at "
            f"{self.min_green_photons} green photons)",
        ]
        for name in (green, red):
            response = self.responses[name]
            lines.append(
                f"  {name}: background {response.background_rate * 1e-3:.3f} kHz, "
                f"response over {response.n_channels} channels "
                f"({response.period:.2f} ns period)"
            )
        return "\n".join(lines)


def load_mfd_data(
    folder: pathlib.Path | str,
    *,
    green: str = "green",
    red: str = "red",
    axes: HistogramAxes | None = None,
    min_green_photons: int = DEFAULT_MIN_GREEN_PHOTONS,
    streams=None,
    n_signal_bins: int = 24,
    n_span_bins: int = 6,
    responses: dict | None = None,
    **response_kwargs,
) -> MfdData:
    """Load a burst folder into everything a 2D MFD fit needs from the measurement.

    Parameters
    ----------
    folder : path-like
        A burst-analysis folder.
    green, red : str
        Detector names.
    axes : HistogramAxes, optional
        Histogram bin edges.
    min_green_photons : int
        Green-photon cut, applied identically to the data and to the model.
    streams : sequence, optional
        Explicit channel definitions, when the folder does not record them.
    n_signal_bins, n_span_bins : int
        Grid of the binned nuisance measure.
    responses : dict, optional
        Per-channel responses to use instead of estimating them from the non-burst
        photons. The estimate is what a real folder has to rely on and it is
        contaminated by bursts below the search threshold; supplying a known
        response isolates whatever else is under test from that.
    **response_kwargs
        Forwarded to :func:`estimate_responses`.

    Returns
    -------
    MfdData
    """
    preparation = prepare_burst_folder(folder, streams=streams, with_photons=True)
    measure = nuisance_measure(preparation, channels=(green, red))
    return MfdData(
        preparation=preparation,
        nuisance=measure,
        binned=measure.binned(n_signal_bins=n_signal_bins, n_span_bins=n_span_bins),
        observed=observed_histogram(
            preparation, axes, green=green, red=red,
            min_green_photons=min_green_photons,
        ),
        responses=responses
        or estimate_responses(preparation, channels=(green, red), **response_kwargs),
        channels=(green, red),
    )


@dataclass
class MfdModel:
    """A set of states with populations, and the optics they are seen through.

    Attributes
    ----------
    optics : Optics
        Correction factors and instrument constants.
    states : list of FretState
        The conformational states.
    populations : numpy.ndarray
        Fraction of molecules in each state, normalised internally.
    donor_only : float
        Fraction of molecules with no active acceptor. Real single-molecule data
        always has some, and leaving it out of the model does not remove it from the
        data — it makes the fit pull a FRET state down to explain it.
    n_distance_samples : int
        Samples of the linker distance distribution.
    """

    optics: Optics
    states: list[FretState] = field(default_factory=list)
    populations: np.ndarray | None = None
    donor_only: float = 0.0
    n_distance_samples: int = 81

    def _species(self) -> tuple[np.ndarray, list[tuple[bool, FretState]]]:
        """Return normalised species weights and their (has-acceptor, state) pairs."""
        if not self.states:
            raise ValueError("the model has no states")
        populations = (
            np.ones(len(self.states))
            if self.populations is None
            else np.asarray(self.populations, dtype=float)
        )
        if populations.size != len(self.states):
            raise ValueError("populations and states disagree in length")
        populations = np.clip(populations, 0.0, None)
        total = populations.sum()
        populations = (
            populations / total if total > 0 else np.full(populations.size, 1.0 / populations.size)
        )
        fraction = float(np.clip(self.donor_only, 0.0, 1.0))
        weights = np.concatenate([[fraction], (1.0 - fraction) * populations])
        species = [(False, FretState(distance=np.inf, name="donor-only"))] + [
            (True, s) for s in self.states
        ]
        return weights, species

    def species_properties(
        self, data: MfdData
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Return the per-species branching and green-channel moments.

        Parameters
        ----------
        data : MfdData
            The measurement, from :func:`load_mfd_data`.

        Returns
        -------
        weights, p_red, green_mean, green_variance : numpy.ndarray
            ``(n_species,)`` each. The histogram takes these per *cell*; a static
            model is the case where they do not depend on the burst.
        """
        green_name, _ = data.channels
        response = data.responses[green_name]
        weights, species = self._species()

        p_red = np.zeros(len(species))
        mean = np.zeros(len(species))
        variance = np.zeros(len(species))
        for i, (has_acceptor, state) in enumerate(species):
            if has_acceptor:
                efficiency = state_efficiency(
                    state, self.optics, n_points=self.n_distance_samples
                )
                amplitudes, lifetimes = donor_lifetime_spectrum_of_state(
                    state, self.optics, n_points=self.n_distance_samples
                )
                p_red[i] = float(red_probability(efficiency, self.optics))
            else:
                # No acceptor: no transfer and no direct excitation, so the only way
                # into the acceptor channel is leakage. Applying δ here would make
                # the donor-only population report an acceptor that is not there.
                donor_only_optics = Optics(
                    **{**self.optics.__dict__, "delta": 0.0}
                )
                p_red[i] = float(red_probability(0.0, donor_only_optics))
                amplitudes = np.array([1.0])
                lifetimes = np.array([self.optics.tau_d0])
            mean[i], variance[i] = response.signal_moments(amplitudes, lifetimes)
        return weights, p_red, mean, variance

    def components(
        self, data: MfdData
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Return the per-cell components the histogram model consumes.

        A static model has one component per species, the same in every nuisance
        cell. The kinetic subclass overrides this to return the occupation-time grid
        instead, which is the entire difference between the two — the histogram code
        below is unchanged.

        Parameters
        ----------
        data : MfdData
            The measurement, from :func:`load_mfd_data`.

        Returns
        -------
        weights, p_red, green_mean, green_variance : numpy.ndarray
            ``(n_cells, n_components)`` each.
        """
        weights, p_red, mean, variance = self.species_properties(data)
        n_cells = data.binned[0].size

        def tile(values):
            return np.broadcast_to(values, (n_cells, values.size))

        return tile(weights), tile(p_red), tile(mean), tile(variance)

    def histogram(self, data: MfdData) -> np.ndarray:
        """Predict the 2D histogram for a measurement.

        Parameters
        ----------
        data : MfdData
            The measurement, from :func:`load_mfd_data`.

        Returns
        -------
        numpy.ndarray
            ``(n_ratio, n_micro_time)``.
        """
        green_name, red_name = data.channels
        weights, p_red, mean, variance = self.components(data)

        return model_histogram(
            data.nuisance,
            data.axes,
            component_weights=weights,
            p_red=p_red,
            green_mean=mean,
            green_variance=variance,
            background_rates=(
                data.responses[green_name].background_rate,
                data.responses[red_name].background_rate,
            ),
            background_micro_time=data.responses[green_name].background_moments(),
            min_green_photons=data.min_green_photons,
            binned=data.binned,
        )

    def score(self, data: MfdData, **kwargs) -> ScoreResult:
        """Score this model against the observed histogram.

        Parameters
        ----------
        data : MfdData
            The measurement, from :func:`load_mfd_data`.
        **kwargs
            Forwarded to
            :func:`~chisurf.core.fluorescence.mfd.sources.histogram_residuals`.

        Returns
        -------
        ScoreResult
        """
        return histogram_residuals(data.observed.counts, self.histogram(data), **kwargs)

    def marginals(self, data: MfdData) -> dict[str, Any]:
        """Return the 1D marginals of the model and the data, for comparison.

        The milestone-1a gate is about *width*, and a width is easiest to read off a
        marginal. Returned together so nothing can compare a model marginal computed
        one way against a data marginal computed another.

        Parameters
        ----------
        data : MfdData
            The measurement, from :func:`load_mfd_data`.

        Returns
        -------
        dict
            ``ratio``/``micro_time`` each mapping to ``(centres, data, model)``.
        """
        model = self.histogram(data)
        observed = data.observed.counts
        scale = observed.sum() / model.sum() if model.sum() > 0 else 1.0
        axes = data.axes
        centres = lambda e: 0.5 * (e[:-1] + e[1:])  # noqa: E731
        return {
            "ratio": (
                centres(axes.ratio_edges),
                observed.sum(axis=1),
                model.sum(axis=1) * scale,
            ),
            "micro_time": (
                centres(axes.micro_time_edges),
                observed.sum(axis=0),
                model.sum(axis=0) * scale,
            ),
        }


@dataclass
class MfdKineticModel(MfdModel):
    """States that exchange during the burst, through the occupation-time law.

    The only thing that changes from the static model is what a *component* is.
    Statically, one component per species. Kinetically, one component per node of
    ``P(f | T, K)`` — a burst that spent a fraction ``f_s`` of its transit in each
    state — with the occupation-time law supplying the weights. Everything
    downstream (the nested background/partition sum, the ``⟨t⟩`` kernel, the
    deviance) is untouched, which is the point of expressing the histogram in terms
    of components in the first place.

    That works because the channel counts and the micro times of a burst depend on
    its state path **only** through ``f``. It is exact, not an approximation.

    Attributes
    ----------
    rate_matrix : numpy.ndarray
        ``(n_states, n_states)`` rates in Hz, ``K[target, source]`` — the shared
        convention of :mod:`chisurf.core.fluorescence.kinetics`, not a private one.
        Must match the number of ``states``.
    n_steps : int, optional
        Transfer-matrix discretization; chosen per burst duration from the rates
        when omitted, which is the right default because a fit loop moves them.
    n_occupation_nodes : int
        Occupation-time nodes kept per burst duration. The propagator's own
        resolution runs to hundreds of nodes under fast exchange and each costs a
        pass through the nested background sum, for a resolution the histogram
        cannot see; see :meth:`OccupationGrid.coarsen`.
    """

    rate_matrix: np.ndarray | None = None
    n_steps: int | None = None
    n_occupation_nodes: int = 16

    def components(
        self, data: MfdData
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Return the occupation-time grid as histogram components, per nuisance cell.

        Parameters
        ----------
        data : MfdData
            The measurement, from :func:`load_mfd_data`.

        Returns
        -------
        weights, p_red, green_mean, green_variance : numpy.ndarray
            ``(n_cells, n_nodes)`` each, padded to the widest grid with zero weight.
        """
        from chisurf.core.fluorescence.mfd.occupation import (
            occupation_time_distribution,
        )

        if self.rate_matrix is None:
            return super().components(data)
        matrix = np.asarray(self.rate_matrix, dtype=float)
        if matrix.shape[0] != len(self.states):
            raise ValueError(
                f"the rate matrix is {matrix.shape[0]}x{matrix.shape[0]} but the "
                f"model has {len(self.states)} states"
            )

        species_weights, p_red, mean, variance = self.species_properties(data)
        # Species 0 is the donor-only population, which does not take part in the
        # exchange: a molecule with no active acceptor has no FRET state to be in.
        donor_only = float(species_weights[0])
        state_p_red = p_red[1:]
        state_mean = mean[1:]
        state_variance = variance[1:]

        durations = data.binned[2][-1]
        n_cells = durations.size

        # One grid per distinct duration. The nuisance measure is binned, so there
        # are a few dozen of them rather than one per burst — which is what keeps
        # the kinetic path the same order of cost as the static one.
        grids = {}
        rows = []
        for cell in range(n_cells):
            window = float(durations[cell])
            key = round(window, 12)
            if key not in grids:
                grids[key] = occupation_time_distribution(
                    matrix, window, n_steps=self.n_steps
                ).coarsen(self.n_occupation_nodes)
            rows.append(grids[key])

        width = 1 + max(len(g) for g in rows)
        weights = np.zeros((n_cells, width))
        cell_p_red = np.zeros((n_cells, width))
        cell_mean = np.zeros((n_cells, width))
        cell_variance = np.zeros((n_cells, width))

        for cell, grid in enumerate(rows):
            n = len(grid)
            # Component 0 is always the donor-only population, unexchanging.
            weights[cell, 0] = donor_only
            cell_p_red[cell, 0] = p_red[0]
            cell_mean[cell, 0] = mean[0]
            cell_variance[cell, 0] = variance[0]

            f = grid.fractions
            weights[cell, 1 : n + 1] = (1.0 - donor_only) * grid.weights
            # A burst that spent fraction f_s in state s emits that fraction of its
            # photons there (equal green-equivalent brightness across states), so
            # the acceptor probability and the micro-time pattern are the f-weighted
            # mixtures. The mixture's variance carries the spread of the states'
            # own means, which is what makes a burst caught mid-exchange sit off
            # the static line rather than on it.
            cell_p_red[cell, 1 : n + 1] = f @ state_p_red
            node_mean, node_variance = mixture_moments(
                f,
                np.broadcast_to(state_mean, f.shape),
                np.broadcast_to(state_variance, f.shape),
            )
            cell_mean[cell, 1 : n + 1] = node_mean
            cell_variance[cell, 1 : n + 1] = node_variance

        return weights, cell_p_red, cell_mean, cell_variance


def burstwise_log_probabilities(
    model: MfdModel,
    data: MfdData,
    *,
    max_bursts: int | None = None,
    seed: int = 0,
) -> np.ndarray:
    """Return each burst's log-probability under a model, photon by photon.

    The maximum-likelihood reference. No binning and no compression: a burst's
    channel counts *and* the micro time of every one of its photons, with the state
    mixture marginalized. This is the information bound the histogram source is
    measured against — and, because it scores each burst exactly once, the only
    source here whose curvature is a legitimate uncertainty.

    Per burst, over the model's components ``c``::

        P(burst) = Σ_c w_c · P(N_R | S, p_c) · Π_photons pattern_c(t_i)

    with the channel counts carrying the same nested Poisson-background and binomial
    partition the histogram uses, so the two sources cannot disagree about what the
    model *is*.

    Parameters
    ----------
    model : MfdModel
        The model to evaluate.
    data : MfdData
        The measurement. Must carry its photons.
    max_bursts : int, optional
        Score a random subset of this many bursts. The cost is linear in photons, so
        a subset is the honest way to trade precision for time — and it is drawn at
        random rather than taken from the front, because burst tables are ordered by
        acquisition and the front of one is not a sample of it.
    seed : int
        Seed for that subsample, so a fit objective stays deterministic.

    Returns
    -------
    numpy.ndarray
        ``(n_scored,)`` log-probabilities.

    Raises
    ------
    ValueError
        If the preparation carries no photons.
    """
    from chisurf.core.fluorescence.burst.photons import stream_index_arrays
    from chisurf.core.fluorescence.mfd.histogram import acceptor_count_distributions

    preparation = data.preparation
    tttrs = preparation.summary.get("_tttrs")
    if not tttrs:
        raise ValueError(
            "the burst-wise source needs the photons; prepare the folder with "
            "with_photons=True"
        )
    green_name, red_name = data.channels
    green_response = data.responses[green_name]
    green_index = preparation.channel_index(green_name)
    red_index = preparation.channel_index(red_name)

    species_weights, species_p_red, _, _ = model.species_properties(data)
    donor_only = float(species_weights[0])
    state_p_red = species_p_red[1:]

    # The per-state *pattern* over micro-time channels, which is what a photon is
    # actually scored against — the moments are a summary of it and cannot score an
    # individual arrival. Index 0 is the donor-only species.
    patterns = []
    for has_acceptor, state in model._species()[1]:
        if has_acceptor:
            amplitudes, lifetimes = donor_lifetime_spectrum_of_state(
                state, model.optics, n_points=model.n_distance_samples
            )
        else:
            amplitudes = np.array([1.0])
            lifetimes = np.array([model.optics.tau_d0])
        patterns.append(green_response.pattern(amplitudes, lifetimes))
    donor_only_pattern = np.asarray(patterns[0])
    state_patterns = np.asarray(patterns[1:])

    # Exchange enters exactly as it does in the histogram — through the
    # occupation-time law — so the two sources cannot disagree about what the model
    # *is*. Grids are computed per duration bin rather than per burst: the law
    # varies smoothly with the window, and one grid per burst would dominate the
    # cost of a source whose point is to be the reference.
    rate_matrix = getattr(model, "rate_matrix", None)
    duration = preparation.duration
    positive = duration[duration > 0]
    if rate_matrix is not None and positive.size:
        edges = np.quantile(positive, np.linspace(0.0, 1.0, 13))
        edges = np.unique(edges)
        duration_bin = np.clip(np.digitize(duration, edges[1:-1]), 0, edges.size - 2)
        representative = [
            float(np.median(duration[duration_bin == b])) if np.any(duration_bin == b)
            else float(np.median(positive))
            for b in range(max(duration_bin.max() + 1, 1))
        ]
        from chisurf.core.fluorescence.mfd.occupation import (
            occupation_time_distribution,
        )

        grids = [
            occupation_time_distribution(
                np.asarray(rate_matrix, dtype=float), window,
                n_steps=getattr(model, "n_steps", None),
            ).coarsen(getattr(model, "n_occupation_nodes", 16))
            for window in representative
        ]
    else:
        duration_bin = np.zeros(len(preparation), dtype=int)
        grids = [None]

    # Per duration bin: the component weights, acceptor probabilities and patterns.
    per_bin = []
    for grid in grids:
        if grid is None:
            fractions = np.eye(len(model.states))
            node_weights = np.asarray(model.species_properties(data)[0][1:])
            total = node_weights.sum()
            node_weights = (
                node_weights / total if total > 0
                else np.full(fractions.shape[0], 1.0 / fractions.shape[0])
            )
        else:
            fractions, node_weights = grid.fractions, grid.weights
        component_weights = np.concatenate(
            [[donor_only], (1.0 - donor_only) * node_weights]
        )
        component_p_red = np.concatenate(
            [[species_p_red[0]], fractions @ state_p_red]
        )
        component_patterns = np.vstack(
            [donor_only_pattern[None, :], fractions @ state_patterns]
        )
        per_bin.append((component_weights, component_p_red, component_patterns))

    # A flat background floor, so a photon in a channel the fluorescence never
    # reaches costs a finite amount rather than -inf. Without it one stray photon
    # annihilates a burst's entire likelihood.
    floor = 1.0 / green_response.n_channels
    background_weight = np.clip(
        green_response.background_rate * preparation.spans[:, green_index]
        / np.maximum(preparation.counts[:, green_index], 1),
        0.0,
        1.0,
    )

    rows = np.arange(len(preparation))
    usable = (
        (preparation.counts[:, green_index] + preparation.counts[:, red_index]) > 0
    )
    rows = rows[usable]
    if max_bursts is not None and rows.size > max_bursts:
        rows = np.sort(
            np.random.default_rng(seed).choice(rows, size=int(max_bursts), replace=False)
        )

    streams = list(preparation.streams)
    cache = {
        key: (np.asarray(t.routing_channels), np.asarray(t.micro_times))
        for key, t in tttrs.items()
    }

    out = np.full(rows.size, -np.inf)
    for position, row in enumerate(rows):
        entry = cache.get(preparation.file_key[row])
        if entry is None:
            continue
        channels, micro = entry
        lo = int(preparation.first_photon[row])
        hi = int(preparation.last_photon[row]) + 1
        index = stream_index_arrays(channels[lo:hi], micro[lo:hi], streams)
        green_photons = micro[lo:hi][index == green_index]

        weights, component_p_red, component_patterns = per_bin[duration_bin[row]]
        signal = int(
            preparation.counts[row, green_index] + preparation.counts[row, red_index]
        )
        n_red = int(preparation.counts[row, red_index])
        counts = acceptor_count_distributions(
            signal,
            component_p_red,
            green_response.background_rate * preparation.spans[row, green_index],
            data.responses[red_name].background_rate
            * preparation.spans[row, red_index],
        )[:, min(n_red, signal)]

        share = float(background_weight[row])
        mixed = (1.0 - share) * component_patterns[:, green_photons] + share * floor
        with np.errstate(divide="ignore"):
            log_photons = np.log(np.maximum(mixed, 1e-300)).sum(axis=1)
            log_counts = np.log(np.maximum(counts, 1e-300))
            terms = np.log(np.maximum(weights, 1e-300)) + log_counts + log_photons
        top = terms.max()
        out[position] = float(top + np.log(np.exp(terms - top).sum()))
    return out


def bootstrap_uncertainties(
    refit,
    data: MfdData,
    *,
    n_resamples: int = 40,
    seed: int = 0,
) -> dict:
    """Estimate parameter uncertainties by resampling bursts.

    The histogram source's own curvature cannot supply these: it scores the same
    bursts through more than one marginal, so the summed deviance is an M-estimator
    and its second derivative is not a likelihood's. Resampling bursts *is* valid,
    because it perturbs the thing that actually varies between repeats of the
    experiment — which bursts you happened to catch.

    Parameters
    ----------
    refit : callable
        ``refit(MfdData) -> dict`` returning the fitted parameters for one resample.
    data : MfdData
        The measurement.
    n_resamples : int
        Bootstrap replicates.
    seed : int
        Random seed.

    Returns
    -------
    dict
        Per parameter, ``{"mean", "std", "values"}``.
    """
    import dataclasses

    rng = np.random.default_rng(seed)
    measure = data.nuisance
    n = len(measure)
    replicates: list[dict] = []
    for _ in range(int(n_resamples)):
        draw = rng.integers(0, n, size=n)
        resampled = dataclasses.replace(
            measure,
            signal=measure.signal[draw],
            spans=measure.spans[draw],
            counts=measure.counts[draw],
            duration=measure.duration[draw],
            rows=measure.rows[draw],
        )
        replica = dataclasses.replace(
            data, nuisance=resampled, binned=resampled.binned()
        )
        replicates.append(refit(replica))

    keys = replicates[0].keys() if replicates else []
    return {
        key: {
            "mean": float(np.mean([r[key] for r in replicates])),
            "std": float(np.std([r[key] for r in replicates], ddof=1)),
            "values": [float(r[key]) for r in replicates],
        }
        for key in keys
    }


def pooled_decay_score(
    model: MfdModel,
    data: MfdData,
    *,
    n_decay_channels: int = 64,
):
    """Score the model against real decays pooled per proximity-ratio bin.

    The third scoring source. A burst's mean micro time is one number, and one
    number cannot separate a within-burst *mixture* of two lifetimes from a single
    intermediate one — they have the same mean and different decays. Pooling the
    photons of each ratio bin back into an actual decay recovers that shape, which
    is precisely the discrimination the histogram source gives up in exchange for
    its speed.

    Bins are on the proximity ratio only. Pooling on a coordinate conditions on it,
    and the ratio is one the model reproduces exactly through the same nested
    background/partition sum the histogram uses; pooling on the lifetime axis too
    would tilt every pooled decay in a way that reads as a lifetime shift.

    Parameters
    ----------
    model : MfdModel
        The model to score.
    data : MfdData
        The measurement. Must carry its photons.
    n_decay_channels : int
        Micro-time channels of the pooled decays.

    Returns
    -------
    chisurf.core.fluorescence.mfd.sources.ScoreResult
    """
    from chisurf.core.fluorescence.mfd.histogram import (
        model_pooled_decays,
        observed_pooled_decays,
        rebin_pattern,
    )
    from chisurf.core.fluorescence.mfd.sources import pooled_decay_residuals

    green_name, red_name = data.channels
    green_response = data.responses[green_name]

    observed = observed_pooled_decays(
        data.preparation,
        data.axes,
        green=green_name,
        red=red_name,
        min_green_photons=data.min_green_photons,
        n_decay_channels=n_decay_channels,
    )

    weights, p_red, _, _ = model.components(data)
    patterns = []
    for has_acceptor, state in model._species()[1]:
        if has_acceptor:
            amplitudes, lifetimes = donor_lifetime_spectrum_of_state(
                state, model.optics, n_points=model.n_distance_samples
            )
        else:
            amplitudes = np.array([1.0])
            lifetimes = np.array([model.optics.tau_d0])
        patterns.append(green_response.pattern(amplitudes, lifetimes))
    patterns = rebin_pattern(np.asarray(patterns), n_decay_channels)

    # A kinetic model's components are occupation nodes, not species, so its
    # patterns are the f-weighted mixtures of the state patterns. Built here from
    # the same grid the histogram used rather than recomputed, so the two sources
    # cannot drift apart.
    if weights.shape[1] != patterns.shape[0]:
        donor_only_pattern = patterns[0]
        state_patterns = patterns[1:]
        from chisurf.core.fluorescence.mfd.occupation import (
            occupation_time_distribution,
        )

        window = float(np.median(data.nuisance.duration))
        grid = occupation_time_distribution(
            np.asarray(model.rate_matrix, dtype=float),
            window,
            n_steps=model.n_steps,
        ).coarsen(model.n_occupation_nodes)
        patterns = np.vstack(
            [donor_only_pattern[None, :], grid.fractions @ state_patterns]
        )
        if patterns.shape[0] != weights.shape[1]:
            # The grid width varies with the burst duration; pad with the
            # equilibrium pattern rather than silently truncating the components.
            pad = weights.shape[1] - patterns.shape[0]
            patterns = np.vstack([patterns, np.repeat(patterns[-1:], pad, axis=0)])

    flat = np.full(patterns.shape[1], 1.0 / patterns.shape[1])
    predicted = model_pooled_decays(
        data.nuisance,
        data.axes,
        component_weights=weights,
        p_red=p_red,
        component_patterns=patterns,
        background_pattern=flat,
        background_rates=(
            green_response.background_rate,
            data.responses[red_name].background_rate,
        ),
        min_green_photons=data.min_green_photons,
        binned=data.binned,
    )
    return pooled_decay_residuals(observed, predicted)
