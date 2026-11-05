"""Read-only, zero-copy views of a photon stream's columns.

``tttr.macro_times`` (and ``micro_times``, ``routing_channels``, ``event_types``) hands out a
fresh copy of the whole column on every call -- 90 ms and 96 MB for the macro times of a
12 M-photon measurement, and the burst pipeline asked for them a dozen times per search. The
photons are a columnar table (``tttr.data()``) whose numeric columns are views into the C++
buffer; :func:`photon_column` returns those views, read-only, so a caller cannot change the
photons other holders of the shared handle see.

The view is the getter's values only when the stream stores what the getter returns: macro times
held delta-compressed, or shifted by a display offset (``macro_time_offset``), are not in the
column, and then the getter's copy is returned. Callers that write into the array must copy it.

A view holds its stream alive. It sees the stream's buffer, so it is for a stream nobody resizes
or rewrites meanwhile: the shared handles of :func:`chisurf.core.fio.staging.open_tttr` are
read-only by contract, and the analyses using this read the photons, they do not edit them.
"""

from __future__ import annotations

from typing import Any

import numpy as np

#: getter attribute -> data-store column
COLUMNS = {
    "macro_times": "macro_time",
    "micro_times": "micro_time",
    "routing_channels": "routing_channel",
    "event_types": "event_type",
}

#: tttrlib's other spellings, which photon-like stand-ins carry too
_ALIASES = {"routing_channels": ("routing_channel",), "event_types": ("event_type",)}


class _Holder:
    """An array interface that keeps the objects owning the buffer alive (the view's base)."""

    def __init__(self, array: np.ndarray, owners: tuple) -> None:
        self.__array_interface__ = array.__array_interface__
        self._keep = (array, owners)


def _macro_column_is_plain(tttr: Any) -> bool:
    """The stored macro times are what ``get_macro_times`` returns (no compression, no offset)."""
    try:
        if int(getattr(tttr, "macro_time_offset", 0) or 0) != 0:
            return False
        compressed = getattr(tttr, "is_macro_time_compression_enabled", None)
        return not (callable(compressed) and compressed())
    except Exception:  # noqa: BLE001 - unknown: the getter's copy is always right
        return False


def photon_column(tttr: Any, name: str) -> np.ndarray:
    """The photon column *name* of *tttr* (``"macro_times"``, ``"micro_times"``,
    ``"routing_channels"``, ``"event_types"``) as a read-only array, without a copy when the
    stream allows it (see the module docstring), else the getter's array.

    Parameters
    ----------
    tttr : tttrlib.TTTR or object
        A photon stream; anything else with the attribute *name* gets ``np.asarray`` of it.
    name : str
        The getter's name.

    Returns
    -------
    numpy.ndarray
        Same values and dtype as ``np.asarray(getattr(tttr, name))``.
    """
    column = COLUMNS.get(name)
    if column is None:
        raise ValueError(f"unknown photon column {name!r}; one of {sorted(COLUMNS)}")
    data = getattr(tttr, "data", None)
    if callable(data) and (name != "macro_times" or _macro_column_is_plain(tttr)):
        try:
            store = data()
            col = store[column]
            view = col.numpy()
        except Exception:  # noqa: BLE001 - an old tttrlib without columns: the getter
            view = None
        if view is not None and len(view) == len(tttr):
            # The array's base holds the stream: the buffer is the TTTR's, and not every tttrlib
            # build ties a column view's lifetime to it (one freed the photons under the view).
            view = np.asarray(_Holder(view, (tttr, store, col)))
            view.flags.writeable = False
            return view
    for attribute in (name, *_ALIASES.get(name, ())):
        if hasattr(tttr, attribute):
            return np.asarray(getattr(tttr, attribute))
    raise AttributeError(f"{type(tttr).__name__} has no {name}")
