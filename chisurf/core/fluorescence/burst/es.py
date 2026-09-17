"""Per-burst FRET efficiency (E) and stoichiometry (S), apparent and corrected.

Turns per-burst photon counts into apparent and fully corrected ``E``/``S`` using
the standard three-cube / ALEX correction.

Channel convention. Generally a channel is ``I_ij`` = photons emitted by
chromophore ``j`` under excitation of chromophore ``i``, with chromophores
numbered in order (donor ``1``, acceptor ``2``, second acceptor ``3``, …) so the
scheme extends to multi-chromophore systems. For the common two-colour
donor/acceptor case the friendly aliases used in this API are

* ``i_dd`` ≡ ``I_11`` — donor emission under donor excitation ("green"),
* ``i_da`` ≡ ``I_12`` — acceptor emission under donor excitation ("red", FRET),
* ``i_aa`` ≡ ``I_22`` — acceptor emission under acceptor excitation ("yellow").

The correction factors follow Hellenkamp 2018: ``alpha`` (α, donor leakage),
``delta`` (δ, direct acceptor excitation), ``gamma`` (γ, detection/quantum-yield
ratio) and ``beta`` (β, excitation-flux ratio; enters the stoichiometry):

    F_dd = i_dd - Bg_dd
    F_aa = i_aa - Bg_aa
    F_da = (i_da - Bg_da) - alpha*F_dd - delta*F_aa
    E = F_da / (F_da + gamma*F_dd)
    S = (gamma*F_dd + F_da) / (gamma*F_dd + F_da + F_aa/beta)

reusing :func:`chisurf.core.fluorescence.crosstalk.correct_three_cube`. Qt-free
and vectorized over bursts.

General case vs. Hellenkamp. The scalar ``alpha``/``beta``/``gamma``/``delta``
factors are the two-colour *reduction* of the general problem, which is stated in
terms of the light-path **excitation** and **emission crosstalk matrices**
(:meth:`...get_crosstalk_matrices`). :func:`corrected_es_general` takes those two
matrices directly and handles any number of chromophores with arbitrary
inter-channel bleed (including acceptor→acceptor leakage the scalar form cannot
express); it reduces exactly to :func:`corrected_es` for the two-colour setup.
"""

from __future__ import annotations

import numpy as np

from chisurf.core.fluorescence.crosstalk import correct_three_cube

__all__ = ["apparent_es", "corrected_es", "corrected_es_matrix", "corrected_es_general"]


def apparent_es(i_dd, i_da, i_aa=None) -> dict:
    """Apparent (uncorrected) proximity ratio ``E`` and raw stoichiometry ``S``.

    Parameters
    ----------
    i_dd, i_da : array_like
        Per-burst donor and acceptor counts under donor excitation
        (``I_11``, ``I_12``).
    i_aa : array_like, optional
        Per-burst acceptor counts under acceptor excitation (``I_22``, ALEX/PIE).
        If omitted, ``S`` is returned as ``None``.

    Returns
    -------
    dict
        ``{"E": proximity_ratio, "S": stoichiometry_or_None}``.
    """
    a = np.asarray(i_dd, dtype=float)
    b = np.asarray(i_da, dtype=float)
    tot = a + b
    with np.errstate(divide="ignore", invalid="ignore"):
        e = np.where(tot != 0, b / tot, 0.0)
    s = None
    if i_aa is not None:
        c = np.asarray(i_aa, dtype=float)
        denom = tot + c
        with np.errstate(divide="ignore", invalid="ignore"):
            s = np.where(denom != 0, tot / denom, 0.0)
    return {"E": e, "S": s}


def corrected_es(
    i_dd,
    i_da,
    i_aa=None,
    *,
    gamma=1.0,
    alpha=0.0,
    beta=1.0,
    delta=0.0,
    bg_dd=0.0,
    bg_da=0.0,
    bg_aa=0.0,
) -> dict:
    """Fully corrected per-burst FRET efficiency ``E`` and stoichiometry ``S``.

    Hellenkamp 2018 correction: ``alpha`` (leakage), ``delta`` (direct
    excitation), ``gamma`` (detection/QY) and ``beta`` (excitation-flux ratio,
    stoichiometry). Channels ``i_dd``/``i_da``/``i_aa`` are the friendly aliases of
    ``I_11``/``I_12``/``I_22`` (see the module docstring).

    Parameters
    ----------
    i_dd, i_da : array_like
        Donor and acceptor counts under donor excitation (``I_11``, ``I_12``).
    i_aa : array_like, optional
        Acceptor counts under acceptor excitation (``I_22``). Required for the
        direct-excitation correction and for ``S``; if omitted it is treated as
        zero (``delta`` then has no effect and ``S`` is ``None``).
    gamma : float, optional
        Detection/quantum-yield ratio (γ).
    alpha : float, optional
        Donor spectral leakage into the acceptor channel (α).
    beta : float, optional
        Excitation-flux ratio (β); scales ``i_aa`` in the stoichiometry.
    delta : float, optional
        Direct acceptor excitation coefficient (δ).
    bg_dd, bg_da, bg_aa : float, optional
        Channel backgrounds for ``i_dd`` / ``i_da`` / ``i_aa``.

    Returns
    -------
    dict
        ``{"E": efficiency, "S": stoichiometry_or_None, "fc": sensitized_emission}``.
    """
    a = np.asarray(i_dd, dtype=float)
    b = np.asarray(i_da, dtype=float)
    f_dd = a - bg_dd
    if i_aa is not None:
        f_aa = np.asarray(i_aa, dtype=float) - bg_aa
    else:
        f_aa = np.zeros_like(f_dd)

    out = correct_three_cube(
        f_dd, b - bg_da, f_aa, donor_leak=alpha, direct_excitation=delta, gamma=gamma
    )
    fc = out["fc"]  # F_da
    e = out["efficiency"]  # F_da / (F_da + gamma*F_dd)

    s = None
    if i_aa is not None:
        num = gamma * f_dd + fc
        denom = num + f_aa / beta
        with np.errstate(divide="ignore", invalid="ignore"):
            s = np.where(denom != 0, num / denom, 0.0)
    return {"E": e, "S": s, "fc": fc}


def corrected_es_matrix(intensity, gamma, alpha, delta=None, background=None, pairs=None) -> dict:
    """Corrected pairwise FRET efficiencies for an N-chromophore system.

    Generalises the two-colour three-cube correction to an N×N intensity matrix
    ``I[i, j]`` = photons of chromophore ``j`` under excitation of chromophore
    ``i`` (chromophores numbered in order: donor 1, acceptor 2, second acceptor
    3, …). For each donor ``i`` the leakage/direct-excitation-corrected
    sensitized emission to each acceptor ``j`` is

        F_ij = (I_ij - Bg_ij) - alpha[i,j]*(I_ii - Bg_ii) - delta[i,j]*(I_jj - Bg_jj)

    and the efficiency uses the **coupled donor budget** — the donor is quenched
    by *all* its acceptors, so

        E_ij = (F_ij / gamma[i,j]) / (F_ii + sum_k F_ik / gamma[i,k])

    which recovers each pairwise E exactly in a multi-acceptor system and reduces
    to :func:`corrected_es` for a single acceptor. (For cross-leakage *between*
    acceptors, spectrally unmix the detection channels first with
    :func:`chisurf.core.fluorescence.crosstalk.invert_mixing`.)

    Parameters
    ----------
    intensity : array_like
        ``(N, N)`` or ``(N, N, M)`` intensity matrix ``I[i, j]`` (``i`` = laser /
        excited chromophore, ``j`` = detection / emitting chromophore); the
        trailing axis is bursts.
    gamma, alpha : array_like
        ``(N, N)`` matrices of pairwise detection factors and donor→acceptor-
        channel leakage.
    delta : array_like, optional
        ``(N, N)`` matrix of direct-excitation coefficients; defaults to zeros.
    background : array_like, optional
        ``(N, N)`` channel backgrounds; defaults to zeros.
    pairs : sequence of tuple, optional
        Donor→acceptor index pairs ``(i, j)`` (0-based) to compute; defaults to
        all ordered pairs ``i < j``.

    Returns
    -------
    dict
        ``{(i, j): {"E": ..., "fc": sensitized_emission}}`` per pair.
    """
    inten = np.asarray(intensity, dtype=float)
    n = inten.shape[0]
    gamma = np.asarray(gamma, dtype=float)
    alpha = np.asarray(alpha, dtype=float)
    delta = np.zeros((n, n)) if delta is None else np.asarray(delta, dtype=float)
    background = np.zeros((n, n)) if background is None else np.asarray(background, dtype=float)
    if pairs is None:
        pairs = [(i, j) for i in range(n) for j in range(i + 1, n)]

    # Group acceptors by donor to share the coupled donor budget.
    donors: dict = {}
    for i, j in pairs:
        donors.setdefault(i, []).append(j)

    out: dict = {}
    for i, acceptors in donors.items():
        f_ii = inten[i, i] - background[i, i]
        fc = {}
        for j in acceptors:
            fc[j] = (
                (inten[i, j] - background[i, j])
                - float(alpha[i, j]) * f_ii
                - float(delta[i, j]) * (inten[j, j] - background[j, j])
            )
        budget = f_ii + sum(fc[j] / float(gamma[i, j]) for j in acceptors)
        for j in acceptors:
            with np.errstate(divide="ignore", invalid="ignore"):
                e = np.where(budget != 0, (fc[j] / float(gamma[i, j])) / budget, 0.0)
            out[(i, j)] = {"E": e, "fc": fc[j]}
    return out


def corrected_es_general(
    intensity, excitation, emission, *, background=None, pairs=None, unmix="naive", ridge=0.0
) -> dict:
    """Corrected pairwise FRET efficiencies from the light-path crosstalk matrices.

    The general form of the correction: instead of the scalar Hellenkamp factors
    (``alpha``/``beta``/``gamma``/``delta``), it consumes the two crosstalk
    matrices the light-path calculator produces —

    * ``excitation[l, k]`` = relative rate at which laser ``l`` directly excites
      chromophore ``k`` (absorption × excitation flux); the diagonal is each
      chromophore's own excitation. Off-diagonals are direct (cross-) excitation.
    * ``emission[k, m]`` = detected brightness of chromophore ``k`` in detection
      channel ``m`` (emission spectrum × filter transmission × detector QE ×
      quantum yield). The diagonal encodes each chromophore's detected brightness;
      off-diagonals are spectral leakage between channels.

    All of leakage, direct excitation and the detection/quantum-yield ratio
    ``gamma`` are carried by these two matrices, so no separate scalar factors are
    needed. The correction is three steps:

    1. **Un-mix emission** — recover each chromophore's true emission under each
       laser, ``e[l, k] = (I[l, :] - Bg) · emission⁻¹``. This removes all spectral
       crosstalk (including acceptor→acceptor) and puts every chromophore on a
       common emission scale (folding in ``gamma`` via the ``emission`` diagonal).
       The inversion is the numerically delicate step: for strong spectral overlap
       ``emission`` is ill-conditioned, so the plain pseudo-inverse (``unmix=
       "naive"``) amplifies shot noise and can yield negative emissions. Choose
       ``unmix="stable"`` (non-negative least squares, sources ≥ 0) and/or a
       ``ridge`` (Tikhonov) penalty for a robust inversion.
    2. **Subtract direct excitation** — the directly-excited part of acceptor
       ``k`` under laser ``l`` is ``(excitation[l, k] / excitation[k, k]) · e[k, k]``,
       giving the FRET-sensitized emission ``F[l, k]``.
    3. **Coupled donor budget** — ``E[l, k] = F[l, k] / (e[l, l] + Σ_a F[l, a])``,
       so a donor quenched by several acceptors yields each exact pairwise ``E``.

    For a two-colour setup this is algebraically identical to
    :func:`corrected_es` (``emission = [[1, α], [0, γ]]``,
    ``excitation = [[1, δ], [0, 1]]``), but it also handles ≥3 chromophores and
    arbitrary inter-channel bleed that the scalar factors cannot express.

    Parameters
    ----------
    intensity : array_like
        ``(L, M)`` or ``(L, M, ...)`` measured intensity ``I[l, m]`` = signal in
        detection channel ``m`` under laser ``l``; the trailing axis is bursts.
    excitation : array_like
        ``(L, N)`` excitation crosstalk matrix ``excitation[l, k]``.
    emission : array_like
        ``(N, M)`` emission/detection crosstalk matrix ``emission[k, m]``. Must be
        invertible in the least-squares sense (``N`` sources ≤ ``M`` channels);
        the pseudo-inverse is used.
    background : array_like, optional
        ``(L, M)`` (broadcastable) per-channel background subtracted from
        ``intensity``; defaults to zeros.
    pairs : sequence of tuple, optional
        Donor→acceptor index pairs ``(l, k)`` (0-based) to compute; defaults to
        all ordered pairs ``l < k``.
    unmix : {"naive", "stable"}, optional
        Emission-unmixing method. ``"naive"`` (default) uses the pseudo-inverse
        (fast, vectorized, but can return negative emissions and is noise-sensitive
        for ill-conditioned ``emission``). ``"stable"`` uses non-negative least
        squares per burst (``crosstalk.invert_mixing(nonneg=True)``) so emissions
        stay ≥ 0 and the solve is robust to strong spectral overlap; slower because
        it loops over bursts. Aliases: ``"pinv"`` → naive; ``"nnls"``/``"nonneg"``
        → stable.
    ridge : float, optional
        Tikhonov regularization strength for the un-mixing (both methods). ``> 0``
        damps noise amplification from an ill-conditioned ``emission`` at the cost
        of a small bias; ``0`` (default) is unregularized.

    Returns
    -------
    dict
        ``{(l, k): {"E": ..., "fc": sensitized_emission}}`` per pair.
    """
    inten = np.asarray(intensity, dtype=float)
    exc = np.asarray(excitation, dtype=float)
    emis = np.asarray(emission, dtype=float)
    if background is not None:
        inten = inten - np.asarray(background, dtype=float)[(...,) + (None,) * (inten.ndim - 2)]

    n_laser, n_det = inten.shape[0], inten.shape[1]
    n_chrom = emis.shape[0]

    # Step 1: un-mix emission. e[l, :] recovers each chromophore's true emission
    # under laser l from the measured channels, solving  I[l, :] = e[l, :] @ emis.
    method = str(unmix).lower()
    if method in ("naive", "pinv", "linear"):
        if ridge and ridge > 0:
            # Tikhonov unmix matrix R = (emis·emisᵀ + λI)⁻¹·emis, applied as Rᵀ.
            gram = emis @ emis.T + float(ridge) * np.eye(n_chrom)
            unmix_mat = np.linalg.solve(gram, emis).T  # (M_det, N_chrom)
        else:
            unmix_mat = np.linalg.pinv(emis)  # (M_det, N_chrom)
        flat = inten.reshape(n_laser, n_det, -1)  # (L, M, B)
        e_emit = np.einsum("lmb,mk->lkb", flat, unmix_mat)  # (L, N_chrom, B)
        e_emit = e_emit.reshape((n_laser, n_chrom) + inten.shape[2:])
    elif method in ("stable", "nnls", "nonneg"):
        from chisurf.core.fluorescence.crosstalk import invert_mixing

        rows = [
            invert_mixing(emis, inten[i], nonneg=True, ridge=float(ridge)) for i in range(n_laser)
        ]
        e_emit = np.stack(rows, axis=0)  # (L, N_chrom, ...)
    else:
        raise ValueError(f"unmix must be 'naive' or 'stable' (got {unmix!r})")

    if pairs is None:
        pairs = [(i, j) for i in range(n_laser) for j in range(i + 1, n_chrom)]
    donors: dict = {}
    for i, j in pairs:
        donors.setdefault(i, []).append(j)

    out: dict = {}
    for i, acceptors in donors.items():
        e_donor = e_emit[i, i]
        fc = {}
        for j in acceptors:
            # Step 2: subtract the directly-excited acceptor emission.
            x_rel = float(exc[i, j]) / float(exc[j, j]) if exc[j, j] != 0 else 0.0
            fc[j] = e_emit[i, j] - x_rel * e_emit[j, j]
        # Step 3: coupled donor budget (emission already on a common scale).
        budget = e_donor + sum(fc[j] for j in acceptors)
        for j in acceptors:
            with np.errstate(divide="ignore", invalid="ignore"):
                e = np.where(budget != 0, fc[j] / budget, 0.0)
            out[(i, j)] = {"E": e, "fc": fc[j]}
    return out
