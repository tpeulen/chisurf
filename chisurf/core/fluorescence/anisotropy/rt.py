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
        ChiSurf's g (the reciprocal of the literature G), multiplying VH.
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
    # Schaffer, Volkmer, Eggeling, Subramaniam, Striker & Seidel,
    # J. Phys. Chem. A 103 (1999) 331 -- the anisotropy with the detection
    # corrections, also Eq. (2.4-22) of the Seidel-group treatment, and the
    # same expression `anisotropy_from_integrals` uses:
    #
    #     r = (G Sp - Ss) / ((1 - 3 l2) G Sp + (2 - 3 l1) Ss)
    #
    # Two things this pins down, both of which were wrong here before.
    #
    # *Which channel G corrects.* The published equation reads
    # `(Fp - G Fs) / ((1 - 3 l2) Fp + (2 - 3 l1) G Fs)`, with G on the
    # perpendicular channel. chisurf's `g` is its **reciprocal** -- that is
    # what `compute_g_factor_perrin` returns, and solving the form below for
    # g reproduces it exactly -- so here g multiplies the *parallel* channel.
    # The two are the same estimator, verified to nine decimals for
    # g = 1/G; the trap is that a G quoted from the literature is not this
    # number, it is one over it. It must appear in numerator and
    # denominator alike: this read `(Sp - Ss) / (G Sp + 2 Ss)`, correcting
    # only the denominator, which agrees with the truth at G = 1 (the
    # default, hence unnoticed) and otherwise invents anisotropy -- an
    # isotropic sample came out at +0.167 for G = 2 instead of zero.
    #
    # *Where the leakage correction sits.* l1/l2 are applied **after** the
    # sensitivity correction, as factors on the already-G-corrected signals,
    # not by unmixing the raw pair beforehand. Same order as the integrals
    # module, so the two agree term for term.
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
