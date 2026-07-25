r"""Assembling the three-colour PDA model: species, distances, bursts.

Puts the three pieces together — :mod:`.species` supplies quadrature nodes over
a correlated distance distribution, :mod:`.physics` turns each node into channel
probabilities, and :mod:`.likelihood` scores the observed counts — and adds the
one structural fact that cannot be delegated to any of them.

Mix once, not twice
-------------------
Each burst carries counts from **both** excitation periods, and both come from
the *same molecule at the same distances*. The blue-excitation trinomial and the
green-excitation binomial must therefore be multiplied together **before**
averaging over the distance distribution:

.. math::

    L_j = \sum_k w_k\, L^{\text{blue}}_j(R_k)\, L^{\text{green}}_j(R_k),

not :math:`\big(\sum_k w_k L^{\text{blue}}_j\big)\big(\sum_k w_k
L^{\text{green}}_j\big)`. Averaging the two halves separately would model a
molecule that redraws its conformation between the blue and green pulses,
throwing away precisely the correlation the experiment exists to measure. In log
space that is one ``logsumexp`` over the node axis applied to the *sum* of the
two log-likelihoods.

The same argument applies once more at the species level: a burst belongs to one
species, so species are mixed after the node average, with their amplitudes.
"""

from __future__ import annotations

import dataclasses

import numpy as np
from scipy.special import logsumexp

from .likelihood import burst_log_likelihood, collapse_bursts
from .physics import (
    ThreeColorSetup,
    blue_channel_probabilities,
    green_channel_probabilities,
)
from .species import covariance_to_cholesky, gauss_hermite_grid

__all__ = [
    "BurstCounts",
    "ThreeColorSpecies",
    "simulate_bursts",
    "total_log_likelihood",
]


@dataclasses.dataclass
class ThreeColorSpecies:
    """One trivariate-Gaussian population of distances.

    Attributes
    ----------
    amplitude : float
        Relative weight of this species; normalised across species.
    means : array_like
        Mean ``(R_GR, R_BG, R_BR)`` in Angstrom.
    covariance : array_like
        ``(3, 3)`` covariance in the same order. Repaired to positive definite
        on use, so an inconsistent set of pairwise correlations is tolerated
        rather than fatal.
    """

    amplitude: float = 1.0
    means: np.ndarray = dataclasses.field(default_factory=lambda: np.array([50.0, 50.0, 50.0]))
    covariance: np.ndarray = dataclasses.field(default_factory=lambda: np.eye(3) * 36.0)

    def quadrature(self, n_nodes: int = 7, truncate: float = 1e-6):
        """Return ``(points, weights)`` over this species' distance distribution."""
        cholesky = covariance_to_cholesky(self.covariance)
        return gauss_hermite_grid(self.means, cholesky, n_nodes=n_nodes, truncate=truncate)


@dataclasses.dataclass
class BurstCounts:
    """Per-burst photon counts of a three-colour PIE measurement.

    Attributes
    ----------
    blue : numpy.ndarray
        ``(n_bursts, 3)`` counts under blue excitation, channel order
        (blue, green, red) — ``F_BB``, ``F_BG``, ``F_BR``.
    green : numpy.ndarray
        ``(n_bursts, 2)`` counts under green excitation, channel order
        (green, red) — ``F_GG``, ``F_GR``.
    multiplicity : numpy.ndarray or None
        Weight per row, set when duplicate bursts have been collapsed.
    """

    blue: np.ndarray
    green: np.ndarray
    multiplicity: np.ndarray = None

    def __post_init__(self):
        """Coerce to arrays and default the multiplicity to one per burst."""
        self.blue = np.atleast_2d(np.asarray(self.blue, dtype=float))
        self.green = np.atleast_2d(np.asarray(self.green, dtype=float))
        if self.blue.shape[0] != self.green.shape[0]:
            raise ValueError("blue and green count tables must have the same burst count")
        if self.multiplicity is None:
            self.multiplicity = np.ones(self.blue.shape[0], dtype=float)
        self.multiplicity = np.asarray(self.multiplicity, dtype=float)

    def collapsed(self) -> "BurstCounts":
        """Return an equivalent table with duplicate bursts merged.

        Exact: the likelihood sees a burst only through its counts, so bursts
        sharing all five collapse to one weighted row. Both excitation periods
        must be collapsed *jointly* — two bursts with the same blue counts but
        different green counts are different bursts.
        """
        joint = np.hstack([self.blue, self.green])
        unique, multiplicity = collapse_bursts(joint)
        n_blue = self.blue.shape[1]
        return BurstCounts(
            blue=unique[:, :n_blue],
            green=unique[:, n_blue:],
            multiplicity=multiplicity.astype(float),
        )


def _species_log_likelihood(
        counts: BurstCounts,
        species: ThreeColorSpecies,
        setup: ThreeColorSetup,
        background_blue,
        background_green,
        photon_number_pmf_blue,
        photon_number_pmf_green,
        n_nodes: int,
        truncate: float,
) -> np.ndarray:
    """Per-burst log likelihood under one species, averaged over its distances."""
    points, weights = species.quadrature(n_nodes=n_nodes, truncate=truncate)
    r_gr, r_bg, r_br = points[:, 0], points[:, 1], points[:, 2]

    p_blue = blue_channel_probabilities(r_bg, r_br, r_gr, setup)
    p_green = green_channel_probabilities(r_gr, setup)

    ll_blue = burst_log_likelihood(
        counts.blue, p_blue, background_blue, photon_number_pmf_blue
    )
    ll_green = burst_log_likelihood(
        counts.green, p_green, background_green, photon_number_pmf_green
    )

    # Both periods observe the same molecule at the same distances, so they are
    # multiplied at each node and only then averaged. See the module docstring.
    ll_node = ll_blue + ll_green
    return logsumexp(np.log(weights)[:, None] + ll_node, axis=0)


def total_log_likelihood(
        counts: BurstCounts,
        species,
        setup: ThreeColorSetup,
        background_blue=None,
        background_green=None,
        photon_number_pmf_blue=None,
        photon_number_pmf_green=None,
        n_nodes: int = 7,
        truncate: float = 1e-6,
) -> float:
    """Total log likelihood of a burst table under a three-colour PDA model.

    Parameters
    ----------
    counts : BurstCounts
        Observed per-burst counts; pass ``counts.collapsed()`` for speed.
    species : sequence of ThreeColorSpecies
        Mixture components; amplitudes are normalised internally.
    setup : ThreeColorSetup
        Förster radii, detection matrix, direct excitation.
    background_blue, background_green : array_like, optional
        Mean background counts per channel, shapes ``(3,)`` and ``(2,)``.
    photon_number_pmf_blue, photon_number_pmf_green : array_like, optional
        Signal photon-number distributions; see
        :mod:`~chisurf.core.fluorescence.pda3c.likelihood`.
    n_nodes : int
        Gauss–Hermite nodes per distance axis.
    truncate : float
        Drop quadrature nodes below this normalised weight.

    Returns
    -------
    float
        Sum over bursts of the log likelihood, weighted by multiplicity.
    """
    species = list(species)
    if not species:
        raise ValueError("at least one species is required")

    amplitudes = np.array([max(float(s.amplitude), 0.0) for s in species], dtype=float)
    total = amplitudes.sum()
    if total <= 0.0:
        raise ValueError("species amplitudes must not all be zero")
    amplitudes = amplitudes / total

    per_species = np.stack(
        [
            _species_log_likelihood(
                counts,
                s,
                setup,
                background_blue,
                background_green,
                photon_number_pmf_blue,
                photon_number_pmf_green,
                n_nodes,
                truncate,
            )
            for s in species
        ],
        axis=0,
    )

    # A burst belongs to one species, so mix species after the node average.
    with np.errstate(divide="ignore"):
        per_burst = logsumexp(np.log(amplitudes)[:, None] + per_species, axis=0)
    return float(np.sum(counts.multiplicity * per_burst))


def simulate_bursts(
        n_bursts: int,
        species,
        setup: ThreeColorSetup,
        photons_blue: float = 30.0,
        photons_green: float = 25.0,
        background_blue=None,
        background_green=None,
        seed: int = 0,
) -> BurstCounts:
    """Draw a synthetic three-colour burst table from a model.

    Generates by the definition rather than by the likelihood's factorisation,
    so recovering a known truth from these bursts tests the forward model rather
    than restating it: each burst picks a species, draws one distance triple
    from its trivariate Gaussian, converts to channel probabilities, and
    multinomially splits an independently drawn photon budget, with Poisson
    background added on top.

    Parameters
    ----------
    n_bursts : int
        Number of bursts.
    species : sequence of ThreeColorSpecies
        Mixture to draw from; amplitudes give the species proportions.
    setup : ThreeColorSetup
        Förster radii, detection matrix, direct excitation.
    photons_blue, photons_green : float
        Mean *signal* photons per burst in each excitation period (Poisson).
    background_blue, background_green : array_like, optional
        Mean background counts per channel.
    seed : int
        Random seed.

    Returns
    -------
    BurstCounts
    """
    rng = np.random.default_rng(seed)
    species = list(species)
    amplitudes = np.array([max(float(s.amplitude), 0.0) for s in species], dtype=float)
    amplitudes = amplitudes / amplitudes.sum()

    which = rng.choice(len(species), size=n_bursts, p=amplitudes)
    distances = np.empty((n_bursts, 3), dtype=float)
    for index, component in enumerate(species):
        rows = which == index
        if not np.any(rows):
            continue
        distances[rows] = rng.multivariate_normal(
            np.asarray(component.means, dtype=float),
            np.asarray(component.covariance, dtype=float),
            size=int(rows.sum()),
        )
    distances = np.clip(distances, 1e-6, None)

    p_blue = blue_channel_probabilities(
        distances[:, 1], distances[:, 2], distances[:, 0], setup
    )
    p_green = green_channel_probabilities(distances[:, 0], setup)

    n_blue = rng.poisson(photons_blue, size=n_bursts)
    n_green = rng.poisson(photons_green, size=n_bursts)

    blue = np.array([rng.multinomial(n, p) for n, p in zip(n_blue, p_blue)], dtype=float)
    green = np.array([rng.multinomial(n, p) for n, p in zip(n_green, p_green)], dtype=float)

    if background_blue is not None:
        blue += rng.poisson(np.asarray(background_blue, dtype=float), size=(n_bursts, 3))
    if background_green is not None:
        green += rng.poisson(np.asarray(background_green, dtype=float), size=(n_bursts, 2))

    return BurstCounts(blue=blue, green=green)
