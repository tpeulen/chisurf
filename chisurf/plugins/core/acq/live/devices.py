"""PicoQuant devices as Record sources: one live path for the hardware and the simulator.

The device layer is CMC's ``pqusb`` package (PicoQuant TCSPC devices over libusb, without
PicoQuant's libraries). A :class:`DeviceSource` wraps any of its ``TcspcDevice`` objects: it runs the
device's continuous stream, decodes the raw records with tttrlib (``decode_records`` with a
carried ``TTTRDecodeState``, the same decoding a PTU file gets) and records the raw words through
pqusb's ``PtuWriter``, so the PTU holds exactly the bytes the device sent.

The PIE smFRET simulator is such a device too (:class:`PieSimDevice`): it turns the photons of
tttrlib's ``SimEngine`` into MultiHarp generic-T3 records, so a simulated run walks the hardware
code path from the FIFO read on -- the decoding, the recording and the analysis are the ones a
MultiHarp run uses.

pqusb is optional: :data:`PQUSB` says whether it imports.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import numpy as np
import tttrlib

from .sources import (
    PhotonBatch,
    PhotonSource,
    Population,
    SimulatedPieSource,
    SourceInfo,
    SourceUnavailable,
)

# pqusb from ~/dev/cmc/tools/pqusb until it is packaged (2026-10-26): installed editable into the
# environment; without it the Record tool offers the photon-level simulator only.
try:
    import pqusb
    from pqusb.device import MODE_T3, TACQ_MAX_MS, DeviceError, Identity, InputSettings, TcspcDevice
    from pqusb.records import RT_GENERIC_T3

    PQUSB = True
except Exception:  # noqa: BLE001 - optional dependency
    pqusb = None
    PQUSB = False
    TcspcDevice = object  # type: ignore[misc,assignment]

__all__ = ["PQUSB", "DeviceSource", "PieSimDevice", "attached_devices", "tttr_record_type"]


#: PicoQuant TTResultFormat_TTTRRecType -> tttrlib record type of the same layout.
_TTTR_RECORD = {
    0x00010303: "RECORD_PHT3",  # PicoHarp 300 T3
    0x00010203: "RECORD_PHT2",
    0x00010304: "RECORD_HHT3v1",  # HydraHarp 400 V1
    0x00010204: "RECORD_HHT2v1",
    0x01010304: "RECORD_HHT3v2",  # HydraHarp 400 V2
    0x01010204: "RECORD_HHT2v2",
    0x00010305: "RECORD_HHT3v2",  # TimeHarp 260 N (V2 layout)
    0x00010205: "RECORD_HHT2v2",
    0x00010306: "RECORD_HHT3v2",  # TimeHarp 260 P
    0x00010206: "RECORD_HHT2v2",
    0x00010307: "RECORD_GENERIC_T3",  # MultiHarp 150/160, PicoHarp 330
    0x00010207: "RECORD_GENERIC_T2",
}


def tttr_record_type(pq_rectype: int) -> int:
    """tttrlib's record type for a PicoQuant one; raises for a layout tttrlib does not decode."""
    name = _TTTR_RECORD.get(int(pq_rectype))
    if name is None or not hasattr(tttrlib, name):
        raise SourceUnavailable(f"tttrlib decodes no PicoQuant record type {int(pq_rectype):#010x}")
    return int(getattr(tttrlib, name))


def attached_devices() -> list[str]:
    """PicoQuant devices libusb sees (``[index] description``); empty without pqusb or devices."""
    if not PQUSB:
        return []
    try:
        return list(pqusb.list_devices())
    except Exception:  # noqa: BLE001 - no libusb backend: no devices
        return []


class DeviceSource(PhotonSource):
    """A pqusb ``TcspcDevice`` streaming T3 records, decoded live and recorded raw.

    Parameters
    ----------
    device : TcspcDevice
        Opened and initialised in T3 mode, settings applied.
    duration_s : float or None
        The device's acquisition timer; ``None`` measures until :meth:`stop`.
    chunk_bytes : int
        Bytes per FIFO read.

    Notes
    -----
    The device's timer ends a timed run (``stops_itself``), so the recording and the analysis cover
    the same records.
    """

    stops_itself = True

    def __init__(self, device, *, duration_s: float | None = None, chunk_bytes: int = 1 << 16):
        if not PQUSB:
            raise SourceUnavailable("pqusb is not installed")
        if device.mode != MODE_T3:
            raise SourceUnavailable("the Record tool measures in T3 mode")
        self.device = device
        self.duration_s = duration_s
        self.chunk_bytes = int(chunk_bytes)
        sync = self._sync_rate()
        if sync <= 0:
            raise SourceUnavailable("no sync signal: connect the laser's sync output")
        self.sync_rate_hz = sync
        period = 1.0 / sync
        res = float(device.resolution_s())
        ident = device.identity
        self.info = SourceInfo(
            name=f"{getattr(ident, 'model', 'device')} {getattr(ident, 'serial', '')}".strip(),
            macro_clock_s=period,
            micro_res_s=res,
            n_micro=max(1, int(round(period / res))),
        )
        self._record_type = tttr_record_type(device.record_type())
        self._gen = None
        self._state = None
        self._stop = threading.Event()
        self._done = threading.Event()
        self._started = 0.0
        self._reader: int | None = None

    def _sync_rate(self) -> float:
        try:
            sync, _inputs = self.device.count_rates()
        except Exception:  # noqa: BLE001 - devices without a rate query state theirs
            sync = getattr(self.device, "sync_rate_hz", 0.0)
        div = max(1, int(getattr(self.device.settings, "sync_div", 1) or 1))
        return float(sync) / div if sync else 0.0

    # -- the source interface -----------------------------------------------------------------
    def start(self) -> None:
        self._stop.clear()
        self._done.clear()
        self._state = tttrlib.TTTRDecodeState()
        tacq_ms = int(self.duration_s * 1000) if self.duration_s else TACQ_MAX_MS
        self._gen = self.device.stream(
            self.chunk_bytes, tacq_ms=tacq_ms, restart=self.duration_s is None
        )
        self._started = time.monotonic()

    def stop(self) -> None:
        """Stop measuring. From the reading thread the stream closes now; from any other thread
        (the UI) the reader closes it on its next read -- a generator closes in its own thread."""
        self._stop.set()
        if threading.get_ident() == self._reader:
            self._close()

    def _close(self) -> None:
        if self._gen is not None:
            gen, self._gen = self._gen, None
            gen.close()  # stops the measurement and joins pqusb's reader thread
        self._done.set()

    @property
    def finished(self) -> bool:
        return self._done.is_set()

    def status(self) -> dict[str, Any]:
        st = self.device.stats
        error = repr(st.error) if getattr(st, "error", None) else ""
        return {
            "queued": 0,
            "dropped": int(getattr(st, "fifo_full", 0)),
            "stalls": int(getattr(st, "consumer_stalls", 0)),
            "error": error,
        }

    def read(self, timeout: float = 0.2) -> PhotonBatch | None:
        """The next chunk of records, decoded (called by the session's worker thread only)."""
        self._reader = threading.get_ident()
        if self._gen is None:
            return None
        if self._stop.is_set():
            self._close()
            return None
        try:
            words = next(self._gen)  # pqusb sends a heartbeat every 0.5 s without data
        except StopIteration:
            self._close()
            return None
        if len(words) == 0:
            return None
        raw = np.frombuffer(words, dtype=np.uint32)
        data = tttrlib.TTTR()
        tttrlib.decode_records(raw, self._record_type, self._state, data)
        if len(data) == 0:
            return PhotonBatch(
                np.zeros(0, np.uint64), np.zeros(0, np.uint16), np.zeros(0, np.int8), raw=raw
            )
        return PhotonBatch(
            np.asarray(data.macro_times).astype(np.uint64),
            np.asarray(data.micro_times).astype(np.uint16),
            np.asarray(data.routing_channels).astype(np.int8),
            raw=raw,
            event=np.asarray(data.event_types).astype(np.int8),
        )

    # -- recording -----------------------------------------------------------------------------
    def make_recorder(self, path, name: str = "", extra: dict | None = None):
        """A PTU writer for the device's raw records (pqusb's, with the device's header and the
        *extra* tags -- the run's acquisition settings, and a scan's ``ImgHdr_*`` tags). String
        values are string tags; bool, int and float values keep their PicoQuant type."""
        typed = {k: v for k, v in (extra or {}).items() if not isinstance(v, str)}
        cls = _typed_writer(typed) if typed else pqusb.PtuWriter
        return _RawPtuRecorder(cls.for_device(str(path), self.device, extra=extra), self)


_UNSET = object()


def _typed_writer(typed: dict):
    """pqusb's ``PtuWriter`` writing the named *extra* tags with their type (pqusb writes every
    extra tag as a string; a scan's ImgHdr tags must be numbers and booleans for readers)."""

    class _TypedPtuWriter(pqusb.PtuWriter):
        _TYPED = dict(typed)

        def _s(self, name, s, idx=-1):
            value = self._TYPED.get(name, _UNSET)
            if value is _UNSET:
                return super()._s(name, s, idx)
            if isinstance(value, bool):
                return self._b(name, value, idx)
            if isinstance(value, (int, np.integer)):
                return self._i(name, int(value), idx)
            return self._f(name, float(value), idx)

    return _TypedPtuWriter


class _RawPtuRecorder:
    def __init__(self, writer, source: DeviceSource):
        self.writer = writer
        self.source = source

    def write(self, batch: PhotonBatch) -> bool:
        if batch.raw is not None and len(batch.raw):
            self.writer.write(batch.raw.tobytes())
        return True

    def close(self) -> None:
        acq_ms = (
            int((time.monotonic() - self.source._started) * 1000) if self.source._started else 0
        )
        self.writer.close(acq_ms=acq_ms, sync_rate_hz=int(round(self.source.sync_rate_hz)))


#: Measurement time the simulated device synthesises per FIFO read at most.
_MAX_READ_S = 0.05

if PQUSB:

    class PieSimDevice(TcspcDevice):
        """A MultiHarp that measures a simulated PIE smFRET sample.

        Records are MultiHarp generic-T3 words built from the photons of
        :class:`~chisurf.plugins.core.acq.live.sources.SimulatedPieSource` (tttrlib's ``SimEngine``):
        one sync per laser period, the micro time in the device's bins, overflow records every 1024
        syncs, delivered at measurement pace through the device FIFO hooks pqusb's ``acquire``
        and ``stream`` read.

        Parameters
        ----------
        populations : sequence of Population
        background_khz : (float, float)
        seed : int
        speed : float
            1 is real time.
        """

        hw_type = "MultiHarp"
        record_types = {MODE_T3: RT_GENERIC_T3}
        base_res_ps = 80

        def __init__(
            self,
            populations=(Population(0.2), Population(0.8)),
            *,
            background_khz=(0.5, 0.5),
            seed: int = 1,
            speed: float = 1.0,
            scheme: str = "pie",
            realism=None,
        ):
            super().__init__()
            self.scheme = scheme
            self.realism = realism
            self.populations = tuple(populations)
            self.background_khz = tuple(background_khz)
            self.seed = int(seed)
            self.speed = float(speed)
            self._photons: SimulatedPieSource | None = None
            self.period_s = 32e-9
            self.sync_rate_hz = 1.0 / self.period_s
            self._t0: float | None = None
            self._tacq_s = 0.0
            self._sent_s = 0.0
            self._wrap = 0
            self._pending = np.zeros(0, np.uint32)
            self._buffer: PhotonBatch | None = None
            self._recent = np.zeros(2, np.int64)

        def initialize(self, mode: int = MODE_T3, refsource: int = 0) -> Identity:
            if mode != MODE_T3:
                raise DeviceError("the PIE simulator measures in T3 mode")
            self.mode, self.nchan = mode, 2
            self.settings.inputs = [InputSettings() for _ in range(self.nchan)]
            what = "PIE smFRET" if self.scheme == "pie" else "two-colour smFRET"
            self.identity = Identity(
                model=f"MultiHarp (simulated {what})", serial="SIMPIE01", partno="sim"
            )
            return self.identity

        # settings: remembered (they go into the PTU header), as pqusb's SimDevice does
        def set_sync_div(self, div):
            self.settings.sync_div = int(div)

        def set_sync_edge_trg(self, level_mv, edge):
            self.settings.sync.level_mv, self.settings.sync.edge = level_mv, edge

        def set_sync_channel_offset(self, ps):
            self.settings.sync.offset_ps = ps

        def set_input_edge_trg(self, ch, level_mv, edge):
            s = self.settings.inputs[ch]
            s.level_mv, s.edge = level_mv, edge

        def set_input_channel_offset(self, ch, ps):
            self.settings.inputs[ch].offset_ps = ps

        def set_input_channel_enable(self, ch, en):
            self.settings.inputs[ch].enabled = bool(en)

        def set_binning(self, code):
            self.settings.binning = int(code)

        def set_offset(self, ns):
            self.settings.offset_ns = int(ns)

        def count_rates(self) -> tuple[int, list[int]]:
            """Sync and per-input rates (Hz) over the last delivered second."""
            return int(round(self.sync_rate_hz)), [int(r) for r in self._recent]

        # -- measurement hooks ------------------------------------------------------------------
        def start(self, tacq_ms: int) -> None:
            if int(self.settings.sync_div) != 1:
                raise DeviceError("the PIE simulator runs with sync divider 1")
            self._photons = SimulatedPieSource(
                self.populations,
                duration_s=None,
                background_khz=self.background_khz,
                seed=self.seed,
                realtime=False,
                scheme=self.scheme,
                **({"realism": self.realism} if self.realism is not None else {}),
            )
            self._photons.start()
            self._t0 = time.monotonic()
            self._tacq_s = tacq_ms / 1000.0
            self._sent_s, self._wrap = 0.0, 0
            self._pending = np.zeros(0, np.uint32)
            self._buffer = None

        def stop(self) -> None:
            self._t0 = None
            if self._photons is not None:
                self._photons.stop()

        def close(self) -> None:
            self.stop()

        def _poll(self, st) -> bool:
            st.sync_rate = int(round(self.sync_rate_hz))
            # the acquisition time is measurement time delivered, not wall time: a simulation that
            # runs slower than the requested speed delays the end, it never shortens the run
            return self._t0 is not None and self._sent_s < self._tacq_s

        def _elapsed(self) -> float:
            return (time.monotonic() - self._t0) * self.speed if self._t0 is not None else 0.0

        def _fifo_read(self, buf, timeout_ms: int) -> int:
            if self._t0 is not None:
                # at most _MAX_READ_S of measurement per read: a consumer that fell behind at a high
                # speed must not make one read synthesise seconds of records at once (memory)
                upto = min(self._elapsed(), self._tacq_s, self._sent_s + _MAX_READ_S)
                if upto - self._sent_s >= 0.005 or (upto >= self._tacq_s > self._sent_s):
                    self._pending = np.concatenate([self._pending, self._records_until(upto)])
                    self._sent_s = upto
            if self._pending.size == 0:
                time.sleep(min(0.005, timeout_ms / 1000.0))
                return 0
            n = min(self._pending.size, len(buf) // 4)
            memoryview(buf)[: 4 * n] = memoryview(self._pending[:n].tobytes())
            self._pending = self._pending[n:]
            return 4 * n

        # -- record synthesis -------------------------------------------------------------------
        def _take_photons(self, upto_s: float):
            """The simulator's photons with arrival time below *upto_s* (seconds)."""
            clock = self._photons.info.macro_clock_s
            limit = np.uint64(int(upto_s / clock))
            parts = []
            while True:
                if self._buffer is None or len(self._buffer) == 0:
                    self._buffer = self._photons.read(timeout=5.0)
                    if self._buffer is None:
                        # the simulator is still computing this stretch: wait for it (a device
                        # cannot skip time it measured) unless it has finished or failed
                        if (
                            self._t0 is None  # stopped
                            or self._photons.finished
                            or self._photons.status().get("error")
                        ):
                            break
                        continue
                cut = int(np.searchsorted(self._buffer.macro, limit))
                b = self._buffer
                parts.append((b.macro[:cut], b.micro[:cut], b.channel[:cut]))
                if cut < len(b):
                    self._buffer = PhotonBatch(
                        b.macro[cut:], b.micro[cut:], b.channel[cut:], b.truth[cut:]
                    )
                    break
                self._buffer = None
            if not parts:
                return np.zeros(0), np.zeros(0, np.int64), np.zeros(0, np.int64)
            t = np.concatenate([p[0] for p in parts]).astype(np.float64) * clock
            micro = np.concatenate([p[1] for p in parts]).astype(np.int64)
            channel = np.concatenate([p[2] for p in parts]).astype(np.int64)
            return t, micro, channel

        def _records_until(self, upto_s: float) -> np.ndarray:
            t, micro, channel = self._take_photons(upto_s)
            src_res = self._photons.info.micro_res_s
            res = self.resolution_s()
            nbins = max(1, int(round(self.period_s / res)))
            dtime = np.minimum((micro * src_res / res).astype(np.int64), nbins - 1)
            nsync = np.floor(t / self.period_s).astype(np.int64)
            for k in range(2):
                self._recent[k] = int(np.sum(channel == k) / max(upto_s - self._sent_s, 1e-9))
            # an overflow record before each photon whose 1024-sync block is new
            wrap = nsync // 1024
            out: list[int] = []
            words = ((channel & 0x3F) << 25) | ((dtime & 0x7FFF) << 10) | (nsync & 0x3FF)
            last = self._wrap
            change = np.flatnonzero(np.diff(np.concatenate([[last], wrap])) > 0)
            start = 0
            for i in change:
                out.extend(words[start:i].tolist())
                self._emit_overflow(out, int(wrap[i]) - last)
                last = int(wrap[i])
                start = i
            out.extend(words[start:].tolist())
            end_wrap = int(np.floor(upto_s / self.period_s)) // 1024
            if end_wrap > last:  # overflows keep coming without photons, as the hardware's do
                self._emit_overflow(out, end_wrap - last)
                last = end_wrap
            self._wrap = last
            return np.asarray(out, dtype=np.uint32)

        @staticmethod
        def _emit_overflow(out: list, n: int) -> None:
            while n > 0:
                k = min(n, 1023)
                out.append(0xFE000000 | k)
                n -= k

else:
    PieSimDevice = None  # type: ignore[assignment]
