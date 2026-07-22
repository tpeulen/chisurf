"""Shared IRF helpers for the MLE consumers.

The sub-bin IRF shift used to prepare a VV/VH instrument response was copied
verbatim into the burst wizard, the pixel-wise imaging tool and the
molecule-wise imaging tool. This is the single canonical implementation they now
share.
"""

from __future__ import annotations

import numpy as np


def interpolate_shift(arr: np.ndarray | None, shift: int | float) -> np.ndarray:
    """Shift a 1-D array by ``shift`` bins, supporting fractional shifts.

    The integer part is applied with :func:`numpy.roll` (zero-padded on the
    vacated side); the fractional part is applied by linear interpolation.

    Parameters
    ----------
    arr : numpy.ndarray or None
        Input array (e.g. an IRF histogram). ``None`` or empty returns an empty
        ``float64`` array.
    shift : int or float
        Number of bins to shift (positive rightwards, negative leftwards).

    Returns
    -------
    numpy.ndarray
        Shifted ``float64`` array, zero-filled. For arrays shorter than two
        points only the integer shift is applied (fractional interpolation is
        skipped to avoid ``numpy.interp`` edge cases).
    """
    if arr is None:
        return np.array([], dtype=np.float64)

    result = np.asarray(arr, dtype=np.float64).copy()
    n = result.size
    if n == 0 or shift == 0:
        return result

    int_shift = int(np.trunc(shift))
    if int_shift != 0:
        result = np.roll(result, int_shift)
        if int_shift > 0:
            result[:int_shift] = 0.0
        else:
            result[int_shift:] = 0.0

    frac_shift = shift - int_shift
    if frac_shift != 0 and n >= 2:
        x = np.arange(result.size)
        result = np.interp(x - frac_shift, x, result, left=0.0, right=0.0)

    return result
