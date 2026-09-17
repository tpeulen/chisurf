"""
Core 2D-FDC (Fluorescence Decay Correlation) matrix creation functions.

The 2D-FDC matrices are built by the photon library (``tttrlib.fdc_scan_log``
and friends), which implements the algorithm of the original MATLAB code
``TK_Create2DFDC_04.m`` by Toru Kondo (Schlau-Cohen lab, MIT) tick for tick,
including its log-axis quantization (verified by running the .m in Octave
against the library; pinned in tttrlib's
``test_fdc2d.py::TestAgainstTheOriginalMatlab``).

The method is two-dimensional fluorescence lifetime correlation (2D-FLC)
spectroscopy, introduced by K. Ishii and T. Tahara, "Two-Dimensional
Fluorescence Lifetime Correlation Spectroscopy. 1. Principle" and ". 2.
Application", J. Phys. Chem. B 117(39), 11414-11422 and 11423-11432 (2013),
doi:10.1021/jp406861u and doi:10.1021/jp406864e, and applied at
single-molecule level in T. Kondo, J. B. Gordon, A. Pinnola, L. Dall'osto,
R. Bassi and G. S. Schlau-Cohen, "Microsecond and millisecond dynamics in
the photosynthetic protein LHCSR1 observed by single-molecule correlation
spectroscopy", Proc. Natl. Acad. Sci. USA 116(23), 11247-11252 (2019),
doi:10.1073/pnas.1821207116.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import numpy as np

def default_chunk_count() -> int:
    """Chunks to split the photon stream into for the 2D-FDC pass.

    One per CPU. The kernels are the photon library's now and parallelise with
    OpenMP, so this is no longer tied to numba's pool -- which it had to be while
    they were numba kernels, because handing a ``prange`` a count its launched
    pool disagreed with made the runtime object rather than over-subscribe.

    The count never changes the result: per-chunk pair counts are integers and
    are summed afterwards, so this is a parallelism and memory decision only.

    Returns
    -------
    int
    """
    import os

    return os.cpu_count() or 1


def fdc_bin_index(tau: np.ndarray, ticks: np.ndarray) -> np.ndarray:
    """The photon library's bin lookup; ``-1`` where it does not place a photon.

    ``searchsorted(ticks, tau, "left") - 1``, valid in ``1 .. len(ticks) - 2``: the
    index a pair lands at in the library's ``(len(ticks) - 1)^2`` matrix, before any
    trim. Used to take back pairs the library counts and the reference does not.
    """
    b = np.searchsorted(ticks, tau, side="left") - 1
    return np.where((b > 0) & (b < ticks.size - 1), b, -1)


def earlier_same_time_pairs(macro: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Index pairs ``(q, p)``, ``p < q``, of photons sharing a macro time.

    The reference walks partners strictly after the reference photon in stream order;
    the library's window search also finds *earlier* photons at the same macro tick
    whenever a window starts at the reference's own time (zero lag, or ``dT = ddT/2``).
    """
    q_all, p_all = [], []
    dup = np.flatnonzero(np.diff(macro) == 0)
    if dup.size == 0:
        return np.zeros(0, int), np.zeros(0, int)
    # runs of equal macro time: start at a dup whose predecessor is not a dup
    starts = dup[np.concatenate([[True], np.diff(dup) > 1])]
    for s0 in starts:
        e = s0 + 1
        while e + 1 < macro.size and macro[e + 1] == macro[s0]:
            e += 1
        for q in range(s0 + 1, e + 1):
            for p in range(s0, q):
                q_all.append(q)
                p_all.append(p)
    return np.asarray(q_all, int), np.asarray(p_all, int)


def create_2d_fdc_numba_int(
    macro_times: np.ndarray,
    micro_times: np.ndarray,
    dT_ticks: int,
    ddT_ticks: int,
    Tstart_ticks: int,
    Tend_ticks: int,
    tMin_over_tStep: int,
    tMax_over_tStep: int,
    lint_bin_factor: int = 2,
    logt_imax_in: int = 100,
    build_lin: bool = True,
    n_chunks: int = 1,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Build the linear and log 2D-FDC matrices for one lag, in one photon pass.

    Both matrices come from a single walk over the stream
    (`fdc_scan_two_axes`) -- two calls would be two passes, which at 1M photons
    is a measured 2.27x.

    The axes and the gate follow ``TK_Create2DFDC_04.m``: ``t_Imax`` is the span
    rounded **up** to a whole number of linear bins, it bounds the micro-time
    gate (so photons above ``tMax`` are admitted, lines 38-40 and 66), and the
    linear matrix is trimmed by one bin on return (lines 170-172, MATLAB being
    1-based over ``1..lint_Imax``).

    ``Tstart_ticks`` and ``Tend_ticks`` are accepted for signature compatibility
    and unused: the library bounds the window by the photon stream itself.
    """
    import tttrlib

    macro = np.ascontiguousarray(macro_times, dtype=np.int64)
    micro = np.ascontiguousarray(micro_times, dtype=np.int64)
    if macro.shape[0] == 0:
        raise ValueError("Input arrays cannot be empty")
    if micro.shape[0] != macro.shape[0]:
        raise ValueError("macro_times and micro_times must have same length")
    span = int(tMax_over_tStep) - int(tMin_over_tStep)
    if span < 0:
        raise ValueError("tMax_over_tStep must be >= tMin_over_tStep")

    factor = int(lint_bin_factor)
    t_imax = tttrlib.fdc_t_imax(span, factor)
    lint_imax = t_imax // factor

    log_ticks = np.zeros(int(logt_imax_in) + 1, dtype=np.int64)
    tttrlib.fdc_log_ticks(t_imax, log_ticks)
    lin_ticks = np.concatenate(
        [[-1], np.arange(0, t_imax + factor, factor)]
    ).astype(np.int64)

    out_log = np.zeros((len(log_ticks) - 1) ** 2, dtype=np.int64)
    out_lin = np.zeros((len(lin_ticks) - 1) ** 2, dtype=np.int64)
    tttrlib.fdc_scan_two_axes(
        macro, micro, np.array([int(dT_ticks)], dtype=np.int64), int(ddT_ticks),
        int(tMin_over_tStep), int(tMax_over_tStep), log_ticks, lin_ticks,
        int(n_chunks), out_log, out_lin, t_imax,
    )

    mat_log = out_log.reshape(int(logt_imax_in), int(logt_imax_in))
    logt_ticks = log_ticks[: int(logt_imax_in)]
    # The library stores linear bin ``ceil(tau / f)`` at index ``ceil(tau / f)``, so
    # index 0 is always empty; the reference's bins 1..lint_Imax-1 are 1:lint_imax.
    # Slicing :lint_imax-1 kept the empty row and dropped the last reference bin,
    # shifting the matrix one bin against its axis (found by running the MATLAB
    # driver in Octave; pinned in test_bootstrap.py).
    mat_lin = out_lin.reshape(len(lin_ticks) - 1, len(lin_ticks) - 1)[1:lint_imax, 1:lint_imax]
    mat_lint = (factor * np.arange(lint_imax, dtype=np.int64))[: lint_imax - 1]
    return mat_lin, mat_lint, mat_log, logt_ticks




def _fdc_scan_log_kernel(
    macro_times: np.ndarray,
    micro_times: np.ndarray,
    dT_ticks: np.ndarray,
    ddT_ticks: int,
    tMin_over_tStep: int,
    tMax_over_tStep: int,
    logt_imax_in: int,
    n_chunks: int,
    lint_bin_factor: int = 1,
) -> np.ndarray:
    """Build one log-binned 2D-FDC matrix per lag in a single photon pass.

    Returns an array of shape ``(n_lags, L, L)`` (``L = logt_imax_in``). The
    photon pass is the library's `fdc_scan_axis`; the axis and the gate are
    built here from the reference's ``t_Imax`` so the result is the paper's.
    """
    import tttrlib

    span = int(tMax_over_tStep) - int(tMin_over_tStep)
    t_imax = tttrlib.fdc_t_imax(span, int(lint_bin_factor))
    ticks = np.zeros(int(logt_imax_in) + 1, dtype=np.int64)
    tttrlib.fdc_log_ticks(t_imax, ticks)
    lags = np.ascontiguousarray(dT_ticks, dtype=np.int64)
    out = np.zeros(lags.size * int(logt_imax_in) ** 2, dtype=np.int64)
    tttrlib.fdc_scan_axis(
        np.ascontiguousarray(macro_times, dtype=np.int64),
        np.ascontiguousarray(micro_times, dtype=np.int64),
        lags, int(ddT_ticks), int(tMin_over_tStep), int(tMax_over_tStep),
        ticks, int(n_chunks), out, t_imax,
    )
    return out.reshape(lags.size, int(logt_imax_in), int(logt_imax_in))




class TwoDFDCreatorNumbaInt:
    """Thin wrapper around numba kernel to enforce int64 inputs."""

    def create_2d_fdc(
        self,
        macro_times: np.ndarray,
        micro_times: np.ndarray,
        dT_ticks: int,
        ddT_ticks: int,
        Tstart_ticks: int = 0,
        Tend_ticks: int = 2**63 - 1,
        tMin_over_tStep: int = 0,
        tMax_over_tStep: int = 4096,
        lint_bin_factor: int = 2,
        logt_imax: int = 100,
        build_lin: bool = True,
        n_chunks: int = 1,
    ):
        """Build the linear and log 2D-FDC matrices via the numba kernel."""
        macro_times = np.ascontiguousarray(macro_times, dtype=np.int64)
        micro_times = np.ascontiguousarray(micro_times, dtype=np.int64)

        if macro_times.shape[0] >= 2 and np.any(macro_times[1:] < macro_times[:-1]):
            raise ValueError("macro_times must be sorted ascending for numba implementation")

        return create_2d_fdc_numba_int(
            macro_times=macro_times,
            micro_times=micro_times,
            dT_ticks=np.int64(dT_ticks),
            ddT_ticks=np.int64(ddT_ticks),
            Tstart_ticks=np.int64(Tstart_ticks),
            Tend_ticks=np.int64(Tend_ticks),
            tMin_over_tStep=np.int64(tMin_over_tStep),
            tMax_over_tStep=np.int64(tMax_over_tStep),
            lint_bin_factor=int(lint_bin_factor),
            logt_imax_in=int(logt_imax),
            build_lin=bool(build_lin),
            n_chunks=int(n_chunks),
        )


class TwoDFDCreator:
    """
    Creates 2D-Fluorescence Decay Correlation (FDC) matrices from TTTR data.

    This class provides a high-level interface for generating 2D-FDC matrices,
    which represent the correlation between photon microtimes (arrival times within
    a laser cycle) separated by a specific macro-time delay (dT).

    The implementation uses Numba for high-performance correlation calculation.
    """

    def __init__(self, prefer_numba: bool = True):
        """
        Initialize the 2D-FDC creator.

        Args:
            prefer_numba: Whether to use the Numba-accelerated backend (default: True).
        """
        self.logger = logging.getLogger(__name__)
        self._numba_creator = TwoDFDCreatorNumbaInt()

    def create_2d_fdc(
        self,
        macro_times: np.ndarray,
        micro_times: np.ndarray,
        dT: float = 0.1,
        ddT: float = 0.05,
        tMin: float = 1.0,
        tMax: float = 12.0,
        logt_imax: int = 100,
        lint_bin_factor: int = 1,
        build_lin: bool = True,
        n_chunks: int | None = None,
        progress_callback: Callable[[float], None] | None = None,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        Create 2D-FDC matrices from photon arrival times.

        This method computes linear and logarithmically binned 2D-FDC matrices.
        The input parameters dT, ddT, tMin, and tMax are expected to be in tick units
        (integers) if raw TTTR data is used, or in physical units if normalized.

        Args:
            macro_times: Array of macro-time arrival ticks.
            micro_times: Array of micro-time arrival ticks.
            dT: Macro-time delay (ticks or seconds).
            ddT: Macro-time window width (ticks or seconds).
            tMin: Lower micro-time gate (ticks or seconds).
            tMax: Upper micro-time gate (ticks or seconds).
            logt_imax: Number of points for the logarithmic time axis.
            lint_bin_factor: Micro-time bin factor for the linear matrix (>=1). Larger
                factors build a smaller matrix directly, avoiding a giant full-resolution
                matrix and speeding up both construction and the downstream fit.
            build_lin: Build the linear matrix (set False to build only the log matrix).
            n_chunks: Number of parallel photon chunks (default: one per thread). Memory
                scales with ``n_chunks * matrix_size``; capped automatically.
            progress_callback: Optional function called with progress (0.0 to 1.0).

        Returns:
            Tuple containing:
            - mat_lin: Linear 2D-FDC matrix (n_tau x n_tau).
            - mat_lin_t: Time axis for linear matrix (ticks or seconds).
            - mat_log: Logarithmic 2D-FDC matrix (log_points x log_points).
            - mat_log_t: Time axis for logarithmic matrix.
        """
        params = self._normalize_inputs(
            macro_times=macro_times,
            micro_times=micro_times,
            dT=dT,
            ddT=ddT,
            tMin=tMin,
            tMax=tMax,
            logt_imax=logt_imax,
        )
        params["lint_bin_factor"] = max(1, int(lint_bin_factor))
        params["build_lin"] = bool(build_lin)
        params["n_chunks"] = self._pick_n_chunks(params, n_chunks)

        self.logger.info(
            "2D-FDC create_2d_fdc called | backend=numba photons=%d dT=%d ddT=%d "
            "tMin=%d tMax=%d logt_imax=%d bin=%d chunks=%d",
            params["n_photons"],
            params["dT_ticks"],
            params["ddT_ticks"],
            params["tMin_ticks"],
            params["tMax_ticks"],
            params["logt_imax"],
            params["lint_bin_factor"],
            params["n_chunks"],
        )
        return self._create_with_numba(params, progress_callback)

    def _pick_n_chunks(self, params: dict, n_chunks: int | None) -> int:
        """Choose a parallel chunk count, capping accumulator memory to ~512 MB."""
        if n_chunks is not None:
            return max(1, int(n_chunks))
        # This called numba's get_num_threads() after numba had left the module; the
        # NameError was swallowed and every build ran single-chunk.
        threads = default_chunk_count()
        span = max(1, params["tMax_over_tStep"] - params["tMin_over_tStep"])
        llin = (span // params["lint_bin_factor"] + 2) if params["build_lin"] else 1
        llog = params["logt_imax"] + 1
        bytes_per_chunk = 8 * (llin * llin + llog * llog)
        max_chunks = max(1, int(512 * 1024 * 1024 / max(1, bytes_per_chunk)))
        return max(1, min(threads, max_chunks))

    def _create_with_numba(self, params: dict, progress_callback: callable | None):
        if progress_callback:
            progress_callback(0.0)

        mat_lin, mat_lin_t, mat_log, mat_log_t = self._numba_creator.create_2d_fdc(
            macro_times=params["macro_times"],
            micro_times=params["micro_times"],
            dT_ticks=params["dT_ticks"],
            ddT_ticks=params["ddT_ticks"],
            Tstart_ticks=params["Tstart_ticks"],
            Tend_ticks=params["Tend_ticks"],
            tMin_over_tStep=params["tMin_over_tStep"],
            tMax_over_tStep=params["tMax_over_tStep"],
            lint_bin_factor=params["lint_bin_factor"],
            logt_imax=params["logt_imax"],
            build_lin=params["build_lin"],
            n_chunks=params["n_chunks"],
        )

        step = 1
        mat_lin_t = (mat_lin_t * step).astype(np.int64, copy=False)
        mat_log_t = (mat_log_t * step).astype(np.int64, copy=False)

        if progress_callback:
            progress_callback(1.0)

        self.logger.info(
            "2D-FDC creation complete via Numba. Processed %d photons.", params["n_photons"]
        )
        return mat_lin, mat_lin_t, mat_log, mat_log_t

    def _normalize_inputs(
        self,
        macro_times: np.ndarray,
        micro_times: np.ndarray,
        dT: float,
        ddT: float,
        tMin: float,
        tMax: float,
        logt_imax: int,
    ) -> dict:
        macro_times_int = self._ensure_int_array(macro_times, "macro_times")
        micro_times_int = self._ensure_int_array(micro_times, "micro_times")

        if macro_times_int.shape[0] != micro_times_int.shape[0]:
            raise ValueError("macro_times and micro_times must have same length")
        if macro_times_int.shape[0] == 0:
            raise ValueError("Input arrays cannot be empty")

        if np.any(macro_times_int[1:] < macro_times_int[:-1]):
            raise ValueError("macro_times must be sorted ascending for 2D-FDC creation")

        tMin_ticks = self._ensure_int_value(tMin, "tMin")
        tMax_ticks = self._ensure_int_value(tMax, "tMax")
        if tMax_ticks <= tMin_ticks:
            raise ValueError("tMax must be greater than tMin after conversion to ticks")

        if macro_times_int.shape[0] < 2:
            raise ValueError("macro_times must contain at least 2 photons for 2D-FDC")

        params = {
            "macro_times": macro_times_int,
            "micro_times": micro_times_int,
            "n_photons": macro_times_int.shape[0],
            "dT_ticks": self._ensure_int_value(dT, "dT", positive=True),
            "ddT_ticks": self._ensure_int_value(ddT, "ddT", positive=True),
            "Tstart_ticks": int(macro_times_int[0]),
            "Tend_ticks": int(macro_times_int[-1]),
            "tMin_ticks": tMin_ticks,
            "tMax_ticks": tMax_ticks,
            "logt_imax": int(max(2, logt_imax)),
        }

        params["tMin_over_tStep"] = tMin_ticks
        params["tMax_over_tStep"] = tMax_ticks

        return params

    def _ensure_int_array(self, array: np.ndarray, name: str) -> np.ndarray:
        arr = np.asanyarray(array)
        if not np.issubdtype(arr.dtype, np.integer):
            self.logger.warning("2D-FDC: %s provided as float; rounding to nearest tick.", name)
            arr = np.rint(arr).astype(np.int64)
        else:
            arr = arr.astype(np.int64, copy=False)
        return np.ascontiguousarray(arr)

    def _ensure_int_value(
        self,
        value: float,
        name: str,
        positive: bool = False,
        allow_zero: bool = False,
        minimum: int | None = None,
    ) -> int:
        if not isinstance(value, (int, np.integer)):
            if not np.isfinite(value):
                raise ValueError(f"{name} must be a finite number")
            self.logger.debug("2D-FDC: %s=%s rounded to nearest integer tick", name, value)
            value = int(round(value))
        else:
            value = int(value)

        if minimum is not None:
            value = max(value, minimum)

        if positive and value <= 0:
            raise ValueError(f"{name} must be positive in tick units")
        if not allow_zero and value == 0:
            value = 1 if positive else 0

        return value

    def create_short_delay_fdc(
        self,
        macro_times: np.ndarray,
        micro_times: np.ndarray,
        tMin: float = 1.0,
        tMax: float = 12.0,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Create a short-delay 2D-FDC matrix (dT = minimum macro difference)."""
        macro_arr = self._ensure_int_array(macro_times, "macro_times")
        min_delay = np.min(np.diff(macro_arr))
        return self.create_2d_fdc(
            macro_arr,
            self._ensure_int_array(micro_times, "micro_times"),
            dT=min_delay,
            ddT=max(1, min_delay // 2),
            tMin=tMin,
            tMax=tMax,
        )[:2]
