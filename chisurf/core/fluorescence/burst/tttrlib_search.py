"""Registry-driven access to tttrlib's burst searches.

The other filters in this package each wrap one tttrlib call with a fixed
signature, so adding an algorithm to tttrlib means adding a wrapper here, a
settings dataclass, a dispatch branch and a row of GUI widgets. This module
removes that chain: tttrlib publishes its burst searches — names, defaults,
types and ranges — in its registry, and everything downstream is generated from
that description.

This module is the burst-search view of :mod:`chisurf.core.tttrlib_registry`,
which reads the registry generally (burst searches, file containers, and
whatever tttrlib adds next) and absorbs version differences. The parameter
description is JSON Schema, which chisurf already renders, so the GUI for a
burst search is built with no algorithm-specific code::

    from chisurf.core import tttrlib_registry

logger = logging.getLogger(__name__)

#: Fraction of the stream above which a "burst" result is not a burst result.
#: Real single-molecule data selects some tens of percent; selecting nearly
#: everything means the search degenerated rather than found something.
IMPLAUSIBLE_COVERAGE = 0.7
    from chisurf.gui.autoform import AutoForm

    view = tttrlib_registry.entry_form_view("burst_search", "maxtree")
    form = AutoForm(view)

A new algorithm in tttrlib therefore appears in the interface on upgrade, with
no change here.
"""

from __future__ import annotations

import logging
import typing

import numpy as np
import tttrlib

from chisurf.core import tttrlib_registry

logger = logging.getLogger(__name__)

#: Fraction of the stream above which a "burst" result is not a burst result.
#: Real single-molecule data selects some tens of percent; selecting nearly
#: everything means the search degenerated rather than found something.
IMPLAUSIBLE_COVERAGE = 0.7
from chisurf.core.fluorescence.burst.utils import create_array_with_ones


def algorithms() -> typing.Dict[str, typing.Dict[str, typing.Any]]:
    """The burst searches tttrlib advertises, keyed by algorithm name.

    A thin view onto the ``burst_search`` category of
    :mod:`chisurf.core.tttrlib_registry`, which is where version differences and
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


def defaults(algorithm: str) -> typing.Dict[str, typing.Any]:
    """Default parameters of ``algorithm`` as a ``{name: value}`` dict."""
    return tttrlib_registry.defaults(tttrlib_registry.BURST_SEARCH, algorithm)


def describe(algorithm: str) -> typing.Dict[str, typing.Any]:
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
    parameters: typing.Optional[typing.Mapping[str, typing.Any]] = None,
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
    return tttr.burst_search_by_name(algorithm, **dict(parameters or {}))


def tttrlib_burst_filter(
    tttr: tttrlib.TTTR,
    algorithm: str,
    parameters: typing.Optional[typing.Mapping[str, typing.Any]] = None,
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
        algorithm, fraction * 100.0, len(start_stop),
    )
