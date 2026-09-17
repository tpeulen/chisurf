"""High-level, Qt-free API for 2D fluorescence lifetime correlation (2D-FLC).

Method: K. Ishii and T. Tahara, "Two-Dimensional Fluorescence Lifetime
Correlation Spectroscopy. 1. Principle" and ". 2. Application", J. Phys.
Chem. B 117(39), 11414-11422 and 11423-11432 (2013), doi:10.1021/jp406861u
and doi:10.1021/jp406864e. The photon-pair pass follows the original
implementation ``TK_Create2DFDC_04.m`` by Toru Kondo (Schlau-Cohen lab, MIT),
see T. Kondo et al., Proc. Natl. Acad. Sci. USA 116(23), 11247-11252 (2019),
doi:10.1073/pnas.1821207116.

The pipeline has two halves:

* **Lifetime resolution** -- resolve the fluorescence-lifetime species from a decay
  histogram (:func:`lifetime_spectrum`) or from a 2D fluorescence-decay correlation
  matrix built from TTTR photon pairs (:func:`two_d_fdc` + :func:`two_d_spectrum`).
* **Dynamics** -- read out the interconversion of those species as a lifetime-filtered
  (species-resolved) correlation and fit its relaxation time
  (:func:`species_correlation`).

Everything operates on plain NumPy arrays so it is usable from scripts, notebooks, the
RPC backend and the GUI alike. ``tttrlib`` and ``scipy`` are imported lazily.

Example:
-------
>>> data = load_tttr("measurement.ptu")                      # doctest: +SKIP
>>> spec = lifetime_spectrum(data.micro_times,               # doctest: +SKIP
...                          n_microtime_bins=data.n_microtime_channels,
...                          micro_time_resolution_ns=data.micro_time_resolution_ns)
>>> spec.peak_lifetimes(2)                                   # doctest: +SKIP
array([1.0, 3.0])
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .core import TwoDFDCreator
from .fit.dynamics import (
    SpeciesCorrelation,
    filtered_correlation,
    fit_relaxation,
    species_filters,
)
from .fit.gaussian import GaussianFitResult, fit_gaussian_multi
from .fit.global_mem import GlobalMEMResult, solve_global_mem_2d
from .fit.helpers import RiseIRFResult, create_1d_fdc, histogram_1d, search_rise_irf
from .fit.ilt import (
    ILTResult1D,
    ILTResult2D,
    build_exp_basis,
    ilt_1d,
    ilt_2d,
    lcurve_1d,
    lifetime_grid,
)
from .fit.kinetics import RateMatrixResult, fit_rate_matrix
from .fit.mem_1d import OneDMEMResult, solve_mem_1d
from .fit.reproduct import Reproduction, reproduce_1d, reproduce_2d, reproduce_global_2d

__all__ = [
    "TttrData",
    "load_tttr",
    "lifetime_spectrum",
    "lifetime_spectrum_mem",
    "species_decay_patterns",
    "two_d_fdc",
    "two_d_fdc_scan",
    "one_d_fdc",
    "two_d_spectrum",
    "species_correlation",
    "rate_matrix_kinetics",
    "global_lifetime_mem",
    "correlate_tttr",
    "fit_tikhonov_2d",
    "fit_mem_2d",
    "fit_gaussian_components",
    "search_irf_rise",
    "simulate_stream",
    "histogram_1d",
    "make_synthetic_irf",
    "detect_irf",
    "lifetime_lcurve",
    "reproduce_1d_fdc",
    "reproduce_2d_fdc",
    "reproduce_fit",
    "separate_data_2d_fdc",
    "bootstrap_2d_fdc",
    "exp_curves",
    "fit_2d_mem_workflow",
    "search_irf_rise_2d",
    "average_2d_mem",
]


# --------------------------------------------------------------------------- loading


@dataclass
class TttrData:
    """A loaded TTTR photon stream and the calibration needed to analyse it."""

    macro_times: np.ndarray  # clock ticks, ascending
    micro_times: np.ndarray  # TCSPC channel indices
    routing_channels: np.ndarray  # detector/routing channel per photon
    macro_time_resolution_s: float  # seconds per macro tick
    micro_time_resolution_ns: float  # ns per micro channel
    n_microtime_channels: int

    @property
    def n_photons(self) -> int:
        """Number of photons in the stream."""
        return int(self.macro_times.shape[0])


def load_tttr(file_path: str | Path, routing_channels: Sequence[int] | None = None) -> TttrData:
    """Load a TTTR file with ``tttrlib`` (format auto-detected).

    Parameters
    ----------
    file_path
        Path to a PTU/HT3/PT3/SPC/HDF5/... file.
    routing_channels
        Optional subset of detector channels to keep (default: all).
    """
    import tttrlib

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"TTTR file not found: {path}")
    tttr = tttrlib.TTTR(str(path))
    header = tttr.get_header()

    macro = np.asarray(tttr.macro_times)
    micro = np.asarray(tttr.micro_times)
    routing = np.asarray(tttr.routing_channels)
    if routing_channels is not None:
        keep = np.isin(routing, np.asarray(list(routing_channels)))
        macro, micro, routing = macro[keep], micro[keep], routing[keep]

    micro_res_ns = float(getattr(header, "micro_time_resolution", 0.0)) * 1e9
    n_channels = int(
        getattr(header, "number_of_micro_time_channels", int(micro.max()) + 1 if micro.size else 1)
    )
    return TttrData(
        macro_times=macro,
        micro_times=micro,
        routing_channels=routing,
        macro_time_resolution_s=float(getattr(header, "macro_time_resolution", 1.0)),
        micro_time_resolution_ns=micro_res_ns,
        n_microtime_channels=n_channels,
    )


# ----------------------------------------------------------------- lifetime spectrum


def _decay_histogram(micro_times: np.ndarray, n_bins: int) -> np.ndarray:
    # Drop micro-times outside [0, n_bins): the TCSPC window can be wider than the gate
    # used for the lifetime fit, and clipping would pile tail photons into the edge bin.
    idx = np.asarray(micro_times).astype(np.int64)
    idx = idx[(idx >= 0) & (idx < n_bins)]
    return np.bincount(idx, minlength=n_bins)[:n_bins].astype(float)


def lifetime_spectrum(
    micro_times: np.ndarray,
    n_microtime_bins: int,
    micro_time_resolution_ns: float,
    *,
    tau_range: tuple[float, float] = (0.3, 8.0),
    n_components: int = 40,
    irf: np.ndarray | None = None,
    irf_time_ns: np.ndarray | None = None,
    method: str = "nnls",
    reg: float | None = None,
    gate: tuple[int, int] | None = None,
) -> ILTResult1D:
    """Resolve the fluorescence-lifetime distribution from a micro-time decay.

    Builds the decay histogram, an IRF-convolved exponential basis over a log-spaced
    lifetime grid, and solves the regularized inverse-Laplace problem.

    Parameters
    ----------
    micro_times
        Per-photon TCSPC-channel indices.
    n_microtime_bins
        Number of TCSPC channels.
    micro_time_resolution_ns
        ns per TCSPC channel (sets the decay time axis).
    tau_range, n_components
        Lifetime grid (ns) for the inversion.
    irf, irf_time_ns
        Optional instrument response function and its ns axis.
    method, reg
        Passed to :func:`~chisurf.plugins.fcs.flc_2d.fit.ilt.ilt_1d`.
    gate
        Optional ``(lo, hi)`` micro-time channel window to restrict the fit.
    """
    n_bins = int(n_microtime_bins)
    decay = _decay_histogram(micro_times, n_bins)
    if gate is None:
        # With an IRF the rising edge is modelled, so fit the whole gate. Without one we
        # tail-fit from the decay maximum, otherwise the unmodelled rise drives NNLS to
        # zero.
        lo = int(np.argmax(decay)) if irf is None else 0
        hi = n_bins
    else:
        lo, hi = gate
    sl = slice(int(lo), int(hi))
    decay = decay[sl]
    time_ns = (np.arange(n_bins) * micro_time_resolution_ns)[sl]
    tau = lifetime_grid(tau_range[0], tau_range[1], n_components)
    basis = build_exp_basis(time_ns, tau, irf=irf, irf_time_ns=irf_time_ns)
    return ilt_1d(decay, basis, tau, method=method, reg=reg)


def lifetime_lcurve(
    micro_times: np.ndarray,
    n_microtime_bins: int,
    micro_time_resolution_ns: float,
    *,
    tau_range: tuple[float, float] = (0.3, 8.0),
    n_components: int = 40,
    irf: np.ndarray | None = None,
    irf_time_ns: np.ndarray | None = None,
    method: str = "nnls",
):
    """Sample the L-curve of the 1D lifetime inversion (for regularization diagnostics).

    Mirrors :func:`lifetime_spectrum`'s decay/basis construction and returns a general
    :class:`chisurf.core.math.regularization.LCurveData` whose corner is the weight the
    auto-selection would pick.
    """
    n_bins = int(n_microtime_bins)
    decay = _decay_histogram(micro_times, n_bins)
    lo = int(np.argmax(decay)) if irf is None else 0
    sl = slice(lo, n_bins)
    decay = decay[sl]
    time_ns = (np.arange(n_bins) * micro_time_resolution_ns)[sl]
    tau = lifetime_grid(tau_range[0], tau_range[1], n_components)
    basis = build_exp_basis(time_ns, tau, irf=irf, irf_time_ns=irf_time_ns)
    return lcurve_1d(decay, basis, method=method)


def species_decay_patterns(
    lifetimes_ns: Sequence[float],
    n_microtime_bins: int,
    micro_time_resolution_ns: float,
    *,
    irf: np.ndarray | None = None,
    irf_time_ns: np.ndarray | None = None,
) -> list[np.ndarray]:
    """Build per-species IRF-convolved decay patterns for fFCS filtering.

    Given the resolved species lifetimes, returns one decay histogram pattern per species
    suitable as ``species_decays`` input to :func:`species_correlation`.
    """
    time_ns = np.arange(int(n_microtime_bins)) * micro_time_resolution_ns
    patterns = []
    for tau in lifetimes_ns:
        col = build_exp_basis(time_ns, np.array([float(tau)]), irf=irf, irf_time_ns=irf_time_ns)[
            :, 0
        ]
        patterns.append(col)
    return patterns


# -------------------------------------------------------------------------- 2D-FDC


def two_d_fdc(
    macro_times: np.ndarray,
    micro_times: np.ndarray,
    *,
    dT: float,
    ddT: float,
    tMin: float = 1,
    tMax: float = 4096,
    logt_imax: int = 100,
    lint_bin_factor: int = 1,
    max_bins: int | None = None,
    build_lin: bool = True,
    n_chunks: int | None = None,
    progress_callback=None,
) -> dict[str, np.ndarray]:
    """Build linear and log-binned 2D fluorescence-decay correlation matrices.

    ``macro_times`` must be integer clock ticks, ascending; ``micro_times`` are TCSPC
    channel indices. ``dT``/``ddT`` are the correlation lag and window in macro ticks;
    ``tMin``/``tMax`` gate the micro-time range (channels).

    Parameters
    ----------
    macro_times, micro_times
        Photon stream: macro ticks (ascending) and micro TCSPC channels.
    dT, ddT
        Correlation lag and full window width (macro ticks).
    tMin, tMax
        Micro-time gate (channels).
    logt_imax
        Number of log-spaced bins for the log matrix.
    lint_bin_factor
        Micro-time bin factor for the linear matrix (>=1). Build a coarser matrix
        directly instead of a giant full-resolution one (much faster + less memory).
    max_bins
        If given, ``lint_bin_factor`` is derived so the linear matrix is at most this
        many bins. Overrides ``lint_bin_factor``.
    build_lin
        Build the linear matrix (set ``False`` to build only the log-binned matrix).
    n_chunks
        Number of parallel photon chunks (default: one per CPU thread).
    progress_callback
        Optional callable invoked with a 0..1 progress fraction.

    Returns a dict with ``mat_lin``, ``mat_lin_t``, ``mat_log``, ``mat_log_t``.
    """
    if max_bins is not None:
        span = max(1, int(round(tMax)) - int(round(tMin)))
        lint_bin_factor = max(1, -(-span // int(max_bins)))  # ceil(span / max_bins)
    creator = TwoDFDCreator()
    mat_lin, mat_lin_t, mat_log, mat_log_t = creator.create_2d_fdc(
        macro_times,
        micro_times,
        dT=dT,
        ddT=ddT,
        tMin=tMin,
        tMax=tMax,
        logt_imax=logt_imax,
        lint_bin_factor=lint_bin_factor,
        build_lin=build_lin,
        n_chunks=n_chunks,
        progress_callback=progress_callback,
    )
    return {"mat_lin": mat_lin, "mat_lin_t": mat_lin_t, "mat_log": mat_log, "mat_log_t": mat_log_t}


def two_d_fdc_scan(
    macro_times: np.ndarray,
    micro_times: np.ndarray,
    dT_ticks: Sequence[int],
    *,
    ddT: float,
    tMin: float = 1,
    tMax: float = 4096,
    logt_imax: int = 60,
    n_chunks: int | None = None,
) -> dict[str, np.ndarray]:
    """Build a log-binned 2D-FDC matrix at many lags in a single photon pass.

    This is the efficient way to watch the 2D-FLC cross-peaks evolve with macro-time lag
    (e.g. for kinetics): the photon stream is traversed once and every reference photon
    visits all lag windows.

    Parameters
    ----------
    macro_times, micro_times
        Photon stream (macro ticks ascending, micro TCSPC channels).
    dT_ticks
        Lag values (macro ticks) to evaluate.
    ddT
        Lag-window half-width source (macro ticks).
    tMin, tMax
        Micro-time gate (channels).
    logt_imax
        Number of log-spaced bins per matrix.
    n_chunks
        Number of parallel photon chunks (default: one per CPU thread).

    Returns a dict with ``matrices`` (``n_lags x L x L``) and ``dT_ticks``.
    """
    from .core import _fdc_scan_log_kernel, default_chunk_count

    macro = np.ascontiguousarray(macro_times, dtype=np.int64)
    micro = np.ascontiguousarray(micro_times, dtype=np.int64)
    if macro.shape[0] >= 2 and np.any(macro[1:] < macro[:-1]):
        raise ValueError("macro_times must be sorted ascending")
    lags = np.ascontiguousarray(np.asarray(dT_ticks, dtype=np.int64))
    if n_chunks is None:
        # A parallelism decision, never a numerical one: the per-chunk counts
        # are integers summed afterwards, so the matrices are identical however
        # the stream is cut. The kernel's module owns the choice because it is
        # the kernel's thread pool being matched.
        n_chunks = default_chunk_count()
    mats = _fdc_scan_log_kernel(
        macro,
        micro,
        lags,
        np.int64(round(ddT)),
        np.int64(round(tMin)),
        np.int64(round(tMax)),
        int(logt_imax),
        int(n_chunks),
    )
    return {"matrices": mats, "dT_ticks": lags}


# keep the historical name as a thin alias
def correlate_tttr(
    macro_times,
    micro_times,
    dT=0.1,
    ddT=0.05,
    tMin=1.0,
    tMax=12.0,
    logt_imax=100,
    progress_callback=None,
) -> dict[str, np.ndarray]:
    """Build a 2D-FDC matrix (deprecated alias for :func:`two_d_fdc`)."""
    return two_d_fdc(
        macro_times,
        micro_times,
        dT=dT,
        ddT=ddT,
        tMin=tMin,
        tMax=tMax,
        logt_imax=logt_imax,
        progress_callback=progress_callback,
    )


def _rebin_square(matrix: np.ndarray, target: int) -> tuple[np.ndarray, int]:
    """Block-sum a square matrix down to about ``target`` bins; return (matrix, factor)."""
    n = matrix.shape[0]
    k = max(1, n // max(1, target))
    m = (n // k) * k
    if k == 1:
        return matrix[:m, :m], 1
    return matrix[:m, :m].reshape(m // k, k, m // k, k).sum(axis=(1, 3)), k


def _matrix_and_basis(
    matrix, time_axis_ns, *, tau_range, n_components, irf, irf_time_ns, max_bins, basis, tau_grid
):
    """Rebinned matrix and sampled basis, or the matrix as given with a supplied basis.

    A sampled basis is only a model of a *uniformly* binned matrix: on a log axis a
    bin spans one channel to hundreds and has to be integrated over
    (:func:`exp_curves`; measured column misfit of a sampled basis there: median 43%).
    So a non-uniform axis without an explicit ``basis`` is refused rather than fitted.
    """
    M = np.asarray(matrix, dtype=float)
    if basis is not None:
        E = np.asarray(basis, dtype=float)
        if tau_grid is None or np.size(tau_grid) != E.shape[1]:
            raise ValueError("a supplied basis needs tau_grid with one lifetime per column")
        n = min(M.shape[0], E.shape[0])
        return M[:n, :n], E[:n], np.asarray(tau_grid, dtype=float)
    t = np.asarray(time_axis_ns, dtype=float)
    steps = np.diff(t[: M.shape[0]])
    if steps.size > 1 and np.ptp(steps) > 1e-6 * abs(float(np.mean(steps))):
        raise ValueError(
            "non-uniform (e.g. log) time axis: pass basis=exp_curves(...).binned_log "
            "and its tau_grid; a point-sampled basis does not model a log-binned matrix"
        )
    M2, k = _rebin_square(M, max_bins)
    if k > 1:
        m = (t.size // k) * k
        t = t[:m].reshape(-1, k).mean(axis=1)
    t = t[: M2.shape[0]]
    tau = lifetime_grid(tau_range[0], tau_range[1], n_components)
    return M2, build_exp_basis(t, tau, irf=irf, irf_time_ns=irf_time_ns), tau


def two_d_spectrum(
    matrix: np.ndarray,
    time_axis_ns: np.ndarray,
    *,
    tau_range: tuple[float, float] = (0.3, 8.0),
    n_components: int = 24,
    irf: np.ndarray | None = None,
    irf_time_ns: np.ndarray | None = None,
    method: str = "tikhonov",
    reg: float | None = None,
    max_bins: int = 80,
    basis: np.ndarray | None = None,
    tau_grid: np.ndarray | None = None,
) -> ILTResult2D:
    """Invert a 2D-FDC matrix into a 2D lifetime distribution ``P``.

    The matrix is block-rebinned to at most ``max_bins`` for tractability, an
    IRF-convolved basis is built on the (rebinned, uniform) time axis, and the
    regularized 2D inverse-Laplace problem ``M = E P E.T`` is solved. ``P``'s diagonal is
    the marginal lifetime spectrum; its off-diagonal encodes lifetime exchange. For a
    log-binned matrix pass ``basis`` (e.g. :func:`exp_curves` ``.binned_log``) and its
    ``tau_grid``; the matrix is then used as given.
    """
    M2, E, tau = _matrix_and_basis(
        matrix,
        time_axis_ns,
        tau_range=tau_range,
        n_components=n_components,
        irf=irf,
        irf_time_ns=irf_time_ns,
        max_bins=max_bins,
        basis=basis,
        tau_grid=tau_grid,
    )
    return ilt_2d(M2, E, tau, method=method, reg=reg)


# alias requested by the manifest / older callers
def fit_tikhonov_2d(matrix, time_axis_ns, **kw) -> ILTResult2D:
    """Alias for :func:`two_d_spectrum` with ``method='tikhonov'``."""
    kw.setdefault("method", "tikhonov")
    return two_d_spectrum(matrix, time_axis_ns, **kw)


def fit_mem_2d(matrix, time_axis_ns, **kw) -> ILTResult2D:
    """2D lifetime inversion via the maximum-entropy method (faithful, slower).

    Delegates to :mod:`chisurf.plugins.fcs.flc_2d.fit.mem_2d`. See
    :func:`two_d_spectrum` for the fast default.
    """
    from .fit.mem_2d import solve_mem_2d

    M2, E, tau = _matrix_and_basis(
        matrix,
        time_axis_ns,
        tau_range=kw.pop("tau_range", (0.3, 8.0)),
        n_components=kw.pop("n_components", 24),
        irf=kw.pop("irf", None),
        irf_time_ns=kw.pop("irf_time_ns", None),
        max_bins=kw.pop("max_bins", 80),
        basis=kw.pop("basis", None),
        tau_grid=kw.pop("tau_grid", None),
    )
    return solve_mem_2d(M2, E, tau, **kw)


# ------------------------------------------------------------------------- dynamics


@dataclass
class DynamicsResult:
    """Species-resolved correlation plus fitted interconversion relaxation."""

    correlation: SpeciesCorrelation
    relaxation: dict[str, float]  # from fit_relaxation on the mean species auto-corr


def species_correlation(
    macro_times: np.ndarray,
    micro_times: np.ndarray,
    species_decays: Sequence[np.ndarray],
    total_decay: np.ndarray | None,
    macro_time_resolution_s: float,
    *,
    n_microtime_bins: int | None = None,
    n_bins: int = 8,
    n_casc: int = 25,
    fit: bool = True,
) -> DynamicsResult:
    """Species-resolved (lifetime-filtered) correlation and its relaxation time.

    Constructs fFCS filters from the species decay patterns, computes the species auto-
    and cross-correlations with ``tttrlib``, and (optionally) fits a single-exponential
    relaxation to the mean species auto-correlation. For a two-state exchange the fitted
    rate equals the sum of the interconversion rates.

    Parameters
    ----------
    macro_times, micro_times
        Photon stream (macro ticks ascending, micro TCSPC channels).
    species_decays
        Per-species decay patterns (see :func:`species_decay_patterns`).
    total_decay
        Total decay histogram; if ``None`` it is built from ``micro_times``.
    macro_time_resolution_s
        Seconds per macro tick (lag-axis calibration).
    n_microtime_bins
        Number of TCSPC channels (defaults to the longest species pattern).
    n_bins, n_casc
        Multi-tau correlator settings (channels per cascade, number of cascades).
    fit
        Fit a single-exponential relaxation to the mean species auto-correlation.
    """
    n_mt = n_microtime_bins or max(len(d) for d in species_decays)
    if total_decay is None:
        total_decay = _decay_histogram(micro_times, n_mt)
    filters = species_filters(total_decay, species_decays)
    corr = filtered_correlation(
        macro_times,
        micro_times,
        filters,
        macro_time_resolution_s,
        n_bins=n_bins,
        n_casc=n_casc,
        n_microtime_bins=n_mt,
    )
    relax: dict[str, float] = {}
    if fit and corr.auto:
        mean_auto = np.mean(np.vstack([corr.auto[i] for i in corr.auto]), axis=0)
        try:
            relax = fit_relaxation(corr.lag_s, mean_auto)
        except Exception:  # pragma: no cover - degenerate data
            relax = {}
    return DynamicsResult(correlation=corr, relaxation=relax)


def global_lifetime_mem(
    matrices: Sequence[np.ndarray],
    time_axis_ns: np.ndarray,
    *,
    n_states: int = 2,
    tau_range: tuple[float, float] = (0.3, 8.0),
    n_components: int = 20,
    irf: np.ndarray | None = None,
    irf_time_ns: np.ndarray | None = None,
    regulator: float = 1.0,
    basis: np.ndarray | None = None,
    tau_grid: np.ndarray | None = None,
) -> GlobalMEMResult:
    """Jointly invert several lag matrices with one shared lifetime distribution.

    Builds the IRF-convolved basis once and runs the global multi-lag 2D-MEM
    (:func:`~chisurf.plugins.fcs.flc_2d.fit.global_mem.solve_global_mem_2d`). All matrices
    must share the same shape and time axis (e.g. linear 2D-FDCs built at different ``dT``
    with the same ``tMin``/``tMax``/binning). Log-binned matrices need ``basis`` and
    ``tau_grid`` (see :func:`two_d_spectrum`).
    """
    mats = [np.asarray(M, dtype=float) for M in matrices]
    _, E, tau = _matrix_and_basis(
        mats[0],
        time_axis_ns,
        tau_range=tau_range,
        n_components=n_components,
        irf=irf,
        irf_time_ns=irf_time_ns,
        max_bins=mats[0].shape[0],
        basis=basis,
        tau_grid=tau_grid,
    )
    n = E.shape[0]
    return solve_global_mem_2d(
        [M[:n, :n] for M in mats], E, tau, n_states=n_states, regulator=regulator
    )


def rate_matrix_kinetics(
    correlation: SpeciesCorrelation,
    *,
    n_states: int = 2,
    populations: Sequence[float] | None = None,
    t_min: float = 5e-4,
    t_max: float = 0.5,
) -> RateMatrixResult:
    """Fit a rate matrix to species correlation decays (per-state rate constants).

    Builds the ``{(i, j): G_ij}`` curve set from a :class:`SpeciesCorrelation` (auto +
    cross) and runs the shared-rate variable-projection fit
    (:func:`~chisurf.plugins.fcs.flc_2d.fit.kinetics.fit_rate_matrix`). For two states the
    reconstructed rate matrix needs the equilibrium ``populations``.
    """
    curves: dict[tuple[int, int], np.ndarray] = {(i, i): g for i, g in correlation.auto.items()}
    curves.update(correlation.cross)
    pops = None if populations is None else np.asarray(populations, dtype=float)
    return fit_rate_matrix(
        correlation.lag_s, curves, n_states=n_states, populations=pops, t_min=t_min, t_max=t_max
    )


# ---------------------------------------------------------------------- reproduction


def _basis(time_axis_ns, tau_grid, irf, irf_time_ns, basis):
    if basis is not None:
        return np.asarray(basis, dtype=float)
    return build_exp_basis(
        np.asarray(time_axis_ns, dtype=float),
        np.asarray(tau_grid, dtype=float),
        irf=irf,
        irf_time_ns=irf_time_ns,
    )


def reproduce_1d_fdc(
    amplitudes: np.ndarray,
    time_axis_ns: np.ndarray,
    *,
    tau_grid: np.ndarray,
    y0: float = 0.0,
    irf: np.ndarray | None = None,
    irf_time_ns: np.ndarray | None = None,
    basis: np.ndarray | None = None,
    decay: np.ndarray | None = None,
    decay_cor: np.ndarray | None = None,
    mi: np.ndarray | None = None,
    regulator: float | None = None,
    area_weighted: bool = False,
) -> Reproduction:
    """Rebuild a 1D-FDC (decay) from a lifetime distribution, to check a fit against data.

    Port of ``TK_FitF_Reproduct1DFDC`` / ``_02``: model ``E A + y0 * bin_width`` on the
    exponential basis of ``tau_grid`` over ``time_axis_ns`` (IRF-convolved when ``irf``
    is given; pass ``basis`` to use your own), with the reference's chi-square, entropy
    and estimator ``Q = chi2 - 2 S / regulator`` when ``decay`` (and ``mi``,
    ``regulator``) are given. See :mod:`~chisurf.plugins.fcs.flc_2d.fit.reproduct` for
    the exact conventions.
    """
    E = _basis(time_axis_ns, tau_grid, irf, irf_time_ns, basis)
    return reproduce_1d(
        amplitudes,
        E,
        time_axis_ns,
        y0=y0,
        data=decay,
        data_cor=decay_cor,
        mi=mi,
        regulator=regulator,
        area_weighted=area_weighted,
    )


def reproduce_2d_fdc(
    amplitudes: np.ndarray,
    correlation: np.ndarray,
    time_axis_ns: np.ndarray,
    *,
    tau_grid: np.ndarray,
    y0: float | Sequence[float] = 0.0,
    irf: np.ndarray | None = None,
    irf_time_ns: np.ndarray | None = None,
    basis: np.ndarray | None = None,
    matrix: np.ndarray | None = None,
    matrix_cor: np.ndarray | None = None,
    mi: np.ndarray | None = None,
    regulator: float | None = None,
    floor_zeros: bool = True,
) -> Reproduction:
    """Rebuild the 2D-FLC map ``A G A^T`` and the 2D-FDC it predicts.

    Port of ``TK_FitF_Reproduct2DFDCand2DFLC_03`` (``correlation`` ``s x s``) and of its
    global form ``TK_GFitF_Reproduct2DFDCand2DFLC_03`` (``correlation``
    ``n_lags x s x s``, ``y0`` and ``matrix`` per lag). ``amplitudes`` is
    ``n_comp x n_states`` on ``tau_grid``. The MATLAB minimizers call this on the other
    binning after a fit -- reproduce on the log axis what was fitted on the linear one,
    and compare. ``floor_zeros`` keeps the reference's lift of exact zeros in ``A``.
    """
    E = _basis(time_axis_ns, tau_grid, irf, irf_time_ns, basis)
    G = np.asarray(correlation, dtype=float)
    kw = dict(data=matrix, data_cor=matrix_cor, mi=mi, regulator=regulator, floor_zeros=floor_zeros)
    if G.ndim == 3:
        return reproduce_global_2d(amplitudes, G, E, time_axis_ns, y0=np.asarray(y0), **kw)
    return reproduce_2d(amplitudes, G, E, time_axis_ns, y0=float(y0), **kw)


def reproduce_fit(
    result,
    time_axis_ns: np.ndarray,
    *,
    irf: np.ndarray | None = None,
    irf_time_ns: np.ndarray | None = None,
    basis: np.ndarray | None = None,
    data: np.ndarray | None = None,
) -> Reproduction:
    """Rebuild the model of a fit result on a time axis, e.g. another binning.

    Accepts what :func:`lifetime_spectrum`, :func:`lifetime_spectrum_mem`,
    :func:`two_d_spectrum`/:func:`fit_mem_2d` and :func:`global_lifetime_mem` return.
    On the axis (and IRF) the fit used it returns exactly the fitted model; ``data``
    adds the reference chi-square.
    """
    from .fit.reproduct import reproduce_result

    E = _basis(time_axis_ns, result.tau_grid, irf, irf_time_ns, basis)
    return reproduce_result(result, E, data=data)


# ------------------------------------------------------- the reference's 2D-MEM workflow


def exp_curves(
    tau_ns,
    xdata_ns,
    irf,
    *,
    t_min_ns,
    t_max_ns,
    t_step_ns,
    lint_bin_factor,
    logt_imax,
    rise_point_irf,
    rise_point_fl=300,
    irf_range=None,
):
    """The reference's exponential basis, integrated over the linear and log 2D-FDC bins.

    Port of ``TK_CreateExpCurve``/``TK_ExpMultiDeco_For2DFLC``; the axes are built the
    ``TK_Create2DFDC_04`` way. ``irf_range`` defaults to ``(50, len(xdata) - 90)``.
    Returns :class:`~chisurf.plugins.fcs.flc_2d.fit.exp_curve.ExpCurves` with
    ``lin_axis_ns``/``log_axis_ns`` attached.
    """
    from .fit.exp_curve import create_exp_curve, matlab_lin_axis_ns, matlab_log_axis_ns

    x = np.asarray(xdata_ns, dtype=float)
    log_axis = matlab_log_axis_ns(t_min_ns, t_max_ns, t_step_ns, lint_bin_factor, logt_imax)
    curves = create_exp_curve(
        tau_ns,
        x,
        irf,
        t_min_ns=t_min_ns,
        t_max_ns=t_max_ns,
        t_step_ns=t_step_ns,
        lint_bin_factor=lint_bin_factor,
        log_axis_ns=log_axis,
        rise_point_fl=rise_point_fl,
        rise_point_irf=rise_point_irf,
        irf_range=(50, x.size - 90) if irf_range is None else irf_range,
    )
    curves.lin_axis_ns = matlab_lin_axis_ns(t_min_ns, t_max_ns, t_step_ns, lint_bin_factor)
    curves.log_axis_ns = log_axis
    return curves


def fit_2d_mem_workflow(matrices, **kwargs):
    """One run of the reference's 2D-MEM drivers (``TK_MyMain_Fit_2DMEM_04`` + ``GFit_2DMEM``).

    See :func:`chisurf.plugins.fcs.flc_2d.fit.workflow_2d.fit_2d_mem_workflow`.
    ``matrices`` is ``separate_data_2d_fdc(...).total()``.
    """
    from .fit.workflow_2d import fit_2d_mem_workflow as _fit

    return _fit(matrices, **kwargs)


def search_irf_rise_2d(matrices, **kwargs):
    """Scan the IRF rise point over the 2D-MEM workflow (``TK_MyMain_Search_RiseIRF_2DMEM``).

    See :func:`chisurf.plugins.fcs.flc_2d.fit.workflow_2d.search_irf_rise_2d`; the result's
    ``best`` is the lowest-chi2 rise point.
    """
    from .fit.workflow_2d import search_irf_rise_2d as _search

    return _search(matrices, **kwargs)


def average_2d_mem(matrices, **kwargs):
    """Average the 2D-MEM workflow over rise points around a centre (``TK_MyMain_Run_Ave2DMEM``).

    See :func:`chisurf.plugins.fcs.flc_2d.fit.workflow_2d.average_2d_mem`.
    """
    from .fit.workflow_2d import average_2d_mem as _average

    return _average(matrices, **kwargs)


# ------------------------------------------------------------------ separate data


def separate_data_2d_fdc(molecules, dT_ticks, ddT_ticks, **kwargs):
    """Per-molecule 2D-FDC set of the reference driver (molecules summed, never mixed).

    Port of the data preparation in
    ``TK_MyMain_Create2DFDC_cor_SeparateData_BootStrap_v02``; see
    :func:`chisurf.plugins.fcs.flc_2d.bootstrap.separate_data_2d_fdc` for the
    parameters. ``result.total()`` gives the summed ``lin``/``log``/``cor_*``/
    ``short_*``/``fdc_1d_*`` matrices.
    """
    from .bootstrap import separate_data_2d_fdc as _separate

    return _separate(molecules, dT_ticks, ddT_ticks, **kwargs)


def bootstrap_2d_fdc(separate, n_replicates: int = 100, **kwargs):
    """Molecule-bootstrap error estimate of every summed 2D-FDC element.

    Draws molecules as the reference driver does (``group_factor``, ``photon_factor``)
    ``n_replicates`` times and returns the replicates with their per-element mean and
    standard deviation. See :func:`chisurf.plugins.fcs.flc_2d.bootstrap.bootstrap_2d_fdc`.
    """
    from .bootstrap import bootstrap_2d_fdc as _bootstrap

    return _bootstrap(separate, n_replicates, **kwargs)


# ------------------------------------------------------------------- 1D-FDC + 1D-MEM


def one_d_fdc(
    macro_times: np.ndarray,
    micro_times: np.ndarray,
    *,
    tMin: float = 0,
    tMax: float = 4096,
    lint_bin_factor: int = 1,
    max_bins: int | None = None,
    logt_imax: int = 100,
    n_chunks: int = 1,
) -> dict[str, np.ndarray]:
    """Build the 1D-FDC (zero-lag same-macro-time decay coincidence).

    Port of ``TK_Create1DFDC_01``. Returns a dict with ``lin_t``/``lin`` (linear axis and
    1D-FDC) and ``log_t``/``log`` (log axis and 1D-FDC), in micro-time tick units.

    Parameters
    ----------
    macro_times, micro_times
        Photon stream (macro ticks ascending, micro TCSPC channels).
    tMin, tMax
        Micro-time gate (channels).
    lint_bin_factor
        Linear micro-time bin factor (>=1).
    max_bins
        If given, derive ``lint_bin_factor`` so the linear axis is at most this many bins.
    logt_imax
        Number of log-spaced bins.
    n_chunks
        Number of parallel photon chunks.
    """
    lo, hi = int(round(tMin)), int(round(tMax))
    if max_bins is not None:
        span = max(1, hi - lo)
        lint_bin_factor = max(1, -(-span // int(max_bins)))
    lin_t, lin, log_t, log = create_1d_fdc(
        macro_times,
        micro_times,
        tMin_ticks=lo,
        tMax_ticks=hi,
        lint_bin_factor=max(1, int(lint_bin_factor)),
        logt_imax=int(logt_imax),
        n_chunks=int(n_chunks),
    )
    return {"lin_t": lin_t, "lin": lin, "log_t": log_t, "log": log}


def _fit_1d_decay(
    decay: np.ndarray,
    time_ns: np.ndarray,
    tau: np.ndarray,
    *,
    irf: np.ndarray | None,
    irf_time_ns: np.ndarray | None,
):
    """Drop leading non-positive bins (the MATLAB ``FitStartI``) and build the basis."""
    decay = np.asarray(decay, dtype=float)
    pos = np.flatnonzero(decay > 0)
    start = int(pos[0]) if pos.size else 0
    decay = decay[start:]
    t = np.asarray(time_ns, dtype=float)[start:]
    basis = build_exp_basis(t, tau, irf=irf, irf_time_ns=irf_time_ns)
    return decay, t, basis


def lifetime_spectrum_mem(
    decay: np.ndarray,
    time_ns: np.ndarray,
    *,
    tau_range: tuple[float, float] = (0.3, 8.0),
    n_components: int = 40,
    irf: np.ndarray | None = None,
    irf_time_ns: np.ndarray | None = None,
    reg: float = 50.0,
    mi_type: int = 0,
    n_outer: int = 12,
) -> OneDMEMResult:
    """Resolve a 1D lifetime distribution by maximum entropy (faithful MATLAB objective).

    This is the explicit 1D-MEM (port of ``TK_FitF_1DMEM_*``); the fast default for routine
    use remains :func:`lifetime_spectrum` (NNLS/Tikhonov ILT). Leading empty bins are
    dropped automatically (the MATLAB ``FitStartI``).

    Parameters
    ----------
    decay
        1D fluorescence-decay (e.g. ``one_d_fdc(...)["lin"]`` or a micro-time histogram).
    time_ns
        Decay time axis (ns).
    tau_range, n_components
        Lifetime grid (ns).
    irf, irf_time_ns
        Optional instrument response and its ns axis.
    reg, mi_type, n_outer
        Passed to :func:`~chisurf.plugins.fcs.flc_2d.fit.mem_1d.solve_mem_1d`.
    """
    tau = lifetime_grid(tau_range[0], tau_range[1], n_components)
    d, t, basis = _fit_1d_decay(decay, time_ns, tau, irf=irf, irf_time_ns=irf_time_ns)
    return solve_mem_1d(
        d,
        basis,
        tau,
        reg=reg,
        mi_type=mi_type,
        n_outer=n_outer,
        t_min=float(t[0]) if t.size else 0.0,
        t_max=float(t[-1]) if t.size else 1.0,
    )


def fit_gaussian_components(
    tau_grid: np.ndarray,
    distribution: np.ndarray,
    n_components: int = 2,
    *,
    fit_offset: bool = False,
) -> GaussianFitResult:
    """Fit discrete Gaussian peaks to a recovered lifetime distribution.

    Port of ``TK_FitF_GaussianMulti``: extract discrete lifetime components (centre, width,
    amplitude) from a smooth ILT/MEM distribution.
    """
    return fit_gaussian_multi(
        np.asarray(tau_grid, float),
        np.asarray(distribution, float),
        n_components,
        fit_offset=fit_offset,
    )


def search_irf_rise(
    decay: np.ndarray,
    time_ns: np.ndarray,
    irf: np.ndarray,
    irf_time_ns: np.ndarray,
    *,
    tau_range: tuple[float, float] = (0.3, 8.0),
    n_components: int = 40,
    shifts=range(-7, 8),
    average_width: int = 13,
    mem_kwargs: dict | None = None,
) -> RiseIRFResult:
    """Scan the IRF rise position and average the 1D-MEM around the optimum.

    Port of ``TK_MyMain_Search_RiseIRF_1DMEM``. Leading empty bins are dropped first.
    """
    tau = lifetime_grid(tau_range[0], tau_range[1], n_components)
    d, t, _ = _fit_1d_decay(decay, time_ns, tau, irf=None, irf_time_ns=None)
    return search_rise_irf(
        d,
        t,
        tau,
        irf,
        irf_time_ns,
        shifts=shifts,
        average_width=average_width,
        mem_kwargs=mem_kwargs,
    )


def make_synthetic_irf(
    time_ns: np.ndarray,
    center_ns: float,
    fwhm_ns: float,
    *,
    shape: float = 0.0,
) -> np.ndarray:
    """Build a synthetic (skewed-)Gaussian IRF on ``time_ns``.

    Thin re-export of the general
    :func:`chisurf.core.fluorescence.tcspc.irf.synthetic_irf` so the plugin reuses the
    shared chisurf IRF helpers instead of duplicating them.
    """
    from chisurf.core.fluorescence.tcspc.irf import synthetic_irf

    return synthetic_irf(time_ns, center_ns, fwhm_ns, shape=shape)


def detect_irf(
    decay: np.ndarray,
    time_ns: np.ndarray,
    *,
    fwhm_ns: float | None = None,
    shape: float = 0.0,
) -> np.ndarray:
    """Detect a decay's prompt position and return a matching synthetic IRF.

    Thin re-export of
    :func:`chisurf.core.fluorescence.tcspc.irf.estimate_irf_from_decay`.
    """
    from chisurf.core.fluorescence.tcspc.irf import estimate_irf_from_decay

    return estimate_irf_from_decay(decay, time_ns, fwhm_ns=fwhm_ns, shape=shape)


def simulate_stream(
    rate_matrix: np.ndarray,
    lifetimes_ns: Sequence[float],
    intensities_cps: Sequence[float],
    *,
    total_time_s: float = 100.0,
    irf: np.ndarray | None = None,
    irf_time_ns: np.ndarray | None = None,
    macro_time_resolution_s: float = 1e-6,
    tstep_ns: float = 0.004,
    n_microtime_channels: int = 3127,
    seed: int = 0,
):
    """Simulate a single-molecule photon stream from an n-state exchange process.

    Thin wrapper around
    :func:`~chisurf.plugins.fcs.flc_2d.simulate.simulate_photon_stream` (port of
    ``TK_MyMain_Simu_PhotonStream``). Returns a ``SimulatedStream`` with macro/micro ticks
    and ground-truth state labels, closing the loop for validation.
    """
    from .simulate import simulate_photon_stream

    return simulate_photon_stream(
        np.asarray(rate_matrix, dtype=float),
        lifetimes_ns,
        intensities_cps,
        total_time_s=total_time_s,
        irf=irf,
        irf_time_ns=irf_time_ns,
        macro_time_resolution_s=macro_time_resolution_s,
        tstep_ns=tstep_ns,
        n_microtime_channels=n_microtime_channels,
        seed=seed,
    )
