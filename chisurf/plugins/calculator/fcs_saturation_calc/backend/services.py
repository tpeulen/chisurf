"""ServiceDispatcher-compatible RPC handlers for the FCS saturation calculator."""

from __future__ import annotations

from typing import Any

import numpy as np

from chisurf.plugins.calculator.fcs_saturation_calc.core import (
    calculate_fcs_curves,
    volume_expansion,
)


def compute_saturation_rpc(
    power_mW: float,
    extinction: float,
    dark_matrix: list[list[float]],
    exc_matrix: list[list[float]],
    brightness: list[float],
    w_r_nm: float = 250.0,
    w_z_nm: float = 1000.0,
    D_um2s: float = 10.0,
    N: float = 1.0,
    include_bunching: bool = True,
    wavelength_nm: float = 488.0,
) -> dict[str, Any]:
    """Compute saturated FCS curves for an arbitrary N-state scheme.

    Parameters
    ----------
    power_mW : float
        Total measured excitation power (mW).
    extinction : float
        Molar extinction coefficient at the excitation wavelength (M^-1 cm^-1).
    dark_matrix, exc_matrix : list of list of float
        N x N rate and excitation cross-section matrices, ``K[target, source]``.
    brightness : list of float
        Relative brightness of each state.
    w_r_nm, w_z_nm : float
        Beam waists (nm).
    D_um2s : float
        Diffusion coefficient (um^2/s).
    N : float
        Number of molecules in the detection volume.
    include_bunching : bool
        Include the photokinetic state-relaxation term.
    wavelength_nm : float
        Excitation wavelength (nm).

    Returns
    -------
    dict
        Lag times (ms), both curves, their amplitudes, and ``V_eff/V_0``.
    """
    dark = np.asarray(dark_matrix, dtype=float)
    exc = np.asarray(exc_matrix, dtype=float)
    q = np.asarray(brightness, dtype=float)
    shared = dict(
        power_mW=power_mW,
        extinction=extinction,
        dark_matrix=dark,
        exc_matrix=exc,
        brightness=q,
        w_r_nm=w_r_nm,
        w_z_nm=w_z_nm,
        wavelength_nm=wavelength_nm,
    )
    tau_ms, g_unpert, g_sat = calculate_fcs_curves(
        D_um2s=D_um2s, N=N, include_bunching=include_bunching, **shared
    )
    return {
        "tau_ms": tau_ms.tolist(),
        "g_unperturbed": g_unpert.tolist(),
        "g_saturated": g_sat.tolist(),
        "g_unperturbed_0": float(g_unpert[0]),
        "g_saturated_0": float(g_sat[0]),
        "v_eff_over_v0": volume_expansion(**shared),
    }


def register_services(dispatcher: Any) -> None:
    """Register the RPC handlers with a ServiceDispatcher.

    Parameters
    ----------
    dispatcher : object
        Anything exposing ``register(name, handler)``.
    """
    dispatcher.register("fcs_saturation.compute", lambda params: compute_saturation_rpc(**params))
