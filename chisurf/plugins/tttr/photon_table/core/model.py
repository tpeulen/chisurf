"""Qt-free model of the photon table.

Loads the photon records of a TTTR object into plain numpy arrays and serves
paged, channel-filtered slices of them. No Qt, no GUI: the same object drives
the EMTK app and a script.
"""

from __future__ import annotations

import pathlib
from typing import Any

import numpy as np


class PhotonTableModel:
    """The photons of one TTTR file, paged for the table."""

    def __init__(self) -> None:
        self.filename: str = ""
        self._micro: np.ndarray = np.empty(0, dtype=np.uint32)
        self._macro: np.ndarray = np.empty(0, dtype=np.uint64)
        self._routing: np.ndarray = np.empty(0, dtype=np.uint8)
        #: Seconds per macro-time unit, from the file header (0 when unknown).
        self.macro_resolution: float = 0.0
        #: Number of micro-time channels the header declares, when known.
        self.n_micro_channels: int = 0

    # ── loading ───────────────────────────────────────────────────────

    def load_tttr(self, tttr: Any, filename: str = "") -> None:
        """Adopt a loaded :class:`tttrlib.TTTR` object.

        The arrays are copied once: the table pages over the copies, so the
        TTTR object can be released by the caller.
        """
        self.filename = filename or str(getattr(tttr, "filename", ""))
        self._micro = np.asarray(tttr.micro_times, dtype=np.uint32).ravel()
        self._macro = np.asarray(tttr.macro_times, dtype=np.uint64).ravel()
        self._routing = np.asarray(tttr.routing_channels, dtype=np.uint8).ravel()
        n = min(len(self._micro), len(self._macro), len(self._routing))
        self._micro, self._macro, self._routing = (
            self._micro[:n],
            self._macro[:n],
            self._routing[:n],
        )
        try:
            self.macro_resolution = float(tttr.header.macro_time_resolution)
        except Exception:
            self.macro_resolution = 0.0
        try:
            self.n_micro_channels = int(tttr.get_number_of_micro_time_channels())
        except Exception:
            self.n_micro_channels = 0

    def load_file(self, path: str | pathlib.Path, tttr_type=None) -> None:
        """Open a TTTR file and load it. ``tttr_type`` pins the container."""
        import tttrlib

        if tttr_type is None:
            tttr = tttrlib.TTTR(str(path))
        else:
            tttr = tttrlib.TTTR(str(path), tttr_type)
        self.load_tttr(tttr, str(path))

    # ── state ─────────────────────────────────────────────────────────

    @property
    def n_photons(self) -> int:
        return int(len(self._micro))

    @property
    def used_channels(self) -> list[int]:
        """The routing channels present in the data, sorted."""
        if not self.n_photons:
            return []
        return sorted(int(c) for c in np.unique(self._routing))

    def acquisition_time_s(self) -> float:
        """The measurement duration in seconds (0 when the resolution is unknown)."""
        if not self.n_photons or self.macro_resolution <= 0.0:
            return 0.0
        return float(self._macro[-1]) * self.macro_resolution

    # ── paging ────────────────────────────────────────────────────────

    def clamp_first(self, first: int, rows: int, channel: int | None = None) -> int:
        """Clamp a page's first photon index into the filtered range."""
        count = self.filtered_count(channel)
        first = int(first)
        first = max(0, min(first, max(count - 1, 0)))
        # Never let a page run past the end of the filtered selection.
        first = max(0, min(first, max(count - rows, 0)))
        return first

    def filtered_count(self, channel: int | None = None) -> int:
        """How many photons the channel filter lets through.

        ``None`` and any negative value (the UI's "All channels" sentinel)
        mean every photon.
        """
        if channel is None or int(channel) < 0:
            return self.n_photons
        return int(np.count_nonzero(self._routing == channel))

    def filtered_indices(self, channel: int | None = None) -> np.ndarray:
        """Photon indices the channel filter lets through.

        ``None`` and any negative value (the UI's "All channels" sentinel)
        mean every photon.
        """
        if channel is None or int(channel) < 0:
            return np.arange(self.n_photons, dtype=np.int64)
        return np.flatnonzero(self._routing == channel).astype(np.int64)

    def page(self, first: int, rows: int, channel: int | None = None) -> list[dict]:
        """One page of table rows: ``count`` photons from ``first`` on.

        The *Photon* column is the photon's index among the filtered photons —
        the row number a downstream script would address — while *Idx* is the
        index in the raw file. ``channel`` filters by routing channel.
        """
        rows = max(1, min(int(rows), 20_000))
        indices = self.filtered_indices(channel)
        first = self.clamp_first(first, rows, channel)
        window = indices[first : first + rows]
        macro_ms = (
            self._macro[window] * self.macro_resolution * 1e3
            if self.macro_resolution > 0
            else self._macro[window]
        )
        return [
            {
                "photon": int(first + j),
                "idx": int(i),
                "channel": int(self._routing[i]),
                "micro": int(self._micro[i]),
                "macro": float(macro_ms[j]),
            }
            for j, i in enumerate(window)
        ]

    def page_tsv(self, first: int, rows: int, channel: int | None = None) -> str:
        """One page as TSV — what 'Copy visible' puts on the clipboard."""
        rows = self.page(first, rows, channel)
        header = "photon\tidx\tchannel\tmicro\tmacro_ms"
        lines = [header]
        lines += [
            f"{r['photon']}\t{r['idx']}\t{r['channel']}\t{r['micro']}\t{r['macro']:.6f}"
            for r in rows
        ]
        return "\n".join(lines) + "\n"
