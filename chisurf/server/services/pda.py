"""Central RPC service for PDA from a burst selection.

Photon Distribution Analysis needs the *photons* of a chosen set of bursts, not
a histogram of a derived quantity. ndX (and any other burst explorer) gates
a sub-population and resolves it to per-file ``(first_photon, last_photon)``
intervals; this service turns those intervals into a PDA S1/S2 experimental
histogram, ready to fit, by driving :class:`chisurf.core.experiments.pda2c.Pda2cReader`
with its ``burst_slices`` path.

Transport-agnostic and Qt-free — the ``chisurf.gui`` module is never imported.
It is the server endpoint the ndX PDA bridge
(:meth:`ndxplorer.analysis.burst_bridge.BurstAnalysisBridge.send_to_pda`) calls
as ``pda.from_bursts``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np

from chisurf.server.services import INVALID_INPUT, OPERATION_FAILED, ServiceResult, service_error
from chisurf.server.session import SessionState


def _as_channel_tuple(channels: Any) -> tuple[list[int], ...]:
    """JSON ``[[0], [1]]`` → ``([0], [1])`` (the reader wants a tuple of lists)."""
    return tuple([int(c) for c in group] for group in channels)


def _as_intervals(ranges: Sequence[Sequence[int]]) -> list[tuple[int, int]]:
    """JSON ``[[a, b], ...]`` → ``[(a, b), ...]`` of ints."""
    return [(int(a), int(b)) for a, b in ranges]


def from_bursts(
    state: SessionState,
    burst_slices: dict[str, Sequence[Sequence[int]]] | None = None,
    channels: Any = None,
    micro_time_ranges: Sequence[Sequence[int]] | None = None,
    reading_routine: str = "PTU",
    minimum_number_of_photons: int = 20,
    maximum_number_of_photons: int = 200,
    minimum_time_window_length: float = 2e-3,
    n_colors: int | None = None,
) -> ServiceResult:
    """Build a PDA experimental histogram from gated burst intervals.

    Parameters
    ----------
    state
        The RPC session (unused; PDA reading is stateless).
    burst_slices
        ``{tttr_path: [[first, last], ...]}`` — the gated bursts, per file, as
        photon-index intervals (the ndX ``.bst`` shape).
    channels
        Detection-channel groups, e.g. ``[[0], [1]]`` for green/red; required.
    micro_time_ranges
        Micro-time gates ``[[lo, hi], ...]``; defaults to a single full window.
    reading_routine
        TTTR reading routine (``"PTU"``, ``"SPC-130"``, …).
    minimum_number_of_photons, maximum_number_of_photons, minimum_time_window_length
        Burst-acceptance thresholds passed to the reader.
    n_colors
        Optional colour count override (2 → S1/S2 histogram).

    Returns
    -------
    dict
        ``{"ok": True, "result": {"curves": [...], "n_files": int}}`` where each
        curve carries its ``s1s2`` histogram (as a nested list), ``shape``,
        ``channels`` and photon-count metadata.
    """
    if not burst_slices:
        return service_error(
            "burst_slices is required and must be non-empty", error_code=INVALID_INPUT
        )
    if channels is None:
        return service_error("channels is required, e.g. [[0], [1]]", error_code=INVALID_INPUT)

    try:
        slices = {str(p): _as_intervals(r) for p, r in burst_slices.items()}
        ch = _as_channel_tuple(channels)
        mtr = [tuple(int(v) for v in w) for w in (micro_time_ranges or [(0, 4096)])]
    except (TypeError, ValueError) as exc:
        return service_error(f"malformed burst_slices/channels: {exc}", error_code=INVALID_INPUT)

    try:
        from chisurf.core.experiments.pda2c import Pda2cReader

        settings: dict[str, Any] = dict(
            channels=ch,
            micro_time_ranges=mtr,
            reading_routine=reading_routine,
            minimum_number_of_photons=int(minimum_number_of_photons),
            maximum_number_of_photons=int(maximum_number_of_photons),
            minimum_time_window_length=float(minimum_time_window_length),
        )
        if n_colors is not None:
            settings["n_colors"] = int(n_colors)
        reader = Pda2cReader(**settings)
        group = reader.read(filename=list(slices), burst_slices=slices)
    except Exception as exc:  # pragma: no cover - depends on TTTR/tttrlib
        return service_error(f"PDA read failed: {exc}", error_code=OPERATION_FAILED, exception=exc)

    curves: list[dict[str, Any]] = []
    for curve in group:
        pda = getattr(curve, "pda", None) or {}
        s1s2 = np.asarray(pda.get("s1s2", []), dtype=float)
        curves.append(
            {
                "name": getattr(curve, "name", None),
                "shape": list(s1s2.shape),
                "s1s2": s1s2.tolist(),
                "channels": [list(g) for g in ch],
                "n_photons": int(s1s2.sum()) if s1s2.size else 0,
                "maximum_number_of_photons": pda.get("maximum_number_of_photons"),
                "minimum_number_of_photons": pda.get("minimum_number_of_photons"),
            }
        )
    return {"ok": True, "result": {"curves": curves, "n_files": len(slices)}}
