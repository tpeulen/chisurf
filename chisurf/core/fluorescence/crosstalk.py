"""General spectral crosstalk / linear-mixing utilities — the numpy adapter.

Crosstalk (spectral bleed-through, direct acceptor excitation, detector
mixing) is a single linear-algebra problem shared across ChiSurf: the light-path
calculator *builds* a forward mixing matrix
(:meth:`...lightpath_simulator...get_crosstalk_matrices`), ratiometric /
sensitized-emission FRET needs to *invert* it to recover true fluorophore
signals, and phasor-FLIM spectral unmixing solves the same constrained inverse.

**The definition and the algebra live in bff** (``IMP.bff.PhotophysicsCrosstalkMatrix`` and
the ``crosstalk_*`` kernels, from ``IMP/bff/CrosstalkMatrix.h``) — owner,
2026-09-04: the excitation and emission crosstalk matrix definition must be in
bff, not in chisurf, per the compute/display line. This module is the Qt-free
numpy *adapter* those consumers share: it converts payloads and ``(n, ...)``
arrays across the boundary and reshapes the results; it owns no arithmetic.
The scalar three-cube correction (:func:`correct_three_cube`) is tttrlib's
(``SpectralCrosstalk``, A/B-validated there against the Hellenkamp 2018
formulas and FRETBursts); this module forwards to it — the duplication
register's "one implementation per algorithm", PRD-105 phase 4.

Conventions
-----------
A mixing matrix ``M`` has shape ``(n_sources, n_detectors)`` with
``M[i, j]`` = contribution of source ``i`` to detector ``j``. The forward model
is ``measured_j = sum_i source_i * M[i, j]`` (i.e. ``measured = Mᵀ @ sources``),
and the inverse recovers the sources from the measured detector signals.
Rows are *labelled* — sources for the excitation matrix (lasers), chromophores
for the emission matrix — and columns likewise; labels are how a payload built
against one instrument description is ordered for another consumer.
"""

from __future__ import annotations

import numpy as np

# The parameter runtime made the same turn: the guard is import-time, the
# error is call-time, so a chisurf that never fits still imports.
try:
    import IMP.bff as _bff

    if not hasattr(_bff, 'PhotophysicsCrosstalkMatrix'):
        raise ImportError("IMP.bff is present but carries no CrosstalkMatrix")
except ImportError as _exc:
    _bff = None
    _bff_import_error = _exc

try:
    import tttrlib as _tttrlib

    if not hasattr(_tttrlib, "correct_three_cube_batch"):
        raise ImportError("tttrlib is present but carries no SpectralCrosstalk")
except ImportError as _exc:
    _tttrlib = None
    _tttrlib_import_error = _exc

__all__ = [
    "matrix_from_payload",
    "apply_mixing",
    "invert_mixing",
    "photon_shuffle_unmix",
    "correct_three_cube",
    "three_cube_fret_efficiency",
]


def _require_bff():
    if _bff is None:
        raise ImportError(
            "chisurf.core.fluorescence.crosstalk requires IMP.bff, the "
            "library that owns the crosstalk-matrix definition; importing "
            f"it failed: {_bff_import_error}"
        )


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
        Requested labels missing from the payload contribute a zero row/column
        (a missing element of a light path is a dark element, not a broken one).

    Returns
    -------
    matrix : numpy.ndarray
        ``(len(rows), len(columns))`` mixing matrix.
    rows : list of str
        The row (source) labels, in the returned order.
    columns : list of str
        The column (detector) labels, in the returned order.
    """
    _require_bff()
    payload_rows = list(payload["rows"])
    payload_cols = list(payload["columns"])
    values = np.asarray(payload["values"], dtype=float)
    if values.size != len(payload_rows) * len(payload_cols):
        raise ValueError(
            f"payload values {values.shape} do not tile "
            f"{len(payload_rows)} x {len(payload_cols)}"
        )
    labelled = _bff.PhotophysicsCrosstalkMatrix(
        payload_rows, payload_cols, [float(v) for v in values.ravel()]
    )
    out_rows = list(rows) if rows is not None else payload_rows
    out_cols = list(columns) if columns is not None else payload_cols
    selected = labelled.select(out_rows, out_cols)
    matrix = np.asarray(selected.get_values(), dtype=float).reshape(
        (selected.get_n_rows(), selected.get_n_columns())
    )
    return matrix, list(selected.get_rows()), list(selected.get_columns())


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
    _require_bff()
    m = np.ascontiguousarray(matrix, dtype=float)
    s = np.ascontiguousarray(sources, dtype=float)
    n_src, n_det = m.shape
    out = _bff.crosstalk_apply_mixing(m, n_src, n_det, s)
    return np.asarray(out).reshape((n_det,) + s.shape[1:])


def invert_mixing(matrix, measured, *, nonneg: bool = False, ridge: float = 0.0):
    """Inverse mixing: recover source signals from measured detector signals.

    Parameters
    ----------
    matrix : array_like
        ``(n_sources, n_detectors)`` mixing matrix.
    measured : array_like
        ``(n_detectors,)`` or ``(n_detectors, ...)`` measured signals.
    nonneg : bool, optional
        If True, solve a non-negative least squares per column (Lawson–Hanson,
        in bff) — the physically-constrained unmixing (sources cannot be
        negative) that stays stable when the mixing matrix is ill-conditioned
        (strong spectral overlap). Otherwise a minimum-norm least-squares
        solution, which is faster but can return negative sources and
        amplifies noise for near-singular ``matrix``.
    ridge : float, optional
        Tikhonov (ridge) regularization strength ``λ``. When ``> 0`` the solve
        minimises ``||Mᵀx − y||² + λ||x||²``, which damps the noise amplification
        of an ill-conditioned ``matrix`` at the cost of a small bias. Applies to
        both the unconstrained solve (closed form) and the non-negative solve
        (via an augmented system). ``0`` (default) is the plain least-squares
        inverse. (The former ``rcond`` cut-off of the pseudo-inverse is gone
        with the numpy implementation; bff's complete-orthogonal-decomposition
        threshold takes its place.)

    Returns
    -------
    numpy.ndarray
        ``(n_sources, ...)`` recovered source signals.
    """
    _require_bff()
    m = np.ascontiguousarray(matrix, dtype=float)
    y = np.ascontiguousarray(measured, dtype=float)
    n_src, n_det = m.shape
    out = _bff.crosstalk_invert_mixing(m, n_src, n_det, y, bool(nonneg),
                                       float(ridge))
    return np.asarray(out).reshape((n_src,) + y.shape[1:])


def photon_shuffle_unmix(counts, matrix, *, abundances=None, seed=None, rng=None):
    """Integer, statistics-preserving spectral unmixing by photon reassignment.

    The least-squares inverses (:func:`invert_mixing`) return *fractional* — and,
    unconstrained, negative — source estimates, which destroys the integer /
    Poisson nature of photon-counting data. This instead **reassigns each detected
    photon to a source**: every one of the ``counts[m]`` photons in detector ``m``
    is attributed to exactly one source ``k`` by a multinomial draw, so the result
    is a non-negative **integer** per-source photon stream. The draw lives in bff
    (``crosstalk_shuffle_unmix``); the expected assignment equals the soft
    (Richardson–Lucy / EM) unmixing, so the method is unbiased on average, and a
    multinomial thinning of a Poisson count is Poisson, so the shot-noise
    statistics downstream analyses see are genuine.

    Parameters
    ----------
    counts : array_like
        ``(n_detectors,)`` or ``(n_detectors, ...)`` **integer** photon counts per
        detector (trailing axes are pixels/bursts).
    matrix : array_like
        ``(n_sources, n_detectors)`` mixing matrix (as elsewhere in this module).
    abundances : array_like, optional
        ``(n_sources, ...)`` source abundances used as the assignment prior. If
        omitted, they are estimated by the non-negative inverse inside bff.
    seed : int, optional
        Seed for bff's generator when ``rng`` is not given; identical seeds give
        identical shuffles.
    rng : numpy.random.Generator, optional
        Explicit random generator (takes precedence over ``seed``); its next
        draw seeds bff's generator, since the draw itself is C++.

    Returns
    -------
    numpy.ndarray
        ``(n_sources, ...)`` non-negative integer per-source photon counts, with
        the same trailing shape as ``counts`` and ``sum_k out[k] == sum_m counts[m]``
        elementwise.
    """
    _require_bff()
    m = np.ascontiguousarray(matrix, dtype=float)
    y = np.ascontiguousarray(counts)
    n_src, n_det = m.shape
    if rng is not None:
        seed = int(rng.integers(0, 2**63 - 1))
    flat_abundances = None
    if abundances is not None:
        a = np.ascontiguousarray(abundances, dtype=float)
        if a.shape != (n_src,) + y.shape[1:]:
            raise ValueError(
                f"abundances {a.shape} do not match (n_sources,) + counts shape "
                f"{(n_src,) + y.shape[1:]}"
            )
        flat_abundances = a
    out = _bff.crosstalk_shuffle_unmix(m, n_src, n_det, y, flat_abundances,
                                       0 if seed is None else int(seed))
    # the kernel publishes a double view; the draw is integral by
    # construction, and the contract here is an integer photon stream
    return np.rint(np.asarray(out)).astype(np.int64).reshape(
        (n_src,) + y.shape[1:])


def correct_three_cube(idd, ida, iaa, *, donor_leak: float, direct_excitation: float,
                       gamma: float = 1.0):
    """Three-cube ratiometric FRET correction (Gordon/Nagy/Lee).

    Forwarded to tttrlib's ``SpectralCrosstalk`` — the engine owner of the
    scalar correction, A/B-validated there against the Hellenkamp 2018
    formulas (1e-12) and FRETBursts ``fretmath`` (1e-10). The correction is

    ``Fc = IDA - donor_leak * IDD - direct_excitation * IAA``

    with the apparent efficiency ``Fc / (Fc + gamma * IDD)``. One guard
    convention is adopted with the engine, stated plainly: where the
    denominator ``Fc + gamma * IDD <= 0`` — over-subtraction, a pathological
    channel — the efficiency is **0**, where this module's numpy twin divided
    anyway and returned a *positive* value for a negative signal (a
    negative-over-negative quotient). A negative efficiency with a positive
    denominator is preserved, as before. ``ratio`` is a plain division and
    keeps its own convention (0 where ``IDD`` is 0). Backgrounds stay the
    caller's business, as before (:func:`...burst.es.corrected_es` subtracts
    them first); tttrlib's own background parameters are passed as zero.

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
        sensitized emission ``Fc``, the apparent FRET efficiency and the
        acceptor/donor ratio ``Fc / IDD``. Each carries the broadcast shape
        of the inputs.
    """
    if _tttrlib is None:
        raise ImportError(
            "chisurf.core.fluorescence.crosstalk requires tttrlib, the "
            "photon library that owns the three-cube correction; importing "
            f"it failed: {_tttrlib_import_error}"
        )
    idd_a = np.asarray(idd, dtype=float)
    ida_a = np.asarray(ida, dtype=float)
    iaa_a = np.asarray(iaa, dtype=float)
    # the engine takes three equal-length vectors; numpy's broadcasting is
    # part of this function's contract, so expand before flattening
    idd_b, ida_b, iaa_b = np.broadcast_arrays(idd_a, ida_a, iaa_a)
    flat = [np.ascontiguousarray(x).ravel() for x in (idd_b, ida_b, iaa_b)]
    shape = idd_b.shape
    out = _tttrlib.correct_three_cube_batch(
        flat[0], flat[1], flat[2],
        float(gamma), float(donor_leak), float(direct_excitation),
    )
    # flat [E, S, Fc] per element
    fc = np.asarray(out[2::3]).reshape(shape)
    efficiency = np.asarray(out[0::3]).reshape(shape)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(idd_a != 0, fc / idd_a, 0.0)
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
