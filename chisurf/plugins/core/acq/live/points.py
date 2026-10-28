"""Point measurements: the focus parked on picked points, one recording per point, in turn.

The MT200 software's point measurement, observed on the instrument
(libphacq ``docs/pi_e725_scanner.md``): the user picks points on an image; for each point the
piezo stage makes a settled move (no wave generator, no line markers) and the TCSPC device records
a run of its own. Here a point's run ends after its time, or -- with ``until_bleached`` -- earlier,
when the molecule has bleached: :class:`BleachDetector` watches the count rate and calls a step
down to the background level.

* :class:`PiScanner` -- the MT200's PI E-725 stage through libphacq's ``pi`` driver (rasters with
  line markers, settled point moves).
* :class:`BleachDetector` -- the count-rate rule that ends a point.
* :class:`PointRecordSession` -- a :class:`~.session.RecordSession` that stops itself on bleaching
  and carries its point in the header.
* :class:`PointSequence` -- the points measured one after the other in a worker thread.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np

from .scanner import ScannerBackend, ScanSettings
from .session import RecordSession, RunResult

_log = logging.getLogger(__name__)

__all__ = ["BleachDetector", "PiScanner", "PointRecordSession", "PointResult", "PointSequence"]



class PiScanner(ScannerBackend):
    """The PI E-725 piezo stage (MT200) through libphacq's ``pi`` driver.

    Parameters
    ----------
    address : str
        What ``phacq``'s ``pi`` driver opens: ``""`` the first E-725 on USB, a USB serial,
        ``"tcp:host[:port]"``, or ``"sim:"`` (the simulator).
    device : phacq.Device, optional
        An already opened ``pi`` device (``address`` is then ignored).
    learn_s, turn_ms : float
        The raster's settling ("learning") time and turnaround (20 ms fast, 35 ms accurate).
    """

    name = "PI E-725 piezo stage"

    def __init__(self, address: str = "", *, device=None, learn_s: float = 5.0,
                 turn_ms: float = 20.0):
        if device is None:
            import phacq

            device = phacq.DriverRegistry.instance().driver("pi").open(address)
        self.device = device
        self.learn_s = float(learn_s)
        self.turn_ms = float(turn_ms)
        self.scan = ScanSettings()

    def configure(self, scan: ScanSettings) -> list[str]:
        problems = scan.validate()
        if problems:
            raise ValueError("; ".join(problems))
        self.scan = scan
        if scan.is_points:
            return []
        d = self.device
        for name, value in (
            ("x0_um", scan.x0_um), ("y0_um", scan.y0_um), ("width_um", scan.area_x_um),
            ("pixels_x", scan.pixels_x), ("lines", scan.pixels_y),
            ("line_pitch_um", scan.area_y_um / max(1, scan.pixels_y)),
            ("dwell_ms", scan.dwell_ms), ("bidirectional", 1 if scan.bidirectional else 0),
            ("learn_s", self.learn_s), ("turn_ms", self.turn_ms),
        ):
            d.set_parameter(name, float(value))
        return []

    def start(self) -> None:
        """Start the raster (learning, line triggers, image); a point list has nothing to start."""
        if not self.scan.is_points:
            self.device.start(0.0)

    def stop(self) -> None:
        self.device.stop()

    def move_to(self, x_um: float, y_um: float) -> tuple[float, float]:
        """Settled move to one point; the position reached."""
        d = self.device
        d.set_parameter("target_x_um", float(x_um))
        d.set_parameter("target_y_um", float(y_um))
        d.set_parameter("move_to_target", 1.0)
        return self.position()

    def position(self) -> tuple[float, float]:
        return float(self.device.get_parameter("x_um")), float(self.device.get_parameter("y_um"))

    def status(self) -> dict[str, Any]:
        return {"running": bool(self.device.measuring())}

    def close(self) -> None:
        self.device.close()


@dataclass
class BleachDetector:
    """Calls a molecule bleached when its count rate stays down at the background.

    The rate is counted in bins of ``bin_s``. The first ``baseline_s`` give the molecule's level;
    the molecule has bleached once the rate stays below
    ``background + fraction * (level - background)`` for ``hold_s``, not before ``min_s``.

    Attributes
    ----------
    background_kcps : float
        The background count rate (no molecule).
    fraction : float
        Where between background and the starting level the threshold lies.
    bin_s, baseline_s, hold_s, min_s : float
        Bin width, the window that sets the level, how long the rate must stay low, and the
        earliest call (seconds from the first photon).
    """

    background_kcps: float = 0.0
    fraction: float = 0.3
    bin_s: float = 0.05
    baseline_s: float = 0.2
    hold_s: float = 0.5
    min_s: float = 0.3
    counts: list = field(default_factory=list)
    bleached_at_s: float | None = None
    _t0: int | None = None

    @property
    def level_kcps(self) -> float | None:
        n = max(1, int(round(self.baseline_s / self.bin_s)))
        if len(self.counts) < n:
            return None
        return float(np.mean(self.counts[:n])) / self.bin_s * 1e-3

    @property
    def threshold_kcps(self) -> float | None:
        level = self.level_kcps
        if level is None:
            return None
        return self.background_kcps + self.fraction * max(0.0, level - self.background_kcps)

    def push(self, macro: np.ndarray, clock_s: float) -> bool:
        """Count photons (macro times in ticks of *clock_s*); True once bleached."""
        if len(macro):
            if self._t0 is None:
                self._t0 = int(macro[0])
            b = ((macro.astype(np.int64) - self._t0) * clock_s / self.bin_s).astype(np.int64)
            hist = np.bincount(b)
            if hist.size > len(self.counts):
                self.counts.extend([0] * (hist.size - len(self.counts)))
            for i in np.nonzero(hist)[0]:
                self.counts[i] += int(hist[i])
        return self._check()

    def _check(self) -> bool:
        if self.bleached_at_s is not None:
            return True
        thr = self.threshold_kcps
        # the last bin is still filling: judge completed bins only
        done = len(self.counts) - 1
        hold = max(1, int(round(self.hold_s / self.bin_s)))
        if thr is None or done < hold or done * self.bin_s < self.min_s:
            return False
        recent = np.asarray(self.counts[done - hold:done], float) / self.bin_s * 1e-3
        if np.all(recent < thr):
            self.bleached_at_s = (done - hold) * self.bin_s
            return True
        return False


class PointRecordSession(RecordSession):
    """One point's recording: a :class:`RecordSession` that carries its point in the header and,
    with a :class:`BleachDetector`, ends itself when the molecule has bleached."""

    def __init__(self, source, *, point: tuple[float, float], index: int,
                 bleach: BleachDetector | None = None, **kwargs):
        tags = dict(kwargs.pop("header_tags", None) or {})
        tags.update({"ChiSurf_Point_Index": int(index), "ChiSurf_Point_X_um": float(point[0]),
                     "ChiSurf_Point_Y_um": float(point[1]),
                     # SymPhoTime's point measurement: one dimension, ident 6, the stage position
                     "ImgHdr_Dimensions": 1, "ImgHdr_Ident": 6,
                     "ImgHdr_X0": float(point[0]), "ImgHdr_Y0": float(point[1])})
        super().__init__(source, header_tags=tags, **kwargs)
        self.point = (float(point[0]), float(point[1]))
        self.index = int(index)
        self.bleach = bleach

    def _push(self, batch) -> None:
        super()._push(batch)
        if self.bleach is not None and not self._stop.is_set():
            if self.bleach.push(batch.photons().macro, self.source.info.macro_clock_s):
                self.stop_reason = "bleached"
                self._stop.set()
                self.source.stop()


@dataclass
class PointResult:
    """One measured point."""

    index: int
    target: tuple[float, float]
    position: tuple[float, float]
    run: RunResult | None
    bleached_at_s: float | None = None


class PointSequence:
    """Measure ``scan.points`` one after the other: settled move, then one recording per point.

    Parameters
    ----------
    scanner : ScannerBackend with ``move_to``
        :class:`PiScanner`, or any backend that parks the focus on a point.
    source : PhotonSource
        Started and stopped once per point.
    scan : ScanSettings
        ``points`` (stage coordinates, µm) and ``point_ms`` (the longest a point runs).
    out_dir : str or Path or None
        Where the recordings go (``<name>_p000.ptu``, ...); ``None`` records nothing.
    until_bleached : bool
        End a point early once its molecule has bleached (``bleach`` sets the rule).
    bleach : callable returning BleachDetector, optional
        A fresh detector per point; default :class:`BleachDetector` with its defaults.
    session_kwargs : dict, optional
        Passed to each :class:`PointRecordSession` (``experiment``, ``settings``, ``embed``).
    on_point : callable, optional
        Called with each :class:`PointResult` as it finishes (worker thread).
    """

    def __init__(self, scanner, source, scan: ScanSettings, *, out_dir=None, name: str = "points",
                 until_bleached: bool = False,
                 bleach: Callable[[], BleachDetector] | None = None,
                 session_kwargs: dict | None = None,
                 on_point: Callable[[PointResult], None] | None = None):
        if not scan.is_points:
            raise ValueError("a point sequence needs points")
        self.scanner = scanner
        self.source = source
        self.scan = scan
        self.out_dir = Path(out_dir) if out_dir else None
        self.name = name
        self.until_bleached = bool(until_bleached)
        self.bleach = bleach or BleachDetector
        self.session_kwargs = dict(session_kwargs or {})
        self.on_point = on_point
        self.results: list[PointResult] = []
        self.current: PointRecordSession | None = None
        self.error = ""
        self._abort = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._abort.clear()
        self._thread = threading.Thread(target=self._run, name="point-sequence", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Abort: the point being measured ends now, no further point is started."""
        self._abort.set()
        session = self.current
        if session is not None:
            session.stop()

    def wait(self, timeout: float | None = None) -> list[PointResult]:
        if self._thread is not None:
            self._thread.join(timeout)
        return self.results

    def run(self) -> list[PointResult]:
        """Measure all points in this thread."""
        self._run()
        return self.results

    def status(self) -> dict[str, Any]:
        session = self.current
        return {
            "running": self.running,
            "point": len(self.results) + (1 if session is not None else 0),
            "points": len(self.scan.points),
            "elapsed_s": (time.monotonic() - session.started_at)
            if session is not None and session.started_at else 0.0,
            "error": self.error,
        }

    def _run(self) -> None:
        try:
            for i, (x, y) in enumerate(self.scan.points):
                if self._abort.is_set():
                    break
                position = self.scanner.move_to(float(x), float(y))
                ptu = self.out_dir / f"{self.name}_p{i:03d}.ptu" if self.out_dir else None
                detector = self.bleach() if self.until_bleached else None
                session = PointRecordSession(
                    self.source, point=(x, y), index=i, bleach=detector,
                    duration_s=self.scan.point_ms * 1e-3, ptu_path=ptu,
                    name=f"{self.name}_p{i:03d}", **self.session_kwargs)
                self.current = session
                session.start()
                run = session.wait()
                self.current = None
                result = PointResult(i, (float(x), float(y)), tuple(position), run,
                                     detector.bleached_at_s if detector else None)
                self.results.append(result)
                if self.on_point is not None:
                    self.on_point(result)
        except Exception as exc:  # noqa: BLE001 - shown in the tool; the points so far are kept
            _log.exception("point sequence failed")
            self.error = f"{type(exc).__name__}: {exc}"
        finally:
            self.current = None
