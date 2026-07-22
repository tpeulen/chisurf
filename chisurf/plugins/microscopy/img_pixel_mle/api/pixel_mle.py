"""Pure IRF-preparation helpers for pixel-wise MLE — no Qt at import time.

These functions prepare the parallel/perpendicular IRF histograms consumed by
the Qt-free core (:mod:`..core.pixel_mle`).  They are shared by the AutoForm
view-model, the RPC backend service and the CLI so the analysis runs without
starting Qt.
"""

from __future__ import annotations

import numpy as np

# The sub-bin IRF shift is shared with the burst and molecule-wise MLE tools.
from chisurf.core.fluorescence.mle.irf import interpolate_shift


def prepare_irf(
    irf_p: np.ndarray,
    irf_s: np.ndarray,
    *,
    threshold: float = -1.0,
    shift: int = 0,
    shift_sp: float = 0.0,
    shift_ss: float = 0.0,
    threshold_vv: float | None = None,
    threshold_vh: float | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Prepare parallel and perpendicular IRF arrays.

    Applies per-channel thresholding, normalisation and sub-bin shifts.

    Parameters
    ----------
    irf_p, irf_s:
        Raw parallel / perpendicular IRF histograms.
    threshold:
        Default fraction of the maximum below which bins are zeroed.
    shift:
        Integer relative shift of the perpendicular channel.
    shift_sp, shift_ss:
        Sub-bin (fractional) shifts applied to each channel independently.
    threshold_vv, threshold_vh:
        Per-channel overrides for the threshold fraction.

    Returns
    -------
    tuple[ndarray, ndarray]
        Prepared (irf_p, irf_s) arrays.
    """
    irf_p = irf_p.astype(np.float64).copy()
    irf_s = irf_s.astype(np.float64).copy()

    t_p = threshold_vv if threshold_vv is not None else threshold
    t_s = threshold_vh if threshold_vh is not None else threshold
    if t_p is not None and t_p > 0 and irf_p.size:
        irf_p[irf_p < t_p * irf_p.max()] = 0.0
    if t_s is not None and t_s > 0 and irf_s.size:
        irf_s[irf_s < t_s * irf_s.max()] = 0.0

    sp = irf_p.sum()
    if sp > 0:
        irf_p /= sp
    ss = irf_s.sum()
    if ss > 0:
        irf_s /= ss

    irf_p = interpolate_shift(irf_p, shift_sp)
    irf_s = interpolate_shift(irf_s, shift_ss)

    if shift != 0:
        irf_s = np.roll(irf_s, shift)
        if shift > 0:
            irf_s[:shift] = 0.0
        else:
            irf_s[shift:] = 0.0

    return irf_p, irf_s
