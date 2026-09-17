"""Qt-free helpers to run lifetime-filtered species correlations in the correlator.

Wraps the channel-aware species-filtered correlation core
(:func:`chisurf.core.fluorescence.fcs.filtered.species_filtered_correlation`)
and emits the correlator's result-dict format (``{x, y, ...}``, lags in ms) so
the GUI/merger can turn the species auto-/cross-correlation matrix into datasets.
This keeps the correlation math testable without Qt; the GUI is a thin caller.
"""

from __future__ import annotations

import numpy as np

from chisurf.core.fluorescence.fcs.filtered import species_filtered_correlation

__all__ = ["filtered_correlation_datasets", "filtered_correlation_from_tttr"]


def filtered_correlation_datasets(
    macro_times,
    micro_times,
    filters,
    macro_time_resolution_s: float,
    *,
    routing_channels=None,
    n_bins: int = 8,
    n_casc: int = 25,
    labels=None,
) -> list[dict]:
    """Species auto/cross correlations as correlator result dicts (lags in ms).

    Parameters
    ----------
    macro_times, micro_times : array_like
        Photon macro-times (ticks) and micro-time (TAC) indices.
    filters : array_like or dict
        Lifetime filters — 2-D ``(n_species, n_bins)``, 3-D
        ``(n_channels, n_species, n_bins)``, or ``{channel: 2-D}`` (channel-aware).
    macro_time_resolution_s : float
        Seconds per macro-time tick.
    routing_channels : array_like, optional
        Per-photon routing channels (used only for channel-aware filters).
    n_bins, n_casc : int, optional
        Multi-tau correlator settings.
    labels : sequence of str, optional
        Species labels used in the dataset names.

    Returns
    -------
    list of dict
        One dict per species pair with keys ``x`` (ms), ``y``, ``species_a``,
        ``species_b`` and ``name``. Auto-correlations come first.
    """
    result = species_filtered_correlation(
        macro_times,
        micro_times,
        filters,
        macro_time_resolution_s,
        routing_channels=routing_channels,
        n_bins=n_bins,
        n_casc=n_casc,
        labels=labels,
    )
    lag_ms = (np.asarray(result.lag_s, dtype=float) * 1000.0).tolist()
    names = result.labels
    out: list[dict] = []
    for i, g in result.auto.items():
        out.append(
            {
                "x": lag_ms,
                "y": np.asarray(g, dtype=float).tolist(),
                "species_a": i,
                "species_b": i,
                "name": f"{names[i]} × {names[i]}",
            }
        )
    for (i, j), g in result.cross.items():
        out.append(
            {
                "x": lag_ms,
                "y": np.asarray(g, dtype=float).tolist(),
                "species_a": i,
                "species_b": j,
                "name": f"{names[i]} × {names[j]}",
            }
        )
    return out


def filtered_correlation_from_tttr(tttr, filters, settings: dict, *, labels=None) -> list[dict]:
    """Run :func:`filtered_correlation_datasets` from a ``tttrlib.TTTR`` object.

    Parameters
    ----------
    tttr : tttrlib.TTTR
        Photon stream (provides macro/micro times, routing channels, resolution).
    filters : array_like or dict
        Lifetime filters (see :func:`filtered_correlation_datasets`).
    settings : dict
        Correlator settings; ``n_bins`` and ``n_casc`` are read.
    labels : sequence of str, optional
        Species labels.

    Returns
    -------
    list of dict
    """
    return filtered_correlation_datasets(
        np.asarray(tttr.macro_times),
        np.asarray(tttr.micro_times),
        filters,
        float(tttr.header.macro_time_resolution),
        routing_channels=np.asarray(tttr.routing_channels),
        n_bins=int(settings.get("n_bins", 8)),
        n_casc=int(settings.get("n_casc", 25)),
        labels=labels,
    )
