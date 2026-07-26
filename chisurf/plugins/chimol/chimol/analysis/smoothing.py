"""Window-averaging a trajectory, as PyMOL's ``smooth`` does.

Transcribed from ``layer3/Executive.cpp::ExecutiveSmooth``. Used to suppress
high-frequency vibration in a molecular-dynamics trajectory so a movie shows the
motion rather than the noise.

Four details are not guessable from the command's help and all four change the
result:

* the half-windows are ``window / 2`` in **integer** arithmetic, taken
  independently as ``backward`` and ``forward``. An even window is therefore
  asymmetric in effect -- ``window=4`` averages two back and two forward over
  five states, not four;
* ``ends`` is not a flag but a four-way choice, and it sets how many states at
  each end are left alone: ``0`` skips one, ``1`` skips none, ``2`` skips a whole
  half-window, ``3`` wraps the trajectory around;
* the average divides by how many states were actually **found**, not by the
  window size, so a state near an unskipped end is averaged over the part of the
  window that exists;
* ``cutoff`` guards against a jump. When one step exceeds it the sum stops
  extending and is padded with the last good position, which keeps an atom that
  crosses a periodic boundary from being averaged with its own image.
"""

from __future__ import annotations

import numpy as np

__all__ = ["END_MODES", "smooth_frames"]

#: ``ends`` -> how many states at each end to leave untouched, and whether the
#: trajectory wraps. Straight from the ``switch (ends)`` in ExecutiveSmooth.
END_MODES: dict[int, tuple[str, bool]] = {
    0: ("one", False),
    1: ("none", False),
    2: ("half_window", False),
    3: ("none", True),
}


def smooth_frames(
    frames: np.ndarray,
    *,
    passes: int = 1,
    window: int = 5,
    first: int = 0,
    last: int | None = None,
    ends: int = 0,
    cutoff: float = -1.0,
    mask: np.ndarray | None = None,
) -> np.ndarray:
    """Return ``frames`` with a running average applied over the state axis.

    Parameters
    ----------
    frames : numpy.ndarray
        ``(T, N, 3)`` coordinates.
    passes : int, optional
        How many times to apply the average. Each pass reads the previous
        pass's output, as PyMOL's cycle loop does, so two passes are not the
        same as one wider window.
    window : int, optional
        Total window width; must be at least 2.
    first, last : int, optional
        State range to smooth, inclusive. ``last=None`` means the final state.
    ends : int, optional
        0 leaves one state at each end alone, 1 smooths to the very ends,
        2 leaves a half-window, 3 wraps the trajectory.
    cutoff : float, optional
        Maximum distance an atom may move between consecutive states before the
        window stops extending. Negative disables the check.
    mask : numpy.ndarray, optional
        Boolean over atoms; only these are smoothed, the rest are copied.

    Returns
    -------
    numpy.ndarray
        A new ``(T, N, 3)`` array. The input is never modified.

    Raises
    ------
    ValueError
        When the window is smaller than 2, or the state range is shorter than
        the window -- PyMOL refuses both rather than quietly doing nothing.
    """
    arr = np.array(frames, dtype=float, copy=True)
    if arr.ndim != 3 or arr.shape[2] != 3:
        raise ValueError("frames must have shape (T, N, 3)")

    n_states = arr.shape[0]
    if last is None or last < 0:
        last = n_states - 1
    first = max(0, int(first))
    last = min(int(last), n_states - 1)
    if last < first:
        first, last = last, first

    window = int(window)
    if abs(window) < 2:
        raise ValueError("window must be at least size 2")

    span = last - first + 1
    if span < abs(window):
        raise ValueError(
            f"the state range holds {span} states, fewer than the window ({abs(window)})"
        )

    backward = abs(window) // 2
    forward = abs(window) // 2

    mode, loop = END_MODES.get(int(ends), ("none", False))
    end_skip = {"one": 1, "none": 0, "half_window": backward}[mode]

    atoms = (
        np.ones(arr.shape[1], dtype=bool) if mask is None
        else np.asarray(mask, dtype=bool)
    )
    if not atoms.any():
        return arr

    cutoff_sq = float(cutoff) ** 2 if float(cutoff) > 0 else -1.0

    for _pass in range(max(1, int(passes))):
        source = arr.copy()
        for state in range(first + end_skip, last - end_skip + 1):
            arr[state, atoms] = _average_one_state(
                source, state, first, last, backward, forward, loop, atoms, cutoff_sq
            )
    return arr


def _average_one_state(
    source: np.ndarray,
    state: int,
    first: int,
    last: int,
    backward: int,
    forward: int,
    loop: bool,
    atoms: np.ndarray,
    cutoff_sq: float,
) -> np.ndarray:
    """The inner window sum for one state, divided by what was found.

    Kept separate because the count is the subtle part: dividing by the window
    width instead of the number of contributing states pulls a state near an
    unskipped end towards the origin, which reads as the trajectory collapsing
    at its ends.
    """
    span = last - first + 1
    total = np.zeros((int(atoms.sum()), 3), dtype=float)
    count = 0
    previous: np.ndarray | None = None

    for offset in range(-backward, forward + 1):
        index = state + offset
        if loop:
            index = first + (index - first) % span
        elif index < first or index > last:
            continue

        current = source[index, atoms]
        if cutoff_sq > 0 and count and previous is not None:
            moved = np.sum((current - previous) ** 2, axis=1)
            if bool(np.any(moved > cutoff_sq)):
                # A jump: stop extending and pad with the last good state, so an
                # atom that crossed a boundary is not averaged with its image.
                remaining = forward - offset + 1
                total += previous * remaining
                count += remaining
                break
        total += current
        count += 1
        previous = current

    if count == 0:
        return source[state, atoms]
    return total / float(count)
