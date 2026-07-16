"""Per-burst FRET efficiency (E) and stoichiometry (S), apparent and corrected.

Turns per-burst photon counts in the donor-under-donor-excitation (green),
acceptor-under-donor-excitation (red) and acceptor-under-acceptor-excitation
(yellow, ALEX/PIE) channels into apparent and fully corrected ``E``/``S``.

The correction is the standard three-cube scheme (Lee 2005; Hellenkamp 2018),
reusing :func:`chisurf.core.fluorescence.crosstalk.correct_three_cube`:

    F_DD = green - Bg
    F_AA = yellow - By
    F_DA = red - Br - alpha*F_DD - delta*F_AA          (donor leakage + direct exc.)
    E = F_DA / (F_DA + gamma*F_DD)
    S = (gamma*F_DD + F_DA) / (gamma*F_DD + F_DA + F_AA)

The module is Qt-free and vectorized over bursts.
"""

from __future__ import annotations

import numpy as np

from chisurf.core.fluorescence.crosstalk import correct_three_cube

__all__ = ["apparent_es", "corrected_es"]


def apparent_es(green, red, yellow=None) -> dict:
    """Apparent (uncorrected) proximity ratio ``E`` and raw stoichiometry ``S``.

    Parameters
    ----------
    green, red : array_like
        Per-burst donor and acceptor counts under donor excitation.
    yellow : array_like, optional
        Per-burst acceptor counts under acceptor excitation (ALEX/PIE). If
        omitted, ``S`` is returned as ``None``.

    Returns
    -------
    dict
        ``{"E": proximity_ratio, "S": stoichiometry_or_None}``.
    """
    g = np.asarray(green, dtype=float)
    r = np.asarray(red, dtype=float)
    gr = g + r
    with np.errstate(divide="ignore", invalid="ignore"):
        e = np.where(gr != 0, r / gr, 0.0)
    s = None
    if yellow is not None:
        y = np.asarray(yellow, dtype=float)
        denom = gr + y
        with np.errstate(divide="ignore", invalid="ignore"):
            s = np.where(denom != 0, gr / denom, 0.0)
    return {"E": e, "S": s}


def corrected_es(green, red, yellow=None, *, gamma=1.0, alpha=0.0, delta=0.0,
                 bg=0.0, br=0.0, by=0.0) -> dict:
    """Fully corrected per-burst FRET efficiency ``E`` and stoichiometry ``S``.

    Parameters
    ----------
    green, red : array_like
        Donor and acceptor counts under donor excitation.
    yellow : array_like, optional
        Acceptor counts under acceptor excitation (ALEX/PIE). Required for the
        direct-excitation correction and for ``S``; if omitted it is treated as
        zero (``delta`` then has no effect and ``S`` is ``None``).
    gamma : float, optional
        Detection/quantum-yield ratio.
    alpha : float, optional
        Donor spectral leakage into the acceptor channel.
    delta : float, optional
        Direct acceptor excitation coefficient.
    bg, br, by : float, optional
        Green / red / yellow channel backgrounds.

    Returns
    -------
    dict
        ``{"E": efficiency, "S": stoichiometry_or_None, "fc": sensitized_emission}``.
    """
    g = np.asarray(green, dtype=float)
    r = np.asarray(red, dtype=float)
    f_dd = g - bg
    if yellow is not None:
        f_aa = np.asarray(yellow, dtype=float) - by
    else:
        f_aa = np.zeros_like(f_dd)

    out = correct_three_cube(
        f_dd, r - br, f_aa, donor_leak=alpha, direct_excitation=delta, gamma=gamma
    )
    fc = out["fc"]  # F_DA
    e = out["efficiency"]  # F_DA / (F_DA + gamma*F_DD)

    s = None
    if yellow is not None:
        num = gamma * f_dd + fc
        denom = num + f_aa
        with np.errstate(divide="ignore", invalid="ignore"):
            s = np.where(denom != 0, num / denom, 0.0)
    return {"E": e, "S": s, "fc": fc}
