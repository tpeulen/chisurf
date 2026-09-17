r"""Translational diffusion in solution: temperature, viscosity, focal volume.

The physics every diffusion measurement needs before it can quote a number:
how a diffusion coefficient depends on temperature and viscosity, and how it
relates to the size of the observation volume.

This lives in the core rather than in one analysis tool because two unrelated
measurements need exactly the same relations:

* **FCS** calibrates the confocal volume from a dye of known ``D``, via
  :math:`V_\mathrm{eff}` and the diffusion time;
* **image correlation** calibrates the beam waists the same way, via
  :math:`w_r^2 = 4 D \tau`.

Both must first correct the reference dye's tabulated ``D`` for the temperature
the experiment was actually run at, and both then invert the same relation.
Keeping one implementation means the two cannot silently disagree about what
"D of Rhodamine 110 at 23 °C" is.

Reference values for the dyes themselves come from
:mod:`chisurf.core.fluorescence.dyes`, which reads them from the metadata store.
"""

from __future__ import annotations

import math

#: Boltzmann constant, J/K.
KB = 1.380649e-23

#: Reference temperature of the tabulated diffusion coefficients, in kelvin.
T_REFERENCE_K = 298.15

#: Water viscosity at the reference temperature, in Pa·s.
ETA_WATER_25C = 8.9e-4


def celsius_to_kelvin(t_celsius: float) -> float:
    """Convert a temperature from degrees Celsius to kelvin.

    Parameters
    ----------
    t_celsius : float
        Temperature in °C.

    Returns
    -------
    float
        Temperature in K.
    """
    return float(t_celsius) + 273.15


def water_viscosity(temperature_k: float) -> float:
    r"""Return the dynamic viscosity of water, in Pa·s.

    Uses the Vogel-type form :math:`\eta(T) = A\,10^{B/(T-C)}` with
    :math:`A = 2.414\times10^{-5}`, :math:`B = 247.8`, :math:`C = 140`.

    Parameters
    ----------
    temperature_k : float
        Absolute temperature in kelvin.

    Returns
    -------
    float
        Dynamic viscosity in Pa·s.

    Raises
    ------
    ValueError
        Below 140 K, where the expression diverges.

    Examples
    --------
    >>> round(water_viscosity(celsius_to_kelvin(25.0)) * 1e3, 4)
    0.8904
    >>> round(water_viscosity(celsius_to_kelvin(37.0)) * 1e3, 4)
    0.6904
    """
    t = float(temperature_k)
    a, b, c = 2.414e-5, 247.8, 140.0
    if t <= c:
        raise ValueError(f"the water-viscosity model needs T > {c} K; got {t}")
    return a * 10.0 ** (b / (t - c))


def stokes_einstein_diffusion(
    temperature_k: float, viscosity: float, hydrodynamic_radius: float
) -> float:
    r"""Return the translational diffusion coefficient of a sphere.

    :math:`D = k_B T / (6 \pi \eta r_h)`.

    Parameters
    ----------
    temperature_k : float
        Absolute temperature in kelvin.
    viscosity : float
        Dynamic viscosity in Pa·s.
    hydrodynamic_radius : float
        Hydrodynamic radius in metres.

    Returns
    -------
    float
        Diffusion coefficient in m²/s.
    """
    return (
        KB * float(temperature_k) / (6.0 * math.pi * float(viscosity) * float(hydrodynamic_radius))
    )


def stokes_einstein_radius(
    temperature_k: float, viscosity: float, diffusion_coefficient: float
) -> float:
    """Return the hydrodynamic radius implied by a diffusion coefficient.

    Inverse of :func:`stokes_einstein_diffusion`.

    Parameters
    ----------
    temperature_k : float
        Absolute temperature in kelvin.
    viscosity : float
        Dynamic viscosity in Pa·s.
    diffusion_coefficient : float
        Diffusion coefficient in m²/s.

    Returns
    -------
    float
        Hydrodynamic radius in metres.
    """
    return (
        KB
        * float(temperature_k)
        / (6.0 * math.pi * float(viscosity) * float(diffusion_coefficient))
    )


def diffusion_at_temperature(
    d25: float,
    temperature_c: float = 25.0,
    viscosity: float | None = None,
) -> float:
    r"""Correct a tabulated 25 °C diffusion coefficient to another temperature.

    .. math::

        D(T, \eta) = D_{25,\mathrm{w}}\,
            \frac{T}{298.15\,\mathrm{K}}\,\frac{\eta_{25,\mathrm{w}}}{\eta(T)}

    Both factors matter and pull the same way: warmer means faster *and* thinner.

    **This correction is not optional.** Diffusion in water changes by roughly
    2.6 % per °C near room temperature, so calibrating against a dye at an
    assumed 25 °C when the bench is at 23 °C biases the reference ``D`` by about
    5 %. Every quantity derived from that calibration inherits the error.

    Parameters
    ----------
    d25 : float
        Tabulated diffusion coefficient in water at 25 °C. Any unit; the result
        carries the same one.
    temperature_c : float
        Actual sample temperature in °C.
    viscosity : float, optional
        Dynamic viscosity of the *sample* in Pa·s, when it is not water — a
        glycerol mixture, a crowded cytoplasm. Defaults to water at that
        temperature.

    Returns
    -------
    float
        Diffusion coefficient at the requested condition, in the unit of *d25*.

    Examples
    --------
    A dye tabulated at 25 °C, measured on a 23 °C bench, actually diffuses ~5 %
    slower:

    >>> round(diffusion_at_temperature(470.0, 23.0), 1)
    445.5
    >>> round(diffusion_at_temperature(470.0, 25.0), 1)
    469.8
    >>> round(diffusion_at_temperature(470.0, 37.0), 1)
    630.3

    Doubling the viscosity halves the diffusion coefficient:

    >>> eta = water_viscosity(celsius_to_kelvin(25.0))
    >>> round(diffusion_at_temperature(470.0, 25.0, viscosity=2 * eta), 1)
    234.9
    """
    t_k = celsius_to_kelvin(temperature_c)
    eta = water_viscosity(t_k) if viscosity is None else float(viscosity)
    if t_k <= 0 or eta <= 0:
        return float("nan")
    return float(d25) * (t_k / T_REFERENCE_K) * (ETA_WATER_25C / eta)


def temperature_sensitivity(temperature_c: float = 25.0) -> float:
    """Return the fractional change in ``D`` per °C, near a given temperature.

    Reported so a tool can tell the user what a temperature uncertainty costs
    them rather than leaving it implicit.

    Parameters
    ----------
    temperature_c : float
        Temperature in °C to evaluate the sensitivity at.

    Returns
    -------
    float
        Relative change of ``D`` per °C (e.g. ``0.027`` for 2.7 %/°C).

    Examples
    --------
    >>> round(temperature_sensitivity(25.0) * 100, 1)
    2.6
    """
    lo = diffusion_at_temperature(1.0, temperature_c - 0.5)
    hi = diffusion_at_temperature(1.0, temperature_c + 0.5)
    mid = diffusion_at_temperature(1.0, temperature_c)
    return float((hi - lo) / mid)


# --- observation volume ----------------------------------------------------
def effective_volume(tau_diffusion: float, diffusion_coefficient: float, s: float) -> float:
    r"""Return the effective confocal volume from a diffusion time.

    :math:`V_\mathrm{eff} = \pi^{3/2} S (4 D \tau_D)^{3/2}`.

    Parameters
    ----------
    tau_diffusion : float
        Diffusion time in seconds.
    diffusion_coefficient : float
        Diffusion coefficient in m²/s.
    s : float
        Structure parameter :math:`w_z / w_{xy}`.

    Returns
    -------
    float
        Effective volume in m³.
    """
    return (
        (math.pi**1.5)
        * float(s)
        * (4.0 * float(diffusion_coefficient) * float(tau_diffusion)) ** 1.5
    )


def diffusion_from_volume(tau_diffusion: float, volume: float, s: float) -> float:
    """Return the diffusion coefficient implied by a known effective volume.

    Inverse of :func:`effective_volume`.

    Parameters
    ----------
    tau_diffusion : float
        Diffusion time in seconds.
    volume : float
        Effective volume in m³.
    s : float
        Structure parameter.

    Returns
    -------
    float
        Diffusion coefficient in m²/s, or NaN for unusable input.
    """
    denom = (math.pi**1.5) * float(s)
    if denom <= 0 or float(tau_diffusion) <= 0:
        return float("nan")
    inner = float(volume) / denom
    if inner <= 0:
        return float("nan")
    return (inner ** (2.0 / 3.0)) / (4.0 * float(tau_diffusion))


def lateral_waist(tau_diffusion: float, diffusion_coefficient: float) -> float:
    r"""Return the lateral beam waist from a diffusion time and a known ``D``.

    :math:`w_{xy} = \sqrt{4 D \tau_D}` — the relation that turns a measurement
    on a reference dye into a calibration of the optics. It is the same
    statement as :func:`effective_volume`, written for the waist that image
    correlation fits.

    Parameters
    ----------
    tau_diffusion : float
        Diffusion time in seconds.
    diffusion_coefficient : float
        Diffusion coefficient in the squared length unit per second; the result
        carries the matching length unit (µm²/s in, µm out).

    Returns
    -------
    float
        Lateral waist, or NaN for unusable input.

    Examples
    --------
    A dye with D = 470 µm²/s and a 30 µs diffusion time gives a waist of
    ~0.24 µm, a typical confocal focus:

    >>> round(lateral_waist(30e-6, 470.0), 3)
    0.237
    """
    d = float(diffusion_coefficient)
    tau = float(tau_diffusion)
    if d <= 0 or tau <= 0:
        return float("nan")
    return math.sqrt(4.0 * d * tau)


def diffusion_time(waist: float, diffusion_coefficient: float) -> float:
    r"""Return the diffusion time for a given waist and ``D``.

    Inverse of :func:`lateral_waist`: :math:`\tau_D = w_{xy}^2 / (4D)`.

    Parameters
    ----------
    waist : float
        Lateral waist, in the length unit matching *diffusion_coefficient*.
    diffusion_coefficient : float
        Diffusion coefficient in length²/s.

    Returns
    -------
    float
        Diffusion time in seconds, or NaN for unusable input.
    """
    d = float(diffusion_coefficient)
    if d <= 0:
        return float("nan")
    return float(waist) ** 2 / (4.0 * d)


def combined_waist(waist_a: float, waist_b: float) -> float:
    r"""Return the effective waist of a cross-correlation between two channels.

    :math:`w_\mathrm{cc} = \sqrt{\tfrac{1}{2}(w_a^2 + w_b^2)}`.

    Two detection channels focus to different waists — chromatic aberration
    alone guarantees it — and their cross-correlation samples the overlap of the
    two volumes. Using either channel's own waist for the cross term biases the
    result.

    Parameters
    ----------
    waist_a, waist_b : float
        The two channel waists, same unit.

    Returns
    -------
    float
        The combined waist, in that unit.

    Examples
    --------
    >>> round(combined_waist(0.20, 0.28), 4)
    0.2433
    """
    return math.sqrt(0.5 * (float(waist_a) ** 2 + float(waist_b) ** 2))


def reference_diffusion(
    dye: str, temperature_c: float = 25.0, viscosity: float | None = None
) -> float:
    """Return a reference dye's diffusion coefficient at a given temperature.

    Joins the metadata store's tabulated value to the temperature correction —
    the single call a calibration needs.

    Parameters
    ----------
    dye : str
        Species name or alias, resolved through
        :func:`chisurf.core.fluorescence.dyes.get_dye`.
    temperature_c : float
        Sample temperature in °C.
    viscosity : float, optional
        Sample viscosity in Pa·s when it is not water.

    Returns
    -------
    float
        Diffusion coefficient in µm²/s, or NaN when the species is unknown.
    """
    from chisurf.core.fluorescence.dyes import diffusion_coefficient_25C

    d25 = diffusion_coefficient_25C(dye)
    if not (d25 == d25):  # NaN
        return float("nan")
    return diffusion_at_temperature(d25, temperature_c, viscosity)
