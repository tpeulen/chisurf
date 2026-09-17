"""Per-state TCSPC decays, kept per detector and merged per colour.

A Viterbi path assigns a state to every photon, and it is tempting to histogram
the micro times of "the photons of state *i*" and call the result that state's
fluorescence decay. It is not one. Photons of one state arrive on **different
detectors**: donor and acceptor photons have different instrument responses,
different micro-time offsets and, above all, different physical meaning. Summing
them produces a curve that is the decay of nothing — its shape moves with the
FRET efficiency, because efficiency is what sets the green:red mixing ratio.

So a decay is only defined *within* a detection colour. This module computes the
histogram at the finest key that is physically meaningful —

    (state, stream, routing channel)

— and merges it upwards. Two different merges matter, and they are not the same:

* **per routing channel** (summing over states or streams) is the physical view:
  one curve per real detector, which is what an IRF is measured for and what the
  saved table carries.
* **per colour** (summing the routing channels of one stream) is the analysis
  view: green, red, yellow.

The distinction between *stream* and *routing channel* is not pedantry. Under
PIE/ALEX the acceptor-excitation stream shares its detectors with the acceptor
stream and is separated only by a micro-time window, so two streams have the
same routing channels. Merging by routing channel alone would pour sensitised
acceptor photons and directly excited ones into one curve — the very mistake
this module exists to prevent, one level down.

Notes
-----
Summing several routing channels into one colour assumes their responses are
aligned; two detectors of the same colour can still differ by an IRF shift. That
assumption is exactly why the per-channel decays are the thing written to disk:
they are what you look at to check it. ChiSurf can correct such a shift when the
data is read — see the per-channel micro-time shifts in
:mod:`chisurf.core.fio.lut_context`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from chisurf.core.datastore import store_from_arrays

__all__ = [
    "StateDecays",
    "colour_groups",
    "decay_table",
    "state_decays",
]

#: Default number of micro-time bins. 256 is enough to see a lifetime difference
#: between states without making the per-channel table unwieldy.
DEFAULT_BINS = 256


@dataclass
class StateDecays:
    """Per-state micro-time histograms, keyed by detector and by colour.

    Attributes
    ----------
    edges : numpy.ndarray
        Micro-time bin edges, shape ``(n_bins + 1,)``. Shared by every curve, so
        any two of them can be compared or divided.
    centers : numpy.ndarray
        Bin centres, shape ``(n_bins,)``, in raw micro-time channels.
    channels : numpy.ndarray
        The routing channels present, ascending. Shape ``(n_channels,)``.
    counts : numpy.ndarray
        Photon counts, shape ``(n_states, n_streams, n_channels, n_bins)``. The
        finest physically meaningful key; both merges are sums over one axis.
    colours : list of str
        Colour names, in role order (donor, acceptor, then any Aex).
    colour_counts : numpy.ndarray
        Counts merged per colour, shape ``(n_states, n_colours, n_bins)``.
    colour_channels : dict
        Which routing channels contributed to each colour — the record that makes
        a merged curve traceable back to the detectors behind it.
    micro_time_ns : float or None
        Nanoseconds per micro-time channel, when known.
    """

    edges: np.ndarray
    centers: np.ndarray
    channels: np.ndarray
    counts: np.ndarray
    colours: list[str]
    colour_counts: np.ndarray
    colour_channels: dict[str, list[int]] = field(default_factory=dict)
    micro_time_ns: float | None = None

    @property
    def n_states(self) -> int:
        """Number of states."""
        return int(self.counts.shape[0])

    def channel_counts(self) -> np.ndarray:
        """Counts per ``(state, routing channel, bin)``, summed over streams."""
        return self.counts.sum(axis=1)

    def centers_ns(self) -> np.ndarray:
        """Bin centres in nanoseconds, or in raw channels when the scale is unknown."""
        if self.micro_time_ns:
            return self.centers * float(self.micro_time_ns)
        return self.centers


def colour_groups(analysis, settings) -> list[tuple[str, tuple[int, ...]]]:
    """Return ``(colour name, stream indices)`` in role order.

    One definition of "which streams are green" shared by the export and the
    plot, so a curve on screen and a curve in the written table cannot disagree
    about what a colour is. Stream indices rather than routing channels, because
    that is what survives PIE and nanotime divisors.

    Parameters
    ----------
    analysis : H2mmAnalysis
        Carries ``donor_streams`` / ``acceptor_streams`` / ``aex_streams``.
    settings : H2mmSettings
        Supplies the detector names.

    Returns
    -------
    list of (str, tuple of int)
    """
    stream_settings = list(getattr(settings, "streams", []) or [])

    def name(i: int, default: str) -> str:
        return stream_settings[i].name if i < len(stream_settings) else default

    groups = [
        (name(0, "green"), tuple(getattr(analysis, "donor_streams", (0,)) or (0,))),
        (name(1, "red"), tuple(getattr(analysis, "acceptor_streams", (1,)) or (1,))),
    ]
    aex = getattr(analysis, "aex_streams", None)
    if aex:
        groups.append((name(2, "yellow"), tuple(aex)))
    return groups


def state_decays(
    micro_time,
    channel,
    stream,
    path,
    *,
    n_states: int,
    groups,
    n_bins: int = DEFAULT_BINS,
    micro_time_ns: float | None = None,
) -> StateDecays:
    """Histogram micro times per ``(state, stream, routing channel)``.

    Parameters
    ----------
    micro_time : array_like
        Per-photon TCSPC micro time.
    channel : array_like
        Per-photon routing channel (the physical detector).
    stream : array_like
        Per-photon stream index, as assigned by the stream definitions — this is
        what separates two colours that share a detector.
    path : array_like
        Per-photon Viterbi state.
    n_states : int
        Number of states in the selected model.
    groups : sequence of (str, sequence of int)
        Colour name → stream indices, from :func:`colour_groups`.
    n_bins : int, optional
        Micro-time bins, shared by every curve.
    micro_time_ns : float, optional
        Nanoseconds per micro-time channel.

    Returns
    -------
    StateDecays

    Raises
    ------
    ValueError
        If the per-photon arrays do not have the same length.
    """
    micro = np.asarray(micro_time, dtype=np.int64)
    chan = np.asarray(channel, dtype=np.int64)
    strm = np.asarray(stream, dtype=np.int64)
    states = np.asarray(path, dtype=np.int64)
    n = micro.shape[0]
    if not (chan.shape[0] == strm.shape[0] == states.shape[0] == n):
        raise ValueError(
            "micro_time, channel, stream and path must describe the same photons "
            f"({n}, {chan.shape[0]}, {strm.shape[0]}, {states.shape[0]})"
        )

    channels = np.unique(chan) if n else np.zeros(0, dtype=np.int64)
    groups = [(str(name), tuple(int(i) for i in idx)) for name, idx in groups]
    n_streams = int(strm.max()) + 1 if n else 1
    n_bins = max(int(n_bins), 1)

    hi = int(micro.max()) + 1 if n else 1
    edges = np.linspace(0, hi, n_bins + 1)
    centers = 0.5 * (edges[:-1] + edges[1:])

    counts = np.zeros((n_states, n_streams, channels.size, n_bins), dtype=np.int64)
    if n:
        # One pass: bin every photon once, then scatter by (state, stream, channel).
        bin_of = np.clip(np.searchsorted(edges, micro, side="right") - 1, 0, n_bins - 1)
        chan_of = np.searchsorted(channels, chan)
        flat = ((states * n_streams + strm) * channels.size + chan_of) * n_bins + bin_of
        valid = (states >= 0) & (states < n_states) & (strm >= 0) & (strm < n_streams)
        tally = np.bincount(flat[valid], minlength=counts.size)
        counts = tally[: counts.size].reshape(counts.shape)

    colours = [name for name, _ in groups]
    colour_counts = np.zeros((n_states, len(groups), n_bins), dtype=np.int64)
    colour_channels: dict[str, list[int]] = {}
    for k, (name, idx) in enumerate(groups):
        sel = [i for i in idx if 0 <= i < n_streams]
        if sel:
            colour_counts[:, k, :] = counts[:, sel, :, :].sum(axis=(1, 2))
            present = counts[:, sel, :, :].sum(axis=(0, 1, 3)) > 0
            colour_channels[name] = [int(c) for c in channels[present]]
        else:
            colour_channels[name] = []

    return StateDecays(
        edges=edges,
        centers=centers,
        channels=channels,
        counts=counts,
        colours=colours,
        colour_counts=colour_counts,
        colour_channels=colour_channels,
        micro_time_ns=micro_time_ns,
    )


def decay_table(decays: StateDecays):
    """Return the per-channel decays as one long, all-numeric table.

    Long form rather than one column per curve, because the number of curves is
    ``states × streams × detectors`` and depends on the fit — a wide table would
    change its columns with the state count. Every column is numeric so ndX opens
    it directly, and the merge to a colour is a ``groupby`` the reader can
    reproduce (and check) without this module.

    Columns: ``State``, ``Stream``, ``Channel``, ``Micro Time``,
    ``Micro Time (ns)``, ``Counts``. Empty ``(state, stream, channel)``
    combinations are dropped. The colour a stream belongs to is deliberately not
    a column — it would be the one non-numeric field in the table — and is
    recorded instead in the result JSON's stream settings.

    Parameters
    ----------
    decays : StateDecays

    Returns
    -------
    tttrlib.DataStore
    """
    n_states, n_streams, n_chan, n_bins = decays.counts.shape
    centers = decays.centers
    centers_ns = decays.centers_ns() if decays.micro_time_ns else np.full(n_bins, np.nan)
    # One block per (state, stream, channel) that saw anything, stacked once at
    # the end rather than concatenated pairwise -- the shape is known, so there
    # is nothing to grow.
    keys = [
        (s, st, c)
        for s in range(n_states)
        for st in range(n_streams)
        for c in range(n_chan)
        if decays.counts[s, st, c].any()
    ]
    if not keys:
        empty = np.zeros(0)
        return store_from_arrays(
            {
                "State": empty.astype(np.int64),
                "Stream": empty.astype(np.int64),
                "Channel": empty.astype(np.int64),
                "Micro Time": centers[:0],
                "Micro Time (ns)": empty,
                "Counts": empty,
            }
        )
    return store_from_arrays(
        {
            "State": np.repeat([s for s, _, _ in keys], n_bins).astype(np.int64),
            "Stream": np.repeat([st for _, st, _ in keys], n_bins).astype(np.int64),
            "Channel": np.repeat([decays.channels[c] for _, _, c in keys], n_bins).astype(np.int64),
            "Micro Time": np.tile(centers, len(keys)),
            "Micro Time (ns)": np.tile(centers_ns, len(keys)),
            "Counts": np.concatenate([decays.counts[k] for k in keys]),
        }
    )
