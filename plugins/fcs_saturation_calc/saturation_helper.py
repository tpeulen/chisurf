"""
Saturation-aware compute helpers for chisurf FCS models.
Based on Widengren 1995 triplet saturation model.
"""

import numpy as np

__version__ = "0.1.0"
__all__ = ["compute_apparent_volume", "compute_power_dependence"]


# From fcs_simulator model:
# alpha = (1/3)*(1 - exp(-2/(S**2))), S = z0/w0
# Veff(P) = V0*(1 + alpha * f_T(P))
# f_T(P) = (P/P_sat)/(1 + P/P_sat)


def compute_apparent_volume(P_mW, w0_nm=250.0, z0_nm=750.0, D_um2s=100.0,
                           F_T_max=0.15, P_sat_mW=5.0):
    """
    Compute power-dependent apparent effective volume and diffusion time.

    Parameters
    ----------
    P_mW : float
        Excitation power (mW).
    w0_nm : float
        1/e^2 beam waist (nm), default 250 nm.
    z0_nm : float
        Axial parameter (nm), default 750 nm.
    D_um2s : float
        Diffusion coefficient (um^2/s), default 100 um^2/s.
    F_T_max : float
        Maximal triplet fraction at saturation, default 0.15.
    P_sat_mW : float
        Saturation power (mW), default 5 mW.

    Returns
    -------
    V_apparent_um3 : float
        Apparent effective volume (um^3).
    tD_eff_us : float
        Diffusion time in microseconds (classical w0^2/(4*D)).
    """
    S = z0_nm / w0_nm
    alpha = (1.0 / 3.0) * (1.0 - np.exp(-2.0 / (S ** 2)))
    
    # V0 from 3D Gaussian (um^3)
    w0_um = w0_nm * 1e-3
    z0_um = z0_nm * 1e-3
    V0_um3 = (np.pi ** 1.5) * (w0_um ** 2) * z0_um
    
    # Saturation and triplet fraction
    s = P_mW / P_sat_mW
    f_T = F_T_max * (s / (s + 1.0))
    
    # Apparent volume
    V_apparent_um3 = V0_um3 * (1.0 + alpha * f_T)
    
    # Classical diffusion time (um, um^2/s -> us)
    tD_eff_us = (w0_nm ** 2) / (4.0 * D_um2s)
    
    return float(V_apparent_um3), float(tD_eff_us)


def compute_power_dependence(powers_mW, **kwargs):
    """
    Power sweep helper returning dict with arrays.

    Parameters
    ----------
    powers_mW : list of float
        Power values in mW.
    **kwargs
        Forwarded to compute_apparent_volume.

    Returns
    -------
    dict
        Keys: power_mW, Veff_um3, tD_eff_us, triplet_fraction
    """
    power_mW = np.asarray(powers_mW, dtype=float)
    result = {
        "power_mW": power_mW.tolist(),
        "Veff_um3": [],
        "tD_eff_us": [],
        "triplet_fraction": [],
    }
    for P in power_mW:
        V, tD = compute_apparent_volume(float(P), **kwargs)
        f_T = kwargs.get('F_T_max', 0.15) * ((P / kwargs.get('P_sat_mW', 5.0)) / 
                                               (P / kwargs.get('P_sat_mW', 5.0) + 1.0))
        result["Veff_um3"].append(float(V))
        result["tD_eff_us"].append(float(tD))
        result["triplet_fraction"].append(float(f_T))
    return result
