"""Qt-free model of the photon table.

Loads every record of a TTTR object -- photons and the scanner's marker records
alike -- into plain numpy arrays and serves paged, channel- and kind-filtered
slices of them. What each record is (photon, pixel / line / frame marker, other
marker) is tttrlib's answer (:meth:`tttrlib.CLSMImage.get_record_kinds`, from the
file header and the scanner's reading routine); the kinds' names and colours are
declared in ``record_kinds.yaml`` beside this module. No Qt, no GUI: the same
object drives the EMTK app and a script.
"""

from __future__ import annotations

import pathlib
import warnings
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import numpy as np
import yaml

#: The declared record kinds.
KINDS_FILE = pathlib.Path(__file__).with_name("record_kinds.yaml")
#: Kind-filter value: every record.
KIND_ALL = "all"
#: Kind-filter value: every marker record, whatever its kind.
KIND_MARKERS = "markers"
#: The key of the photon kind (every other kind is a marker).
KIND_PHOTON = "photon"
#: tttrlib's ``CLSM_RECORD_OTHER_MARKER``, for a tttrlib build that predates it.
_OTHER_MARKER = 5


@dataclass(frozen=True)
class RecordKind:
    """One declared kind of record (an entry of ``record_kinds.yaml``)."""

    key: str
    label: str
    codes: tuple[int, ...]
    colour: str | None
    description: str

    @property
    def is_marker(self) -> bool:
        return self.key != KIND_PHOTON


@lru_cache(maxsize=1)
def record_kinds() -> tuple[RecordKind, ...]:
    """The kinds declared in ``record_kinds.yaml``, in declaration order.

    Raises
    ------
    ValueError
        A kind without a key or codes, a code claimed twice, or no photon kind:
        the file is wrong and must fail where it is read.
    """
    data = yaml.safe_load(KINDS_FILE.read_text(encoding="utf-8")) or {}
    kinds: list[RecordKind] = []
    seen: set[int] = set()
    for entry in data.get("kinds") or []:
        key = str(entry.get("key") or "")
        codes = tuple(int(c) for c in entry.get("codes") or [])
        if not key or not codes:
            raise ValueError(f"record kind {entry!r} needs a key and codes")
        if seen & set(codes):
            raise ValueError(f"record kind {key!r} claims a code another kind has")
        seen |= set(codes)
        kinds.append(
            RecordKind(
                key=key,
                label=str(entry.get("label") or key),
                codes=codes,
                colour=entry.get("colour") or None,
                description=str(entry.get("description") or ""),
            )
        )
    if not any(k.key == KIND_PHOTON for k in kinds):
        raise ValueError("record_kinds.yaml declares no photon kind")
    return tuple(kinds)


def classify_records(tttr: Any) -> np.ndarray:
    """tttrlib's kind code (``CLSMRecordKind``) of every record of *tttr*.

    A file whose header describes an image scan is classified by a
    :class:`tttrlib.CLSMImage` built on it without pixels: the image resolves the
    marker channels from the header and the reading routine, and
    ``get_record_kinds`` names each record by those. Any other file has no named
    markers, so tttrlib calls each of its marker records an *other* marker. An
    object without event types (a stand-in, a bare array source) holds photons only.
    """
    n = len(tttr.micro_times)
    event_types = getattr(tttr, "event_types", None)
    if event_types is None:
        return np.zeros(n, dtype=np.int8)
    import tttrlib

    if not hasattr(tttrlib.CLSMImage, "classify_records_events"):
        # A tttrlib built before the record classifier: the markers cannot be
        # named, so every one is an "other" marker until tttrlib is rebuilt.
        warnings.warn(
            "this tttrlib build lacks CLSMImage.classify_records_events / get_record_kinds; "
            "the Photon Table lists every marker as 'other'. Rebuild tttrlib "
            "(pixi run build-tttrlib) to name pixel, line and frame markers.",
            RuntimeWarning,
            stacklevel=2,
        )
        codes = np.zeros(n, dtype=np.int8)
        codes[np.asarray(event_types)[:n] != 0] = _OTHER_MARKER
        return codes

    if _is_scan(tttr):
        try:
            image = tttrlib.CLSMImage(tttr, build_pixels=False)
            return np.asarray(image.get_record_kinds(), dtype=np.int8)
        except Exception:  # noqa: BLE001 - a scan tttrlib cannot frame has unnamed markers
            pass
    unnamed = tttrlib.CLSMSettings(
        marker_frame_start=[],
        marker_line_start=-1,
        marker_line_stop=-1,
        marker_event_type=1,
        use_pixel_markers=False,
    )
    return np.asarray(
        tttrlib.CLSMImage.classify_records_events(
            np.ascontiguousarray(event_types, dtype=np.int8),
            np.ascontiguousarray(tttr.routing_channels, dtype=np.int8),
            np.ascontiguousarray(tttr.micro_times, dtype=np.uint16),
            unnamed,
        ),
        dtype=np.int8,
    )


def _is_scan(tttr: Any) -> bool:
    """Whether tttrlib reads *tttr*'s header as an image scan (geometry or a scan routine)."""
    import tttrlib

    header = getattr(tttr, "header", None)
    if not isinstance(tttr, tttrlib.TTTR) or header is None:
        return False
    try:
        if tttrlib.CLSMImageInfo.from_header(header).is_valid():
            return True
    except Exception:  # noqa: BLE001 - a header without imaging tags
        pass
    try:
        return header.tag("BH_SPC_ReadingRoutine").get("value") not in (None, "", -1)
    except Exception:  # noqa: BLE001 - tag absent
        return False


class PhotonTableModel:
    """The records of one TTTR file, paged for the table."""

    def __init__(self) -> None:
        self.filename: str = ""
        self._micro: np.ndarray = np.empty(0, dtype=np.uint32)
        self._macro: np.ndarray = np.empty(0, dtype=np.uint64)
        self._routing: np.ndarray = np.empty(0, dtype=np.uint8)
        #: tttrlib's kind code of every record.
        self._codes: np.ndarray = np.empty(0, dtype=np.int8)
        #: Seconds per macro-time unit, from the file header (0 when unknown).
        self.macro_resolution: float = 0.0
        #: Number of micro-time channels the header declares, when known.
        self.n_micro_channels: int = 0
        self._counts: dict[str, int] = {}

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
        self._codes = np.asarray(classify_records(tttr), dtype=np.int8).ravel()
        n = min(len(self._micro), len(self._macro), len(self._routing), len(self._codes))
        self._micro, self._macro, self._routing, self._codes = (
            self._micro[:n],
            self._macro[:n],
            self._routing[:n],
            self._codes[:n],
        )
        code_counts = np.bincount(self._codes.astype(np.int64) & 0xFF, minlength=256)
        self._counts = {k.key: int(sum(code_counts[c] for c in k.codes)) for k in record_kinds()}
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
    def n_records(self) -> int:
        """Every record of the file: photons and markers."""
        return int(len(self._micro))

    @property
    def n_photons(self) -> int:
        """The photon records."""
        return self._counts.get(KIND_PHOTON, 0)

    @property
    def n_markers(self) -> int:
        """The marker records, of every kind."""
        return self.n_records - self.n_photons

    def kind_counts(self) -> dict[str, int]:
        """``{kind key: records}`` for every declared kind, in declaration order."""
        return {k.key: self._counts.get(k.key, 0) for k in record_kinds()}

    @property
    def used_channels(self) -> list[int]:
        """The routing channels present in the data, sorted."""
        if not self.n_records:
            return []
        return sorted(int(c) for c in np.unique(self._routing))

    def acquisition_time_s(self) -> float:
        """The measurement duration in seconds (0 when the resolution is unknown)."""
        if not self.n_records or self.macro_resolution <= 0.0:
            return 0.0
        return float(self._macro[-1]) * self.macro_resolution

    # ── filtering ─────────────────────────────────────────────────────

    def _mask(self, channel: int | None, kind: str | None) -> np.ndarray | None:
        """The records both filters let through, or ``None`` for every record."""
        mask = None
        if channel is not None and int(channel) >= 0:
            mask = self._routing == channel
        if kind not in (None, "", KIND_ALL):
            if kind == KIND_MARKERS:
                photon = next(k for k in record_kinds() if k.key == KIND_PHOTON)
                wanted = ~np.isin(self._codes, photon.codes)
            else:
                match = [k for k in record_kinds() if k.key == kind]
                codes = match[0].codes if match else ()
                wanted = np.isin(self._codes, codes)
            mask = wanted if mask is None else (mask & wanted)
        return mask

    def filtered_count(self, channel: int | None = None, kind: str | None = None) -> int:
        """How many records the channel and kind filters let through.

        ``None`` and any negative channel (the UI's "All channels" sentinel)
        mean every channel; ``None`` or ``"all"`` every kind, ``"markers"``
        every marker, a kind key that kind.
        """
        mask = self._mask(channel, kind)
        return self.n_records if mask is None else int(np.count_nonzero(mask))

    def filtered_indices(self, channel: int | None = None, kind: str | None = None) -> np.ndarray:
        """Record indices the channel and kind filters let through (see :meth:`filtered_count`)."""
        mask = self._mask(channel, kind)
        if mask is None:
            return np.arange(self.n_records, dtype=np.int64)
        return np.flatnonzero(mask).astype(np.int64)

    # ── paging ────────────────────────────────────────────────────────

    def clamp_first(
        self, first: int, rows: int, channel: int | None = None, kind: str | None = None
    ) -> int:
        """Clamp a page's first record index into the filtered range."""
        count = self.filtered_count(channel, kind)
        first = int(first)
        first = max(0, min(first, max(count - 1, 0)))
        # Never let a page run past the end of the filtered selection.
        first = max(0, min(first, max(count - rows, 0)))
        return first

    def page(
        self, first: int, rows: int, channel: int | None = None, kind: str | None = None
    ) -> list[dict]:
        """One page of table rows: ``rows`` records from ``first`` on.

        The *photon* field is the record's index among the filtered records --
        the row number a downstream script would address -- while *idx* is the
        index in the raw file. *kind* is the declared label of the record's
        kind, *kind_key* its key.
        """
        rows = max(1, min(int(rows), 20_000))
        indices = self.filtered_indices(channel, kind)
        first = self.clamp_first(first, rows, channel, kind)
        window = indices[first : first + rows]
        macro_ms = (
            self._macro[window] * self.macro_resolution * 1e3
            if self.macro_resolution > 0
            else self._macro[window]
        )
        by_code = {c: k for k in record_kinds() for c in k.codes}
        out = []
        for j, i in enumerate(window):
            k = by_code.get(int(self._codes[i]))
            out.append(
                {
                    "photon": int(first + j),
                    "idx": int(i),
                    "kind": k.label if k else str(int(self._codes[i])),
                    "kind_key": k.key if k else "",
                    "channel": int(self._routing[i]),
                    "micro": int(self._micro[i]),
                    "macro": float(macro_ms[j]),
                }
            )
        return out

    def page_tsv(
        self, first: int, rows: int, channel: int | None = None, kind: str | None = None
    ) -> str:
        """One page as TSV -- what 'Copy visible' puts on the clipboard."""
        records = self.page(first, rows, channel, kind)
        header = "photon\tidx\tkind\tchannel\tmicro\tmacro_ms"
        lines = [header]
        lines += [
            f"{r['photon']}\t{r['idx']}\t{r['kind_key']}\t{r['channel']}\t{r['micro']}"
            f"\t{r['macro']:.6f}"
            for r in records
        ]
        return "\n".join(lines) + "\n"
