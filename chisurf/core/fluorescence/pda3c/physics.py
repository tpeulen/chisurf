r"""Multi-colour FRET as three matrices: excitation, transfer, emission.

Turns inter-dye distances into the per-channel photon probabilities the burst
likelihood in :mod:`~chisurf.core.fluorescence.pda3c.likelihood` consumes, by
composing three linear maps in the orientation the rest of ChiSurf already uses
(``(sources, detectors)``, see :mod:`chisurf.core.fluorescence.crosstalk`):

.. math::

    p(\text{laser } \ell) \;\propto\;
        \underbrace{X_{\ell,\cdot}}_{\text{excitation}}\;
        \underbrace{T(R)}_{\text{transfer}}\;
        \underbrace{M}_{\text{emission}}

============ ================== ==============================================
matrix       shape              meaning
============ ================== ==============================================
``excitation`` ``(lasers, dyes)`` probability that a pulse of laser ``ℓ``
                                 deposits its excitation on dye ``d``. **Rows
                                 sum to one** — a pulse excites exactly one dye,
                                 so direct excitation of the redder dyes
                                 *partitions* the excitation rather than adding
                                 to it. Off-diagonals are direct excitation.
``transfer``   ``(dyes, dyes)``   probability that an excitation deposited on
                                 dye ``i`` is finally emitted by dye ``j``.
                                 Built from the distances; see below.
``emission``   ``(dyes, chans)``  probability that a photon emitted by dye ``d``
                                 is counted in channel ``c``. Folds quantum
                                 yield, filter transmission, detector efficiency
                                 and spectral bleed-through. Off-diagonals are
                                 emission crosstalk.
============ ================== ==============================================

``excitation`` and ``emission`` are exactly the two matrices
``lightpath_simulator``'s ``get_crosstalk_matrices()`` produces (``laser × dye``
and ``dye × detector``), so a simulated light path can be dropped straight in
via :meth:`ThreeColorSetup.from_crosstalk_matrices`. The two-colour PDA nuisance
group spells the same quantities out as scalars — ``ExDG``/``ExAG`` are one
excitation row, ``gG``/``gR`` the emission diagonal, ``cGD``/``cGA``/``cRD``/
``cRA`` its off-diagonals.

The transfer matrix
-------------------
This is the part that is genuinely multi-colour. With
$x_{ij} = (R_{0,ij}/R_{ij})^6$, an excited dye $i$ distributes its excitation
over the dyes below it in energy, and the pathways **compete** — they are rates
out of one excited state, so they share a denominator:

.. math::

    E_{i \to j} = \frac{x_{ij}}{1 + \sum_{k>i} x_{ik}}.

Opening a second acceptor therefore *reduces* transfer to the first even though
that distance has not moved; reading a two-colour formula off one pair of a
three-colour construct overestimates its distance, in the direction that mimics
the molecule getting longer.

Energy may then **cascade** onward, so $T$ is the upper-triangular matrix
accumulating every route from $i$ to $j$ — for three dyes,

.. math::

    T = \begin{pmatrix}
        1 - E_{BG} - E_{BR} & E_{BG}(1-E_{GR}) & E_{BR} + E_{BG}E_{GR} \\
        0 & 1 - E_{GR} & E_{GR} \\
        0 & 0 & 1
    \end{pmatrix}.

The red entry of the first row carries two distinguishable routes — direct
$B\to R$ and the $B\to G\to R$ relay — and that redundancy is exactly why three
distances are identifiable from count statistics at all.

Writing it as a matrix rather than by hand generalises for free: $T$ is built by
a downhill recursion over any number of dyes, so a four-colour construct needs
no new algebra here.
"""

from __future__ import annotations

import dataclasses

import numpy as np

from chisurf.core.fluorescence.crosstalk import apply_mixing, matrix_from_payload

__all__ = [
    "ThreeColorSetup",
    "blue_channel_probabilities",
    "channel_probabilities",
    "channel_weights",
    "green_channel_probabilities",
    "relative_brightness",
    "transfer_efficiencies",
    "transfer_matrix",
]

#: Dye order used throughout: blue, green, red (increasing wavelength).
DYES = ("B", "G", "R")
#: Laser order: the blue and green (PIE/ALEX) excitation periods.
LASERS = ("blue", "green")
#: Detection channel order.
CHANNELS = ("blue", "green", "red")


def _symmetric_radii(value) -> np.ndarray:
    """Coerce Förster radii to a symmetric ``(n_dyes, n_dyes)`` matrix."""
    array = np.asarray(value, dtype=float)
    if array.ndim == 2:
        return 0.5 * (array + array.T)
    raise ValueError("forster_radii must be a square matrix")


@dataclasses.dataclass
class ThreeColorSetup:
    """Dye pair radii plus the excitation and emission probability matrices.

    Attributes
    ----------
    forster_radii : numpy.ndarray
        Symmetric ``(n_dyes, n_dyes)`` Förster radii in Angstrom; only the
        strictly upper triangle is read (a pair, not a direction).
    excitation : numpy.ndarray
        ``(n_lasers, n_dyes)``; row ``ℓ`` is how laser ``ℓ`` distributes its
        excitation over the dyes. Rows are projected onto the probability
        simplex on construction — clipped non-negative, then normalised —
        because a pulse excites exactly one dye.
    emission : numpy.ndarray
        ``(n_dyes, n_channels)``; ``emission[d, c]`` is the probability that a
        photon emitted by dye ``d`` is counted in channel ``c``.
    """

    forster_radii: np.ndarray = dataclasses.field(
        default_factory=lambda: np.full((3, 3), 50.0)
    )
    excitation: np.ndarray = dataclasses.field(default_factory=lambda: np.eye(2, 3))
    emission: np.ndarray = dataclasses.field(default_factory=lambda: np.eye(3))

    def __post_init__(self):
        """Coerce the matrices to arrays and project the excitation rows onto the simplex."""
        self.forster_radii = _symmetric_radii(self.forster_radii)
        self.excitation = np.atleast_2d(np.asarray(self.excitation, dtype=float))
        self.emission = np.atleast_2d(np.asarray(self.emission, dtype=float))

        # A pulse excites exactly one dye. Normalising here is what makes direct
        # excitation partition rather than top up -- getting this wrong is
        # invisible at zero direct excitation and grows with it.
        #
        # Normalising by the sum enforces only half of what a probability row
        # is: an over-subscribed direct excitation (de_BG + de_BR > 1) leaves
        # the direct term *negative* while the row still sums to exactly one,
        # so the normalisation is a silent no-op over a negative probability.
        # Clip first -- with the rescale below that projects the row back onto
        # the simplex rather than shipping an entry no downstream formula can
        # interpret.
        self.excitation = np.clip(self.excitation, 0.0, None)
        totals = self.excitation.sum(axis=1, keepdims=True)
        self.excitation = np.divide(
            self.excitation,
            np.where(totals > 0.0, totals, 1.0),
            out=np.zeros_like(self.excitation),
            where=totals > 0.0,
        )

    @property
    def n_dyes(self) -> int:
        """Number of dyes."""
        return self.emission.shape[0]

    @classmethod
    def from_scalars(
            cls,
            r0_bg: float = 50.0,
            r0_br: float = 50.0,
            r0_gr: float = 50.0,
            crosstalk_bg: float = 0.0,
            crosstalk_br: float = 0.0,
            crosstalk_gr: float = 0.0,
            gamma_bg: float = 1.0,
            gamma_br: float = 1.0,
            direct_excitation_blue=(0.0, 0.0),
            direct_excitation_green: float = 0.0,
    ) -> ThreeColorSetup:
        """Build a setup from the scalar corrections the field usually quotes.

        A convenience over the matrix form for the common triangular case, and
        the bridge to the two-colour nuisance group's vocabulary. ``crosstalk_xy``
        is emission of dye ``x`` leaking into channel ``y``; ``gamma_xy`` is the
        detection efficiency of dye ``y`` relative to dye ``x``.

        Parameters
        ----------
        r0_bg, r0_br, r0_gr : float
            Förster radii of the three pairs, in Angstrom.
        crosstalk_bg, crosstalk_br, crosstalk_gr : float
            Emission bleed-through B→green, B→red and G→red channels.
        gamma_bg, gamma_br : float
            Detection efficiency of G and R relative to B.
        direct_excitation_blue : tuple of float
            Chance a blue pulse lands directly on (G, R).
        direct_excitation_green : float
            Chance a green pulse lands directly on R.

        Returns
        -------
        ThreeColorSetup
        """
        de_bg, de_br = direct_excitation_blue
        radii = np.array(
            [
                [0.0, r0_bg, r0_br],
                [r0_bg, 0.0, r0_gr],
                [r0_br, r0_gr, 0.0],
            ]
        )
        excitation = np.array(
            [
                [1.0 - de_bg - de_br, de_bg, de_br],
                [0.0, 1.0 - direct_excitation_green, direct_excitation_green],
            ]
        )
        # dye -> channel; a redder dye does not leak into a bluer channel.
        emission = np.array(
            [
                [1.0, crosstalk_bg, crosstalk_br],
                [0.0, gamma_bg, gamma_bg * crosstalk_gr],
                [0.0, 0.0, gamma_br],
            ]
        )
        return cls(forster_radii=radii, excitation=excitation, emission=emission)

    @classmethod
    def from_crosstalk_matrices(
            cls,
            payload,
            forster_radii,
            dyes=DYES,
            lasers=LASERS,
            detectors=CHANNELS,
    ) -> ThreeColorSetup:
        """Build a setup from a light-path simulator's crosstalk payload.

        ``get_crosstalk_matrices()`` already emits a ``laser × dye`` excitation
        matrix and a ``dye × detector`` emission matrix — the same two objects
        this model wants — so a simulated optical path can be used directly
        instead of hand-entered correction factors.

        Parameters
        ----------
        payload : dict
            The ``get_crosstalk_matrices()`` return value.
        forster_radii : array_like
            Symmetric ``(n_dyes, n_dyes)`` Förster radii; not part of the light
            path, so supplied separately.
        dyes, lasers, detectors : sequence of str
            Label ordering to select from the payload.

        Returns
        -------
        ThreeColorSetup
        """
        excitation, _, _ = matrix_from_payload(
            payload["excitation"], rows=lasers, columns=dyes
        )
        emission, _, _ = matrix_from_payload(
            payload["emission"], rows=dyes, columns=detectors
        )
        return cls(forster_radii=forster_radii, excitation=excitation, emission=emission)


def transfer_efficiencies(distances, setup: ThreeColorSetup) -> np.ndarray:
    """Return the pairwise transfer efficiencies out of each excited dye.

    ``result[..., i, j]`` is the probability that an excitation on dye ``i``
    transfers to dye ``j`` in one step. The competition is in the shared
    denominator: every downhill pathway out of ``i`` is a rate leaving the same
    excited state.

    Parameters
    ----------
    distances : array_like
        ``(..., n_dyes, n_dyes)`` symmetric inter-dye distances in Angstrom.
        Use :func:`distances_to_matrix` to build this from pair distances — the
        matrix form is required rather than inferred, because with three dyes
        the pair count equals the dye count and a ``(3, 3)`` array is genuinely
        ambiguous between "three pair-vectors" and "one distance matrix".
    setup : ThreeColorSetup
        Supplies the Förster radii.

    Returns
    -------
    numpy.ndarray
        ``(..., n_dyes, n_dyes)`` one-step transfer efficiencies, zero on and
        below the diagonal.
    """
    distances = np.asarray(distances, dtype=float)
    n = setup.n_dyes
    radii = setup.forster_radii
    if distances.shape[-2:] != (n, n):
        raise ValueError(
            f"distances must be (..., {n}, {n}); use distances_to_matrix() for pairs"
        )

    upper = np.triu(np.ones((n, n), dtype=bool), k=1)
    with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
        x = np.where(
            upper & (distances > 0.0),
            (radii / np.where(distances > 0.0, distances, 1.0)) ** 6,
            0.0,
        )
        # A zero distance is infinitely fast transfer.
        x = np.where(upper & (distances <= 0.0), np.inf, x)
        denominator = 1.0 + x.sum(axis=-1, keepdims=True)
        efficiencies = np.where(np.isfinite(denominator), x / denominator, 0.0)

    # With an infinite rate present, it takes the whole excitation (split evenly
    # if several are infinite, which only happens at coincident dyes).
    infinite = np.isinf(x)
    any_infinite = infinite.any(axis=-1, keepdims=True)
    if np.any(any_infinite):
        share = infinite / np.maximum(infinite.sum(axis=-1, keepdims=True), 1)
        efficiencies = np.where(any_infinite, share, efficiencies)
    return efficiencies


def transfer_matrix(distances, setup: ThreeColorSetup) -> np.ndarray:
    """Return ``T[..., i, j]``: excitation on dye ``i`` finally emitted by ``j``.

    Accumulates every downhill route, so it includes relays: the ``B→R`` entry
    for three dyes is ``E_BR + E_BG·E_GR``. Built by a recursion from the reddest
    dye upward, which works for any number of dyes.

    Parameters
    ----------
    distances : array_like
        ``(..., n_dyes, n_dyes)`` symmetric inter-dye distances in Angstrom.
    setup : ThreeColorSetup
        Supplies the Förster radii.

    Returns
    -------
    numpy.ndarray
        ``(..., n_dyes, n_dyes)`` upper-triangular row-stochastic matrix.
    """
    efficiencies = transfer_efficiencies(distances, setup)
    n = setup.n_dyes
    shape = efficiencies.shape[:-2]
    matrix = np.zeros(shape + (n, n), dtype=float)

    # Reddest dye emits itself; work upward, each dye either emitting or handing
    # its excitation to a redder one which then follows its own row.
    matrix[..., n - 1, n - 1] = 1.0
    for i in range(n - 2, -1, -1):
        matrix[..., i, i] = 1.0 - efficiencies[..., i, :].sum(axis=-1)
        for j in range(i + 1, n):
            matrix[..., i, :] += efficiencies[..., i, j, None] * matrix[..., j, :]
    return matrix


def distances_to_matrix(pairs, n_dyes: int = 3) -> np.ndarray:
    """Return a symmetric distance matrix from upper-triangular pair distances.

    Parameters
    ----------
    pairs : array_like
        ``(..., n_pairs)`` distances in row-major upper-triangular order; for
        three dyes that is ``(R_BG, R_BR, R_GR)``.
    n_dyes : int
        Number of dyes.

    Returns
    -------
    numpy.ndarray
        ``(..., n_dyes, n_dyes)`` symmetric matrix with zeros on the diagonal.
    """
    pairs = np.asarray(pairs, dtype=float)
    rows, cols = np.triu_indices(n_dyes, k=1)
    out = np.zeros(pairs.shape[:-1] + (n_dyes, n_dyes), dtype=float)
    out[..., rows, cols] = pairs
    out[..., cols, rows] = pairs
    return out


def channel_weights(distances, setup: ThreeColorSetup, laser: int = 0) -> np.ndarray:
    """Return un-normalised detected weight per channel.

    The quantity :func:`channel_probabilities` normalises away. Its **sum** is
    the molecule's detected brightness: energy transfer moves photons between
    channels whose detection efficiencies differ, so a high-FRET molecule is
    genuinely dimmer or brighter than a low-FRET one, and therefore produces
    smaller or larger bursts. Keeping the denominator is all that is needed to
    know by how much (see :func:`relative_brightness`).

    Parameters
    ----------
    distances : array_like
        ``(..., n_dyes, n_dyes)`` symmetric distances.
    setup : ThreeColorSetup
        Excitation, emission and Förster radii.
    laser : int
        Row of the excitation matrix to use.

    Returns
    -------
    numpy.ndarray
        ``(M, n_channels)`` un-normalised weights.
    """
    transfer = transfer_matrix(np.asarray(distances, dtype=float), setup)
    emitting = np.einsum("d,...dj->...j", setup.excitation[laser], transfer)
    weights = apply_mixing(setup.emission, emitting.reshape(-1, setup.n_dyes).T).T
    return np.atleast_2d(weights)


def relative_brightness(distances, setup: ThreeColorSetup, laser: int = 0) -> np.ndarray:
    """Return detected brightness relative to the same molecule without FRET.

    ``1`` means a molecule as bright as the no-transfer reference; below one it
    contributes smaller bursts, above one larger. Used to give each species its
    own photon-number distribution, since otherwise a dim species is
    over-weighted — it appears at the same amplitude while contributing fewer
    photons per burst.

    Parameters
    ----------
    distances : array_like
        ``(..., n_dyes, n_dyes)`` symmetric distances.
    setup : ThreeColorSetup
        Excitation, emission and Förster radii.
    laser : int
        Row of the excitation matrix to use.

    Returns
    -------
    numpy.ndarray
        ``(M,)`` relative brightness.
    """
    distances = np.asarray(distances, dtype=float)
    weights = channel_weights(distances, setup, laser).sum(axis=-1)
    # Reference: the same optics with every dye pair infinitely far apart, so
    # no transfer happens and each laser's excitation is detected where it fell.
    far = np.full(distances.shape[-2:], 1e12)
    np.fill_diagonal(far, 0.0)
    reference = channel_weights(far, setup, laser).sum(axis=-1)
    reference = np.where(reference > 0.0, reference, 1.0)
    return weights / reference


def channel_probabilities(distances, setup: ThreeColorSetup, laser: int = 0) -> np.ndarray:
    """Per-photon channel probabilities for one excitation period.

    Composes the three matrices: the laser's excitation row, the distance
    dependent transfer matrix, and the emission matrix — the last through
    :func:`chisurf.core.fluorescence.crosstalk.apply_mixing`, so this model
    mixes spectra the same way the rest of ChiSurf does.

    Parameters
    ----------
    distances : array_like
        ``(..., n_dyes, n_dyes)`` symmetric distances (see
        :func:`distances_to_matrix`).
    setup : ThreeColorSetup
        Excitation, emission and Förster radii.
    laser : int
        Row of the excitation matrix to use.

    Returns
    -------
    numpy.ndarray
        ``(M, n_channels)`` probabilities, rows summing to one.
    """
    transfer = transfer_matrix(np.asarray(distances, dtype=float), setup)
    # excitation row (n_dyes,) through T -> emitting-dye weights (..., n_dyes)
    emitting = np.einsum("d,...dj->...j", setup.excitation[laser], transfer)
    # ... then dye -> channel, in the shared (sources, detectors) convention.
    channels = apply_mixing(setup.emission, emitting.reshape(-1, setup.n_dyes).T).T

    totals = channels.sum(axis=-1, keepdims=True)
    return np.atleast_2d(
        np.divide(
            channels,
            np.where(totals > 0.0, totals, 1.0),
            out=np.zeros_like(channels),
            where=totals > 0.0,
        )
    )


def blue_channel_probabilities(r_bg, r_br, r_gr, setup: ThreeColorSetup) -> np.ndarray:
    """Channel probabilities under blue excitation, from the three distances.

    Parameters
    ----------
    r_bg, r_br, r_gr : array_like
        Distances in Angstrom, shape ``(M,)`` or scalar.
    setup : ThreeColorSetup
        Excitation, emission and Förster radii.

    Returns
    -------
    numpy.ndarray
        ``(M, 3)``, channel order (blue, green, red) — the trinomial parameter.
    """
    pairs = np.stack(np.broadcast_arrays(r_bg, r_br, r_gr), axis=-1)
    return channel_probabilities(distances_to_matrix(pairs, setup.n_dyes), setup, laser=0)


def green_channel_probabilities(r_gr, setup: ThreeColorSetup) -> np.ndarray:
    """Channel probabilities under green excitation, restricted to (green, red).

    The blue dye is a spectator, so nothing emits into the blue channel and its
    probability is zero — dropping it and renormalising is therefore exact, not
    an approximation, whenever the emission matrix has no green/red leakage into
    the blue channel. When it does, the renormalisation accounts for it.

    Parameters
    ----------
    r_gr : array_like
        Green–red distance in Angstrom, shape ``(M,)`` or scalar.
    setup : ThreeColorSetup
        Excitation, emission and Förster radii.

    Returns
    -------
    numpy.ndarray
        ``(M, 2)``, channel order (green, red).
    """
    r_gr = np.asarray(r_gr, dtype=float)
    far = np.full_like(r_gr, 1e12, dtype=float)
    pairs = np.stack(np.broadcast_arrays(far, far, r_gr), axis=-1)
    full = channel_probabilities(
        distances_to_matrix(pairs, setup.n_dyes), setup, laser=1
    )[..., 1:]
    totals = full.sum(axis=-1, keepdims=True)
    return np.divide(
        full,
        np.where(totals > 0.0, totals, 1.0),
        out=np.zeros_like(full),
        where=totals > 0.0,
    )
