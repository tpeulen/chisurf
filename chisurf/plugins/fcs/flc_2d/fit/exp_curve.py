"""The exponential basis of the original 2D-FLC fits, integrated over each matrix bin.

Port of ``TK_ExpMultiDeco_For2DFLC.m`` and ``TK_CreateExpCurve.m`` (T. Kondo,
Schlau-Cohen lab, MIT).

``exp_multi_deco`` convolves ``exp(-t/tau)`` with the instrument response on the TCSPC
channel grid. The IRF is placed by two **rise points** (1-based channel indices, as in
the MATLAB): IRF channel ``I`` lands on data channel ``I - (rise_point_irf -
rise_point_fl)``, and only IRF channels ``irf_range[0]..irf_range[1]`` contribute. The
IRF is used as given -- baseline-subtracted, negative samples included -- and the whole
basis is divided by its **single** largest element, not column by column.

``create_exp_curve`` crops that basis to the micro-time gate and **sums** it over the
bins of the linear and logarithmic 2D-FDC axes. The fits then compare binned counts
with a binned model.

This differs from :func:`chisurf.plugins.fcs.flc_2d.fit.ilt.build_exp_basis`, which
*samples* each column at the bin position, removes an IRF baseline and clips it at
zero, and normalizes every column to 1. Measured with the reference IRF, gate
0.5-12.2 ns, 4 ps channels, factor 4, 100 log bins, tau 0.05-5.05 ns (residual norm
of each column after its best scale, relative to the column):

* same convolution, sampled at the bin centre instead of summed: **linear <= 0.7%**,
  **log median 43%, max 50%** -- a log bin spans one channel to hundreds, so sampling
  misweights short against long lifetimes by the bin width;
* ``build_exp_basis`` against this basis: linear median 3.8% (the IRF baseline and
  clipping convention), log median 30%, max 84%.

So the plugin's own inversions, which run on the linear (block-rebinned) matrix, are
within a few percent of the reference model, and a **log-binned matrix must be fitted
with ``binned_log``** -- :func:`~chisurf.plugins.fcs.flc_2d.api.two_d_spectrum` refuses a
non-uniform axis without an explicit basis.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = [
    "ExpCurves",
    "exp_multi_deco",
    "create_exp_curve",
    "matlab_lin_axis_ns",
    "matlab_log_axis_ns",
    "basis_fft_hwhm",
]


@dataclass
class ExpCurves:
    """The three bases ``TK_CreateExpCurve`` returns (columns follow ``tau``)."""

    full: np.ndarray  # (n_channels_in_gate, n_tau): cropped, per channel
    binned_lin: np.ndarray  # (n_lin_bins, n_tau)
    binned_log: np.ndarray  # (n_log_bins, n_tau)


def matlab_lin_axis_ns(
    t_min_ns: float, t_max_ns: float, t_step_ns: float, lint_bin_factor: int
) -> np.ndarray:
    """``Mat_2DFDC_lint`` of ``TK_Create2DFDC_04`` after its trim (ns)."""
    f = int(lint_bin_factor)
    t_imax = int(np.ceil((t_max_ns - t_min_ns) / t_step_ns)) + f
    lint_imax = -(-t_imax // f)
    return (f * t_step_ns) * np.arange(lint_imax - 1, dtype=float)


def matlab_log_axis_ns(
    t_min_ns: float, t_max_ns: float, t_step_ns: float, lint_bin_factor: int, logt_imax: int
) -> np.ndarray:
    """``Mat_2DFDC_logt`` of ``TK_Create2DFDC_04`` after its trim (ns, real-valued)."""
    f = int(lint_bin_factor)
    t_imax = int(np.ceil((t_max_ns - t_min_ns) / t_step_ns)) + f
    t_imax = (-(-t_imax // f)) * f
    L = int(logt_imax)
    return t_imax ** (np.arange(L, dtype=float) / L) * t_step_ns - t_step_ns


def exp_multi_deco(
    tau_ns: np.ndarray,
    xdata_ns: np.ndarray,
    irf: np.ndarray,
    *,
    rise_point_fl: int,
    rise_point_irf: int,
    irf_range: tuple[int, int],
) -> np.ndarray:
    """IRF-convolved exponentials on the channel grid (``TK_ExpMultiDeco_For2DFLC``).

    Parameters
    ----------
    tau_ns
        Lifetimes (ns), one column each.
    xdata_ns
        Channel times (ns); the decays start at ``xdata_ns[0]``.
    irf
        Instrument response per channel, same grid as ``xdata_ns``.
    rise_point_fl, rise_point_irf
        1-based rise channels of the fluorescence and of the IRF; their difference
        shifts the IRF.
    irf_range
        1-based, inclusive IRF channels that are convolved.

    Returns ``(n_channels, n_tau)``, divided by its largest element.
    """
    x = np.asarray(xdata_ns, dtype=float)
    irf = np.asarray(irf, dtype=float)
    n = x.size
    idev = int(rise_point_irf) - int(rise_point_fl)
    lo, hi = int(irf_range[0]), int(irf_range[1])
    shifts = np.arange(lo, hi + 1) - idev  # 1-based data channel of each IRF sample
    if shifts.min() < 1:
        raise ValueError("the shifted IRF range starts before the first data channel")
    keep = shifts <= n
    start = int(shifts[keep].min()) - 1
    kernel = np.zeros(int(shifts[keep].max()) - start)
    np.add.at(kernel, shifts[keep] - 1 - start, irf[np.arange(lo, hi + 1)[keep] - 1])
    out = np.zeros((n, np.size(tau_ns)))
    for j, tau in enumerate(np.atleast_1d(tau_ns)):
        decay = np.exp(-1.0 / float(tau) * (x - x[0]))
        # only the IRF's support is convolved; the zeros around it cost O(n^2) otherwise
        out[start:, j] = np.convolve(kernel, decay[: n - start])[: n - start]
    return out / out.max()


def create_exp_curve(
    tau_ns: np.ndarray,
    xdata_ns: np.ndarray,
    irf: np.ndarray,
    *,
    t_min_ns: float,
    t_max_ns: float,
    t_step_ns: float,
    lint_bin_factor: int,
    log_axis_ns: np.ndarray,
    rise_point_fl: int,
    rise_point_irf: int,
    irf_range: tuple[int, int],
) -> ExpCurves:
    """Crop the convolved basis to the gate and bin it like the 2D-FDC (``TK_CreateExpCurve``).

    The linear bins sum ``lint_bin_factor`` channels; a last bin that runs past the gate
    is completed by repeating its final channels (the reference's mirror padding). A
    one-channel slice is summed across the lifetimes instead, as MATLAB's ``sum`` does
    on a row -- a defect of the reference at ``lint_bin_factor = 1`` that is reproduced,
    not fixed (fit on the log axis, as the reference does, or use a factor > 1). It also
    hits the reference's own default gate: 0.5-12.2 ns at factor 4 leaves one channel
    for the last linear bin, which then holds a sum over every lifetime. A
    log bin ``k`` collects the channels whose time since the gate start is in
    ``(log_axis_ns[k], log_axis_ns[k + 1]]``; everything past the last edge goes into
    the last bin. ``log_axis_ns`` is :func:`matlab_log_axis_ns`.
    """
    full = exp_multi_deco(
        tau_ns,
        xdata_ns,
        irf,
        rise_point_fl=rise_point_fl,
        rise_point_irf=rise_point_irf,
        irf_range=irf_range,
    )
    x = np.asarray(xdata_ns, dtype=float)
    v1 = int(np.round(t_min_ns / t_step_ns))  # 1-based rows, inclusive
    v2 = int(np.round(t_max_ns / t_step_ns))
    curve = full[v1 - 1 : v2]
    xs = x[v1 - 1 : v2] - x[v1 - 1]

    def msum(rows):
        # MATLAB's sum() of a single row sums *along* the row: a scalar, added to every
        # column. Kept: it is what the reference computes for a one-channel slice (every
        # bin at lint_bin_factor = 1, and a one-channel mirror pad).
        return rows.sum() if rows.shape[0] == 1 else rows.sum(axis=0)

    f = int(lint_bin_factor)
    imax = v2 - v1
    n_lin = -(-imax // f)
    lin = np.empty((n_lin, curve.shape[1]))
    for i in range(1, n_lin + 1):
        a, b = 1 + f * (i - 1), f * i
        if b <= imax:
            lin[i - 1] = msum(curve[a - 1 : b])
        else:
            lin[i - 1] = msum(curve[a - 1 : imax]) + msum(curve[imax - (b - imax) : imax])

    edges = np.asarray(log_axis_ns, dtype=float)
    k_max = edges.size
    log = np.zeros((k_max, curve.shape[1]))
    k = 2
    for i in range(curve.shape[0]):
        while k <= k_max and not xs[i] <= edges[k - 1]:
            k += 1
        log[k - 2] += curve[i]
    return ExpCurves(full=curve, binned_lin=lin, binned_log=log)


def basis_fft_hwhm(
    tau_ns: np.ndarray,
    irf: np.ndarray,
    *,
    rise_point_fl: int,
    rise_point_irf: int,
    irf_range: tuple[int, int],
    t_step_ns: float = 0.004,
    n_channels: int = 50_000,
) -> tuple[np.ndarray, np.ndarray]:
    """Spectral width of each basis column (``TK_MyMain_Exp_FFT_FWHM``).

    The IRF-convolved decays on a long grid (``n_channels`` at ``t_step_ns``) are
    Fourier transformed (``n = 2^nextpow2``), and the half width at half maximum of
    each power spectrum ``|Y|^2/n`` is found by linear interpolation after counting the
    frequencies above half maximum -- which assumes the spectrum falls monotonically,
    as a Lorentzian does. Returns ``(hwhm_GHz, hwhm_ns)`` with
    ``hwhm_ns = 1/(2 pi hwhm_GHz)``: the time scale a lifetime is resolved on once the
    IRF is folded in (for a bare exponential it is ``tau``).
    """
    x = np.arange(int(n_channels)) * float(t_step_ns)
    curves = exp_multi_deco(
        tau_ns,
        x,
        irf,
        rise_point_fl=rise_point_fl,
        rise_point_irf=rise_point_irf,
        irf_range=irf_range,
    )
    k = curves.shape[0]
    n = 1 << int(np.ceil(np.log2(k)))
    freq = (1.0 / t_step_ns) * np.arange(n // 2 + 1) / n
    power = np.abs(np.fft.fft(curves, n=n, axis=0)) ** 2 / n
    power = power[: n // 2 + 1]
    hwhm = np.empty(curves.shape[1])
    for j in range(curves.shape[1]):
        half = power[:, j].max() / 2.0
        m = int(np.sum(power[:, j] > half))  # 1-based index of the last point above
        frac = (power[m - 1, j] - half) / (power[m - 1, j] - power[m, j])
        hwhm[j] = freq[m - 1] + frac * (freq[m] - freq[m - 1])
    return hwhm, 1.0 / (2 * np.pi * hwhm)
