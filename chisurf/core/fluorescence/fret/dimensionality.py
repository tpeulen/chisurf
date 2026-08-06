"""FRET to acceptors *distributed* rather than placed, in 1, 2 or 3 dimensions.

The familiar single-distance expressions assume one donor and one acceptor at a
fixed separation. They do not apply when acceptors are spread through a volume,
across a membrane, or along a helix: there the donor is surrounded by many
acceptors at many distances, and the observable is an acceptor **density**, not
a distance.

For a random distribution with no diffusion and no excluded volume the donor
decay is known in closed form, and its shape depends on the dimensionality:

.. math::

    I_{DA}(t) = I_D^0 \\,\\exp\\!\\left[-\\frac{t}{\\tau_{D(0)}}
                - 2\\,\\eta_d \\left(\\frac{t}{\\tau_{D(0)}}\\right)^{d/6}\\right]

with :math:`d = 1, 2, 3` and a reduced density
:math:`\\eta_d = \\tfrac{1}{2}\\Gamma(1 - d/6)\\,C/C_0`. The stretch exponent
:math:`d/6` — a sixth, a third, a half — is the signature: the three decays are
distinguishable in practice, and a decay generated in one dimensionality cannot
be fitted by the law for another.

:math:`C_0` is the acceptor density that places, on average, one acceptor within
:math:`R_0` of the donor, so :math:`C/C_0` is directly "how many acceptors are
within a Förster radius". At :math:`C = C_0` the transfer efficiencies are
72.4 %, 67.2 % and 64.2 % in three, two and one dimensions -- the standard text
rounds the last two to 66 % and 63 %, which does not reproduce; see
``test/fluorescence/test_fret_dimensionality.py``.

The orientation factor does not appear explicitly: :math:`\\kappa^2 = 2/3` is
assumed in :math:`R_0`, which requires rotational averaging within the donor
lifetime. A rotationally frozen three-dimensional solution has
:math:`\\langle\\kappa^2\\rangle = 0.476` instead, and needs 1.18-fold more
acceptor for the same transfer (see :mod:`chisurf.core.fluorescence.anisotropy.kappa2`).

The theory page is ``docs/concepts/distributed_acceptors.md``.
"""

from __future__ import annotations

import math

import numpy as np

__all__ = [
    "characteristic_density",
    "reduced_density",
    "donor_decay",
    "transfer_efficiency",
    "quenching_factor",
    "quench_decay",
]

#: Allowed dimensionalities, and the gamma-function argument each uses.
_DIMENSIONS = (1, 2, 3)


def _check_dimension(dimension: int) -> int:
    """Validate *dimension* and return it as an int.

    A non-integral value is rejected rather than truncated: ``int(2.5)`` is 2,
    which would silently answer a question nobody asked.
    """
    try:
        d = int(dimension)
        integral = d == dimension
    except (TypeError, ValueError):
        integral = False
        d = None
    if not integral or d not in _DIMENSIONS:
        raise ValueError(f"dimension must be 1, 2 or 3, got {dimension!r}")
    return d


def characteristic_density(forster_radius: float, dimension: int) -> float:
    """Acceptor density :math:`C_0` that puts one acceptor within :math:`R_0`.

    Parameters
    ----------
    forster_radius : float
        Förster radius :math:`R_0`, in whatever length unit the result should
        be reciprocal to (Å in, Å⁻³/Å⁻²/Å⁻¹ out).
    dimension : int
        1 (along a line), 2 (in a plane) or 3 (through a volume).

    Returns
    -------
    float
        :math:`C_0`, in inverse length to the power *dimension*:

        * 3-D: :math:`C_0 = (\\tfrac{4}{3}\\pi R_0^3)^{-1}`
        * 2-D: :math:`C_0 = (\\pi R_0^2)^{-1}`
        * 1-D: :math:`C_0 = (2 R_0)^{-1}`

    Raises
    ------
    ValueError
        If *forster_radius* is not positive or *dimension* is not 1, 2 or 3.

    Examples
    --------
    >>> from chisurf.core.fluorescence.fret.dimensionality import characteristic_density
    >>> round(1.0 / characteristic_density(50.0, 3), 1)   # the sphere volume, A^3
    523598.8
    >>> round(1.0 / characteristic_density(50.0, 2), 1)   # the circle area, A^2
    7854.0
    >>> round(1.0 / characteristic_density(50.0, 1), 1)   # the segment, A
    100.0
    """
    d = _check_dimension(dimension)
    r0 = float(forster_radius)
    if not r0 > 0:
        raise ValueError(f"forster_radius must be positive, got {forster_radius!r}")
    if d == 3:
        return 1.0 / (4.0 / 3.0 * math.pi * r0**3)
    if d == 2:
        return 1.0 / (math.pi * r0**2)
    return 1.0 / (2.0 * r0)


def reduced_density(c_over_c0: float, dimension: int) -> float:
    """Reduced acceptor density :math:`\\eta_d` entering the decay law.

    :math:`\\eta_d = \\tfrac{1}{2}\\,\\Gamma(1 - d/6)\\,C/C_0`, which is
    :math:`\\gamma`, :math:`\\beta` and :math:`\\delta` in the three- two- and
    one-dimensional literature respectively.

    Parameters
    ----------
    c_over_c0 : float
        Acceptor density in units of :func:`characteristic_density` — the mean
        number of acceptors within :math:`R_0` of a donor.
    dimension : int
        1, 2 or 3.

    Returns
    -------
    float
        The reduced density.

    Raises
    ------
    ValueError
        If *c_over_c0* is negative or *dimension* is not 1, 2 or 3.

    Examples
    --------
    At ``c_over_c0 = 1`` these are the half-gamma constants quoted in the
    literature — 0.886 (= √π/2), 0.677 and 0.564:

    >>> from chisurf.core.fluorescence.fret.dimensionality import reduced_density
    >>> [round(reduced_density(1.0, d), 3) for d in (3, 2, 1)]
    [0.886, 0.677, 0.564]
    """
    d = _check_dimension(dimension)
    c = float(c_over_c0)
    if c < 0:
        raise ValueError(f"c_over_c0 must be non-negative, got {c_over_c0!r}")
    return 0.5 * math.gamma(1.0 - d / 6.0) * c


def donor_decay(
    time: np.ndarray,
    tau_d0: float,
    c_over_c0: float,
    dimension: int,
) -> np.ndarray:
    """Donor intensity decay with acceptors distributed in *dimension* dimensions.

    Parameters
    ----------
    time : numpy.ndarray
        Times at which to evaluate the decay, in the same unit as *tau_d0*.
        Negative times raise.
    tau_d0 : float
        Donor lifetime in the absence of acceptor, :math:`\\tau_{D(0)}`.
    c_over_c0 : float
        Acceptor density in units of :func:`characteristic_density`. Zero gives
        the unquenched single-exponential donor decay.
    dimension : int
        1, 2 or 3.

    Returns
    -------
    numpy.ndarray
        The decay, normalized to 1 at ``t = 0``.

    Raises
    ------
    ValueError
        If *tau_d0* is not positive, any time is negative, or the inputs are
        otherwise out of range.

    Notes
    -----
    The stretched term is :math:`(t/\\tau_{D(0)})^{d/6}`, so its derivative at
    :math:`t = 0` is infinite for every *dimension*. The decay is therefore
    steep at early times — steeper the lower the dimensionality — which is the
    feature that makes the three cases separable in a reconvolution fit and the
    reason a distributed-acceptor decay is badly described by a sum of
    exponentials.

    Examples
    --------
    >>> import numpy as np
    >>> from chisurf.core.fluorescence.fret.dimensionality import donor_decay
    >>> t = np.array([0.0, 1.0, 4.0])
    >>> np.round(donor_decay(t, tau_d0=4.0, c_over_c0=0.0, dimension=3), 4)
    array([1.    , 0.7788, 0.3679])
    """
    d = _check_dimension(dimension)
    t = np.asarray(time, dtype=float)
    tau = float(tau_d0)
    if not tau > 0:
        raise ValueError(f"tau_d0 must be positive, got {tau_d0!r}")
    if np.any(t < 0):
        raise ValueError("time must be non-negative")
    eta = reduced_density(c_over_c0, d)
    x = t / tau
    return np.exp(-x - 2.0 * eta * np.power(x, d / 6.0))


def transfer_efficiency(
    c_over_c0: float,
    dimension: int,
    *,
    n_points: int = 200_001,
    t_max_tau: float = 200.0,
) -> float:
    """Transfer efficiency for a distributed acceptor population.

    There is no closed form in one and two dimensions (the series solutions are
    infinite), so the efficiency is obtained by integrating the decay:
    :math:`E = 1 - \\int I_{DA}\\,\\mathrm{d}t \\,/\\, \\int I_{D}\\,\\mathrm{d}t`.

    Parameters
    ----------
    c_over_c0 : float
        Acceptor density in units of :func:`characteristic_density`.
    dimension : int
        1, 2 or 3.
    n_points : int, optional
        Samples used for the quadrature. The integrand has an infinite
        derivative at the origin, so this is deliberately generous.
    t_max_tau : float, optional
        Upper limit of the integration, in units of :math:`\\tau_{D(0)}`.

    Returns
    -------
    float
        The transfer efficiency, between 0 and 1.

    Examples
    --------
    At :math:`C = C_0` transfer is efficient in every dimensionality, and more
    so the more directions the acceptors can approach from:

    >>> from chisurf.core.fluorescence.fret.dimensionality import transfer_efficiency
    >>> [round(transfer_efficiency(1.0, d), 3) for d in (3, 2, 1)]
    [0.724, 0.672, 0.641]
    """
    d = _check_dimension(dimension)
    if n_points < 3:
        raise ValueError("n_points must be at least 3")
    t = np.linspace(0.0, float(t_max_tau), int(n_points))
    quenched = donor_decay(t, 1.0, c_over_c0, d)
    reference = np.exp(-t)
    return float(1.0 - np.trapz(quenched, t) / np.trapz(reference, t))


def quenching_factor(
    time: np.ndarray,
    tau_d0: float,
    c_over_c0: float,
    dimension: int,
) -> np.ndarray:
    """The distributed-acceptor quenching factor, separable from the donor decay.

    The transfer rate to an acceptor at distance *r* is
    :math:`k_T = \\tau_{D(0)}^{-1}(R_0/r)^6`, and since
    :math:`R_0^6 \\propto Q_D = \\tau_{D(0)}/\\tau_n` this is
    :math:`\\propto \\tau_n^{-1} r^{-6}` — it depends on the donor's
    **radiative** rate, not on its total lifetime. So a donor whose decay is
    multi-exponential because different molecules are differently *quenched*
    presents one and the same transfer-rate field to the acceptors, and the
    quenching factor multiplies the whole donor decay rather than acting on each
    species separately:

    .. math::

        I_{DA}(t) = I_{D}(t)\\,
                    \\exp\\!\\left[-2\\eta_d
                    \\left(\\frac{t}{\\tau_{D(0)}}\\right)^{d/6}\\right]

    :math:`\\tau_{D(0)}` here is the reference lifetime that :math:`R_0` — and
    therefore :math:`C_0` — was computed with, not a property of any one species.

    Parameters
    ----------
    time : numpy.ndarray
        Time axis, non-negative.
    tau_d0 : float
        The reference donor lifetime :math:`R_0` was defined against.
    c_over_c0 : float
        Acceptor density in units of :func:`characteristic_density`.
    dimension : int
        1, 2 or 3.

    Returns
    -------
    numpy.ndarray
        The factor, 1 at ``t = 0`` and falling monotonically.

    Examples
    --------
    Multiplying a single-exponential donor by it reproduces
    :func:`donor_decay`:

    >>> import numpy as np
    >>> from chisurf.core.fluorescence.fret.dimensionality import (
    ...     donor_decay, quenching_factor)
    >>> t = np.linspace(0.0, 8.0, 5)
    >>> both = np.exp(-t / 4.0) * quenching_factor(t, 4.0, 0.8, 2)
    >>> bool(np.allclose(both, donor_decay(t, 4.0, 0.8, 2)))
    True
    """
    d = _check_dimension(dimension)
    t = np.asarray(time, dtype=float)
    tau = float(tau_d0)
    if not tau > 0:
        raise ValueError(f"tau_d0 must be positive, got {tau_d0!r}")
    if np.any(t < 0):
        raise ValueError("time must be non-negative")
    eta = reduced_density(c_over_c0, d)
    return np.exp(-2.0 * eta * np.power(t / tau, d / 6.0))


def quench_decay(
    donor_decay_curve: np.ndarray,
    time: np.ndarray,
    tau_d0: float,
    c_over_c0: float,
    dimension: int,
) -> np.ndarray:
    """Apply distributed-acceptor quenching to a donor-only **decay**.

    The donor decay is whatever it is — measured, simulated, single- or
    multi-exponential — and this multiplies it by the common
    :func:`quenching_factor`. Nothing here needs to know how the donor decay was
    parameterized, which is the point: the quenching is a property of the
    acceptor field, not of the donor's decay law.

    Apply it to the **unconvolved** decay: the quenching is photophysics and
    happens before the instrument sees anything.

    Parameters
    ----------
    donor_decay_curve : numpy.ndarray
        Donor-only decay, sampled on *time*.
    time : numpy.ndarray
        Time axis, non-negative, same length as *donor_decay_curve*.
    tau_d0 : float
        Reference donor lifetime that :math:`R_0` — and hence :math:`C_0` — was
        computed with.
    c_over_c0 : float
        Acceptor density in units of :func:`characteristic_density`.
    dimension : int
        1, 2 or 3.

    Returns
    -------
    numpy.ndarray
        The quenched decay, on the same scale as the input.

    Raises
    ------
    ValueError
        If the two arrays differ in length, or the other inputs are out of range.

    Examples
    --------
    Quenching a single-exponential donor reproduces :func:`donor_decay`:

    >>> import numpy as np
    >>> from chisurf.core.fluorescence.fret.dimensionality import (
    ...     donor_decay, quench_decay)
    >>> t = np.linspace(0.0, 8.0, 5)
    >>> got = quench_decay(np.exp(-t / 4.0), t, 4.0, 0.8, 2)
    >>> bool(np.allclose(got, donor_decay(t, 4.0, 0.8, 2)))
    True
    """
    d = _check_dimension(dimension)
    y = np.asarray(donor_decay_curve, dtype=float)
    t = np.asarray(time, dtype=float)
    if y.shape != t.shape:
        raise ValueError(
            f"donor_decay_curve and time must have the same shape, "
            f"got {y.shape} and {t.shape}"
        )
    return y * quenching_factor(t, tau_d0, c_over_c0, d)
