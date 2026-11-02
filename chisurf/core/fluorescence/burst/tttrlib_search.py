"""Registry-driven access to tttrlib's burst searches.

The other filters in this package each wrap one tttrlib call with a fixed
signature, so adding an algorithm to tttrlib means adding a wrapper here, a
settings dataclass, a dispatch branch and a row of GUI widgets. This module
removes that chain: tttrlib publishes its burst searches — names, defaults,
types and ranges — in its registry, and everything downstream is generated from
that description.

This module is the burst-search view of :mod:`chisurf.core.registry.tttrlib`,
which reads the registry generally (burst searches, file containers, and
whatever tttrlib adds next) and absorbs version differences. The parameter
description is JSON Schema, which chisurf already renders, so the GUI for a
burst search is built with no algorithm-specific code::

    from chisurf.core.registry import tttrlib as tttrlib_registry

    view = tttrlib_registry.entry_form_view("burst_search", "maxtree")
    view.view_spec()  # the sections an emtk form draws

A new algorithm in tttrlib therefore appears in the interface on upgrade, with
no change here.
"""

from __future__ import annotations

import logging
import typing

import numpy as np
import tttrlib

from chisurf.core.registry import tttrlib as tttrlib_registry

logger = logging.getLogger(__name__)

#: Fraction of the stream above which a "burst" result is not a burst result.
#: Real single-molecule data selects some tens of percent; selecting nearly
#: everything means the search degenerated rather than found something.
IMPLAUSIBLE_COVERAGE = 0.7
from chisurf.core.fluorescence.burst.utils import create_array_with_ones


def algorithms() -> dict[str, dict[str, typing.Any]]:
    """The burst searches tttrlib advertises, keyed by algorithm name.

    A thin view onto the ``burst_search`` category of
    :mod:`chisurf.core.registry.tttrlib`, which is where version differences and
    the fallback for older tttrlib builds are handled. Returns an empty dict when
    no registry is published, so callers can fall back to chisurf's own filters.

    Returns
    -------
    dict
        ``{name: {"name", "label", "summary", "description", "method",
        "params_schema"}}``.
    """
    return tttrlib_registry.entries(tttrlib_registry.BURST_SEARCH)


def is_available() -> bool:
    """Whether the installed tttrlib publishes a burst-search registry."""
    return tttrlib_registry.is_available(tttrlib_registry.BURST_SEARCH)


def defaults(algorithm: str) -> dict[str, typing.Any]:
    """Default parameters of ``algorithm`` as a ``{name: value}`` dict."""
    return tttrlib_registry.defaults(tttrlib_registry.BURST_SEARCH, algorithm)


def describe(algorithm: str) -> dict[str, typing.Any]:
    """Registry entry for ``algorithm``.

    Raises
    ------
    ValueError
        If the algorithm is unknown, naming the available alternatives.
    """
    return tttrlib_registry.describe(tttrlib_registry.BURST_SEARCH, algorithm)


def search(
    tttr: tttrlib.TTTR,
    algorithm: str,
    parameters: typing.Mapping[str, typing.Any] | None = None,
) -> np.ndarray:
    """Run a burst search by name and return its burst boundaries.

    Parameters
    ----------
    tttr : tttrlib.TTTR
        Photon data to search.
    algorithm : str
        Key from :func:`algorithms`, e.g. ``"sliding_window"`` or ``"maxtree"``.
    parameters : mapping, optional
        Parameter overrides. Anything omitted takes its registry default, so a
        GUI only has to send the values the user actually touched.

    Returns
    -------
    np.ndarray
        ``(n, 2)`` array of inclusive ``[start, stop]`` photon indices.
    """
    describe(algorithm)  # reject an unknown name before touching the data
    parameters = dict(parameters or {})
    detectors = parameters.pop(SEARCH_DETECTORS, None)
    if algorithm == "cusum_sprt" and detectors:
        return _search_detectors(tttr, algorithm, parameters, detectors)
    if algorithm == "cusum_sprt" and float(parameters.get("background_cps") or 0.0) <= 0.0:
        # tttrlib's own estimate is the median rate of 100-photon bins: a burst packs many such
        # bins into little time, so the estimate drifts up toward burst rates. Pass the
        # inter-photon-gap estimate instead (the CUSUM's "0 = estimate from the data").
        estimate = estimate_background_cps(tttr)
        if estimate > 0:
            parameters["background_cps"] = estimate
    return tttr.burst_search_by_name(algorithm, **parameters)


#: Search parameter naming the detectors whose photons a CUSUM/SPRT search runs on, as
#: ``{name: {"chs": [...], "micro_time_ranges": [...]}}``. Taken out before tttrlib sees the
#: parameters; it travels with them so the search, its preview and its fingerprint all see it.
SEARCH_DETECTORS = "_detectors"


def _detector_mask(tttr: typing.Any, detectors: typing.Mapping[str, typing.Any]) -> np.ndarray:
    """The photons of *detectors*: their channels, inside their micro-time gates."""
    from tttrlib import micro_time_mask

    from chisurf.core.fluorescence.channels import channel_mask

    routing = np.asarray(tttr.routing_channels)
    micro = np.asarray(tttr.micro_times)
    mask = np.zeros(routing.shape, dtype=bool)
    for det in detectors.values():
        chs = list((det or {}).get("chs") or [])
        if chs:
            mask |= channel_mask(routing, chs) & np.asarray(
                micro_time_mask(micro, (det or {}).get("micro_time_ranges")), dtype=bool
            )
    return mask


def channel_streams(detectors: typing.Mapping[str, typing.Any]) -> dict:
    """*detectors* split into one stream per routing channel (``"ch1"``), each inside its
    detector's micro-time gates -- the streams the Background tool fits. A channel two detectors
    gate differently (PIE's prompt and delayed) stays two streams."""
    out: dict = {}
    for name, det in detectors.items():
        gates = [list(r) for r in (det or {}).get("micro_time_ranges") or []]
        for ch in (det or {}).get("chs") or []:
            key = f"ch{int(ch)}"
            if key in out and out[key]["micro_time_ranges"] != gates:
                key = f"ch{int(ch)} ({name})"
            out[key] = {"chs": [int(ch)], "micro_time_ranges": gates}
    return out


def detector_backgrounds_cps(tttr: typing.Any, detectors: typing.Mapping[str, typing.Any]) -> dict:
    """Background count rate (counts/s) of each routing channel of *detectors*, as the Background
    tool estimates it: ``{"ch0": cps, ...}``.

    One stream per channel (:func:`channel_streams`), one fit window for all of them
    (:func:`~chisurf.core.fluorescence.burst.background.seed_tail_window`) and an exponential fit
    of each one's tail in it (:func:`~chisurf.core.fluorescence.burst.background.
    interphoton_time_diagnostics`). Per channel, not per detector: fitting a detector's channels
    as one stream moves the shared window and gave other numbers than the tool (DNA13bp_3: 2.25
    kcps for green 0+2 and red 1 against the tool's 3.317 over ch0-ch3).
    """
    from chisurf.core.fluorescence.burst import background as bg

    scale = float(tttr.header.macro_time_resolution) * 1e3  # ticks -> ms
    gaps = {
        name: bg._detector_interphoton_times(tttr, det, scale)
        for name, det in channel_streams(detectors).items()
    }
    usable = [g for g in gaps.values() if g.size > 1]
    window = bg.seed_tail_window(usable, binsize_ms=0.1, min_counts=1) if usable else None
    out = {}
    for name, dt in gaps.items():
        if dt.size < 2:
            out[name] = 0.0
            continue
        fit = bg.interphoton_time_diagnostics(
            dt, binsize_ms=0.1, tail_fraction=0.8, min_counts=1, tail_range_ms=window
        )
        out[name] = max(0.0, float(fit.rate_khz) * 1e3)
    return out


def _search_detectors(tttr, algorithm: str, parameters: dict, detectors) -> np.ndarray:
    """*algorithm* on the photons of *detectors* only, its background theirs; full-stream indices.

    The background rate a CUSUM tests against is the rate of the photons it reads: the detectors
    the bursts are selected on, not every channel of the file. ``0`` is their sum as the
    Background tool estimates it.
    """
    index = np.flatnonzero(_detector_mask(tttr, detectors))
    if index.size < 2:
        return np.zeros((0,), dtype=np.int64)
    if float(parameters.get("background_cps") or 0.0) <= 0.0:
        total = sum(detector_backgrounds_cps(tttr, detectors).values())
        if total <= 0:
            total = estimate_background_cps(tttr, sorted({c for d in detectors.values() for c in (d or {}).get("chs", [])}))
        if total > 0:
            parameters["background_cps"] = total
    found = np.asarray(tttr[index].burst_search_by_name(algorithm, **parameters), dtype=np.int64)
    return index[found] if found.size else found



#: The inter-photon times above this quantile are the background's: bursts add short gaps only.
BACKGROUND_GAP_QUANTILE = 0.9


def estimate_background_cps(tttr: typing.Any, channels: typing.Sequence[int] | None = None) -> float:
    """Background count rate (counts/s) of *tttr* (of its *channels*, if given).

    Background photons arrive at random, so the gaps between them are exponential with the
    background rate, and an exponential has no memory: the gaps longer than some ``t0`` exceed it
    by an exponential of the same rate. Bursts add short gaps only, so the gaps above the
    :data:`BACKGROUND_GAP_QUANTILE` of all gaps are background, and the rate is one over their
    mean excess (the maximum-likelihood estimate). Recovers a known background within 2 % with up
    to 80 % of the photons in bursts.

    The median of counts in 1 ms time bins used before took integer values at ~4 counts a bin
    (``4.00 kcps`` for any rate between 3.5 and 4.5) and overstated the background with bursts.

    Returns
    -------
    float
        Counts per second; ``0.0`` when there are too few photons or no duration.
    """
    macro = np.asarray(tttr.macro_times, dtype=np.int64)
    if channels is not None:
        from chisurf.core.fluorescence.channels import channel_mask

        macro = macro[channel_mask(np.asarray(tttr.routing_channels), list(channels))]
    resolution = float(tttr.header.macro_time_resolution)
    if macro.size < 10 or resolution <= 0:
        return 0.0
    gaps = np.diff(macro)
    gaps = gaps[gaps > 0]
    if gaps.size < 10:
        return 0.0
    k = int(BACKGROUND_GAP_QUANTILE * (gaps.size - 1))
    t0 = np.partition(gaps, k)[k]
    excess = gaps[gaps > t0] - t0
    if excess.size == 0 or excess.mean() <= 0:
        return 0.0
    return float(1.0 / (excess.mean() * resolution))


def tttrlib_burst_filter(
    tttr: tttrlib.TTTR,
    algorithm: str,
    parameters: typing.Mapping[str, typing.Any] | None = None,
) -> np.ndarray:
    """Boolean photon mask from a registry-selected burst search.

    The mask form the other filters in this package return, so this composes with
    them in :func:`~chisurf.plugins.burst.burst_selection.api.selection.apply_photon_filters`.

    Note that the searches return *inclusive* stop indices while
    :func:`create_array_with_ones` fills half-open intervals, so the stop is
    advanced by one; without that the last photon of every burst is dropped.

    Returns
    -------
    np.ndarray
        Boolean mask of selected photons, of length ``len(tttr)``.
    """
    start_stop = np.asarray(search(tttr, algorithm, parameters), dtype=np.int64)
    start_stop = start_stop.reshape((-1, 2))
    if start_stop.size:
        _warn_if_degenerate(algorithm, start_stop, len(tttr))
        start_stop = start_stop.copy()
        start_stop[:, 1] += 1
    return create_array_with_ones(start_stop, len(tttr))


def _warn_if_degenerate(algorithm: str, start_stop: np.ndarray, n_photons: int) -> None:
    """Say so when a search selected essentially the whole stream.

    A handful of bursts spanning everything looks like a successful analysis in
    the burst table — a burst count, a mean duration, a mean size — so nothing
    downstream flags it, and the numbers are meaningless. The searches that
    measure a burst against an estimated *background* assume bursts are a
    minority of the trace; where they are not, the baseline is itself a burst
    rate and every component clears the contrast and significance tests.
    """
    if n_photons <= 0:
        return
    covered = int((start_stop[:, 1] - start_stop[:, 0] + 1).sum())
    fraction = covered / float(n_photons)
    if fraction < IMPLAUSIBLE_COVERAGE:
        return
    logger.warning(
        "%s selected %.0f%% of the photon stream in %d burst(s) - that is the "
        "whole measurement, not a burst selection. These searches assume bursts "
        "are a minority of the trace; if this data is densely occupied, or the "
        "stream was already filtered down to bright photons before the search "
        "ran, set min_contrast and min_significance to 0 (they are measured "
        "against a background estimate that is not valid here), or run the "
        "search on the unfiltered stream.",
        algorithm,
        fraction * 100.0,
        len(start_stop),
    )
