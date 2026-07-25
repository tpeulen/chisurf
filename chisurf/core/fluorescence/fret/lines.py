"""Analytic FRET lines in the E–lifetime plane (static, dynamic, no-linker).

A *FRET line* is the locus that a population of molecules must occupy in the
two-dimensional plot of FRET efficiency ``E`` against the **fluorescence-averaged
donor lifetime in presence of the acceptor**, ``tau_f`` = ⟨τ⟩_f (the lifetime an
experimenter obtains from a mono-exponential fit of the donor decay of a burst).

Two lines matter:

* the **static** line — every molecule of the population has the same mean
  donor–acceptor distance, blurred only by the (fast) linker distribution of
  width ``sigma``. A static, structurally homogeneous species sits *on* it.
* the **dynamic** line — the molecule interconverts between two limiting
  distances during the burst. Populations then bow *to the right* of the static
  line, which is the standard diagnostic for sub-burst dynamics.

Both are built from one relation, ``tau(R) = tau_D0 / (1 + (R0/R)^6)``, averaged
over the distance distribution and over a (possibly multi-exponential) donor
decay:

    tau_x = Σ a_i tau_i / Σ a_i               (species-averaged)
    tau_f = Σ a_i tau_i² / Σ a_i tau_i        (fluorescence-averaged)
    E     = 1 − tau_x / tau_D0_x

`E` follows the **species-averaged** lifetime because the transfer efficiency is
an amplitude-weighted quantity, while the measured x-axis is the
**fluorescence-averaged** lifetime — the difference between the two is exactly
what bends the static line away from the ``E = 1 − tau/tau_D0`` diagonal.

This module is deliberately model-free, Qt-free and dependency-light: it needs
only the donor lifetimes, the Förster radius and the linker width, so it can be
used inside the accurate-FRET calibration
(:mod:`chisurf.core.fluorescence.fret.accurate`), in headless scripts and for
plot overlays. The *model-driven* generator, which sweeps any registered ChiSurf
lifetime/FRET model (worm-like chain, mixtures, …) and needs a fit object, is
:mod:`chisurf.core.fluorescence.fret.fret_line`; both agree to numerical
precision for the Gaussian case (``test/models/test_fret_lines_analytic.py``).

References
----------
Sisamakis et al., Methods Enzymol. 475, 455 (2010) — E–τ diagrams and FRET lines.
Kalinin, Valeri, Antonik, Felekyan, Seidel, J. Phys. Chem. B 114, 7983 (2010).
Barth et al., J. Chem. Phys. 156, 141501 (2022) — dynamic FRET lines.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

__all__ = [
    "FretLine",
    "donor_lifetime_spectrum",
    "gaussian_distance_distribution",
    "lifetime_averages",
    "static_fret_line",
    "dynamic_fret_line",
    "no_linker_line",
]


# ---------------------------------------------------------------------------
# building blocks
# ---------------------------------------------------------------------------


def donor_lifetime_spectrum(donor) -> tuple[np.ndarray, np.ndarray]:
    """Normalize a donor-only decay specification into amplitudes and lifetimes.

    Parameters
    ----------
    donor : float or array_like
        Either a single donor-only lifetime (ns), a sequence of lifetimes (equal
        amplitudes assumed), or a sequence of ``(amplitude, lifetime)`` pairs.

    Returns
    -------
    tuple of numpy.ndarray
        ``(amplitudes, lifetimes)`` with amplitudes normalized to sum 1.
    """
    arr = np.atleast_1d(np.asarray(donor, dtype=float))
    if arr.ndim == 1:
        x = np.ones_like(arr)
        tau = arr
    elif arr.ndim == 2 and arr.shape[1] == 2:
        x = arr[:, 0].astype(float)
        tau = arr[:, 1].astype(float)
    else:
        raise ValueError("donor must be a lifetime, a list of lifetimes or (x, tau) pairs")
    if np.any(tau <= 0):
        raise ValueError("donor lifetimes must be positive")
    total = float(np.sum(x))
    if total <= 0:
        raise ValueError("donor amplitudes must sum to a positive number")
    return x / total, tau


def gaussian_distance_distribution(mean, sigma: float, *, n_points: int = 81,
                                   n_sigma: float = 3.5, r_min: float = 1.0):
    """Discretized Gaussian donor–acceptor distance distribution.

    Represents the fast linker/dye distribution around a mean distance. A width
    of zero collapses to a single distance.

    Parameters
    ----------
    mean : float or array_like
        Mean donor–acceptor distance(s) (Å). An array yields one distribution
        per entry (leading axis).
    sigma : float
        Standard deviation of the distribution (Å); ``0`` gives a delta.
    n_points : int, optional
        Number of distance samples per distribution.
    n_sigma : float, optional
        Half-width of the sampled range in units of ``sigma``.
    r_min : float, optional
        Distances are clipped at this lower bound (Å) to keep ``(R0/R)^6``
        finite.

    Returns
    -------
    tuple of numpy.ndarray
        ``(weights, distances)``, both shaped ``(..., n_points)`` and with the
        weights normalized along the last axis.
    """
    mean = np.atleast_1d(np.asarray(mean, dtype=float))
    if sigma <= 0:
        return np.ones(mean.shape + (1,)), mean[..., None]
    offsets = np.linspace(-n_sigma * sigma, n_sigma * sigma, int(n_points))
    r = np.clip(mean[..., None] + offsets, r_min, None)
    w = np.exp(-0.5 * ((r - mean[..., None]) / sigma) ** 2)
    w = w / np.sum(w, axis=-1, keepdims=True)
    return w, r


def lifetime_averages(amplitudes, lifetimes) -> tuple[np.ndarray, np.ndarray]:
    """Species- and fluorescence-averaged lifetime of a lifetime spectrum.

    Parameters
    ----------
    amplitudes, lifetimes : array_like
        Amplitudes ``a_i`` and lifetimes ``tau_i``; averaged over the last axis
        so a stack of spectra can be reduced in one call.

    Returns
    -------
    tuple of numpy.ndarray
        ``(tau_x, tau_f)`` — ``Σ a tau / Σ a`` and ``Σ a tau² / Σ a tau``.
    """
    a = np.asarray(amplitudes, dtype=float)
    t = np.asarray(lifetimes, dtype=float)
    s0 = np.sum(a, axis=-1)
    s1 = np.sum(a * t, axis=-1)
    s2 = np.sum(a * t * t, axis=-1)
    with np.errstate(divide="ignore", invalid="ignore"):
        tau_x = np.where(s0 != 0, s1 / s0, 0.0)
        tau_f = np.where(s1 != 0, s2 / s1, 0.0)
    return tau_x, tau_f


def _state_spectrum(distance_weights, distances, donor_x, donor_tau, r0: float):
    """Lifetime spectrum of one FRET state (distance distribution × donor decay).

    Returns amplitudes and lifetimes flattened over (donor component, distance)
    along the last axis.
    """
    # tau[..., j, i] = donor_tau[i] / (1 + (r0/R_j)^6)
    quench = 1.0 / (1.0 + (r0 / distances) ** 6)
    tau = quench[..., None] * donor_tau[None, :]
    amp = distance_weights[..., None] * donor_x[None, :]
    shape = tau.shape[:-2] + (tau.shape[-2] * tau.shape[-1],)
    return amp.reshape(shape), tau.reshape(shape)


# ---------------------------------------------------------------------------
# the line object
# ---------------------------------------------------------------------------


@dataclass
class FretLine:
    """A FRET line: matching ``E``, ``tau_f`` and ``tau_x`` arrays plus metadata.

    Attributes
    ----------
    tau_f, tau_x, efficiency : numpy.ndarray
        Fluorescence-averaged lifetime (the plotted x-axis), species-averaged
        lifetime and FRET efficiency along the line.
    tau_d0 : float
        Species-averaged donor-only lifetime the efficiency refers to.
    parameter : numpy.ndarray
        The swept quantity (mean distance for a static line, the fraction of
        state 1 for a dynamic line).
    name, kind : str
        Human-readable label and one of ``"static"``/``"dynamic"``/``"no-linker"``.
    meta : dict
        The generating parameters (``r0``, ``sigma``, …), for provenance.
    """

    tau_f: np.ndarray
    tau_x: np.ndarray
    efficiency: np.ndarray
    tau_d0: float
    parameter: np.ndarray | None = None
    name: str = "FRET line"
    kind: str = "static"
    meta: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Sort the line by ``tau_f`` so the interpolators are well-defined."""
        order = np.argsort(np.asarray(self.tau_f, dtype=float))
        self.tau_f = np.asarray(self.tau_f, dtype=float)[order]
        self.tau_x = np.asarray(self.tau_x, dtype=float)[order]
        self.efficiency = np.asarray(self.efficiency, dtype=float)[order]
        if self.parameter is not None:
            self.parameter = np.asarray(self.parameter, dtype=float)[order]

    # ── interpolation ──
    def efficiency_at(self, tau_f):
        """FRET efficiency the line predicts for a measured donor lifetime.

        Parameters
        ----------
        tau_f : array_like
            Fluorescence-averaged donor lifetime(s) in the presence of the
            acceptor (ns). Values outside the sampled range are clamped to the
            line's endpoints.

        Returns
        -------
        numpy.ndarray
            Predicted efficiency, ``NaN`` where ``tau_f`` is not finite.
        """
        t = np.asarray(tau_f, dtype=float)
        out = np.interp(t, self.tau_f, self.efficiency)
        return np.where(np.isfinite(t), out, np.nan)

    def lifetime_at(self, efficiency):
        """Donor lifetime the line predicts for a given FRET efficiency.

        Parameters
        ----------
        efficiency : array_like
            FRET efficiency (0…1).

        Returns
        -------
        numpy.ndarray
            Fluorescence-averaged donor lifetime (ns).
        """
        e = np.asarray(efficiency, dtype=float)
        # efficiency decreases with tau_f -> flip for np.interp's ascending x.
        return np.interp(e, self.efficiency[::-1], self.tau_f[::-1])

    def deviation(self, efficiency, tau_f):
        """Signed vertical distance of measured points from the line.

        Positive values sit **above** the line — a higher efficiency than a
        static population of that donor lifetime, equivalently a longer lifetime
        than a static population of that efficiency. Sub-burst dynamics shift
        populations that way (towards the dynamic line); a systematically
        *negative* deviation of a known-static sample instead points at a too
        large ``gamma`` (the intensity efficiency falls with ``gamma``).

        Parameters
        ----------
        efficiency, tau_f : array_like
            Measured efficiency and fluorescence-averaged donor lifetime.

        Returns
        -------
        numpy.ndarray
            ``efficiency - line.efficiency_at(tau_f)``.
        """
        return np.asarray(efficiency, dtype=float) - self.efficiency_at(tau_f)

    # ── export ──
    def polynomial(self, degree: int = 4) -> np.ndarray:
        """Polynomial coefficients of the ``tau_x(tau_f)`` conversion function.

        The same convention as
        :attr:`~chisurf.core.fluorescence.fret.fret_line.FRETLineGenerator.polynom_coefficients`
        (highest power first), suitable for exporting a line to external plotting
        software.

        Parameters
        ----------
        degree : int, optional
            Degree of the fitted polynomial.

        Returns
        -------
        numpy.ndarray
            Coefficients as returned by :func:`numpy.polyfit`.
        """
        deg = int(min(degree, max(1, self.tau_f.size - 1)))
        return np.polyfit(self.tau_f, self.tau_x, deg)

    def as_overlay(self, style: dict | None = None) -> dict:
        """Return the line in the shared plot-overlay contract.

        The same ``{"name", "kind", "x", "y", "style", "axes"}`` dictionary that
        ``fret_line_overlays`` and ``phasor.overlays`` emit, so ndXplorer and the
        ChiSurf plots draw analytic and model-based lines through one interface.

        Parameters
        ----------
        style : dict, optional
            Style hints (``color``, ``width``, ``dash``).

        Returns
        -------
        dict
            The overlay description.
        """
        return {
            "name": self.name,
            "kind": "curve",
            "x": self.tau_f,
            "y": self.efficiency,
            "style": style or {"color": "#50c0ff", "width": 2},
            "axes": {"x": "tau_f", "y": "e_fret", "label": "E vs fluorescence-averaged lifetime"},
        }


# ---------------------------------------------------------------------------
# line generators
# ---------------------------------------------------------------------------


def static_fret_line(donor=4.0, *, r0: float = 52.0, sigma: float = 6.0,
                     distance_range: tuple[float, float] = (10.0, 150.0),
                     n_points: int = 200, n_distance_samples: int = 81,
                     name: str = "static FRET line") -> FretLine:
    """Build the static FRET line for a Gaussian-broadened donor–acceptor distance.

    Sweeps the *mean* distance and, at each point, averages the donor decay over
    the linker distribution. This is the line a structurally homogeneous
    (static) population must lie on; deviations to longer lifetimes at the same
    efficiency indicate dynamics or a wrong ``gamma`` — which is exactly what
    :func:`chisurf.core.fluorescence.fret.accurate.gamma_from_lifetime` exploits.

    Parameters
    ----------
    donor : float or array_like, optional
        Donor-only lifetime (ns), list of lifetimes, or ``(amplitude, lifetime)``
        pairs for a multi-exponential donor.
    r0 : float, optional
        Förster radius (Å).
    sigma : float, optional
        Width of the linker distance distribution (Å). ``0`` gives the
        no-linker limit (see :func:`no_linker_line`).
    distance_range : tuple of float, optional
        ``(min, max)`` mean distance swept (Å).
    n_points : int, optional
        Number of points along the line.
    n_distance_samples : int, optional
        Samples used to discretize the Gaussian at each mean distance.
    name : str, optional
        Label carried by the returned line.

    Returns
    -------
    FretLine
        The line, sorted by ``tau_f``.

    Examples
    --------
    >>> line = static_fret_line(4.0, r0=52.0, sigma=6.0)
    >>> bool(0.0 < line.efficiency_at(2.0) < 1.0)
    True
    """
    donor_x, donor_tau = donor_lifetime_spectrum(donor)
    tau_d0 = float(np.sum(donor_x * donor_tau))
    r_mean = np.linspace(float(distance_range[0]), float(distance_range[1]), int(n_points))
    w, r = gaussian_distance_distribution(r_mean, float(sigma), n_points=n_distance_samples)
    amp, tau = _state_spectrum(w, r, donor_x, donor_tau, float(r0))
    tau_x, tau_f = lifetime_averages(amp, tau)
    return FretLine(
        tau_f=tau_f, tau_x=tau_x, efficiency=1.0 - tau_x / tau_d0, tau_d0=tau_d0,
        parameter=r_mean, name=name, kind="static",
        meta={"r0": float(r0), "sigma": float(sigma), "donor": donor},
    )


def no_linker_line(donor=4.0, *, n_points: int = 200, name: str = "no-linker line") -> FretLine:
    """Build the ``E = 1 − tau/tau_D0`` limit line for a single, sharp distance.

    With a mono-exponential donor and no distance distribution the species- and
    fluorescence-averaged lifetimes coincide and the static line degenerates into
    a straight diagonal. Useful as a reference against which the linker-induced
    curvature of :func:`static_fret_line` is judged; with a multi-exponential
    donor the line is curved even without a linker distribution.

    Parameters
    ----------
    donor : float or array_like, optional
        Donor-only lifetime specification (see
        :func:`donor_lifetime_spectrum`).
    n_points : int, optional
        Number of points along the line.
    name : str, optional
        Label carried by the returned line.

    Returns
    -------
    FretLine
        The line.
    """
    return static_fret_line(
        donor, sigma=0.0, n_points=n_points, n_distance_samples=1, name=name,
    )


def dynamic_fret_line(donor=4.0, *, r0: float = 52.0, sigma: float = 6.0,
                      distance_1: float = 40.0, distance_2: float = 70.0,
                      n_points: int = 200, n_distance_samples: int = 81,
                      name: str = "dynamic FRET line") -> FretLine:
    """Dynamic FRET line for fast exchange between two limiting distances.

    Sweeps the fraction of state 1 from 0 to 1. Because the two states mix as
    *species* (their lifetime spectra add) while the plotted lifetime is
    fluorescence-averaged, the resulting line bows away from the static line;
    populations falling on it are exchanging on a timescale faster than the
    burst duration.

    Parameters
    ----------
    donor : float or array_like, optional
        Donor-only lifetime specification.
    r0 : float, optional
        Förster radius (Å).
    sigma : float, optional
        Linker width of each limiting state (Å).
    distance_1, distance_2 : float, optional
        Mean donor–acceptor distances of the two limiting states (Å).
    n_points : int, optional
        Number of mixing fractions sampled.
    n_distance_samples : int, optional
        Samples used to discretize each Gaussian.
    name : str, optional
        Label carried by the returned line.

    Returns
    -------
    FretLine
        The line, with ``parameter`` = fraction of state 1.
    """
    donor_x, donor_tau = donor_lifetime_spectrum(donor)
    tau_d0 = float(np.sum(donor_x * donor_tau))
    w, r = gaussian_distance_distribution(
        np.array([float(distance_1), float(distance_2)]), float(sigma),
        n_points=n_distance_samples,
    )
    amp, tau = _state_spectrum(w, r, donor_x, donor_tau, float(r0))
    fractions = np.linspace(0.0, 1.0, int(n_points))
    # Species mixture: the two lifetime spectra are concatenated and their
    # amplitudes weighted by the state fractions.
    mixed_tau = np.broadcast_to(np.concatenate([tau[0], tau[1]]), (fractions.size, tau[0].size * 2))
    mixed_amp = np.concatenate(
        [fractions[:, None] * amp[0][None, :], (1.0 - fractions)[:, None] * amp[1][None, :]],
        axis=-1,
    )
    tau_x, tau_f = lifetime_averages(mixed_amp, mixed_tau)
    return FretLine(
        tau_f=tau_f, tau_x=tau_x, efficiency=1.0 - tau_x / tau_d0, tau_d0=tau_d0,
        parameter=fractions, name=name, kind="dynamic",
        meta={"r0": float(r0), "sigma": float(sigma), "donor": donor,
              "distance_1": float(distance_1), "distance_2": float(distance_2)},
    )
