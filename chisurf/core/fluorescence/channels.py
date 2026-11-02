"""Which photons a detector's routing channels select -- fast, for every burst tool.

``np.isin(routing, channels)`` sorts and searches the whole photon stream; with routing channels
being small integers a lookup table answers the same question in one gather, about ten times
faster on tens of millions of photons. Every burst step selects photons by channel, often several
times per file, so this is where the pipeline's time went.
"""

from __future__ import annotations

import numpy as np

#: Above this channel number the table would be large: fall back to :func:`numpy.isin`.
_MAX_LUT = 1 << 16


def channel_mask(routing, channels) -> np.ndarray:
    """Boolean mask of the photons whose routing channel is one of *channels*.

    Parameters
    ----------
    routing : array_like of int
        Routing channel per photon.
    channels : iterable of int
        The detector's channels.

    Returns
    -------
    numpy.ndarray of bool
        Same shape as *routing*; equal to ``np.isin(routing, channels)``.
    """
    routing = np.asarray(routing)
    chs = np.asarray(list(channels) if not isinstance(channels, np.ndarray) else channels).ravel()
    if routing.size == 0 or chs.size == 0:
        return np.zeros(routing.shape, dtype=bool)
    if routing.dtype.kind not in "iu" or chs.dtype.kind not in "iu":
        return np.isin(routing, chs)
    lo = int(routing.min()) if routing.dtype.kind == "i" else 0
    hi = int(routing.max())
    if lo < 0 or hi >= _MAX_LUT:
        return np.isin(routing, chs)
    lut = np.zeros(hi + 1, dtype=bool)
    chs = chs[(chs >= 0) & (chs <= hi)]
    lut[chs.astype(np.int64)] = True
    return lut[routing]
