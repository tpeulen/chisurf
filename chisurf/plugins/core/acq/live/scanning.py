"""A scan with real hardware: the TCSPC device records while the scanner rasters.

The image is never sampled from the scanner: the scanner's trigger outputs (the PI E-725 sends a
line start on output 1 and a line stop on output 2, libphacq ``docs/pi_e725_scanner.md``) are cabled
to the TCSPC unit's marker inputs, so the line markers arrive in the photon stream and the image is
built from that stream alone (:class:`~.imaging.LiveImage`), exactly as from a recorded file.

* :class:`ScannedSource` -- a photon source that starts the device first (so no line marker is
  missed), then runs the raster frame by frame in a thread of its own (the E-725's learning blocks
  for seconds), and stops the device once the last frame is done.
* :func:`open_scanner` -- the scanner a settings file's ``scanner`` section names
  (``{"driver": "pi", "address": ""}``; ``"sim:"`` is libphacq's simulator).
* :func:`scanner_scan` -- a scan as this scanner runs it (no frame marker; line markers 1 and 2).
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import replace
from typing import Any

from .scanner import ScannerBackend, ScanSettings
from .sources import PhotonSource

_log = logging.getLogger(__name__)

__all__ = ["SCANNER_DRIVERS", "ScannedSource", "open_scanner", "scanner_scan"]

#: Scanner drivers a settings file may name.
SCANNER_DRIVERS = ("pi",)
#: The E-725's trigger outputs as SymPhoTime cables them: output 1 line start, output 2 line stop.
PI_LINE_START, PI_LINE_STOP = 1, 2
#: The scanner's own settings the form shows; the raster itself comes from the Scan panel.
SCAN_PANEL_KEYS = ("x0_um", "y0_um", "width_um", "pixels_x", "lines", "line_pitch_um", "dwell_ms",
                   "bidirectional", "target_x_um", "target_y_um", "move_to_target")


def open_scanner(section: dict) -> ScannerBackend:
    """Open the scanner a settings file's ``scanner`` section names.

    Parameters
    ----------
    section : dict
        ``driver`` (``"pi"``), ``address`` (``""`` the first E-725 on USB, a USB serial,
        ``"tcp:host[:port]"``, ``"sim:"`` the simulator) and optionally ``settings`` (the
        scanner's own settings by phacq name, e.g. ``learn_s``, ``turn_ms``).
    """
    driver = str(section.get("driver") or "pi")
    if driver not in SCANNER_DRIVERS:
        raise ValueError(f"scanner.driver: {driver!r} is not one of {SCANNER_DRIVERS}")
    from .points import PiScanner

    scanner = PiScanner(str(section.get("address") or ""))
    settings = section.get("settings") or {}
    for name, value in settings.items():
        if name not in SCAN_PANEL_KEYS:
            scanner.device.set_parameter(str(name), float(value))
    return scanner


def scanner_scan(scan: ScanSettings) -> ScanSettings:
    """*scan* as the E-725 runs it: line markers 1 and 2, no frame marker (frames are counted in
    lines), one plane."""
    return replace(scan, line_start_marker=PI_LINE_START, line_stop_marker=PI_LINE_STOP,
                   frame_marker=0, z_planes=1, points=[])


class ScannedSource(PhotonSource):
    """The TCSPC device recording while the scanner rasters, frame after frame.

    Parameters
    ----------
    tcspc : PhotonSource
        The device's source (``live.devices.DeviceSource``); started without a time limit and
        stopped when the raster is done.
    scanner : ScannerBackend
        Configured with *scan* and started once per frame.
    scan : ScanSettings
        The raster (see :func:`scanner_scan`).
    tail_s : float
        Recording after the last frame (the last line's photons and stop marker).
    """

    stops_itself = True

    def __init__(self, tcspc: PhotonSource, scanner: ScannerBackend, scan: ScanSettings, *,
                 tail_s: float = 0.2):
        self.tcspc = tcspc
        self.scanner = scanner
        self.scan = scan
        self.tail_s = float(tail_s)
        self.info = tcspc.info
        self.duration_s = None
        self.frame = 0
        self.notes: list[str] = []
        self.error = ""
        self._abort = threading.Event()
        self._thread: threading.Thread | None = None

    def __getattr__(self, name: str):
        # the device's recorder writes its raw records: offered only when the device has one
        if name == "make_recorder":
            return getattr(self.tcspc, "make_recorder")
        raise AttributeError(name)

    def start(self) -> None:
        self._abort.clear()
        self.error = ""
        self.notes = list(self.scanner.configure(self.scan) or [])
        self.tcspc.start()
        self._thread = threading.Thread(target=self._raster, name="scanner-raster", daemon=True)
        self._thread.start()

    def _raster(self) -> None:
        try:
            for frame in range(max(1, int(self.scan.frames))):
                if self._abort.is_set():
                    return
                self.frame = frame
                self.scanner.start()  # learning, line triggers, the image (blocks while learning)
                while not self._abort.is_set() and self.scanner.status().get("running"):
                    time.sleep(0.02)
            end = time.monotonic() + self.tail_s
            while not self._abort.is_set() and time.monotonic() < end:
                time.sleep(0.01)
        except Exception as exc:  # noqa: BLE001 - the run ends; shown in the tool
            _log.exception("scanner failed")
            self.error = f"scanner: {exc}"
        finally:
            try:
                self.scanner.stop()
            except Exception:  # noqa: BLE001 - parked or not, the device stops below
                _log.exception("scanner stop failed")
            self.tcspc.stop()

    def stop(self) -> None:
        self._abort.set()
        try:
            self.scanner.stop()
        except Exception:  # noqa: BLE001
            pass
        self.tcspc.stop()

    def read(self, timeout: float = 0.2):
        return self.tcspc.read(timeout)

    @property
    def finished(self) -> bool:
        return self.tcspc.finished

    def status(self) -> dict[str, Any]:
        st = dict(self.tcspc.status())
        if self.error:
            st["error"] = self.error
        return st
