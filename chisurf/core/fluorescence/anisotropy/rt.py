"""Time-resolved anisotropy r(t) from a parallel and a perpendicular decay."""

from __future__ import annotations

import numpy as np

__all__ = ["rt_curves"]


def rt_curves(t, vv, vh, g: float = 1.0, l1: float = 0.0, l2: float = 0.0):
    """Uncorrected and corrected anisotropy from a VV/VH pair.

    Parameters
    ----------
    t : array_like
        Time axis.
    vv, vh : array_like
        Parallel and perpendicular decays, background already subtracted.
    g : float
        Detection sensitivity factor multiplying the perpendicular VH decay.
    l1, l2 : float
        Objective-aperture mixing corrections.

    Returns
    -------
    tuple
        ``(t, r_uncorrected, r_corrected)`` over the channels where both are finite.
    """
    t = np.asarray(t, dtype=float)
    vv = np.asarray(vv, dtype=float)
    vh = np.asarray(vh, dtype=float)
    # G multiplies VH in both numerator and denominator; see Ströhl et al.,
    # DOI 10.1088/2050-6120/aa872e, Eq. 1. Aperture factors l1/l2 are
    # applied to those corrected signals and require separate calibration.
    gs = g * vh
    den_unc = vv + 2.0 * gs
    with np.errstate(divide="ignore", invalid="ignore"):
        r_unc = np.where(np.abs(den_unc) > 1e-12, (vv - gs) / den_unc, np.nan)
    den_cor = (1.0 - 3.0 * l2) * vv + (2.0 - 3.0 * l1) * gs
    with np.errstate(divide="ignore", invalid="ignore"):
        r_cor = np.where(np.abs(den_cor) > 1e-12, (vv - gs) / den_cor, np.nan)
    finite = np.isfinite(t) & np.isfinite(r_unc) & np.isfinite(r_cor)
    if np.any(finite):
        return t[finite], r_unc[finite], r_cor[finite]
    return t, r_unc, r_cor
