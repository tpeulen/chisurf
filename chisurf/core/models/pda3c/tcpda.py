r"""Three-colour PDA fitting model (PRD-65 stage 2, GUI surface).

Wraps the compute core in :mod:`chisurf.core.fluorescence.pda3c` as a ChiSurf
fitting model, so three-colour PDA is reachable from the add-fit flow like any
other model. The compute definition lives here; the editor layout is declared
separately in ``tcpda.view.json`` (PRD-38 model/view-spec split).

What is fitted
--------------
Species are trivariate Gaussians over $(R_{GR}, R_{BG}, R_{BR})$ with a full
covariance — the off-diagonals are the point of three-colour FRET, since three
separate two-colour experiments give three marginals and can never say whether
the distances move *together*. Widths and correlations are the user-facing
parameterisation; the covariance is rebuilt (and repaired to positive definite)
on every evaluation.

The objective
-------------
This is a **burst likelihood**, not a histogram chi-square, so the residual is
built to make the two comparable. Each burst contributes its multinomial
**deviance** against the saturated model that puts the observed fraction in each
channel,

.. math::

    r_j = \sqrt{2\,\big(\ell^{\text{sat}}_j - \ell_j\big)},

so :math:`\sum_j r_j^2 = \text{const} - 2\log L`. Minimising the sum of squares
is therefore exactly maximising the likelihood — the saturated term is
parameter-independent and cannot move the optimum — and the reported number is
a deviance rather than an arbitrary log-likelihood. This is the same reasoning
behind the Poisson deviance the two-colour PDA models use.

**Read** :math:`\chi^2_r` **here as relative, not absolute.** The saturated
model has three free cells per burst, so the deviance is a
:math:`3n`-parameter model against a handful — and with tens of photons split
over three channels the per-cell counts are far too small for the usual
asymptotics. Measured on simulated data at the true parameters it settles
around 2.4, essentially independent of dataset size, rather than at one. It is
therefore a sound way to compare fits of the *same* data, and a poor way to
decide in absolute terms whether a model is adequate; for that, use the
error-surface and F-test machinery, or a parametric bootstrap of the kind
`chisurf.core.models.pda.consistency` performs for two colours.

The displayed curve
-------------------
The three proximity-ratio histograms (``F_BG/N_blue``, ``F_BR/N_blue``,
``F_GR/N_green``) concatenated. They are computed **analytically**, not by
Monte-Carlo: a marginal of a multinomial is a binomial, so the predicted
histogram is a sum of binomial pmfs over the observed burst-size distribution
and the quadrature nodes. Deterministic and cheap, where resampling would be
neither.
"""

from __future__ import annotations

import numpy as np

import chisurf as cs
from chisurf.core.fitting.parameter import FittingParameter, FittingParameterGroup
from chisurf.core.fluorescence.pda3c import (
    BurstCounts,
    ThreeColorSetup,
    ThreeColorSpecies,
    covariance_from_statistics,
    distances_to_matrix,
    relative_brightness,
)
from chisurf.core.fluorescence.pda3c.likelihood import log_multinomial_pmf
from chisurf.core.models.model import ModelCurve

#: Bin edges of each displayed proximity-ratio histogram.
N_RATIO_BINS = 41


class TcPdaSpecies(FittingParameterGroup):
    """Trivariate-Gaussian distance populations of a three-colour sample.

    One component carries an amplitude, three mean distances with their widths,
    and the three pairwise correlations. The correlations are bounded to
    ``(-1, 1)``; an inconsistent triple is repaired to the nearest valid
    covariance rather than rejected, because a fit can pass through one.
    """

    #: Distances (and correlations) carried per species, in order.
    PAIRS = ("GR", "BG", "BR")
    CORRELATIONS = ("GR-BG", "GR-BR", "BG-BR")

    def __init__(self, name: str = "tcpda_species", **kwargs):
        """Initialize an empty species list."""
        super().__init__(name=name, **kwargs)
        # Flat lists, three entries per species. Nesting the triples would read
        # more naturally but hides them from the group's parameter discovery,
        # which walks lists of parameters and does not descend into tuples --
        # the parameters would then never become free and the fit would sit
        # still while reporting success.
        self._amplitudes = []
        self._means = []
        self._sigmas = []
        self._correlations = []

    def __len__(self):
        """Return the number of species."""
        return len(self._amplitudes)

    def means_of(self, index: int) -> list:
        """Return the three mean-distance parameters of species ``index``."""
        return self._means[3 * index: 3 * index + 3]

    def sigmas_of(self, index: int) -> list:
        """Return the three width parameters of species ``index``."""
        return self._sigmas[3 * index: 3 * index + 3]

    def correlations_of(self, index: int) -> list:
        """Return the three correlation parameters of species ``index``."""
        return self._correlations[3 * index: 3 * index + 3]

    def append(self, r_gr: float = 55.0, r_bg: float = 50.0, r_br: float = 65.0,
               sigma: float = 6.0, amplitude: float = 1.0):
        """Append one trivariate-Gaussian species.

        Parameters
        ----------
        r_gr, r_bg, r_br : float
            Mean distances of the three dye pairs, in Angstrom.
        sigma : float
            Initial width for all three pairs.
        amplitude : float
            Relative species weight.
        """
        i = len(self) + 1
        self._amplitudes.append(
            FittingParameter(value=amplitude, name=f"A({i})", label_text=f"A<sub>{i}</sub>")
        )
        for tag, value in zip(self.PAIRS, (r_gr, r_bg, r_br)):
            self._means.append(
                FittingParameter(value=value, name=f"R{tag}({i})", lb=1.0, ub=200.0,
                                 bounds_on=True, label_text=f"R<sub>{tag},{i}</sub>")
            )
            self._sigmas.append(
                FittingParameter(value=sigma, name=f"s{tag}({i})", lb=0.5, ub=60.0,
                                 bounds_on=True, label_text=f"s<sub>{tag},{i}</sub>")
            )
        for tag in self.CORRELATIONS:
            self._correlations.append(
                FittingParameter(value=0.0, name=f"rho{tag}({i})", lb=-0.99, ub=0.99,
                                 bounds_on=True, fixed=True,
                                 label_text=f"&rho;<sub>{tag},{i}</sub>")
            )

    def pop(self):
        """Remove the last species."""
        if not self._amplitudes:
            return
        self._amplitudes.pop()
        for store in (self._means, self._sigmas, self._correlations):
            del store[-3:]

    def _distance_parameter_rows(self) -> list:
        """Return ``(A, R_GR, s_GR, R_BG, s_BG, R_BR, s_BR)`` per species.

        Row source for the editor's paired table (``row_width = 7``), matching
        the layout the field is used to reading.
        """
        rows = []
        for index, amplitude in enumerate(self._amplitudes):
            rows.append(amplitude)
            for mean, sigma in zip(self.means_of(index), self.sigmas_of(index)):
                rows.append(mean)
                rows.append(sigma)
        return rows

    def _correlation_parameter_rows(self) -> list:
        """Return the three pairwise correlations per species (``row_width = 3``)."""
        return list(self._correlations)

    def as_species(self, labeling_fraction: float = 1.0) -> list:
        """Return the compute-core species for the current parameter values.

        Parameters
        ----------
        labeling_fraction : float
            Fraction of molecules carrying the *intended* dye assignment. Below
            one, every population is accompanied by a mirror population in which
            the green and red labels have swapped sites — see
            :meth:`TcPdaModel.stochastic_labeling` for why that is the right
            correction and not a missing-dye one.

        Returns
        -------
        list of ThreeColorSpecies
        """
        labeling_fraction = float(np.clip(labeling_fraction, 0.0, 1.0))
        out = []
        for index, amplitude in enumerate(self._amplitudes):
            mu = np.array([float(p.value) for p in self.means_of(index)])
            sigma = np.array([max(float(p.value), 1e-6) for p in self.sigmas_of(index)])
            rho = np.clip(
                [float(p.value) for p in self.correlations_of(index)], -0.999, 0.999
            )
            weight = max(float(amplitude.value), 0.0)
            out.append(
                ThreeColorSpecies(
                    amplitude=weight * labeling_fraction,
                    means=mu,
                    covariance=covariance_from_statistics(sigma, rho),
                )
            )
            if labeling_fraction < 1.0:
                # Swapping the green and red labels swaps which site each is on,
                # so R_BG <-> R_BR (with their widths). R_GR is the distance
                # *between* the two swapped dyes and is unchanged, as is their
                # mutual correlation; the two correlations with GR trade places.
                out.append(
                    ThreeColorSpecies(
                        amplitude=weight * (1.0 - labeling_fraction),
                        means=np.array([mu[0], mu[2], mu[1]]),
                        covariance=covariance_from_statistics(
                            np.array([sigma[0], sigma[2], sigma[1]]),
                            np.array([rho[1], rho[0], rho[2]]),
                        ),
                    )
                )
        return out


class TcPdaSetup(FittingParameterGroup):
    """Förster radii, spectral corrections and per-channel background.

    The scalar vocabulary the field quotes; the model turns it into the
    excitation / emission probability matrices the compute core composes (see
    :class:`~chisurf.core.fluorescence.pda3c.ThreeColorSetup`). A simulated
    light path can supply the same matrices directly instead.
    """

    def __init__(self, name: str = "tcpda_setup", **kwargs):
        """Initialize the instrument description with neutral defaults."""
        super().__init__(name=name, **kwargs)

        def fixed(value, key, label, lb=0.0, ub=1e6):
            return FittingParameter(value=value, name=key, label_text=label,
                                    lb=lb, ub=ub, bounds_on=True, fixed=True)

        self._R0_bg = fixed(49.0, "R0(BG)", "R<sub>0</sub>(BG)", 1.0, 200.0)
        self._R0_br = fixed(52.0, "R0(BR)", "R<sub>0</sub>(BR)", 1.0, 200.0)
        self._R0_gr = fixed(51.0, "R0(GR)", "R<sub>0</sub>(GR)", 1.0, 200.0)

        self._ct_bg = fixed(0.0, "ct(BG)", "ct B\u2192green", 0.0, 1.0)
        self._ct_br = fixed(0.0, "ct(BR)", "ct B\u2192red", 0.0, 1.0)
        self._ct_gr = fixed(0.0, "ct(GR)", "ct G\u2192red", 0.0, 1.0)

        self._gamma_bg = fixed(1.0, "gamma(BG)", "&gamma;<sub>BG</sub>", 1e-3, 100.0)
        self._gamma_br = fixed(1.0, "gamma(BR)", "&gamma;<sub>BR</sub>", 1e-3, 100.0)

        self._de_bg = fixed(0.0, "de(BG)", "de B\u2192G", 0.0, 0.9)
        self._de_br = fixed(0.0, "de(BR)", "de B\u2192R", 0.0, 0.9)
        self._de_gr = fixed(0.0, "de(GR)", "de G\u2192R", 0.0, 0.9)

        self._bg_bb = fixed(0.0, "BG(bb)", "bg blue|blue", 0.0, 1e4)
        self._bg_bg = fixed(0.0, "BG(bg)", "bg blue|green", 0.0, 1e4)
        self._bg_br = fixed(0.0, "BG(br)", "bg blue|red", 0.0, 1e4)
        self._bg_gg = fixed(0.0, "BG(gg)", "bg green|green", 0.0, 1e4)
        self._bg_gr = fixed(0.0, "BG(gr)", "bg green|red", 0.0, 1e4)

        # Fraction of molecules carrying the intended dye assignment. Free this
        # when the two labelling sites are chemically equivalent.
        self._labeling_fraction = FittingParameter(
            value=1.0, name="F(labeling)", label_text="F<sub>labeling</sub>",
            lb=0.0, ub=1.0, bounds_on=True, fixed=True,
        )

    def as_setup(self) -> ThreeColorSetup:
        """Return the compute-core setup for the current parameter values."""
        return ThreeColorSetup.from_scalars(
            r0_bg=float(self._R0_bg.value),
            r0_br=float(self._R0_br.value),
            r0_gr=float(self._R0_gr.value),
            crosstalk_bg=float(self._ct_bg.value),
            crosstalk_br=float(self._ct_br.value),
            crosstalk_gr=float(self._ct_gr.value),
            gamma_bg=float(self._gamma_bg.value),
            gamma_br=float(self._gamma_br.value),
            direct_excitation_blue=(float(self._de_bg.value), float(self._de_br.value)),
            direct_excitation_green=float(self._de_gr.value),
        )

    @property
    def labeling_fraction(self) -> float:
        """Fraction of molecules with the intended green/red site assignment."""
        return float(np.clip(self._labeling_fraction.value, 0.0, 1.0))

    @property
    def background_blue(self) -> np.ndarray:
        """Mean background counts of the three blue-excitation channels."""
        return np.array([float(self._bg_bb.value), float(self._bg_bg.value),
                         float(self._bg_br.value)])

    @property
    def background_green(self) -> np.ndarray:
        """Mean background counts of the two green-excitation channels."""
        return np.array([float(self._bg_gg.value), float(self._bg_gr.value)])


class TcPdaModel(ModelCurve):
    """Three-colour photon-distribution-analysis model."""

    name = "tcPDA (three-colour)"

    #: Declarative AutoForm layout (PRD-38 model/view-spec split).
    view_spec_file = "tcpda.view.json"

    def __init__(self, fit, species: TcPdaSpecies = None, setup: TcPdaSetup = None, **kwargs):
        """Initialize the three-colour PDA model.

        Parameters
        ----------
        fit : chisurf.core.fitting.fit.Fit
            Fit whose ``data.meta_data['pda3c']`` carries the burst table.
        species : TcPdaSpecies, optional
            Distance-population group.
        setup : TcPdaSetup, optional
            Instrument description.
        **kwargs
            Forwarded to :class:`~chisurf.core.models.model.ModelCurve`.
        """
        super().__init__(fit, **kwargs)
        self.species = species or TcPdaSpecies(fit=fit, **kwargs)
        self.setup = setup or TcPdaSetup(fit=fit, **kwargs)
        if len(self.species) == 0:
            self.species.append()

        #: Gauss-Hermite nodes per distance axis; 5 is ample for a Gaussian.
        self.n_nodes = 5
        #: Drop quadrature nodes below this normalised weight.
        self.truncate = 1e-6
        #: Correct for green/red labels landing on either of two equivalent
        #: sites. Off by default: it doubles the species count, and it is only
        #: physical when the sites really are equivalent.
        self.stochastic_labeling = False
        #: Give each species its own photon-number distribution, scaled by
        #: how bright energy transfer makes it. Off by default: it changes
        #: the likelihood normalisation, so chi2r is not comparable across
        #: the switch.
        self.brightness_correction = False
        self._counts_cache = None

    # -- data ------------------------------------------------------------

    def burst_counts(self) -> BurstCounts | None:
        """Return the (collapsed) burst table from the fit's dataset."""
        if self._counts_cache is not None:
            return self._counts_cache
        payload = None
        data = getattr(self.fit, "data", None)
        meta = getattr(data, "meta_data", None)
        if isinstance(meta, dict):
            payload = meta.get("pda3c")
        if payload is None:
            payload = getattr(data, "pda3c", None)
        if not isinstance(payload, dict):
            return None
        try:
            counts = BurstCounts(blue=payload["blue"], green=payload["green"]).collapsed()
        except Exception:
            return None
        self._counts_cache = counts
        return counts

    # -- objective -------------------------------------------------------

    def _saturated_log_likelihood(self, counts: BurstCounts) -> np.ndarray:
        """Per-burst log likelihood of the model that fits each burst exactly.

        The multinomial with ``p = F / N``. Parameter-independent, so it shifts
        the objective by a constant and cannot move the optimum; it is here only
        so the reported chi2r is calibrated rather than an arbitrary
        log-likelihood.
        """
        total = 0.0
        for table in (counts.blue, counts.green):
            n = table.sum(axis=1, keepdims=True)
            with np.errstate(divide="ignore", invalid="ignore"):
                p = np.where(n > 0, table / np.where(n > 0, n, 1.0), 0.0)
            total = total + log_multinomial_pmf(table, p)
        return total

    def _labeling_weight(self) -> float:
        """Return the labelling fraction to expand species with.

        One when the correction is off, so the species list is untouched and
        the model costs exactly what it did before.
        """
        if not getattr(self, "stochastic_labeling", False):
            return 1.0
        return self.setup.labeling_fraction

    @property
    def n_points(self) -> int:
        """Number of independent observations behind the objective.

        Not the length of the displayed curve — that is a projection for
        looking at, while the objective is the burst likelihood. Each burst
        contributes the free cells of its two photon partitions: two from the
        blue trinomial and one from the green binomial. Getting this wrong does
        not change the fit, but it does make the reported chi2r meaningless
        (and, when the curve is shorter than the parameter count, negative).
        """
        counts = self.burst_counts()
        if counts is None:
            return 0
        n_bursts = float(np.sum(counts.multiplicity))
        free_cells = (counts.blue.shape[1] - 1) + (counts.green.shape[1] - 1)
        return int(round(n_bursts * free_cells))

    def get_wres(self, fit, xmin: int = None, xmax: int = None) -> np.ndarray:
        """Return per-burst multinomial deviance residuals.

        ``sum(wres**2)`` equals ``const - 2 log L``, so least-squares
        minimisation of this vector is maximum-likelihood estimation.
        """
        counts = self.burst_counts()
        if counts is None:
            return np.zeros(0, dtype=np.float64)
        try:
            per_burst = self._per_burst_log_likelihood(counts)
            saturated = self._saturated_log_likelihood(counts)
        except Exception:
            return np.zeros(0, dtype=np.float64)
        deviance = 2.0 * (saturated - per_burst) * counts.multiplicity
        return np.sqrt(np.maximum(deviance, 0.0))

    def _burst_size_pmfs(self, counts: BurstCounts):
        """Return the measured burst-size distributions of the two periods."""
        cached = getattr(self, "_pmf_cache", None)
        if cached is not None:
            return cached
        out = []
        for table in (counts.blue, counts.green):
            sizes = table.sum(axis=1).astype(int)
            pmf = np.bincount(sizes, weights=counts.multiplicity)
            total = pmf.sum()
            out.append(pmf / total if total > 0 else pmf)
        self._pmf_cache = tuple(out)
        return self._pmf_cache

    def _species_photon_number_pmfs(self, counts: BurstCounts, component):
        """Return this species' photon-number distributions, or ``(None, None)``.

        A species whose transfer makes it dim produces smaller bursts. Ignoring
        that over-weights it: it is credited the same amplitude while
        contributing fewer photons. The correction stretches the measured
        burst-size distribution by the species' relative brightness, which is a
        by-product of the channel weights rather than a new parameter.
        """
        if not getattr(self, "brightness_correction", False):
            return None, None
        setup = self.setup.as_setup()
        distances = distances_to_matrix(
            np.array([component.means[1], component.means[2], component.means[0]])
        )
        reference_blue, reference_green = self._burst_size_pmfs(counts)
        return (
            scale_photon_number_pmf(
                reference_blue, float(np.ravel(relative_brightness(distances, setup, 0))[0])
            ),
            scale_photon_number_pmf(
                reference_green, float(np.ravel(relative_brightness(distances, setup, 1))[0])
            ),
        )

    def _per_burst_log_likelihood(self, counts: BurstCounts) -> np.ndarray:
        """Return the per-burst log likelihood under the current parameters."""
        from scipy.special import logsumexp

        from chisurf.core.fluorescence.pda3c.model import _species_log_likelihood

        setup = self.setup.as_setup()
        species = self.species.as_species(self._labeling_weight())
        amplitudes = np.array([max(s.amplitude, 0.0) for s in species], dtype=float)
        if amplitudes.sum() <= 0.0:
            amplitudes = np.ones_like(amplitudes)
        amplitudes = amplitudes / amplitudes.sum()

        per_species = np.stack(
            [
                _species_log_likelihood(
                    counts, s, setup,
                    self.setup.background_blue, self.setup.background_green,
                    *self._species_photon_number_pmfs(counts, s),
                    self.n_nodes, self.truncate,
                )
                for s in species
            ],
            axis=0,
        )
        with np.errstate(divide="ignore"):
            return logsumexp(np.log(amplitudes)[:, None] + per_species, axis=0)

    def total_log_likelihood(self) -> float:
        """Return the total log likelihood of the dataset.

        Deliberately routed through the same per-burst evaluation the residual
        uses, rather than the standalone core function: a diagnostic that can
        disagree with the objective is worse than no diagnostic. (It did, once —
        the standalone path silently ignored the brightness correction.)
        """
        counts = self.burst_counts()
        if counts is None:
            return float("nan")
        per_burst = self._per_burst_log_likelihood(counts)
        return float(np.sum(counts.multiplicity * per_burst))

    # -- display ---------------------------------------------------------

    def update_model(self, verbose: bool = None, **kwargs):
        """Recompute the predicted proximity-ratio histograms.

        Analytic, not resampled: each displayed ratio is a *marginal* of the
        photon partition, and a multinomial marginal is a binomial, so the
        predicted histogram is a weighted sum of binomial pmfs over the observed
        burst sizes and the quadrature nodes.
        """
        counts = self.burst_counts()
        if counts is None:
            self.d = np.vstack((np.arange(1), np.zeros(1)))
            return
        y = predicted_ratio_histograms(
            counts, self.species.as_species(self._labeling_weight()), self.setup.as_setup(),
            n_nodes=self.n_nodes, truncate=self.truncate,
        )
        total = float(np.sum(counts.multiplicity))
        self.d = np.vstack((np.arange(y.size), y * total))


def _binomial_marginal_histogram(sizes, weights, probabilities, node_weights) -> np.ndarray:
    """Return the predicted histogram of ``k / n`` for a binomial marginal.

    Parameters
    ----------
    sizes : array_like
        Distinct burst sizes ``n``.
    weights : array_like
        Weight of each burst size (its multiplicity).
    probabilities : array_like
        Per-node success probability.
    node_weights : array_like
        Quadrature weights.

    Returns
    -------
    numpy.ndarray
        Normalised histogram over ``N_RATIO_BINS`` bins of ``k / n`` in [0, 1].
    """
    from scipy.stats import binom

    edges = np.linspace(0.0, 1.0, N_RATIO_BINS + 1)
    out = np.zeros(N_RATIO_BINS, dtype=float)
    total_weight = float(np.sum(weights))
    if total_weight <= 0.0:
        return out
    for n, w in zip(sizes, weights):
        n = int(n)
        if n <= 0:
            continue
        k = np.arange(n + 1)
        pmf = binom.pmf(k[None, :], n, np.asarray(probabilities)[:, None])
        mixed = node_weights @ pmf
        index = np.clip(np.digitize(k / n, edges) - 1, 0, N_RATIO_BINS - 1)
        np.add.at(out, index, mixed * (w / total_weight))
    return out


def predicted_ratio_histograms(counts: BurstCounts, species, setup, n_nodes=5,
                               truncate=1e-6) -> np.ndarray:
    """Return the three predicted proximity-ratio histograms, concatenated.

    Order: ``F_BG/N_blue``, ``F_BR/N_blue``, ``F_GR/N_green`` — the projections
    the incumbent's three tabs show.

    Parameters
    ----------
    counts : BurstCounts
        Observed burst table (supplies the burst-size distribution).
    species : sequence of ThreeColorSpecies
        Mixture components.
    setup : ThreeColorSetup
        Instrument description.
    n_nodes : int
        Gauss-Hermite nodes per distance axis.
    truncate : float
        Drop quadrature nodes below this normalised weight.

    Returns
    -------
    numpy.ndarray
        ``3 * N_RATIO_BINS`` normalised bin contents.
    """
    from chisurf.core.fluorescence.pda3c import (
        blue_channel_probabilities,
        green_channel_probabilities,
    )

    amplitudes = np.array([max(float(s.amplitude), 0.0) for s in species], dtype=float)
    if amplitudes.sum() <= 0.0:
        amplitudes = np.ones_like(amplitudes)
    amplitudes = amplitudes / amplitudes.sum()

    n_blue = counts.blue.sum(axis=1)
    n_green = counts.green.sum(axis=1)
    blue_sizes, blue_weights = _weighted_unique(n_blue, counts.multiplicity)
    green_sizes, green_weights = _weighted_unique(n_green, counts.multiplicity)

    out = np.zeros(3 * N_RATIO_BINS, dtype=float)
    for amplitude, component in zip(amplitudes, species):
        points, node_weights = component.quadrature(n_nodes=n_nodes, truncate=truncate)
        p_blue = blue_channel_probabilities(
            points[:, 1], points[:, 2], points[:, 0], setup
        )
        p_green = green_channel_probabilities(points[:, 0], setup)
        out[:N_RATIO_BINS] += amplitude * _binomial_marginal_histogram(
            blue_sizes, blue_weights, p_blue[:, 1], node_weights
        )
        out[N_RATIO_BINS:2 * N_RATIO_BINS] += amplitude * _binomial_marginal_histogram(
            blue_sizes, blue_weights, p_blue[:, 2], node_weights
        )
        out[2 * N_RATIO_BINS:] += amplitude * _binomial_marginal_histogram(
            green_sizes, green_weights, p_green[:, 1], node_weights
        )
    return out / 3.0


def observed_ratio_histograms(counts: BurstCounts) -> np.ndarray:
    """Return the three measured proximity-ratio histograms, concatenated."""
    edges = np.linspace(0.0, 1.0, N_RATIO_BINS + 1)
    n_blue = counts.blue.sum(axis=1)
    n_green = counts.green.sum(axis=1)
    out = []
    for values, sizes in (
        (counts.blue[:, 1], n_blue),
        (counts.blue[:, 2], n_blue),
        (counts.green[:, 1], n_green),
    ):
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.where(sizes > 0, values / np.where(sizes > 0, sizes, 1.0), 0.0)
        hist, _ = np.histogram(ratio[sizes > 0], bins=edges,
                               weights=counts.multiplicity[sizes > 0])
        out.append(hist)
    stacked = np.concatenate(out)
    total = stacked.sum()
    return stacked / total if total > 0 else stacked


def _weighted_unique(values, weights):
    """Return distinct values and their summed weights."""
    values = np.asarray(values)
    weights = np.asarray(weights, dtype=float)
    unique, inverse = np.unique(values, return_inverse=True)
    summed = np.zeros(unique.size, dtype=float)
    np.add.at(summed, inverse, weights)
    return unique, summed


def get_tcpda_ratio_curves(fit) -> list:
    """Return data / model / residual curves for the AutoForm distribution plot.

    Qt-free accessor, so the plot stays authorable in ``view.json``.

    Parameters
    ----------
    fit : chisurf.core.fitting.fit.Fit
        Fit whose model is a :class:`TcPdaModel`.

    Returns
    -------
    list
        ``[[data_y, x], [model_y, x], [residual, x]]``.
    """
    model = getattr(fit, "model", None)
    counts = getattr(model, "burst_counts", lambda: None)()
    if counts is None:
        return []
    observed = observed_ratio_histograms(counts)
    predicted = predicted_ratio_histograms(
        counts, model.species.as_species(model._labeling_weight()), model.setup.as_setup(),
        n_nodes=model.n_nodes, truncate=model.truncate,
    )
    total = float(np.sum(counts.multiplicity))
    x = np.arange(observed.size, dtype=float)
    data_y = observed * total
    model_y = predicted * total
    sigma = np.sqrt(np.maximum(data_y, 1.0))
    return [[data_y, x], [model_y, x], [(data_y - model_y) / sigma, x]]


def get_tcpda_distance_distributions(fit) -> list:
    """Return the three marginal distance distributions P(R) for plotting.

    Parameters
    ----------
    fit : chisurf.core.fitting.fit.Fit
        Fit whose model is a :class:`TcPdaModel`.

    Returns
    -------
    list
        One ``[p, r]`` curve per dye pair (GR, BG, BR).
    """
    model = getattr(fit, "model", None)
    if model is None or not hasattr(model, "species"):
        return []
    r = cs.core.models.tcspc.fret.rda_axis
    curves = []
    for axis in range(3):
        density = np.zeros_like(r, dtype=float)
        for component in model.species.as_species(model._labeling_weight()):
            mu = float(component.means[axis])
            sigma = float(np.sqrt(max(component.covariance[axis, axis], 1e-12)))
            density += component.amplitude * np.exp(-0.5 * ((r - mu) / sigma) ** 2)
        total = density.sum()
        curves.append([density / total if total > 0 else density, r])
    return curves


def scale_photon_number_pmf(pmf, brightness: float) -> np.ndarray:
    """Stretch a photon-number distribution by a relative brightness.

    A molecule ``brightness`` times as bright produces bursts ``brightness``
    times as large, so its distribution is the reference with the count axis
    stretched: ``P_scaled(n) = P(n / brightness)``, resampled onto the integer
    grid. Linear in the counts, which is the usual approximation.

    Parameters
    ----------
    pmf : array_like
        Reference photon-number distribution, indexed by count.
    brightness : float
        Relative brightness; ``1`` returns the reference unchanged.

    Returns
    -------
    numpy.ndarray
        Normalised distribution on the same grid.
    """
    pmf = np.asarray(pmf, dtype=float)
    if not np.isfinite(brightness) or brightness <= 0.0 or pmf.size == 0:
        return pmf
    if abs(brightness - 1.0) < 1e-12:
        return pmf
    grid = np.arange(pmf.size, dtype=float)
    scaled = np.interp(grid / brightness, grid, pmf, left=0.0, right=0.0)
    total = scaled.sum()
    return scaled / total if total > 0 else scaled
