"""General spectral crosstalk / linear-mixing utilities.

Crosstalk (spectral bleed-through, direct acceptor excitation, detector
mixing) is a single linear-algebra problem shared across ChiSurf: the light-path
calculator *builds* a forward mixing matrix
(:meth:`...lightpath_simulator...get_crosstalk_matrices`), ratiometric /
sensitized-emission FRET needs to *invert* it to recover true fluorophore
signals, and phasor-FLIM spectral unmixing solves the same constrained inverse.
This module is the Qt-free, array-based core those consumers share.

Conventions
-----------
A mixing matrix ``M`` has shape ``(n_sources, n_detectors)`` with
``M[i, j]`` = contribution of source ``i`` to detector ``j``. The forward model
is ``measured_j = sum_i source_i * M[i, j]`` (i.e. ``measured = Mᵀ @ sources``),
and the inverse recovers the sources from the measured detector signals.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "matrix_from_payload",
    "apply_mixing",
    "invert_mixing",
    "correct_three_cube",
    "three_cube_fret_efficiency",
]


def matrix_from_payload(payload, rows=None, columns=None):
    """Build an ordered NumPy mixing matrix from a light-path crosstalk payload.

    Parameters
    ----------
    payload : dict
        A matrix payload as returned by ``get_crosstalk_matrices()`` — a mapping
        with ``"rows"`` (source labels), ``"columns"`` (detector labels) and a
        dense row-major ``"values"`` list (``values[row][col]``).
    rows, columns : sequence of str, optional
        Label subset/ordering to select. Defaults to the payload's own order.
        Requested labels missing from the payload contribute a zero row/column.

    Returns
    -------
    matrix : numpy.ndarray
        ``(len(rows), len(columns))`` mixing matrix.
    rows : list of str
        The row (source) labels, in the returned order.
    columns : list of str
        The column (detector) labels, in the returned order.
    """
    payload_rows = list(payload["rows"])
    payload_cols = list(payload["columns"])
    values = np.asarray(payload["values"], dtype=float)
    row_index = {label: i for i, label in enumerate(payload_rows)}
    col_index = {label: j for j, label in enumerate(payload_cols)}

    out_rows = list(rows) if rows is not None else payload_rows
    out_cols = list(columns) if columns is not None else payload_cols
    matrix = np.zeros((len(out_rows), len(out_cols)), dtype=float)
    for i, r in enumerate(out_rows):
        if r not in row_index:
            continue
        for j, c in enumerate(out_cols):
            if c in col_index:
                matrix[i, j] = values[row_index[r], col_index[c]]
    return matrix, out_rows, out_cols


def apply_mixing(matrix, sources):
    """Forward mixing: predict detector signals from source signals.

    Parameters
    ----------
    matrix : array_like
        ``(n_sources, n_detectors)`` mixing matrix.
    sources : array_like
        ``(n_sources,)`` or ``(n_sources, ...)`` source signals (per pixel/burst
        along trailing axes).

    Returns
    -------
    numpy.ndarray
        ``(n_detectors, ...)`` predicted detector signals.
    """
    m = np.asarray(matrix, dtype=float)
    s = np.asarray(sources, dtype=float)
    flat = s.reshape(s.shape[0], -1)
    out = m.T @ flat
    return out.reshape((m.shape[1],) + s.shape[1:])


def invert_mixing(matrix, measured, *, nonneg: bool = False, rcond=None):
    """Inverse mixing: recover source signals from measured detector signals.

    Parameters
    ----------
    matrix : array_like
        ``(n_sources, n_detectors)`` mixing matrix.
    measured : array_like
        ``(n_detectors,)`` or ``(n_detectors, ...)`` measured signals.
    nonneg : bool, optional
        If True, solve a non-negative least squares per column
        (``scipy.optimize.nnls``) — the physically-constrained unmixing used in
        the phasor path. Otherwise a (pseudo-)inverse least-squares solution.
    rcond : float, optional
        Cut-off passed to :func:`numpy.linalg.pinv` for the unconstrained solve.

    Returns
    -------
    numpy.ndarray
        ``(n_sources, ...)`` recovered source signals.
    """
    m = np.asarray(matrix, dtype=float)
    y = np.asarray(measured, dtype=float)
    a = m.T  # detectors x sources
    if nonneg:
        from scipy.optimize import nnls

        flat = y.reshape(y.shape[0], -1)
        out = np.empty((a.shape[1], flat.shape[1]), dtype=float)
        for k in range(flat.shape[1]):
            out[:, k], _ = nnls(a, flat[:, k])
        return out.reshape((a.shape[1],) + y.shape[1:])
    pinv = np.linalg.pinv(a, rcond=rcond) if rcond is not None else np.linalg.pinv(a)
    flat = y.reshape(y.shape[0], -1)
    out = pinv @ flat
    return out.reshape((pinv.shape[0],) + y.shape[1:])


def correct_three_cube(idd, ida, iaa, *, donor_leak: float, direct_excitation: float,
                       gamma: float = 1.0):
    """Three-cube ratiometric FRET correction (Gordon/Nagy).

    Corrects the measured raw FRET (acceptor-under-donor-excitation) channel for
    donor spectral bleed-through and direct acceptor excitation, using the
    donor-only (IDD) and acceptor-only (IAA) reference channels:

    ``Fc = IDA - donor_leak * IDD - direct_excitation * IAA``.

    Parameters
    ----------
    idd : array_like
        Donor emission under donor excitation (scalar or per-pixel/burst array).
    ida : array_like
        Raw FRET channel: acceptor emission under donor excitation.
    iaa : array_like
        Acceptor emission under acceptor excitation.
    donor_leak : float
        Donor bleed-through coefficient (``d``, donor signal fraction leaking
        into the FRET channel), calibrated from a donor-only sample.
    direct_excitation : float
        Direct acceptor-excitation coefficient (``a``), calibrated from an
        acceptor-only sample.
    gamma : float, optional
        Detection/quantum-yield correction factor (used by the efficiency).

    Returns
    -------
    dict
        ``{"fc": ..., "efficiency": ..., "ratio": ...}`` — the corrected
        sensitized emission ``Fc``, the apparent FRET efficiency
        ``Fc / (Fc + gamma * IDD)`` and the acceptor/donor ratio ``Fc / IDD``.
    """
    idd = np.asarray(idd, dtype=float)
    ida = np.asarray(ida, dtype=float)
    iaa = np.asarray(iaa, dtype=float)
    fc = ida - donor_leak * idd - direct_excitation * iaa
    efficiency = three_cube_fret_efficiency(fc, idd, gamma=gamma)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(idd != 0, fc / idd, 0.0)
    return {"fc": fc, "efficiency": efficiency, "ratio": ratio}


def three_cube_fret_efficiency(fc, idd, *, gamma: float = 1.0):
    """Apparent FRET efficiency ``Fc / (Fc + gamma * IDD)`` from corrected signals.

    Parameters
    ----------
    fc : array_like
        Corrected sensitized emission.
    idd : array_like
        Donor emission under donor excitation.
    gamma : float, optional
        Detection/quantum-yield correction factor.

    Returns
    -------
    numpy.ndarray
        Apparent FRET efficiency; zero where the denominator vanishes.
    """
    fc = np.asarray(fc, dtype=float)
    idd = np.asarray(idd, dtype=float)
    denom = fc + gamma * idd
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(denom != 0, fc / denom, 0.0)
