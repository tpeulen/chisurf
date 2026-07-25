"""Qt-free core for the FCS confocal (diffusion/volume) calculator.

Unit conversions, the shape diffusion models, and a single ``compute_confocal``
solver used by the backend RPC.

The temperature/viscosity/Stokes-Einstein physics and the effective-volume
relations are **not** implemented here: they live in
:mod:`chisurf.core.fluorescence.diffusion`, shared with image-correlation
waist calibration, which needs exactly the same relations. The wrappers below
keep this module's historical API while delegating to that one, so the two
cannot disagree about what "D of a dye at 23 °C" is. The reference-dye table
moved to :mod:`chisurf.core.fluorescence.dyes` for the same reason.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List

from chisurf.core.fluorescence import diffusion as _diffusion

# ========= Constants & conversions =========
KB = 1.380649e-23  # J/K
NA = 6.02214076e23 # 1/mol
N_PER_nM_fL = NA * 1e-9 * 1e-15  # ≈ 0.602214076


def mPa_s_to_Pa_s(eta_mPa_s: float) -> float:
    """Convert viscosity from mPa·s to Pa·s.

    Parameters
    ----------
    eta_mPa_s : float
        Viscosity in mPa·s.

    Returns
    -------
    float
        Viscosity in Pa·s.
    """
    return eta_mPa_s * 1e-3

def Pa_s_to_mPa_s(eta_Pa_s: float) -> float:
    """Convert viscosity from Pa·s to mPa·s.

    Parameters
    ----------
    eta_Pa_s : float
        Viscosity in Pa·s.

    Returns
    -------
    float
        Viscosity in mPa·s.
    """
    return eta_Pa_s * 1e3

def nm_to_m(x_nm: float) -> float:
    """Convert a length from nanometers to meters.

    Parameters
    ----------
    x_nm : float
        Length in nm.

    Returns
    -------
    float
        Length in m.
    """
    return x_nm * 1e-9

def m_to_nm(x_m: float) -> float:
    """Convert a length from meters to nanometers.

    Parameters
    ----------
    x_m : float
        Length in m.

    Returns
    -------
    float
        Length in nm.
    """
    return x_m * 1e9

def um2s_to_m2s(D_um2_s: float) -> float:
    """Convert a diffusion coefficient from µm²/s to m²/s.

    Parameters
    ----------
    D_um2_s : float
        Diffusion coefficient in µm²/s.

    Returns
    -------
    float
        Diffusion coefficient in m²/s.
    """
    return D_um2_s * 1e-12

def m2s_to_um2s(D_m2_s: float) -> float:
    """Convert a diffusion coefficient from m²/s to µm²/s.

    Parameters
    ----------
    D_m2_s : float
        Diffusion coefficient in m²/s.

    Returns
    -------
    float
        Diffusion coefficient in µm²/s.
    """
    return D_m2_s * 1e12

def us_to_s(t_us: float) -> float:
    """Convert a time from microseconds to seconds.

    Parameters
    ----------
    t_us : float
        Time in µs.

    Returns
    -------
    float
        Time in s.
    """
    return t_us * 1e-6

def s_to_us(t_s: float) -> float:
    """Convert a time from seconds to microseconds.

    Parameters
    ----------
    t_s : float
        Time in s.

    Returns
    -------
    float
        Time in µs.
    """
    return t_s * 1e6

def m3_to_fL(v_m3: float) -> float:
    """Convert a volume from m³ to femtoliters.

    Parameters
    ----------
    v_m3 : float
        Volume in m³.

    Returns
    -------
    float
        Volume in fL.
    """
    return v_m3 / 1e-18

def fL_to_m3(v_fL: float) -> float:
    """Convert a volume from femtoliters to m³.

    Parameters
    ----------
    v_fL : float
        Volume in fL.

    Returns
    -------
    float
        Volume in m³.
    """
    return v_fL * 1e-18


def water_viscosity_Pa_s(T_K: float) -> float:
    """Water viscosity (Pa·s). Delegates to the shared diffusion physics."""
    return _diffusion.water_viscosity(T_K)


def stokes_einstein_D(T_K: float, eta_Pa_s: float, r_h_m: float) -> float:
    """Translational diffusion coefficient of a sphere (m²/s)."""
    return _diffusion.stokes_einstein_diffusion(T_K, eta_Pa_s, r_h_m)


def stokes_einstein_rh(T_K: float, eta_Pa_s: float, D_m2_s: float) -> float:
    """Hydrodynamic radius (m) from a known diffusion coefficient."""
    return _diffusion.stokes_einstein_radius(T_K, eta_Pa_s, D_m2_s)


def veff_from_tau_D_S(tau_s: float, D_m2_s: float, S: float) -> float:
    """Effective focal volume (m³) from diffusion time, D and structure parameter."""
    return _diffusion.effective_volume(tau_s, D_m2_s, S)


def D_from_tau_Veff_S(tau_s: float, Veff_m3: float, S: float) -> float:
    """Diffusion coefficient (m²/s) from the effective volume and S."""
    return _diffusion.diffusion_from_volume(tau_s, Veff_m3, S)


def scale_D_from_25C(D25_um2_s: float, T_K: float, eta_Pa_s: float) -> float:
    """Scale a 25 °C water diffusion coefficient to arbitrary (T, eta)."""
    return _diffusion.diffusion_at_temperature(
        D25_um2_s, T_K - 273.15, viscosity=eta_Pa_s
    )


def perrin_friction_ellipsoid(p: float) -> float:
    """Perrin translational friction factor for an ellipsoid.

    The axial ratio is :math:`p = a/b` (semi-major/ semi-minor axis).
    """
    if p < 1:  # oblate
        q = 1.0 / p
        return math.sqrt(q*q - 1.0) / (pow(q, 2.0/3.0) * math.atan(math.sqrt(q*q - 1.0)))
    elif p > 1:  # prolate
        q = 1.0 / p
        return math.sqrt(1.0 - q*q) / (pow(q, 2.0/3.0) * math.log((1.0 + math.sqrt(1.0 - q*q)) / q))
    else:  # sphere
        return 1.0


def perrin_friction_cylinder(p: float) -> float:
    """Translational friction factor for a cylinder.

    Uses the Hansen (2004) polynomial approximation for :math:`F_t(p)` with
    :math:`p = L/d` (length/diameter).
    """
    lnp = math.log(p)
    return 1.0304 + 0.0193 * pow(lnp, 1) + 0.06229 * pow(lnp, 2) + 0.00476 * pow(lnp, 3) + 0.00166 * pow(lnp, 4) + 2.66e-6 * pow(lnp, 7)


def diffusion_ellipsoid(T_K: float, eta_Pa_s: float, a_m: float, b_m: float) -> float:
    """Diffusion coefficient for an ellipsoid with semi-axes a and b.

    Uses the equivalent radius :math:`R_e = (ab^2)^{1/3}` and Perrin
    translational friction factor :math:`F_t(p)` with :math:`p=a/b`.
    Returns :math:`D` in µm²/s.
    """
    p = a_m / b_m
    Ft = perrin_friction_ellipsoid(p)
    Re = pow(a_m * a_m * b_m, 1.0/3.0)  # equivalent radius
    D = KB * T_K / (6.0 * math.pi * eta_Pa_s * Re * Ft)
    return m2s_to_um2s(D)


def diffusion_cylinder(T_K: float, eta_Pa_s: float, L_m: float, d_m: float) -> float:
    """Diffusion coefficient for a cylinder of length L and diameter d.

    Uses the equivalent radius and Hansen (2004) Perrin factor approximation
    for aspect ratio :math:`p=L/d`. Returns :math:`D` in µm²/s.
    """
    p = L_m / d_m
    Ft = perrin_friction_cylinder(p)
    Re = pow(3.0 / (2.0 * p * p), 1.0/3.0) * L_m / 2.0
    D = KB * T_K / (6.0 * math.pi * eta_Pa_s * Re * Ft)
    return m2s_to_um2s(D)


# ========= Reference dyes (looked up in MMFDB) =========
# Diffusion is a dye property: D(25 °C, water) lives on the MMFDB probe next to
# quantum yield and extinction coefficient. ChiSurf keeps no private table.
def reference_dyes(refresh: bool = False) -> Dict[str, Dict]:
    """Return the MMFDB reference species that carry a diffusion coefficient.

    Parameters
    ----------
    refresh : bool, optional
        Re-read MMFDB instead of using the cached lookup. Default False.

    Returns
    -------
    dict
        Mapping of species name to its MMFDB entry (``d25_um2_s``, ``sources``,
        ``category``, ``probe_id``).
    """
    from chisurf.core.fluorescence.dyes import reference_dyes as _reference_dyes

    return _reference_dyes(refresh=refresh)


def dye_names(refresh: bool = False) -> List[str]:
    """Return the sorted names of the MMFDB reference species."""
    from chisurf.core.fluorescence.dyes import dye_names as _dye_names

    return _dye_names(refresh=refresh)


def dye_diffusion_25C(name: str) -> float:
    """Return ``D(25 °C, water)`` in µm²/s for an MMFDB species (NaN if unknown)."""
    from chisurf.core.fluorescence.dyes import diffusion_coefficient_25C

    return diffusion_coefficient_25C(name)


def get_dye(name: str) -> Dict | None:
    """Return the MMFDB entry for a species name or alias (``None`` if unknown)."""
    from chisurf.core.fluorescence.dyes import get_dye as _get_dye

    return _get_dye(name)


# ========= High-level solver =========
def compute_confocal(
    tau_us: float,
    S: float,
    temp_C: float,
    eta_mPa_s: float,
    use_water_eta: bool,
    constraint: str,
    D_um2_s: float,
    rh_nm: float,
    veff_fL: float,
    conc_nM: float,
    num_mols: float,
    invN: float,
    last_edited: str = "conc",
) -> Dict[str, Any]:
    """Solve the linked confocal-FCS quantities for one constraint.

    ``constraint`` is ``"D"`` (fix D → compute Veff, r_h), ``"rh"`` (fix r_h →
    compute D, Veff) or ``"V"`` (fix Veff → compute D, r_h). ``last_edited`` is
    one of ``"conc"`` / ``"N"`` / ``"invN"`` and controls the occupancy coupling.
    Returns the full set of derived values (µm²/s, nm, fL, mPa·s, nM, N, 1/N).
    """
    T_K = float(temp_C) + 273.15
    if use_water_eta:
        eta = water_viscosity_Pa_s(T_K)
        eta_mPa_s = Pa_s_to_mPa_s(eta)
    else:
        eta = mPa_s_to_Pa_s(float(eta_mPa_s))

    tau_s = us_to_s(float(tau_us))
    D_m2_s = um2s_to_m2s(float(D_um2_s))
    rh_m = nm_to_m(float(rh_nm))
    Veff_m3 = fL_to_m3(float(veff_fL))
    S = float(S)

    if constraint == "D":
        if tau_s > 0 and S > 0 and D_m2_s > 0:
            veff_fL = m3_to_fL(veff_from_tau_D_S(tau_s, D_m2_s, S))
        if D_m2_s > 0:
            rh_nm = m_to_nm(stokes_einstein_rh(T_K, eta, D_m2_s))
    elif constraint == "rh":
        if rh_m > 0:
            D_new = stokes_einstein_D(T_K, eta, rh_m)
            D_um2_s = m2s_to_um2s(D_new)
            if tau_s > 0 and S > 0:
                veff_fL = m3_to_fL(veff_from_tau_D_S(tau_s, D_new, S))
    elif constraint == "V":
        if tau_s > 0 and S > 0 and Veff_m3 > 0:
            D_new = D_from_tau_Veff_S(tau_s, Veff_m3, S)
            if math.isfinite(D_new) and D_new > 0:
                D_um2_s = m2s_to_um2s(D_new)
                rh_nm = m_to_nm(stokes_einstein_rh(T_K, eta, D_new))

    # Occupancy coupling (N ↔ concentration) once Veff is known.
    V_fL = float(veff_fL)
    if V_fL > 0:
        if last_edited == "N":
            N = float(num_mols)
            conc_nM = N / (V_fL * N_PER_nM_fL)
            invN = (1.0 / N) if N > 0 else 0.0
        elif last_edited == "invN":
            N = (1.0 / float(invN)) if float(invN) > 0 else 0.0
            num_mols = N
            conc_nM = (N / (V_fL * N_PER_nM_fL)) if V_fL > 0 else 0.0
        else:
            N = float(conc_nM) * V_fL * N_PER_nM_fL
            num_mols = N
            invN = (1.0 / N) if N > 0 else 0.0

    return {
        "D_um2_s": float(D_um2_s),
        "rh_nm": float(rh_nm),
        "veff_fL": float(veff_fL),
        "eta_mPa_s": float(eta_mPa_s),
        "conc_nM": float(conc_nM),
        "num_mols": float(num_mols),
        "invN": float(invN),
    }
