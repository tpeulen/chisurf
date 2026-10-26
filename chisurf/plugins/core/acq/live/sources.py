"""Photon sources for live recording: something that hands out decoded photons in time order.

A source is what the Record tool measures from. It is started, read in batches while it runs, and
stopped; it says what its clocks are (:class:`SourceInfo`) and how it is doing (:meth:`status`).
Three exist:

* :class:`SimulatedPieSource` -- a PIE smFRET measurement simulated by tttrlib's ``SimEngine``,
  handed out at the pace a real one would arrive. Populations are given by their FRET efficiency
  E and stoichiometry S, so a run has a known answer.
* :class:`FileReplaySource` -- a recorded measurement played back at measurement speed.
* a device -- not available yet: the MultiHarp source arrives with the driver being built in CMC
  and implements this same interface.

The simulator models two lasers per molecule the way tttrlib does for ALEX (one excitation grid
and one brightness row per laser, alternating every ``dt``), then places each photon of the red
(acceptor-exciting) laser into the second half of the laser period. Per molecule this is what
pulsed interleaved excitation produces: the same molecule excited alternately by both lasers,
separated in micro-time -- prompt window for the green pulse, delay window for the red one.
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import tttrlib

__all__ = [
    "FileReplaySource",
    "PhotonBatch",
    "PhotonSource",
    "Population",
    "SimulatedPieSource",
    "SourceInfo",
    "SourceUnavailable",
]


class SourceUnavailable(RuntimeError):
    """The source cannot run here (no driver, no file)."""


@dataclass(frozen=True)
class SourceInfo:
    """The clocks of a source's photons.

    Attributes
    ----------
    name : str
        What the Record tool shows.
    macro_clock_s : float
        Seconds per macro-time tick.
    micro_res_s : float
        Seconds per micro-time channel.
    n_micro : int
        Micro-time channels in one laser period (the PIE period).
    """

    name: str
    macro_clock_s: float
    micro_res_s: float
    n_micro: int


@dataclass
class PhotonBatch:
    """Decoded photons in time order: macro-time ticks, micro-time channels, routing channels.

    ``truth`` is the simulator's population index per photon (background is the index after the
    last population); real sources leave it ``None``. ``raw`` is the device's undecoded records the
    batch came from, when there were any (what a device recording writes).
    """

    macro: np.ndarray
    micro: np.ndarray
    channel: np.ndarray
    truth: np.ndarray | None = None
    raw: np.ndarray | None = None

    def __len__(self) -> int:
        return len(self.macro)


class PhotonSource:
    """The interface every source implements. One thread reads; :meth:`stop` may come from any."""

    info: SourceInfo

    def start(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    def read(self, timeout: float = 0.2) -> PhotonBatch | None:
        """The photons that arrived since the last read; ``None`` when nothing came in *timeout*."""
        raise NotImplementedError

    @property
    def finished(self) -> bool:
        """Nothing more will come (stopped, or the data ran out)."""
        raise NotImplementedError

    def status(self) -> dict[str, Any]:
        """Health for the Record tool: ``queued`` batches, ``dropped`` batches, ``error``."""
        return {"queued": 0, "dropped": 0, "error": ""}


@dataclass(frozen=True)
class Population:
    """A simulated FRET population.

    Attributes
    ----------
    E, S : float
        FRET efficiency and stoichiometry of a molecule (with gamma = beta = 1).
    concentration : float
        Molecules per simulation box (tttrlib's ``population``).
    brightness : float
        Photons per ms under the green laser at the focus centre (donor + acceptor channel).
    """

    E: float
    S: float = 0.5
    concentration: float = 1.5
    brightness: float = 300.0


@dataclass
class _Clock:
    """Wall-clock pacing: how much measurement time may have arrived by now."""

    speed: float = 1.0
    realtime: bool = True
    t0: float = field(default_factory=time.monotonic)

    def allowed_s(self) -> float:
        return (time.monotonic() - self.t0) * self.speed if self.realtime else float("inf")


#: The simulator's time base (tttrlib's convention: one macro unit = 1 ms).
_DT_MS = 0.01  # one simulation window = 10 us
_MACRO_TICK_MS = _DT_MS / 1024  # ~9.77 ns, as tttrlib's own ALEX example
_LASER_PERIOD_NS = 32.0
_MICRO_RES_NS = 0.008
_N_MICRO = int(round(_LASER_PERIOD_NS / _MICRO_RES_NS))  # 4000 channels per period
_HALF = _N_MICRO // 2


class SimulatedPieSource(PhotonSource):
    """A PIE smFRET measurement from tttrlib's ``SimEngine``, delivered at measurement pace.

    Parameters
    ----------
    populations : sequence of Population
        The FRET species; each molecule carries donor and acceptor.
    duration_s : float, optional
        Length of the measurement; ``None`` runs until :meth:`stop`.
    background_khz : (float, float)
        Background count rate per detector (donor, acceptor), uniform in micro-time.
    seed : int
        Seeds diffusion and emission; segment *k* uses ``seed + k``, so a run is reproducible.
    batch_s : float
        Measurement time per batch handed to the reader.
    speed : float
        1 is real time; larger plays faster.
    realtime : bool
        ``False`` hands batches out as fast as they are simulated (tests).
    segment_s : float
        Measurement time simulated per engine run. Molecules are re-seeded at a segment boundary,
        which may cut a burst; long segments make that rare.

    Notes
    -----
    Routing channel 0 is the donor detector, 1 the acceptor detector. The prompt window is the
    first half of the 32 ns period, the delay window the second.
    """

    def __init__(
        self,
        populations=(Population(0.2), Population(0.8)),
        *,
        duration_s: float | None = 10.0,
        background_khz=(0.5, 0.5),
        seed: int = 1,
        batch_s: float = 0.1,
        speed: float = 1.0,
        realtime: bool = True,
        segment_s: float = 5.0,
    ):
        self.populations = tuple(populations)
        self.duration_s = duration_s
        self.background_khz = tuple(background_khz)
        self.seed = int(seed)
        self.batch_s = float(batch_s)
        self.segment_s = float(segment_s)
        self._clock = _Clock(speed=float(speed), realtime=bool(realtime))
        self.info = SourceInfo(
            name="Simulator (PIE smFRET)",
            macro_clock_s=_MACRO_TICK_MS * 1e-3,
            micro_res_s=_MICRO_RES_NS * 1e-9,
            n_micro=_N_MICRO,
        )
        self._queue: queue.Queue = queue.Queue(maxsize=8)
        self._stop = threading.Event()
        self._done = threading.Event()
        self._thread: threading.Thread | None = None
        self._pending: PhotonBatch | None = None
        self._released_s = 0.0
        self.error = ""

    # -- the simulation ---------------------------------------------------------------------
    def config(self, segment: int) -> dict:
        """The ``SimEngine`` configuration of one segment (public: the tests read the truth)."""
        species = []
        for p in self.populations:
            green = float(p.brightness)
            red = green * (1.0 - p.S) / max(p.S, 1e-9)
            species.append(
                {
                    "D": 0.05,
                    "q_alex": [[(1.0 - p.E) * green, p.E * green], [0.0, red]],
                    "decay": {
                        "lifetimes": [4.0 * (1.0 - p.E) + 0.1],
                        "amplitudes": [1.0],
                        "dt": _MICRO_RES_NS,
                    },
                }
            )
        n = len(species)
        bg_pattern = [1.0] * _HALF
        return {
            "settings": {
                "dt": _DT_MS,
                "n_ph_max": 50_000_000,
                "n_channels": 2,
                "n_microtime_channels": _N_MICRO,
                "microtime_resolution": _MICRO_RES_NS,
                "laser_period": _LASER_PERIOD_NS,
                "alex_period": 2 * _DT_MS,
                "alex_markers": False,
                "active_margin": 1.0,
                "fast_grid_bbox": True,
                "max_windows": int(round(self.segment_s * 1000.0 / _DT_MS)),
                "seed_diffusion": self.seed + 7919 * segment,
                "seed_emission": self.seed + 104729 * segment + 1,
            },
            "box": {"xy": 2.0, "z": 4.0},
            "species": species,
            "k_rad": [0.0] * (n * n),
            "k_nrad": [0.0] * (n * n),
            # tttrlib's background is a rate per macro unit (ms) and channel.
            "background": [float(b) for b in self.background_khz],
            "background_decay": {"pattern": bg_pattern, "dt": _MICRO_RES_NS},
            "population": [float(p.concentration) for p in self.populations],
            "excitation": [
                {
                    "type": "gaussian3d",
                    "w0": 0.3,
                    "z0": 2.0,
                    "extent_xy": 2.0,
                    "extent_z": 4.0,
                    "spacing": 0.1,
                },
                {
                    "type": "gaussian3d",
                    "w0": 0.32,
                    "z0": 2.1,
                    "extent_xy": 2.0,
                    "extent_z": 4.0,
                    "spacing": 0.1,
                },
            ],
        }

    def simulate_segment(self, segment: int) -> PhotonBatch:
        """All photons of one segment, PIE-encoded and sorted; macro times start at the segment."""
        engine = tttrlib.SimEngine.from_dict(self.config(segment))
        engine.run()
        ph = engine.photons()
        keep = np.asarray(ph["event_type"]) == 0
        window = np.asarray(ph["macro_window"])[keep].astype(np.int64)
        arrival = np.asarray(ph["arrival_time"])[keep]
        t_ms = window * _DT_MS + arrival
        macro = np.floor(t_ms / _MACRO_TICK_MS).astype(np.uint64)
        macro += np.uint64(int(round(segment * self.segment_s * 1000.0 / _MACRO_TICK_MS)))
        # The laser of a window alternates every dt (alex_period = 2 dt): odd windows are red.
        red = (window % 2) == 1
        micro = (np.asarray(ph["micro_time"])[keep].astype(np.int64) % _HALF) + np.where(
            red, _HALF, 0
        )
        channel = np.asarray(ph["channel"])[keep].astype(np.int8)
        species = np.asarray(ph["species"])[keep].astype(np.int16)
        order = np.argsort(macro, kind="stable")
        return PhotonBatch(
            macro[order], micro[order].astype(np.uint16), channel[order], species[order]
        )

    def _produce(self) -> None:
        try:
            segment = 0
            while not self._stop.is_set():
                if self.duration_s is not None and segment * self.segment_s >= self.duration_s:
                    break
                batch = self.simulate_segment(segment)
                if self.duration_s is not None:
                    limit = int(self.duration_s * 1000.0 / _MACRO_TICK_MS)
                    cut = int(np.searchsorted(batch.macro, np.uint64(limit)))
                    batch = PhotonBatch(
                        batch.macro[:cut], batch.micro[:cut], batch.channel[:cut], batch.truth[:cut]
                    )
                while not self._stop.is_set():
                    try:
                        self._queue.put(batch, timeout=0.2)
                        break
                    except queue.Full:
                        continue
                segment += 1
        except Exception as exc:  # noqa: BLE001 - reported through status(), the reader stops
            self.error = f"{type(exc).__name__}: {exc}"
        finally:
            self._done.set()

    # -- the source interface -----------------------------------------------------------------
    def start(self) -> None:
        self._stop.clear()
        self._done.clear()
        self._clock = _Clock(speed=self._clock.speed, realtime=self._clock.realtime)
        self._released_s = 0.0
        self._thread = threading.Thread(target=self._produce, name="sim-pie-source", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    @property
    def finished(self) -> bool:
        return (
            (self._stop.is_set() or self._done.is_set())
            and self._queue.empty()
            and self._pending is None
        )

    def status(self) -> dict[str, Any]:
        return {"queued": self._queue.qsize(), "dropped": 0, "error": self.error}

    def read(self, timeout: float = 0.2) -> PhotonBatch | None:
        deadline = time.monotonic() + timeout
        while True:
            if self._pending is None:
                try:
                    self._pending = self._queue.get(timeout=max(0.0, deadline - time.monotonic()))
                except queue.Empty:
                    return None
            if self._stop.is_set():
                self._pending = None
                return None
            allowed = self._clock.allowed_s()
            upto = (
                min(allowed, self._released_s + self.batch_s)
                if self._clock.realtime
                else float("inf")
            )
            pending = self._pending
            if upto == float("inf"):
                cut = len(pending)
            else:
                cut = int(
                    np.searchsorted(pending.macro, np.uint64(int(upto / self.info.macro_clock_s)))
                )
            if cut == 0 and len(pending):
                if time.monotonic() >= deadline:
                    return None
                time.sleep(min(0.02, max(0.0, deadline - time.monotonic())))
                continue
            out = PhotonBatch(
                pending.macro[:cut], pending.micro[:cut], pending.channel[:cut], pending.truth[:cut]
            )
            rest = PhotonBatch(
                pending.macro[cut:], pending.micro[cut:], pending.channel[cut:], pending.truth[cut:]
            )
            self._pending = rest if len(rest) else None
            if upto != float("inf"):
                self._released_s = upto
            return out


class FileReplaySource(PhotonSource):
    """A recorded measurement played back at measurement speed.

    Parameters
    ----------
    path : str or Path
        A TTTR file or a container member address (``m000.pto/m000.ptu``).
    speed, realtime, batch_s : see :class:`SimulatedPieSource`.
    """

    def __init__(self, path, *, speed: float = 1.0, realtime: bool = True, batch_s: float = 0.1):
        self.path = str(path)
        try:
            from chisurf.core.fio.staging import open_tttr

            self._tttr = open_tttr(self.path)
        except Exception:  # noqa: BLE001 - a plain file opens directly
            self._tttr = tttrlib.TTTR(self.path)
        if self._tttr is None or len(self._tttr) == 0:
            raise SourceUnavailable(f"no photons in {self.path}")
        header = self._tttr.header
        micro_res = float(header.micro_time_resolution) or 1e-12
        n_micro = int(getattr(header, "number_of_micro_time_channels", 0) or 0)
        if n_micro <= 0:
            micro = np.asarray(self._tttr.micro_times)
            n_micro = int(micro.max()) + 1 if len(micro) else 1
        self.info = SourceInfo(
            name=f"Replay: {Path(self.path).name}",
            macro_clock_s=float(header.macro_time_resolution),
            micro_res_s=micro_res,
            n_micro=n_micro,
        )
        self._macro = np.asarray(self._tttr.macro_times).astype(np.uint64)
        self._micro = np.asarray(self._tttr.micro_times).astype(np.uint16)
        self._channel = np.asarray(self._tttr.routing_channels).astype(np.int8)
        self._t0 = int(self._macro[0])
        self._clock = _Clock(speed=float(speed), realtime=bool(realtime))
        self.batch_s = float(batch_s)
        self._pos = 0
        self._stop = threading.Event()

    def start(self) -> None:
        self._pos = 0
        self._stop.clear()
        self._clock = _Clock(speed=self._clock.speed, realtime=self._clock.realtime)

    def stop(self) -> None:
        self._stop.set()

    @property
    def finished(self) -> bool:
        return self._stop.is_set() or self._pos >= len(self._macro)

    def read(self, timeout: float = 0.2) -> PhotonBatch | None:
        if self.finished:
            return None
        deadline = time.monotonic() + timeout
        while True:
            if self._clock.realtime:
                upto = self._t0 + int(self._clock.allowed_s() / self.info.macro_clock_s)
                end = int(np.searchsorted(self._macro, np.uint64(upto), side="right"))
            else:
                end = min(len(self._macro), self._pos + 100_000)
            if end > self._pos:
                s = slice(self._pos, end)
                self._pos = end
                return PhotonBatch(self._macro[s], self._micro[s], self._channel[s])
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.02)
