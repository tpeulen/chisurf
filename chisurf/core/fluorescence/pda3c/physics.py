r"""Three-colour FRET: distances to per-photon detection probabilities.

Turns a triple of inter-dye distances into the channel probabilities the
burst likelihood in :mod:`~chisurf.core.fluorescence.pda3c.likelihood` consumes.

Three dyes — blue (B), green (G), red (R) — give three distances
$R_{BG}$, $R_{BR}$, $R_{GR}$ with their own Förster radii. The essential
difference from two colours is that the transfer pathways **compete and
cascade**, so no channel probability is a function of one distance alone.

Blue excitation
---------------
An excited blue dye has three fates, competing as rates, so with
$x_{BG}=(R_{0,BG}/R_{BG})^6$ and $x_{BR}=(R_{0,BR}/R_{BR})^6$,

.. math::

    E_{BG} = \frac{x_{BG}}{1 + x_{BG} + x_{BR}}, \qquad
    E_{BR} = \frac{x_{BR}}{1 + x_{BG} + x_{BR}}.

Note the shared denominator: opening a B→R pathway *reduces* $E_{BG}$ even
though $R_{BG}$ has not moved. Reading a two-colour formula off the blue-green
pair of a three-colour construct is therefore wrong, and wrong in a direction
that mimics the molecule getting longer.

Energy delivered to green may then continue to red, so the emitting dye is

.. math::

    P(B) = 1 - E_{BG} - E_{BR}, \quad
    P(G) = E_{BG}(1 - E_{GR}), \quad
    P(R) = E_{BR} + E_{BG} E_{GR}.

The red channel is fed by two distinguishable routes — direct B→R transfer and
the two-step B→G→R relay — which is exactly why the three distances are
identifiable from the count statistics at all.

Green excitation
----------------
Under green (PIE/ALEX) excitation the blue dye is a spectator and the system is
two-colour: $P(G) = 1 - E_{GR}$, $P(R) = E_{GR}$, with $E_{GR}$ the ordinary
Förster efficiency. $R_{GR}$ therefore appears in *both* excitation periods,
which is what ties the two halves of a burst together.

Detection
---------
Emission is mapped to counted channels by one matrix,
``detection[c, d]`` = probability that a photon emitted by dye ``d`` is counted
in channel ``c``. It folds quantum yield, filter transmission, detector
efficiency and spectral crosstalk into a single object — the same quantity
``lightpath_simulator``'s ``get_crosstalk_matrices()`` already builds. The
incumbent suite carries the same information as loose scalars (``cr_bg``,
``cr_br``, ``cr_gr`` crosstalk; ``gamma_bg``, ``gamma_br``, ``gamma_gr``
relative brightness); the matrix form is lower triangular, since a redder dye
never leaks into a bluer channel, and it enforces ``gamma_bg = gamma_br /
gamma_gr`` structurally instead of storing two and deriving the third.

Direct excitation
-----------------
A laser pulse excites **exactly one** dye, so the direct-excitation
probabilities *partition* the excitation rather than adding to it: with ``de_bg``
and ``de_br`` the chances that a blue pulse lands on G or R, the blue dye gets
the remainder ``1 - de_bg - de_br``, and every B-excitation pathway is scaled by
it. Treating direct excitation as extra weight on top instead leaves the donor's
share at one; because the channel probabilities are normalised afterwards, that
error is invisible at zero direct excitation and grows with it — a silent bias
in exactly the correction meant to remove one. Verified against the incumbent in
``test/models/test_pda3c_pam_ab.py``.
"""

from __future__ import annotations

import dataclasses

import numpy as np

__all__ = [
    "ThreeColorSetup",
    "blue_channel_probabilities",
    "green_channel_probabilities",
    "transfer_efficiencies",
]


@dataclasses.dataclass
class ThreeColorSetup:
    """Instrument and dye description shared by both excitation periods.

    Attributes
    ----------
    r0_bg, r0_br, r0_gr : float
        Förster radii in Angstrom for the three dye pairs.
    detection : numpy.ndarray
        ``(3, 3)`` matrix; ``detection[c, d]`` is the probability that a photon
        emitted by dye ``d`` (order B, G, R) is counted in channel ``c`` (order
        blue, green, red). Defaults to the identity — perfect, crosstalk-free
        detection with unit quantum yield.
    direct_excitation_blue : tuple of float
        Probability that a blue-laser excitation lands directly on (G, R). The
        blue dye receives the **remainder**, ``1 - de_bg - de_br`` — the laser's
        excitation is partitioned, not topped up. Adding direct excitation as
        extra weight instead would leave the donor's share untouched and shift
        every channel probability.
    direct_excitation_green : float
        Probability that a green-laser excitation lands directly on R; G
        receives ``1 - de_gr``.
    """

    r0_bg: float = 50.0
    r0_br: float = 50.0
    r0_gr: float = 50.0
    detection: np.ndarray = dataclasses.field(default_factory=lambda: np.eye(3))
    direct_excitation_blue: tuple = (0.0, 0.0)
    direct_excitation_green: float = 0.0

    def __post_init__(self):
        """Coerce the detection matrix to a ``(3, 3)`` float array."""
        self.detection = np.asarray(self.detection, dtype=float).reshape(3, 3)


def transfer_efficiencies(r_bg, r_br, r_gr, setup: ThreeColorSetup):
    """Return the three transfer efficiencies for the given distances.

    Parameters
    ----------
    r_bg, r_br, r_gr : array_like
        Inter-dye distances in Angstrom; broadcast against each other.
    setup : ThreeColorSetup
        Förster radii.

    Returns
    -------
    tuple of numpy.ndarray
        ``(E_BG, E_BR, E_GR)``. The first two share a denominator — the B→G and
        B→R pathways compete for the same excited blue dye.
    """
    r_bg = np.asarray(r_bg, dtype=float)
    r_br = np.asarray(r_br, dtype=float)
    r_gr = np.asarray(r_gr, dtype=float)

    with np.errstate(divide="ignore", over="ignore"):
        x_bg = np.where(r_bg > 0.0, (setup.r0_bg / np.maximum(r_bg, 1e-12)) ** 6, np.inf)
        x_br = np.where(r_br > 0.0, (setup.r0_br / np.maximum(r_br, 1e-12)) ** 6, np.inf)
        x_gr = np.where(r_gr > 0.0, (setup.r0_gr / np.maximum(r_gr, 1e-12)) ** 6, np.inf)

    # A clipped-to-zero distance makes x infinite, so the ratios below evaluate
    # to nan before the guards replace them; the guards are the definition, the
    # errstate just stops numpy narrating the intermediate.
    denominator = 1.0 + x_bg + x_br
    with np.errstate(invalid="ignore"):
        e_bg = np.where(np.isfinite(denominator), x_bg / denominator, 0.0)
        e_br = np.where(np.isfinite(denominator), x_br / denominator, 0.0)
        e_gr = np.where(np.isinf(x_gr), 1.0, x_gr / (1.0 + x_gr))
    # A zero distance sends its own pathway to 1 and starves the other.
    e_bg = np.where(np.isinf(x_bg) & ~np.isinf(x_br), 1.0, e_bg)
    e_br = np.where(np.isinf(x_br) & ~np.isinf(x_bg), 1.0, e_br)
    return e_bg, e_br, e_gr


def _normalise(weights):
    """Normalise emission weights to per-photon channel probabilities."""
    total = weights.sum(axis=-1, keepdims=True)
    return np.where(total > 0.0, weights / np.where(total > 0.0, total, 1.0), 0.0)


def blue_channel_probabilities(r_bg, r_br, r_gr, setup: ThreeColorSetup) -> np.ndarray:
    """Per-photon channel probabilities under blue excitation.

    Parameters
    ----------
    r_bg, r_br, r_gr : array_like
        Distances in Angstrom, shape ``(M,)`` or scalar.
    setup : ThreeColorSetup
        Förster radii, detection matrix and direct-excitation terms.

    Returns
    -------
    numpy.ndarray
        Shape ``(M, 3)``, rows summing to one, in channel order (blue, green,
        red) — the trinomial parameter of a blue-excitation burst.
    """
    e_bg, e_br, e_gr = transfer_efficiencies(r_bg, r_br, r_gr, setup)
    dex_g, dex_r = setup.direct_excitation_blue
    # The laser excites exactly one dye: B with the remaining probability.
    p_excite_b = 1.0 - dex_g - dex_r

    # Emission weight per dye: which dye ends up carrying the excitation.
    emission = np.stack(
        [
            p_excite_b * (1.0 - e_bg - e_br),
            p_excite_b * e_bg * (1.0 - e_gr) + dex_g * (1.0 - e_gr),
            p_excite_b * (e_br + e_bg * e_gr) + dex_g * e_gr + dex_r,
        ],
        axis=-1,
    )
    emission = np.clip(emission, 0.0, None)
    # Always 2-D, so a scalar distance and an array of them index alike.
    return np.atleast_2d(_normalise(emission @ setup.detection.T))


def green_channel_probabilities(r_gr, setup: ThreeColorSetup) -> np.ndarray:
    """Per-photon channel probabilities under green excitation.

    The blue dye is a spectator here, so this is the ordinary two-colour
    partition — but over the *same* ``r_gr`` the blue period sees, which is what
    lets the two excitation periods constrain each other.

    Parameters
    ----------
    r_gr : array_like
        Green–red distance in Angstrom, shape ``(M,)`` or scalar.
    setup : ThreeColorSetup
        Förster radii, detection matrix and direct-excitation term.

    Returns
    -------
    numpy.ndarray
        Shape ``(M, 2)``, rows summing to one, in channel order (green, red).
    """
    r_gr = np.asarray(r_gr, dtype=float)
    _, _, e_gr = transfer_efficiencies(r_gr, r_gr, r_gr, setup)
    dex_r = setup.direct_excitation_green
    p_excite_g = 1.0 - dex_r

    emission = np.stack(
        [
            np.broadcast_to(p_excite_g * (1.0 - e_gr), e_gr.shape),
            p_excite_g * e_gr + dex_r,
        ],
        axis=-1,
    )
    emission = np.clip(emission, 0.0, None)

    # Only the green and red detection channels are open under green excitation,
    # so drop the blue row and the blue emitter column of the detection matrix.
    detection_gr = setup.detection[1:, 1:]
    return np.atleast_2d(_normalise(emission @ detection_gr.T))
