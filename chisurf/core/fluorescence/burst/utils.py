"""
Utility functions for burst detection and analysis.

This module contains common utility functions used by various burst detection
algorithms in the chisurf package.
"""

import numpy as np


def _fill_intervals(arr: np.ndarray, starts: np.ndarray, stops: np.ndarray) -> None:
    """Set ``arr[start:stop]`` to ``True`` for every ``(start, stop)`` pair.

    Parameters
    ----------
    arr : numpy.ndarray
        Boolean array, modified in place.
    starts, stops : numpy.ndarray
        Interval bounds; ``stop`` is exclusive.

    Notes
    -----
    Written as a difference array (``+1`` at each start, ``-1`` at each stop,
    then a running sum) rather than a loop of slice assignments, so the cost is
    one pass over ``arr`` regardless of how many intervals there are — a burst
    search can return tens of thousands. Overlapping intervals are handled by
    construction, and existing ``True`` values are preserved: the mask is
    OR-ed in, not assigned over.
    """
    if len(starts) == 0:
        return
    delta = np.zeros(arr.shape[0] + 1, dtype=np.intp)
    np.add.at(delta, starts, 1)
    np.add.at(delta, stops, -1)
    arr[np.cumsum(delta[:-1]) > 0] = True


def create_array_with_ones(start_stop_pairs: np.ndarray, length: int) -> np.ndarray:
    """
    Create a boolean array of the given length, set to True (1)
    in the intervals [start, stop) defined by start_stop_pairs.

    Parameters
    ----------
    start_stop_pairs : np.ndarray
        Array of shape (n, 2) containing start and stop indices.
        Each row is a pair [start, stop] defining an interval.
    length : int
        Length of the output array.

    Returns
    -------
    np.ndarray
        Boolean array of length `length` with True values in the
        intervals defined by `start_stop_pairs`.
    """
    arr = np.zeros(length, dtype=bool)
    if len(start_stop_pairs) == 0:
        return arr
    pairs = np.asarray(start_stop_pairs, dtype=np.intp)
    _fill_intervals(arr, pairs[:, 0], pairs[:, 1])
    return arr
