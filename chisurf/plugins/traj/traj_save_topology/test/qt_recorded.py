"""Qt-reference helpers for the trajectory tools' parity tests.

The Qt widgets are retired; their recorded answers live in each plugin's
``qt_reference.json``. A trajectory the Qt tool wrote is stored as a coordinate
summary (shape plus a sample), which :func:`same_coordinates` compares against.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np


def summarize(xyz) -> dict:
    """Return the shape and a sample of a ``(frames, atoms, 3)`` coordinate array.

    Parameters
    ----------
    xyz : array_like
        Coordinates.

    Returns
    -------
    dict
        ``shape`` and ``sample`` (every ``n//6``-th frame at every 97th atom).
    """
    xyz = np.asarray(xyz)
    return {"shape": list(xyz.shape), "sample": xyz[:: max(1, len(xyz) // 6), ::97].tolist()}


def same_coordinates(xyz, summary: dict, atol: float = 1e-4) -> bool:
    """Return whether *xyz* has the recorded shape and sample.

    Parameters
    ----------
    xyz : array_like
        Coordinates from the native tool.
    summary : dict
        A :func:`summarize` record of the Qt tool's output.
    atol : float
        Absolute tolerance.

    Returns
    -------
    bool
    """
    xyz = np.asarray(xyz)
    if list(xyz.shape) != summary["shape"]:
        return False
    sample = xyz[:: max(1, len(xyz) // 6), ::97]
    return bool(np.allclose(sample, np.asarray(summary["sample"]), atol=atol))


def load_reference(test_dir) -> dict:
    """Load ``qt_reference.json`` beside a plugin's tests.

    Parameters
    ----------
    test_dir : str or pathlib.Path
        The plugin's ``test`` directory.

    Returns
    -------
    dict
    """
    return json.loads((Path(test_dir) / "qt_reference.json").read_text())
