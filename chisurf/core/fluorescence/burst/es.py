"""Per-burst FRET efficiency (E) and stoichiometry (S), apparent and corrected.

Turns per-burst photon counts into apparent and fully corrected ``E``/``S`` using
the standard three-cube / ALEX correction with the **Hellenkamp 2018**
nomenclature. The three signal channels are

* ``I_DD`` — donor emission under donor excitation ("green"),
* ``I_DA`` — acceptor emission under donor excitation ("red", the FRET channel),
* ``I_AA`` — acceptor emission under acceptor excitation ("yellow", ALEX/PIE).

The correction factors are Hellenkamp's ``alpha`` (α, donor leakage), ``delta``
(δ, direct acceptor excitation), ``gamma`` (γ, detection/quantum-yield ratio) and
``beta`` (β, excitation-flux ratio; enters the stoichiometry):

    F_DD = I_DD - Bg_DD
    F_AA = I_AA - Bg_AA
    F_DA = (I_DA - Bg_DA) - alpha*F_DD - delta*F_AA
    E = F_DA / (F_DA + gamma*F_DD)
    S = (gamma*F_DD + F_DA) / (gamma*F_DD + F_DA + F_AA/beta)

reusing :func:`chisurf.core.fluorescence.crosstalk.correct_three_cube`. Qt-free
and vectorized over bursts.
"""

from __future__ import annotations

import numpy as np

from chisurf.core.fluorescence.crosstalk import correct_three_cube

__all__ = ["apparent_es", "corrected_es"]


def apparent_es(i_dd, i_da, i_aa=None) -> dict:
    """Apparent (uncorrected) proximity ratio ``E`` and raw stoichiometry ``S``.

    Parameters
    ----------
    i_dd, i_da : array_like
        Per-burst donor and acceptor counts under donor excitation
        (``I_DD``, ``I_DA``).
    i_aa : array_like, optional
        Per-burst acceptor counts under acceptor excitation (``I_AA``, ALEX/PIE).
        If omitted, ``S`` is returned as ``None``.

    Returns
    -------
    dict
        ``{"E": proximity_ratio, "S": stoichiometry_or_None}``.
    """
    dd = np.asarray(i_dd, dtype=float)
    da = np.asarray(i_da, dtype=float)
    tot = dd + da
    with np.errstate(divide="ignore", invalid="ignore"):
        e = np.where(tot != 0, da / tot, 0.0)
    s = None
    if i_aa is not None:
        aa = np.asarray(i_aa, dtype=float)
        denom = tot + aa
        with np.errstate(divide="ignore", invalid="ignore"):
            s = np.where(denom != 0, tot / denom, 0.0)
    return {"E": e, "S": s}


def corrected_es(i_dd, i_da, i_aa=None, *, gamma=1.0, alpha=0.0, beta=1.0, delta=0.0,
                 bg_dd=0.0, bg_da=0.0, bg_aa=0.0) -> dict:
    """Fully corrected per-burst FRET efficiency ``E`` and stoichiometry ``S``.

    Hellenkamp 2018 correction: ``alpha`` (leakage), ``delta`` (direct
    excitation), ``gamma`` (detection/QY) and ``beta`` (excitation-flux ratio,
    stoichiometry).

    Parameters
    ----------
    i_dd, i_da : array_like
        Donor and acceptor counts under donor excitation (``I_DD``, ``I_DA``).
    i_aa : array_like, optional
        Acceptor counts under acceptor excitation (``I_AA``). Required for the
        direct-excitation correction and for ``S``; if omitted it is treated as
        zero (``delta`` then has no effect and ``S`` is ``None``).
    gamma : float, optional
        Detection/quantum-yield ratio (γ).
    alpha : float, optional
        Donor spectral leakage into the acceptor channel (α).
    beta : float, optional
        Excitation-flux ratio (β); scales ``I_AA`` in the stoichiometry.
    delta : float, optional
        Direct acceptor excitation coefficient (δ).
    bg_dd, bg_da, bg_aa : float, optional
        Channel backgrounds for ``I_DD`` / ``I_DA`` / ``I_AA``.

    Returns
    -------
    dict
        ``{"E": efficiency, "S": stoichiometry_or_None, "fc": sensitized_emission}``.
    """
    dd = np.asarray(i_dd, dtype=float)
    da = np.asarray(i_da, dtype=float)
    f_dd = dd - bg_dd
    if i_aa is not None:
        f_aa = np.asarray(i_aa, dtype=float) - bg_aa
    else:
        f_aa = np.zeros_like(f_dd)

    out = correct_three_cube(
        f_dd, da - bg_da, f_aa, donor_leak=alpha, direct_excitation=delta, gamma=gamma
    )
    fc = out["fc"]  # F_DA
    e = out["efficiency"]  # F_DA / (F_DA + gamma*F_DD)

    s = None
    if i_aa is not None:
        num = gamma * f_dd + fc
        denom = num + f_aa / beta
        with np.errstate(divide="ignore", invalid="ignore"):
            s = np.where(denom != 0, num / denom, 0.0)
    return {"E": e, "S": s, "fc": fc}
