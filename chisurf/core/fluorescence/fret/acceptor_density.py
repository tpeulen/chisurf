"""FRET to an acceptor *density* rather than to a placed acceptor, in 1, 2 or 3 dimensions.

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
``test/fluorescence/test_fret_acceptor_density.py``.

The orientation factor does not appear explicitly: :math:`\\kappa^2 = 2/3` is
assumed in :math:`R_0`, which requires rotational averaging within the donor
lifetime. A rotationally frozen three-dimensional solution has
:math:`\\langle\\kappa^2\\rangle = 0.476` instead, and needs 1.18-fold more
acceptor for the same transfer (see :mod:`chisurf.core.fluorescence.anisotropy.kappa2`).

The theory page is ``docs/concepts/acceptor_density.md``.

The arithmetic lives in IMP.bff (``FRETAcceptorDensity.h``), where the
``tcspc_fret_acceptor_density`` model evaluates it; this module forwards to it
and keeps only the argument checks a Python caller expects.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "characteristic_density",
    "reduced_density",
    "donor_decay",
    "transfer_efficiency",
    "quenching_factor",
    "quench_decay",
    "absolute_density",
]

#: Allowed dimensionalities.
_DIMENSIONS = (1, 2, 3)


def _bff():
    import IMP.bff
    return IMP.bff


def _check_dimension(dimension: int) -> int:
    """1, 2 or 3; a non-integral value is rejected rather than truncated.

    ``int(2.5)`` is 2, which would silently answer a question nobody asked.
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
    """C0, the acceptor density with one acceptor within R0 on average (length^-d).

    3-D: 1/(4/3 pi R0^3); 2-D: 1/(pi R0^2); 1-D: 1/(2 R0).

    >>> round(1.0 / characteristic_density(50.0, 3), 1)   # the sphere volume, A^3
    523598.8
    >>> round(1.0 / characteristic_density(50.0, 2), 1)   # the circle area, A^2
    7854.0
    >>> round(1.0 / characteristic_density(50.0, 1), 1)   # the segment, A
    100.0
    """
    d = _check_dimension(dimension)
    if not float(forster_radius) > 0:
        raise ValueError(f"forster_radius must be positive, got {forster_radius!r}")
    return float(_bff().acceptor_characteristic_density(float(forster_radius), d))


def reduced_density(c_over_c0: float, dimension: int) -> float:
    """eta_d = Gamma(1 - d/6) / 2 * C/C0.

    >>> [round(reduced_density(1.0, d), 3) for d in (3, 2, 1)]
    [0.886, 0.677, 0.564]
    """
    d = _check_dimension(dimension)
    if float(c_over_c0) < 0:
        raise ValueError(f"c_over_c0 must be non-negative, got {c_over_c0!r}")
    return float(_bff().acceptor_reduced_density(float(c_over_c0), d))


def quenching_factor(time: np.ndarray, tau_d0: float, c_over_c0: float, dimension: int) -> np.ndarray:
    """exp[-2 eta_d (t/tau_D(0))^(d/6)] on *time*."""
    d = _check_dimension(dimension)
    t = np.asarray(time, dtype=float)
    if not float(tau_d0) > 0:
        raise ValueError(f"tau_d0 must be positive, got {tau_d0!r}")
    if np.any(t < 0):
        raise ValueError("time must be non-negative")
    if float(c_over_c0) < 0:
        raise ValueError(f"c_over_c0 must be non-negative, got {c_over_c0!r}")
    flat = np.asarray(_bff().acceptor_quenching_factor(
        np.ascontiguousarray(t.ravel()), float(tau_d0), float(c_over_c0), d), dtype=float)
    return flat.reshape(t.shape)


def donor_decay(time: np.ndarray, tau_d0: float, c_over_c0: float, dimension: int) -> np.ndarray:
    """The quenched decay of a single-exponential donor, normalized to 1 at t = 0.

    >>> t = np.array([0.0, 1.0, 4.0])
    >>> np.round(donor_decay(t, tau_d0=4.0, c_over_c0=0.0, dimension=3), 4)
    array([1.    , 0.7788, 0.3679])
    """
    t = np.asarray(time, dtype=float)
    factor = quenching_factor(t, tau_d0, c_over_c0, dimension)
    return np.exp(-t / float(tau_d0)) * factor


def transfer_efficiency(c_over_c0: float, dimension: int, *, n_points: int = 200_001,
                        t_max_tau: float = 200.0) -> float:
    """E = 1 - int I_DA / int I_D, by the trapezoid rule (no closed form in 1-D and 2-D)."""
    d = _check_dimension(dimension)
    if n_points < 3:
        raise ValueError("n_points must be at least 3")
    if float(c_over_c0) < 0:
        raise ValueError(f"c_over_c0 must be non-negative, got {c_over_c0!r}")
    return float(_bff().acceptor_transfer_efficiency(float(c_over_c0), d, int(n_points), float(t_max_tau)))


def quench_decay(donor_decay_curve: np.ndarray, time: np.ndarray, tau_d0: float, c_over_c0: float,
                 dimension: int) -> np.ndarray:
    """Multiply an arbitrary donor-only decay by the acceptor-density quenching factor."""
    y = np.asarray(donor_decay_curve, dtype=float)
    t = np.asarray(time, dtype=float)
    if y.shape != t.shape:
        raise ValueError(
            f"donor_decay_curve and time must have the same shape, got {y.shape} and {t.shape}")
    return y * quenching_factor(t, tau_d0, c_over_c0, dimension)


def absolute_density(c_over_c0: float, forster_radius: float, dimension: int) -> float:
    """The absolute acceptor density C/C0 * C0, in length^-dimension."""
    return float(c_over_c0) * characteristic_density(forster_radius, dimension)
