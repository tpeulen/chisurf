"""Turn a gated burst selection into a TCSPC decay or a photon-counting histogram.

A burst explorer gates a sub-population on derived quantities — lifetime, FRET
efficiency, anisotropy — and the natural next question is "what does *that*
population look like under a different analysis?". Answering it needs the
population's **photons**, not a histogram of the quantity it was gated on, and
the explorer already resolves a gate to per-file ``(first_photon, last_photon)``
intervals.

:mod:`chisurf.server.services.pda` was the first consumer of those intervals.
This module adds the other two:

``tcspc.from_bursts``
    Micro-time histogram (fluorescence decay) of the gated photons, per detector
    group. This is exactly well-defined: the decay of a chosen set of photons is
    the decay of that set, and gating on a burst-level quantity does not distort
    the micro-time distribution within the photons it keeps.

``pch.from_bursts``
    Photon-counting histogram P(k) of the gated photons. **This one carries a
    selection bias that the caller has to know about**, so it is stated here, in
    the result, and in the docs rather than left for someone to rediscover:

    PCH's usual meaning — molecular brightness and occupancy from the shape of
    P(k) — assumes the counting bins are a *fair sample of the trace*, including
    the empty stretches between molecules. Bursts are, by construction, the
    bright stretches. Binning only burst interiors therefore truncates the
    low-k side of P(k), and fitting brightness to it will overestimate epsilon
    and underestimate N.

    Both readings are offered, because both are legitimately wanted:

    * ``span`` (default) bins the **whole trace between the first and last gated
      photon**, so the inter-burst background is present and P(k) keeps its
      usual meaning. This is what you want to fit a brightness model.
    * ``interior`` bins **only inside the burst intervals**. Useful for
      comparing the count statistics of two gated populations against each
      other, and misleading if fitted as an absolute brightness.

    The result always reports which mode ran, the fraction of the span the
    bursts occupy, and — for ``interior`` — an explicit ``selection_bias``
    warning string, so a caller that ignores the docs still sees it.

Transport-agnostic and Qt-free: ``chisurf.gui`` is never imported.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from chisurf.server.services import INVALID_INPUT, OPERATION_FAILED, ServiceResult, service_error
from chisurf.server.session import SessionState

#: Warning attached to an ``interior``-mode PCH result.
INTERIOR_BIAS_NOTE = (
    "Counted only inside burst intervals: the inter-burst background is absent, "
    "so P(k) is truncated at low k. Comparable between gated populations; not "
    "valid as an absolute molecular brightness. Use mode='span' to fit brightness."
)


def _as_intervals(ranges: Sequence[Sequence[int]]) -> List[Tuple[int, int]]:
    """JSON ``[[a, b], ...]`` → ``[(a, b), ...]`` of ints."""
    return [(int(a), int(b)) for a, b in ranges]


def _open(path: str, reading_routine: Optional[str] = None):
    """Reopen a source measurement the way the burst analysis originally read it.

    A burst table is a set of pointers back into a photon stream, so these
    services have to reopen files someone else analysed. **How** they were read
    is recorded in the analysis folder's manifest
    (:mod:`chisurf.core.fio.fluorescence.burst_manifest`), and that recorded
    container type is what is used — in preference to anything the caller passed
    and instead of anything inferred from the file extension.

    Extension-based inference is what this replaces. It produced a container
    type called ``"SPC"`` for ``.spc`` files, which ``tttrlib`` does not accept
    and does not report as an error: it prints to stderr and returns an object
    with **zero photons**, so an analysis ran on nothing and looked like a
    measurement without signal.

    Order of preference: the manifest, then an explicit argument, then letting
    ``tttrlib`` identify the container itself. Everything goes through
    :func:`chisurf.core.fio.staging.open_tttr`, which resolves the type and adds
    staging and LUT-awareness.
    """
    from chisurf.core.fio.fluorescence.burst_manifest import (
        read_analysis_manifest,
        reading_settings_for,
    )
    from chisurf.core.fio.staging import open_tttr

    recorded = reading_settings_for(path, read_analysis_manifest(path))
    container = recorded.get("container_type") or reading_routine
    if recorded.get("container_type"):
        logging.debug(
            "reading %s as %s, as recorded by the burst analysis",
            path, recorded["container_type"],
        )
    return open_tttr(path, container)


def _selected_indices(
    n_photons: int, intervals: Sequence[Tuple[int, int]]
) -> np.ndarray:
    """Photon indices covered by *intervals*, clipped to the file and deduplicated.

    Parameters
    ----------
    n_photons : int
        Photons in the file, used to clip intervals that run past the end.
    intervals : sequence of (int, int)
        Inclusive ``(first, last)`` photon-index pairs, as burst tables store
        them.

    Returns
    -------
    numpy.ndarray
        Sorted, unique photon indices.
    """
    parts = []
    for first, last in intervals:
        lo = max(0, int(first))
        hi = min(int(n_photons) - 1, int(last))
        if hi >= lo:
            parts.append(np.arange(lo, hi + 1, dtype=np.int64))
    if not parts:
        return np.empty(0, dtype=np.int64)
    return np.unique(np.concatenate(parts))


def _micro_time_bins(tttr: Any, micro: np.ndarray) -> int:
    """Length of the file's micro-time axis, in native TAC channels.

    The axis is the instrument's TAC/ADC range as declared by the header
    (``number_of_micro_time_channels``), **not** the highest micro-time value
    that happens to be occupied. The occupied maximum is data-dependent: two
    files of the same measurement essentially never agree on it, so decays built
    from them could not be summed, and a single-file decay would be short of the
    instrument axis an IRF or a background decay is measured on.

    Parameters
    ----------
    tttr : tttrlib.TTTR
        The open photon stream, read for its header.
    micro : numpy.ndarray
        The file's micro times, used only as a fallback for a header that does
        not declare the range, and as a floor so no photon falls off the axis.

    Returns
    -------
    int
        Number of native micro-time bins, at least one.
    """
    adc = int(getattr(tttr.header, "number_of_micro_time_channels", 0) or 0)
    occupied = int(micro.max()) + 1 if micro.size else 1
    return max(adc, occupied, 1)


def _channel_filter(channels: np.ndarray, wanted: Optional[Sequence[int]]) -> np.ndarray:
    """Boolean mask selecting *wanted* routing channels (all when ``None``)."""
    if wanted is None:
        return np.ones(channels.shape, dtype=bool)
    return np.isin(channels, np.asarray(list(wanted), dtype=channels.dtype))


def from_bursts_decay(
    state: SessionState,
    burst_slices: Optional[Dict[str, Sequence[Sequence[int]]]] = None,
    channels: Any = None,
    reading_routine: Optional[str] = None,
    coarsening: int = 1,
    stream_names: Optional[Sequence[str]] = None,
) -> ServiceResult:
    """Build micro-time decays from gated burst intervals.

    Registered as ``tcspc.from_bursts``.

    The decay spans the instrument's whole TAC range (the header's
    ``number_of_micro_time_channels``), not just the occupied bins, so the same
    setup always yields the same axis — one that lines up with an IRF or a
    background decay, and one that can be summed over the files a gate spans.
    Gating several files measured with *different* TAC ranges is rejected rather
    than summed.

    Parameters
    ----------
    state : SessionState
        The RPC session (unused; reading is stateless).
    burst_slices : dict, optional
        ``{tttr_path: [[first, last], ...]}`` — the gated bursts per file, as
        photon-index intervals.
    channels : list, optional
        Detector groups, e.g. ``[[0, 8], [1, 9]]`` for green/red. One decay is
        returned per group. All channels in one group when omitted.
    reading_routine : str, optional
        TTTR container type; auto-detected from the file when omitted.
    coarsening : int
        Micro-time binning factor; ``1`` keeps the native resolution.
    stream_names : sequence of str, optional
        Names for the groups, defaulting to ``ch0``, ``ch1``, …

    Returns
    -------
    dict
        ``{"ok": True, "result": {"decays": [...], "n_files": int,
        "n_photons": int}}``; each decay carries ``name``, ``channels``,
        ``counts``, ``time_axis`` (ns) and ``n_photons``.
    """
    if not burst_slices:
        return service_error(
            "burst_slices is required and must be non-empty", error_code=INVALID_INPUT
        )
    try:
        slices = {str(p): _as_intervals(r) for p, r in burst_slices.items()}
        groups = (
            [[int(c) for c in g] for g in channels]
            if channels is not None
            else None
        )
    except (TypeError, ValueError) as exc:
        return service_error(
            f"malformed burst_slices/channels: {exc}", error_code=INVALID_INPUT
        )

    try:
        n_groups = len(groups) if groups is not None else 1
        names = list(stream_names) if stream_names else [
            f"ch{i}" for i in range(n_groups)
        ]
        accum: List[Optional[np.ndarray]] = [None] * n_groups
        dt_ns = None
        used = 0
        step_size = max(1, int(coarsening))
        axis: tuple[int, int, str] | None = None

        for path, intervals in slices.items():
            tttr = _open(path, reading_routine)
            micro = np.asarray(tttr.micro_times)
            routing = np.asarray(tttr.routing_channels)
            index = _selected_indices(micro.size, intervals)
            if index.size == 0:
                continue
            if dt_ns is None:
                # tttrlib reports the micro-time bin width in seconds.
                dt_ns = float(tttr.header.micro_time_resolution) * 1e9

            sel_micro = micro[index]
            sel_routing = routing[index]
            n_bins = _micro_time_bins(tttr, micro)
            # Round the binned axis up: flooring would drop the last, partly
            # filled coarse bin and shorten the axis by one for some factors.
            n_out = -(-n_bins // step_size)
            if axis is None:
                axis = (n_out, n_bins, path)
            elif n_out != axis[0]:
                return service_error(
                    f"the gated files disagree on the micro-time axis: {path} has "
                    f"{n_bins} micro-time channels, {axis[2]} has {axis[1]}; a decay "
                    "can only be summed over files measured with the same TAC range",
                    error_code=INVALID_INPUT,
                )

            for i in range(n_groups):
                wanted = groups[i] if groups is not None else None
                mask = _channel_filter(sel_routing, wanted)
                if not mask.any():
                    continue
                binned = sel_micro[mask] // step_size
                counts = np.bincount(binned, minlength=n_out).astype(float)
                used += int(mask.sum())
                accum[i] = counts if accum[i] is None else accum[i] + counts
    except Exception as exc:  # pragma: no cover - depends on tttrlib/files
        return service_error(
            f"decay read failed: {exc}", error_code=OPERATION_FAILED, exception=exc
        )

    step = (dt_ns or 1.0) * step_size
    decays = []
    for i, counts in enumerate(accum):
        if counts is None:
            continue
        decays.append(
            {
                "name": names[i] if i < len(names) else f"ch{i}",
                "channels": groups[i] if groups is not None else None,
                "counts": counts.tolist(),
                "time_axis": (np.arange(counts.size) * step).tolist(),
                "n_photons": int(counts.sum()),
            }
        )
    if not decays:
        return service_error(
            "no photons in the gated intervals for the requested channels",
            error_code=INVALID_INPUT,
        )
    return {
        "ok": True,
        "result": {
            "decays": decays,
            "n_files": len(slices),
            "n_photons": used,
            "micro_time_resolution_ns": dt_ns,
            "coarsening": int(coarsening),
        },
    }


def from_bursts_pch(
    state: SessionState,
    burst_slices: Optional[Dict[str, Sequence[Sequence[int]]]] = None,
    channels: Optional[Sequence[int]] = None,
    reading_routine: Optional[str] = None,
    bin_time_us: float = 50.0,
    mode: str = "span",
    micro_time_min: Optional[int] = None,
    micro_time_max: Optional[int] = None,
) -> ServiceResult:
    """Build a photon-counting histogram from gated burst intervals.

    Registered as ``pch.from_bursts``. Read :data:`INTERIOR_BIAS_NOTE` and the
    module docstring before fitting brightness to a ``mode="interior"`` result.

    Parameters
    ----------
    state : SessionState
        The RPC session (unused; reading is stateless).
    burst_slices : dict, optional
        ``{tttr_path: [[first, last], ...]}`` — the gated bursts per file.
    channels : sequence of int, optional
        Routing channels to include; all channels when omitted.
    reading_routine : str, optional
        TTTR container type; auto-detected from the file when omitted.
    bin_time_us : float
        Counting bin width in microseconds.
    mode : {"span", "interior"}
        ``"span"`` bins the whole trace between the first and last gated photon,
        keeping the inter-burst background so P(k) means what PCH usually means.
        ``"interior"`` bins only within the burst intervals, which truncates the
        low-k side — comparable between populations, not an absolute brightness.
    micro_time_min, micro_time_max : int, optional
        Micro-time gate applied before binning.

    Returns
    -------
    dict
        ``{"ok": True, "result": {...}}`` carrying ``k_vals``, ``p_exp``
        (normalised), ``counts``, ``n_bins``, ``n_photons``, ``mode``,
        ``burst_duty_cycle`` and, for ``interior``, ``selection_bias``.
    """
    if not burst_slices:
        return service_error(
            "burst_slices is required and must be non-empty", error_code=INVALID_INPUT
        )
    if mode not in ("span", "interior"):
        return service_error(
            f"mode must be 'span' or 'interior', got {mode!r}", error_code=INVALID_INPUT
        )
    if bin_time_us <= 0:
        return service_error("bin_time_us must be positive", error_code=INVALID_INPUT)

    try:
        slices = {str(p): _as_intervals(r) for p, r in burst_slices.items()}
    except (TypeError, ValueError) as exc:
        return service_error(
            f"malformed burst_slices: {exc}", error_code=INVALID_INPUT
        )

    try:
        counts_per_bin: List[np.ndarray] = []
        total_photons = 0
        burst_seconds = 0.0
        span_seconds = 0.0

        for path, intervals in slices.items():
            tttr = _open(path, reading_routine)
            macro = np.asarray(tttr.macro_times, dtype=np.float64)
            routing = np.asarray(tttr.routing_channels)
            micro = np.asarray(tttr.micro_times)
            if macro.size == 0:
                continue
            dt = float(tttr.header.macro_time_resolution)  # seconds per tick
            bin_ticks = (float(bin_time_us) * 1e-6) / dt
            if bin_ticks < 1.0:
                return service_error(
                    f"bin_time_us={bin_time_us} is shorter than one macro-time tick "
                    f"({dt * 1e6:.4g} us) for {path}",
                    error_code=INVALID_INPUT,
                )

            index = _selected_indices(macro.size, intervals)
            if index.size == 0:
                continue

            keep = _channel_filter(routing, channels)
            if micro_time_min is not None:
                keep &= micro >= int(micro_time_min)
            if micro_time_max is not None:
                keep &= micro <= int(micro_time_max)

            first, last = int(index[0]), int(index[-1])
            span_seconds += (macro[last] - macro[first]) * dt
            for lo, hi in intervals:
                lo_c, hi_c = max(0, int(lo)), min(macro.size - 1, int(hi))
                if hi_c >= lo_c:
                    burst_seconds += (macro[hi_c] - macro[lo_c]) * dt

            if mode == "span":
                # Every photon between the first and last gated photon, so the
                # empty stretches between bursts are counted as the zeros they are.
                window = np.zeros(macro.size, dtype=bool)
                window[first : last + 1] = True
            else:
                window = np.zeros(macro.size, dtype=bool)
                window[index] = True

            sel = window & keep
            if not sel.any():
                continue

            times = macro[sel] - macro[first]
            n_bin = int(np.floor((macro[last] - macro[first]) / bin_ticks)) + 1
            which = np.minimum((times / bin_ticks).astype(np.int64), n_bin - 1)
            per_bin = np.bincount(which, minlength=n_bin).astype(np.int64)

            if mode == "interior":
                # Bins that lie entirely between bursts are not "zero counts
                # observed", they are "not observed" — dropping them is what
                # makes this mode a comparison of burst interiors rather than a
                # trace with the background deleted.
                inside = np.zeros(n_bin, dtype=bool)
                for lo, hi in intervals:
                    lo_c, hi_c = max(0, int(lo)), min(macro.size - 1, int(hi))
                    if hi_c < lo_c:
                        continue
                    b0 = int((macro[lo_c] - macro[first]) / bin_ticks)
                    b1 = int((macro[hi_c] - macro[first]) / bin_ticks)
                    inside[max(0, b0) : min(n_bin, b1 + 1)] = True
                per_bin = per_bin[inside]

            counts_per_bin.append(per_bin)
            total_photons += int(per_bin.sum())
    except Exception as exc:  # pragma: no cover - depends on tttrlib/files
        return service_error(
            f"PCH read failed: {exc}", error_code=OPERATION_FAILED, exception=exc
        )

    if not counts_per_bin:
        return service_error(
            "no photons in the gated intervals for the requested channels",
            error_code=INVALID_INPUT,
        )

    all_counts = np.concatenate(counts_per_bin)
    k_max = int(all_counts.max())
    histogram = np.bincount(all_counts, minlength=k_max + 1).astype(float)
    p_exp = histogram / histogram.sum() if histogram.sum() else histogram

    result: Dict[str, Any] = {
        "k_vals": list(range(k_max + 1)),
        "counts": histogram.tolist(),
        "p_exp": p_exp.tolist(),
        "n_bins": int(all_counts.size),
        "n_photons": total_photons,
        "n_files": len(slices),
        "bin_time_us": float(bin_time_us),
        "mode": mode,
        # How much of the analysed span the bursts actually occupy. Near 1 means
        # the two modes nearly agree; near 0 means they differ enormously, which
        # is exactly when reading an 'interior' P(k) as a brightness misleads.
        "burst_duty_cycle": (burst_seconds / span_seconds) if span_seconds > 0 else None,
    }
    if mode == "interior":
        result["selection_bias"] = INTERIOR_BIAS_NOTE
    return {"ok": True, "result": result}


def consumers(state: SessionState = None) -> ServiceResult:
    """Advertise what a gated burst population can be handed to.

    Registered as ``bursts.consumers``. This is the seam that lets an explorer
    show a "send selection to" menu without knowing a single ChiSurf method
    name: ChiSurf publishes the list, the client renders it and sends a ``key``
    back. Adding an analysis is a row in ``burst_consumers.json`` plus a service
    — no client release.

    The core list ships in :file:`chisurf/server/burst_consumers.json`; plugins
    extend it by declaring a ``burst_consumers`` array in their ``manifest.json``
    using the same field names. A plugin entry with an existing ``key``
    replaces the core one, so a plugin can supersede a built-in analysis.

    Returns
    -------
    dict
        ``{"ok": True, "result": {"consumers": [...]}}`` in menu order.
    """
    entries: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []

    for entry in _core_consumers() + _plugin_consumers():
        key = entry.get("key")
        if not key or not entry.get("rpc"):
            logging.warning("ignoring a burst consumer with no key/rpc: %r", entry)
            continue
        if key not in entries:
            order.append(key)
        entries[key] = entry

    return {"ok": True, "result": {"consumers": [entries[k] for k in order]}}


def _core_consumers() -> List[Dict[str, Any]]:
    """Read the consumers that ship with ChiSurf."""
    from importlib import resources

    try:
        with resources.files("chisurf.server").joinpath(
            "burst_consumers.json"
        ).open(encoding="utf-8") as fp:
            return list(json.load(fp).get("consumers", []))
    except Exception as exc:  # pragma: no cover - packaging accident
        logging.error("could not read burst_consumers.json: %s", exc)
        return []


def _plugin_consumers() -> List[Dict[str, Any]]:
    """Collect ``burst_consumers`` declared by plugin manifests.

    A burst analysis that lives in a plugin should be able to advertise itself
    the same way it advertises its RPC methods, rather than requiring an edit to
    a core file it does not own.
    """
    import pathlib

    found: List[Dict[str, Any]] = []
    root = pathlib.Path(__file__).resolve().parents[2] / "plugins"
    if not root.is_dir():
        return found
    for manifest in root.rglob("manifest.json"):
        try:
            declared = json.loads(manifest.read_text(encoding="utf-8")).get(
                "burst_consumers"
            )
        except Exception as exc:
            logging.debug("skipping unreadable manifest %s: %s", manifest, exc)
            continue
        if isinstance(declared, list):
            found.extend(d for d in declared if isinstance(d, dict))
    return found
