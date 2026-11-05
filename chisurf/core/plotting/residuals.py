"""The range of a weighted-residual axis: symmetric about zero, always (toolkit-free).

The drawing half of the rule -- strip above the data, one x-axis, a thick zero line -- is
:mod:`chisurf.emtk.residual_plot`; this is the number both drawing paths and the MLE display
(:func:`chisurf.core.fluorescence.mle.display.residual_ylim`) take the range from.
"""

from __future__ import annotations

from typing import Any

import numpy as np


def symmetric_limit(
    values: Any,
    *,
    percentile: float = 100.0,
    pad: float = 1.08,
    minimum: float = 0.0,
) -> float:
    """The half-height ``r`` of a residual axis drawn ``-r .. r``.

    Parameters
    ----------
    values : array-like or sequence of array-like
        The residuals shown (every trace); NaN and inf are ignored.
    percentile : float
        ``100`` takes ``max |wres|`` (every point visible); below 100 a robust reach that
        lets one spike leave the strip rather than flatten everything else.
    pad : float
        Headroom factor, so the extreme point does not sit on the frame.
    minimum : float
        The smallest reach returned (e.g. ``3`` for residuals in units of sigma, so a
        perfect fit does not blow noise up to the full strip).

    Returns
    -------
    float
        A finite, positive reach; ``1.0`` (or *minimum*) when there is nothing finite.
    """
    if isinstance(values, (list, tuple)):
        parts = [np.ravel(np.asarray(v, dtype=float)) for v in values]
        flat = np.concatenate(parts) if parts else np.zeros(0)
    else:
        flat = np.ravel(np.asarray(values, dtype=float))
    flat = np.abs(flat[np.isfinite(flat)])
    if flat.size == 0:
        return float(max(minimum, 1.0))
    reach = float(flat.max() if percentile >= 100.0 else np.percentile(flat, percentile))
    reach *= float(pad)
    if not np.isfinite(reach) or reach <= 0.0:
        reach = 1.0
    return float(max(reach, minimum))
