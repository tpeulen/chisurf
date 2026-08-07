"""Summary statistics for burst-selection results."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from chisurf.plugins.burst.burst_selection.api.features import _names, _rows


def summarize_dataframes(frames: Sequence) -> dict[str, float]:
    """Compute summary statistics for burst summary tables.

    Parameters
    ----------
    frames : sequence of mapping or pandas.DataFrame
        Burst summary tables. Anything column-addressable — a frame, a
        ``{name: array}`` mapping, a columnar store — since none of the
        arithmetic here depends on which.

    Returns
    -------
    dict
        Summary statistics.
    """
    n_bursts = sum(_rows(frame) for frame in frames)
    n_photons = sum(
        float(np.asarray(frame["nphotons"], dtype=float).sum())
        for frame in frames
        if "nphotons" in _names(frame)
    )
    durations = [
        np.asarray(frame["duration"], dtype=float)
        for frame in frames
        if "duration" in _names(frame)
    ]
    brightness = [
        np.asarray(frame["nphotons"], dtype=float)
        / np.maximum(np.asarray(frame["duration"], dtype=float), np.finfo(float).eps)
        for frame in frames
        if "nphotons" in _names(frame) and "duration" in _names(frame)
    ]
    all_durations = np.concatenate(durations) if durations else np.array([], dtype=float)
    all_brightness = np.concatenate(brightness) if brightness else np.array([], dtype=float)

    return {
        "n_bursts": float(n_bursts),
        "n_photons": float(n_photons),
        "mean_duration": float(np.mean(all_durations)) if len(all_durations) else np.nan,
        "std_duration": float(np.std(all_durations)) if len(all_durations) else np.nan,
        "mean_brightness": float(np.mean(all_brightness)) if len(all_brightness) else np.nan,
        "std_brightness": float(np.std(all_brightness)) if len(all_brightness) else np.nan,
    }
