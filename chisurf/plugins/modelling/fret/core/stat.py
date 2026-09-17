"""PMI ``stat.*.out`` files, for live docking progress and score curves.

Both readers are ``IMP.bff``'s, in C++: the format is a docking run's output
and reading it is not this application's business. This module is the name
the plugin imports them under.
"""

from __future__ import annotations


def count_frames(stat_path) -> int:
    """Completed frames recorded in a PMI ``stat.*.out``.

    Parameters
    ----------
    stat_path : str or pathlib.Path
        The stat file.

    Returns
    -------
    int
        The number of frames, or ``0`` for a missing or unreadable file --
        a progress bar asking how far a job has got wants a number.
    """
    import IMP.bff as bff

    return int(bff.count_frames(str(stat_path)))


def read_score_series(stat_path) -> tuple[list[float], list[float]]:
    """``(frames, scores)`` from a PMI stat file or a ``frame,score`` CSV.

    Parameters
    ----------
    stat_path : str or pathlib.Path
        The stat file, or a two-column CSV.

    Returns
    -------
    tuple of list of float
        The frame indices and the total scores. A partial file from a
        running job is fine, and so is a line that does not parse.
    """
    import IMP.bff as bff

    series = bff.read_score_series(str(stat_path))
    # Two values per point: frame, then score.
    flat = list(series)
    return flat[0::2], flat[1::2]


__all__ = ["count_frames", "read_score_series"]
