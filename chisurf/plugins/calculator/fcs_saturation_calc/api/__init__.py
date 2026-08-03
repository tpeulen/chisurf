"""Public Python API for the FCS saturation calculator.

Computes numerically saturated FCS curves for an arbitrary N-state photochemical
scheme. The scheme is fully described by three arrays and nothing else:

``dark_matrix``
    ``K[target, source]`` in Hz — every power-independent transition
    (fluorescence decay, intersystem crossing, isomerisation, energy transfer,
    thermal recovery). The diagonal is derived, never supplied.
``exc_matrix``
    ``K[target, source]`` relative excitation cross sections; multiplied by the
    local excitation rate ``k_exc(r, z)``.
``brightness``
    ``Q_i`` per state — a state is bright because this says so.

Two states is the minimum (ground plus excited). Everything else — triplets,
cis isomers, FRET partners — is just more states, and no function here treats
any state position as special.
"""

from __future__ import annotations

import numpy as np

from chisurf.plugins.calculator.fcs_saturation_calc.core import (
    calculate_fcs_curves,
    compute_power_sweep_curves,
    compute_volume_profile,
    volume_expansion,
)

__all__ = [
    "calculate_fcs_curves",
    "compute_power_sweep_curves",
    "compute_volume_profile",
    "volume_expansion",
    "two_state_scheme",
    "triplet_scheme",
    "isomerisation_scheme",
    "simulate_saturation",
]


def two_state_scheme(
    lifetime_ns: float = 4.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The minimal scheme: a ground state and one emitting excited state.

    Parameters
    ----------
    lifetime_ns : float
        Fluorescence lifetime of the excited state (ns).

    Returns
    -------
    tuple of np.ndarray
        ``(dark_matrix, exc_matrix, brightness)``.
    """
    dark = np.zeros((2, 2))
    dark[0, 1] = 1e9 / float(lifetime_ns)
    exc = np.zeros((2, 2))
    exc[1, 0] = 1.0
    return dark, exc, np.array([0.0, 1.0])


def triplet_scheme(
    lifetime_ns: float = 4.0,
    isc_yield: float = 0.01,
    triplet_lifetime_us: float = 2.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """A three-state scheme with one non-emitting trapped state.

    Written for the singlet/triplet case of a rhodamine, but the arrays carry no
    such assumption: state 3 is simply a dark state reached from state 2.

    Parameters
    ----------
    lifetime_ns : float
        Excited-state fluorescence lifetime (ns).
    isc_yield : float
        Branching yield into the dark state.
    triplet_lifetime_us : float
        Lifetime of the dark state (us).

    Returns
    -------
    tuple of np.ndarray
        ``(dark_matrix, exc_matrix, brightness)``.
    """
    k_total = 1e9 / float(lifetime_ns)
    dark = np.zeros((3, 3))
    dark[0, 1] = k_total * (1.0 - float(isc_yield))
    dark[2, 1] = k_total * float(isc_yield)
    dark[0, 2] = 1e6 / float(triplet_lifetime_us)
    exc = np.zeros((3, 3))
    exc[1, 0] = 1.0
    return dark, exc, np.array([0.0, 1.0, 0.0])


def isomerisation_scheme(
    lifetime_ns: float = 1.0,
    isomerisation_yield: float = 0.03,
    isomer_lifetime_ms: float = 1.0,
    isc_yield: float = 0.004,
    triplet_lifetime_us: float = 5.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """A four-state cyanine-like scheme: emitter, dark isomer and dark trap.

    States are ``1`` ground, ``2`` excited, ``3`` isomer, ``4`` trapped. The
    isomer is populated from the excited state and recovers thermally on a
    millisecond timescale — that separation of timescales is what makes it
    visible in an FCS curve.

    Parameters
    ----------
    lifetime_ns : float
        Excited-state fluorescence lifetime (ns).
    isomerisation_yield : float
        Branching yield into the isomer.
    isomer_lifetime_ms : float
        Thermal recovery time of the isomer (ms).
    isc_yield : float
        Branching yield into the trapped state.
    triplet_lifetime_us : float
        Lifetime of the trapped state (us).

    Returns
    -------
    tuple of np.ndarray
        ``(dark_matrix, exc_matrix, brightness)``.
    """
    k_total = 1e9 / float(lifetime_ns)
    dark = np.zeros((4, 4))
    dark[0, 1] = k_total * (1.0 - float(isomerisation_yield) - float(isc_yield))
    dark[2, 1] = k_total * float(isomerisation_yield)
    dark[3, 1] = k_total * float(isc_yield)
    dark[0, 2] = 1e3 / float(isomer_lifetime_ms)
    dark[0, 3] = 1e6 / float(triplet_lifetime_us)
    exc = np.zeros((4, 4))
    exc[1, 0] = 1.0
    return dark, exc, np.array([0.0, 1.0, 0.0, 0.0])


def simulate_saturation(
    scheme: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None,
    power_mW: float = 2.0,
    extinction: float = 250000.0,
    wavelength_nm: float = 488.0,
    w_r_nm: float = 250.0,
    w_z_nm: float = 1000.0,
    D_um2s: float = 10.0,
    N: float = 1.0,
    include_bunching: bool = True,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Simulate the unperturbed and saturated FCS curves for a scheme.

    Parameters
    ----------
    scheme : tuple, optional
        ``(dark_matrix, exc_matrix, brightness)``; :func:`triplet_scheme` is
        used when omitted.
    power_mW : float
        Total measured excitation power (mW).
    extinction : float
        Molar extinction coefficient at the excitation wavelength (M^-1 cm^-1).
    wavelength_nm : float
        Excitation wavelength (nm).
    w_r_nm, w_z_nm : float
        Beam waists (nm).
    D_um2s : float
        Diffusion coefficient (um^2/s).
    N : float
        Number of molecules in the detection volume.
    include_bunching : bool
        Include the photokinetic state-relaxation term.

    Returns
    -------
    tuple of np.ndarray
        ``(tau_ms, g_unperturbed, g_saturated)``.
    """
    dark_matrix, exc_matrix, brightness = scheme if scheme else triplet_scheme()
    return calculate_fcs_curves(
        power_mW=power_mW,
        extinction=extinction,
        dark_matrix=dark_matrix,
        exc_matrix=exc_matrix,
        brightness=brightness,
        w_r_nm=w_r_nm,
        w_z_nm=w_z_nm,
        D_um2s=D_um2s,
        N=N,
        include_bunching=include_bunching,
        wavelength_nm=wavelength_nm,
    )
