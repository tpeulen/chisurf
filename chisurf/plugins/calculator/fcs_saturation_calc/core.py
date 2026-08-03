"""Core calculations for the FCS saturation calculator.

Every number here comes from :mod:`chisurf.core.fluorescence.fcs.saturation`,
the same module the ``FCS (kinetics)`` fitting model evaluates, so the
calculator and the fit can never disagree about the physics or the units. This
module only converts the display units (mW, nm, um^2/s) the GUI works in.
"""

from __future__ import annotations

import numpy as np

from chisurf.core.fluorescence.fcs.saturation import (
    DEFAULT_WAVELENGTH_M,
    compute_power_sweep,
    effective_volume,
    emission_profile,
    excitation_rate,
    gaussian_g_diff,
    saturated_curve_shape,
    steady_state_full_populations,
)

#: Lag-time grid the calculator reports on: 100 ns to 10 s, log spaced.
TAU_DECADES = (-7, 1)
N_TAU = 300


def lag_times_s(n: int = N_TAU) -> np.ndarray:
    """Return the calculator's standard logarithmic lag-time grid in seconds."""
    return np.logspace(TAU_DECADES[0], TAU_DECADES[1], n)


def calculate_fcs_curves(
    power_mW: float,
    extinction: float,
    dark_matrix: np.ndarray,
    exc_matrix: np.ndarray,
    brightness: np.ndarray,
    w_r_nm: float,
    w_z_nm: float,
    D_um2s: float,
    N: float = 1.0,
    b: float = 0.0,
    include_bunching: bool = True,
    wavelength_nm: float = DEFAULT_WAVELENGTH_M * 1e9,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute the unperturbed (Gaussian) and the saturated FCS curves.

    Parameters
    ----------
    power_mW : float
        Total measured excitation power (mW).
    extinction : float
        Molar extinction coefficient at the excitation wavelength (M^-1 cm^-1).
    dark_matrix : np.ndarray
        N x N power-independent rate matrix ``K_dark`` in Hz.
    exc_matrix : np.ndarray
        N x N excitation cross-section matrix ``K_exc``.
    brightness : np.ndarray
        Relative brightness of each state, shape ``(N,)``.
    w_r_nm : float
        Radial 1/e^2 beam waist (nm).
    w_z_nm : float
        Axial 1/e^2 beam waist (nm).
    D_um2s : float
        Translational diffusion coefficient (um^2/s).
    N : float
        Number of molecules in the detection volume.
    b : float
        Baseline offset.
    include_bunching : bool
        Include the photokinetic state-relaxation (bunching) term.
    wavelength_nm : float
        Excitation wavelength (nm).

    Returns
    -------
    tuple of np.ndarray
        ``(tau_ms, g_unperturbed, g_saturated)``. At zero power the two curves
        are identical, because zero power is exactly the unsaturated case.
    """
    w0_m = w_r_nm * 1e-9
    z0_m = w_z_nm * 1e-9
    D_m2s = D_um2s * 1e-12
    power_W = power_mW * 1e-3

    tau_s = lag_times_s()
    g_unperturbed = b + (1.0 / N) * gaussian_g_diff(tau_s, w0_m, z0_m, D_m2s)

    g_sat_shape = saturated_curve_shape(
        tau_s,
        power_W=power_W,
        extinction=extinction,
        dark_matrix=dark_matrix,
        exc_matrix=exc_matrix,
        brightness=brightness,
        w0=w0_m,
        z0=z0_m,
        D=D_m2s,
        include_bunching=include_bunching,
        wavelength_m=wavelength_nm * 1e-9,
    )
    return tau_s * 1e3, g_unperturbed, b + (1.0 / N) * g_sat_shape


def compute_power_sweep_curves(
    power_mW: float,
    extinction: float,
    dark_matrix: np.ndarray,
    exc_matrix: np.ndarray,
    brightness: np.ndarray,
    w_r_nm: float,
    w_z_nm: float,
    D_um2s: float,
    wavelength_nm: float = DEFAULT_WAVELENGTH_M * 1e9,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute the volume expansion ratio and diffusion time versus laser power.

    Parameters
    ----------
    power_mW : float
        Power the sweep is centred on (mW).
    extinction : float
        Molar extinction coefficient at the excitation wavelength (M^-1 cm^-1).
    dark_matrix, exc_matrix : np.ndarray
        The scheme's rate and cross-section matrices.
    brightness : np.ndarray
        Relative brightness of each state.
    w_r_nm, w_z_nm : float
        Beam waists (nm).
    D_um2s : float
        Diffusion coefficient (um^2/s).
    wavelength_nm : float
        Excitation wavelength (nm).

    Returns
    -------
    tuple of np.ndarray
        ``(powers_mW, v_eff_over_v0, tau_d_ms)``.
    """
    return compute_power_sweep(
        power_mW=power_mW,
        extinction=extinction,
        dark_matrix=dark_matrix,
        exc_matrix=exc_matrix,
        brightness=brightness,
        w_r_nm=w_r_nm,
        w_z_nm=w_z_nm,
        D_um2s=D_um2s,
        wavelength_nm=wavelength_nm,
    )


def compute_volume_profile(
    power_mW: float,
    extinction: float,
    dark_matrix: np.ndarray,
    exc_matrix: np.ndarray,
    brightness: np.ndarray,
    w_r_nm: float,
    w_z_nm: float,
    state_labels: list[str] | None = None,
    wavelength_nm: float = DEFAULT_WAVELENGTH_M * 1e9,
) -> dict[str, np.ndarray | list[str]]:
    """Compute radial profiles of the excitation rate and the state populations.

    Parameters
    ----------
    power_mW : float
        Laser power (mW).
    extinction : float
        Molar extinction coefficient at the excitation wavelength (M^-1 cm^-1).
    dark_matrix, exc_matrix : np.ndarray
        The scheme's rate and cross-section matrices.
    brightness : np.ndarray
        Relative brightness of each state.
    w_r_nm, w_z_nm : float
        Beam waists (nm).
    state_labels : list of str, optional
        Display names of the states; state numbers are used when omitted.
    wavelength_nm : float
        Excitation wavelength (nm).

    Returns
    -------
    dict
        ``r_nm``, ``k_exc_norm`` (scaled to its peak), ``P_states`` (N x M),
        ``emission`` (absolute, same scale as the populations) and ``labels``.
    """
    w0_m = w_r_nm * 1e-9
    z0_m = w_z_nm * 1e-9

    r = np.linspace(0.0, 3.5 * w0_m, 140)
    z = np.zeros_like(r)
    k_exc = excitation_rate(
        r, z, w0_m, z0_m, power_mW * 1e-3, extinction, wavelength_nm * 1e-9
    )
    k_exc_peak = float(k_exc[0])
    k_exc_norm = (k_exc / k_exc_peak) if k_exc_peak > 0 else np.zeros_like(r)

    P_states = steady_state_full_populations(k_exc, dark_matrix, exc_matrix)
    q = np.asarray(brightness, dtype=float)
    # Absolute, on the same scale as the populations it is built from. Scaling it
    # to its own peak instead put the emission at 1.0 in the focal centre while
    # the only bright state sat at 0.17 there -- two curves on one axis that
    # cannot both be read, and it looks like the state labels are swapped.
    emission = np.tensordot(q, P_states, axes=(0, 0))

    n_states = P_states.shape[0]
    if not state_labels or len(state_labels) < n_states:
        labels = [str(i + 1) for i in range(n_states)]
    else:
        labels = [str(lab).split(" ")[0] for lab in state_labels[:n_states]]

    return {
        "r_nm": r * 1e9,
        "k_exc_norm": k_exc_norm,
        "P_states": P_states,
        "emission": emission,
        "labels": labels,
    }


def volume_expansion(
    power_mW: float,
    extinction: float,
    dark_matrix: np.ndarray,
    exc_matrix: np.ndarray,
    brightness: np.ndarray,
    w_r_nm: float,
    w_z_nm: float,
    wavelength_nm: float = DEFAULT_WAVELENGTH_M * 1e9,
) -> float:
    """Return ``V_eff / V_0`` at one power, straight from the real-space integrals.

    Parameters
    ----------
    power_mW : float
        Laser power (mW).
    extinction : float
        Molar extinction coefficient at the excitation wavelength (M^-1 cm^-1).
    dark_matrix, exc_matrix : np.ndarray
        The scheme's rate and cross-section matrices.
    brightness : np.ndarray
        Relative brightness of each state.
    w_r_nm, w_z_nm : float
        Beam waists (nm).
    wavelength_nm : float
        Excitation wavelength (nm).

    Returns
    -------
    float
        The volume expansion ratio; ``1.0`` at zero power.
    """
    from chisurf.core.fluorescence.fcs.saturation import (
        DEFAULT_N_R,
        DEFAULT_N_Z,
        GRID_EXTENT_WAISTS,
    )

    if power_mW <= 0.0:
        return 1.0
    w0_m, z0_m = w_r_nm * 1e-9, w_z_nm * 1e-9
    r = np.linspace(0.0, GRID_EXTENT_WAISTS * w0_m, DEFAULT_N_R)
    z = np.linspace(-GRID_EXTENT_WAISTS * z0_m, GRID_EXTENT_WAISTS * z0_m, DEFAULT_N_Z)
    R, Z = np.meshgrid(r, z, indexing="ij")
    k_exc = excitation_rate(
        R, Z, w0_m, z0_m, power_mW * 1e-3, extinction, wavelength_nm * 1e-9
    )
    profile = emission_profile(k_exc, dark_matrix, exc_matrix, brightness)
    v_eff = effective_volume(r, z, profile)
    v_0 = np.pi**1.5 * w0_m**2 * z0_m
    return float(v_eff / v_0) if v_eff > 0 else 1.0
