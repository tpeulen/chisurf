"""Shared photon-level micro-time shift logic for TTTR data.

A *photon-level* micro-time shift moves the micro-time (TAC) values of every
photon on a routing channel by an integer number of bins, **wrapping** modulo
the number of micro-time channels (so no counts are lost off either end). It is
used to align channels/IRFs that were not aligned at acquisition time.

This is distinct from the *histogram-level* shift applied by the TCSPC readers
(``micro_time_shift`` / ``vh_shift``), which pads the already-binned decay and
is deliberately kept separate.

The canonical implementation used to live in the ``microtime_shifter`` plugin
(``chisurf.plugins.tttr.tttr_microtime_shifter.api.shift``); it now lives here
so that both the plugin and the core reading seam
(:func:`chisurf.core.fio.staging.open_tttr`) share one code path. The plugin
re-exports these helpers for backward compatibility.
"""

from __future__ import annotations

import numpy as np


def compute_effective_shifts(
    global_shift: int,
    channel_shifts: dict[int, int],
    routing_channels: np.ndarray,
    n_mt: int,
) -> dict[int, int]:
    """Compute the effective per-channel micro-time shift modulo *n_mt*.

    Parameters
    ----------
    global_shift : int
        Shift applied to every routing channel.
    channel_shifts : dict
        Per-channel additional shifts, keyed by routing channel.
    routing_channels : numpy.ndarray
        Array of routing-channel values (used to enumerate the channels present).
    n_mt : int
        Number of micro-time channels (the wrap modulus).

    Returns
    -------
    dict
        Mapping ``{routing_channel: effective_shift}`` with each shift reduced
        modulo *n_mt*.
    """
    used = sorted(set(int(c) for c in routing_channels))
    effective: dict[int, int] = {}
    for ch in used:
        per_ch = int(channel_shifts.get(ch, 0)) if channel_shifts else 0
        effective[ch] = (int(global_shift) + per_ch) % int(n_mt)
    return effective


def apply_shifts(
    tt,
    global_shift: int = 0,
    channel_shifts: dict[int, int] | None = None,
) -> dict[int, int]:
    """Apply per-channel micro-time shifts to a ``tttrlib.TTTR`` in place.

    Each routing channel present in *tt* is shifted by
    ``(global_shift + channel_shifts[ch]) % n_mt`` using tttrlib's
    :meth:`shift_micro_time_by_channel` (a wrapping shift). Channels with a zero
    effective shift are skipped.

    Parameters
    ----------
    tt : tttrlib.TTTR
        TTTR object to shift (modified in place).
    global_shift : int
        Shift applied to every routing channel.
    channel_shifts : dict, optional
        Per-channel additional shifts, keyed by routing channel.

    Returns
    -------
    dict
        Mapping ``{routing_channel: effective_shift}`` of the shifts actually
        applied.
    """
    channel_shifts = channel_shifts or {}
    n_mt = int(tt.header.get_effective_number_of_micro_time_channels())
    routing = tt.routing_channels
    used = sorted(set(int(c) for c in routing))
    effective: dict[int, int] = {}
    for ch in used:
        per_ch = int(channel_shifts.get(ch, 0))
        tot = (int(global_shift) + per_ch) % n_mt
        if tot != 0:
            tt.shift_micro_time_by_channel(int(ch), int(tot))
        effective[int(ch)] = int(tot)
    return effective
