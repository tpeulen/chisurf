"""Live imaging: the image builds up line by line from a scan's marker stream.

:class:`LiveImage` reads the photon stream the way tttrlib's CLSM reader reads a scan file: a line
opens at its *line start* marker and closes at its *line stop* marker; a photon in between lands in
pixel ``(t - start) * nx // (stop - start)``; a *frame* marker starts a new frame, and without frame
markers a frame is ``ny`` lines. A line's photons wait in a small buffer until its stop marker
arrives, so the image is exact while it is built -- equal, pixel by pixel, to ``CLSMImage`` of the
recorded file.

:func:`imaging_qc` is the imaging counterpart of the smFRET quality checker (traffic lights):
pile-up, the markers' consistency (lines per frame, unclosed lines, frames), and the signal.
:class:`ImageRecordSession` is a :class:`~.session.RecordSession` whose live analysis is a
:class:`LiveImage`; :func:`image_replay_source` replays an image file of the workspace through it.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np

from chisurf.core.fluorescence.excitation import micro_mask

from .scanner import ScanSettings, marker_bit, scan_from_tags
from .session import RecordSession, quality_record
from .sources import FileReplaySource, PhotonBatch, SourceUnavailable

_log = logging.getLogger(__name__)

__all__ = [
    "ImageRecordSession",
    "LiveImage",
    "image_replay_source",
    "imaging_qc",
    "scan_of_file",
]

#: Width of the count-rate trace's bins (s) in imaging.
TRACE_BIN_S = 0.1


class LiveImage:
    """The image of a running scan, from photons and markers.

    Parameters
    ----------
    scan : ScanSettings
        Pixels per line, lines per frame, bidirectional, and the marker numbers.
    macro_clock_s, micro_res_s : float
        The stream's clocks.
    n_micro : int
        Micro-time channels per laser period.
    channels : sequence of int
        The detectors (routing channels) of the photons.
    windows : dict, optional
        Micro-time windows ``{name: [lo, hi)}`` (PIE): an image per window.
    """

    def __init__(
        self,
        scan: ScanSettings,
        *,
        macro_clock_s: float,
        micro_res_s: float,
        n_micro: int,
        channels=(0, 1),
        windows: dict | None = None,
    ):
        self.scan = scan
        self.clock = float(macro_clock_s)
        self.micro_res = float(micro_res_s)
        self.n_micro = max(1, int(n_micro))
        self.channels = tuple(int(c) for c in channels)
        self.windows = {str(k): (int(v[0]), int(v[1])) for k, v in (windows or {}).items()}
        self.nx, self.ny = int(scan.nx), int(scan.ny)
        self._start_bit = marker_bit(scan.line_start_marker)
        self._stop_bit = marker_bit(scan.line_stop_marker)
        self._frame_bit = marker_bit(scan.frame_marker) if scan.frame_marker else 0
        self.clear()

    def clear(self) -> None:
        shape = (self.ny, self.nx)
        self.counts = {c: np.zeros(shape, np.int64) for c in self.channels}
        self.micro_sum = np.zeros(shape, np.float64)
        self.window_counts = {w: np.zeros(shape, np.int64) for w in self.windows}
        self.decays = {c: np.zeros(self.n_micro, np.int64) for c in self.channels}
        self.frame = 0
        self.line = 0  # line index within the frame
        self.lines_done = 0  # closed lines, all frames
        self.lines_in_frame: list[int] = []  # closed lines per finished frame
        self.unclosed_lines = 0  # a line start before the previous line's stop
        self.stray_stops = 0  # a line stop without an open line
        self.photons = 0
        self.photons_in_lines = 0
        self.max_pixel_rate_hz = 0.0
        self._open: int | None = None  # macro time of the open line's start
        self._buf: list[tuple[np.ndarray, np.ndarray, np.ndarray]] = []
        self._first: int | None = None
        self._last: int | None = None
        self._trace: dict[int, np.ndarray] = {c: np.zeros(0, np.int64) for c in self.channels}
        self.revision = 0

    # -- the stream ------------------------------------------------------------------------------
    def push(self, batch: PhotonBatch) -> None:
        """Feed a batch of photons and markers in time order."""
        n = len(batch)
        if n == 0:
            return
        macro = np.asarray(batch.macro, dtype=np.int64)
        micro = np.asarray(batch.micro, dtype=np.int64)
        channel = np.asarray(batch.channel, dtype=np.int64)
        event = (
            np.asarray(batch.event, dtype=np.int64)
            if batch.event is not None
            else np.zeros(n, np.int64)
        )
        if self._first is None:
            self._first = int(macro[0])
        self._last = int(macro[-1])
        photon = event == 0
        self._account(macro[photon], micro[photon], channel[photon])
        marker_at = np.flatnonzero(~photon)
        start = 0
        for i in marker_at:
            self._take(macro[start:i], micro[start:i], channel[start:i], photon[start:i])
            self._marker(int(channel[i]), int(macro[i]))
            start = i + 1
        self._take(macro[start:], micro[start:], channel[start:], photon[start:])
        self.revision += 1

    def flush(self) -> None:
        """The run ended: a line still open has no stop and is not drawn."""
        if self._open is not None:
            self.unclosed_lines += 1
        self._open, self._buf = None, []

    def _account(self, macro, micro, channel) -> None:
        """Photon totals, decays and the count-rate trace (all photons, in lines or not)."""
        self.photons += len(macro)
        for c in self.channels:
            sel = channel == c
            if not np.any(sel):
                continue
            m = micro[sel]
            m = m[(m >= 0) & (m < self.n_micro)]
            self.decays[c] += np.bincount(m, minlength=self.n_micro)[: self.n_micro]
            b = ((macro[sel] - self._first) * self.clock / TRACE_BIN_S).astype(np.int64)
            counts = np.bincount(b)
            tr = self._trace[c]
            if counts.size > tr.size:
                tr = np.concatenate([tr, np.zeros(counts.size - tr.size, np.int64)])
            tr[: counts.size] += counts
            self._trace[c] = tr

    def _take(self, macro, micro, channel, photon) -> None:
        if self._open is None or len(macro) == 0:
            return
        sel = photon
        if np.any(sel):
            self._buf.append((macro[sel], micro[sel], channel[sel]))

    def _marker(self, bits: int, t: int) -> None:
        if self._frame_bit and bits & self._frame_bit:
            if self.line > 0:
                self._end_frame()
        if bits & self._stop_bit:
            if self._open is None:
                self.stray_stops += 1
            else:
                self._close_line(self._open, t)
            self._open, self._buf = None, []
        if bits & self._start_bit:
            if self._open is not None:
                self.unclosed_lines += 1
            if not self._frame_bit and self.line >= self.ny:
                self._end_frame()
            self._open, self._buf = t, []

    def _end_frame(self) -> None:
        self.lines_in_frame.append(self.line)
        self.frame += 1
        self.line = 0

    def _close_line(self, start: int, stop: int) -> None:
        y = self.line
        self.line += 1
        self.lines_done += 1
        if y >= self.ny or stop <= start:
            return
        if not self._buf:
            return
        macro = np.concatenate([b[0] for b in self._buf])
        micro = np.concatenate([b[1] for b in self._buf])
        channel = np.concatenate([b[2] for b in self._buf])
        # tttrlib's CLSM arithmetic: a whole number of ticks per pixel, the pixel by multiplying
        # with its reciprocal; photons past the last whole pixel are not drawn
        pixel_ticks = (stop - start) // self.nx
        if pixel_ticks <= 0:
            return
        x = ((macro - start).astype(np.float64) * (1.0 / float(pixel_ticks))).astype(np.int64)
        ok = (x >= 0) & (x < self.nx)
        x, micro, channel = x[ok], micro[ok], channel[ok]
        if self.scan.bidirectional and y % 2 == 1:
            x = self.nx - 1 - x
        self.photons_in_lines += len(x)
        line_total = np.zeros(self.nx, np.int64)
        for c in self.channels:
            sel = channel == c
            if np.any(sel):
                row = np.bincount(x[sel], minlength=self.nx)[: self.nx]
                self.counts[c][y] += row
                line_total += row
        self.micro_sum[y] += np.bincount(x, weights=micro.astype(np.float64), minlength=self.nx)[
            : self.nx
        ]
        for name, (lo, hi) in self.windows.items():
            sel = micro_mask(micro, [(lo, hi)])
            if np.any(sel):
                self.window_counts[name][y] += np.bincount(x[sel], minlength=self.nx)[: self.nx]
        pixel_s = (stop - start) * self.clock / self.nx
        if pixel_s > 0 and line_total.size:
            self.max_pixel_rate_hz = max(self.max_pixel_rate_hz, float(line_total.max()) / pixel_s)

    # -- what the view takes ---------------------------------------------------------------------
    def intensity(self) -> np.ndarray:
        """All detectors, all frames (lines x pixels)."""
        total = np.zeros((self.ny, self.nx), np.int64)
        for c in self.channels:
            total += self.counts[c]
        return total

    def mean_arrival_ns(self) -> np.ndarray:
        """Mean micro time per pixel (ns); NaN where no photon arrived (fast FLIM)."""
        n = self.intensity().astype(np.float64)
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(n > 0, self.micro_sum / n * self.micro_res * 1e9, np.nan)

    def images(self) -> dict[str, np.ndarray]:
        """Every map the view offers, by name."""
        out = {"Intensity": self.intensity().astype(np.float64)}
        out["Mean arrival time (ns)"] = self.mean_arrival_ns()
        for c in self.channels:
            out[f"Detector {c}"] = self.counts[c].astype(np.float64)
        for name, arr in self.window_counts.items():
            out[f"Window {name}"] = arr.astype(np.float64)
        return out

    def snapshot(self) -> dict[str, Any]:
        elapsed = (
            (self._last - self._first) * self.clock
            if self._first is not None and self._last is not None
            else 0.0
        )
        trace_counts = {f"ch{c}": self._trace[c].copy() for c in self.channels}
        return {
            "revision": self.revision,
            "photons": int(self.photons),
            "photons_in_lines": int(self.photons_in_lines),
            "bursts": 0,
            "burst_rate_hz": 0.0,
            "elapsed_s": float(elapsed),
            "background_cps": {},
            "histograms": {},
            "images": self.images(),
            "frame": int(self.frame),
            "line": int(self.line),
            "lines_done": int(self.lines_done),
            "lines_in_frame": list(self.lines_in_frame),
            "unclosed_lines": int(self.unclosed_lines),
            "stray_stops": int(self.stray_stops),
            "max_pixel_rate_hz": float(self.max_pixel_rate_hz),
            "nx": self.nx,
            "ny": self.ny,
            "trace": {"bin_width_s": TRACE_BIN_S, "first_bin": 0, "counts": trace_counts},
            "decays": {f"ch{c}": self.decays[c].copy() for c in self.channels},
        }

    def table(self) -> dict:
        return {}


def _light(value: float, green: float, amber: float, higher_is_worse: bool = True) -> str:
    if higher_is_worse:
        return "green" if value < green else ("amber" if value < amber else "red")
    return "green" if value > green else ("amber" if value > amber else "red")


def imaging_qc(snap: dict, scan: ScanSettings, *, sync_rate_hz: float) -> dict:
    """The imaging verdict: traffic lights per check, the worst one overall.

    Checks: pile-up (the brightest pixel's count rate against the laser rate -- TCSPC counts at most
    one photon per period, so above a few percent the decays are distorted), lines per frame (every
    finished frame has exactly the scan's lines: the markers are consistent), unclosed lines and
    stray stops (a marker lost), and the signal (photons per pixel).
    """
    lines_done = int(snap.get("lines_done", 0))
    if lines_done == 0:
        return {
            "ready": False,
            "level": "grey",
            "checks": [],
            "metrics": {},
            "why": "No line finished yet.",
        }
    checks = []
    pile = float(snap.get("max_pixel_rate_hz", 0.0)) / max(float(sync_rate_hz), 1.0)
    checks.append(
        {
            "name": "Pile-up",
            "light": _light(pile, 0.01, 0.05),
            "value": f"{pile * 100:.2f} % of the laser rate",
            "detail": "The brightest pixel's count rate against the laser repetition rate. TCSPC "
            "registers at most one photon per laser period; above about 5 % the decays are "
            "distorted toward early times.",
            "action": "Lower the excitation power or attenuate the detection."
            if pile >= 0.01
            else "",
        }
    )
    frames = [int(n) for n in snap.get("lines_in_frame", [])]
    wrong = [n for n in frames if n != scan.ny]
    checks.append(
        {
            "name": "Lines per frame",
            "light": "red" if wrong else ("green" if frames else "grey"),
            "value": (
                f"{len(frames) - len(wrong)}/{len(frames)} frames with {scan.ny} lines"
                if frames
                else "first frame running"
            ),
            "detail": "Every finished frame must hold exactly the scan's lines; other numbers mean "
            "line or frame markers are missing or extra.",
            "action": "Check the scanner's marker outputs and the marker numbers of the scan."
            if wrong
            else "",
        }
    )
    lost = int(snap.get("unclosed_lines", 0)) + int(snap.get("stray_stops", 0))
    checks.append(
        {
            "name": "Line markers",
            "light": "green" if lost == 0 else ("amber" if lost <= 2 else "red"),
            "value": f"{lost} unpaired",
            "detail": "A line start must be followed by its line stop. Unpaired markers lose the "
            "line's photons.",
            "action": "Check the marker cabling and that line start and stop are not swapped."
            if lost
            else "",
        }
    )
    image = np.asarray((snap.get("images") or {}).get("Intensity", np.zeros((1, 1))), float)
    ny = max(1, int(snap.get("ny", 1)))
    frames_seen = lines_done / ny
    bright = np.sort(image.ravel())[-max(1, image.size // 20) :]
    per_pixel = float(bright.mean()) / max(frames_seen, 1.0) if bright.size else 0.0
    first_frame = frames_seen < 1.0
    checks.append(
        {
            "name": "Signal",
            "light": "grey" if first_frame else _light(per_pixel, 10.0, 1.0, higher_is_worse=False),
            "value": "first frame running"
            if first_frame
            else f"{per_pixel:.1f} photons per bright pixel",
            "detail": "Photons per frame in the brightest 5 % of the pixels (the structures, not the "
            "empty background). Fast FLIM needs tens of photons per pixel; lifetime fits "
            "need hundreds (accumulate frames).",
            "action": "Increase the dwell time, the frames or the excitation."
            if (per_pixel < 10 and not first_frame)
            else "",
        }
    )
    order = {"grey": 0, "green": 1, "amber": 2, "red": 3}
    level = max((c["light"] for c in checks), key=lambda x: order[x])
    return {
        "ready": True,
        "level": level,
        "checks": checks,
        "metrics": {"pile_up": pile, "photons_per_pixel": per_pixel},
        "why": "",
    }


class ImageRecordSession(RecordSession):
    """A recording of a scan: the live analysis is a :class:`LiveImage`, the verdict
    :func:`imaging_qc`, and the recording becomes an *Imaging* photons dataset.

    Parameters
    ----------
    source : PhotonSource
        Photons and markers.
    scan : ScanSettings
    windows : dict, optional
        Micro-time windows for per-window images (PIE).
    **kwargs
        As :class:`~.session.RecordSession` (``duration_s``, ``ptu_path``, ``name``, ``embed``,
        ``settings``).
    """

    dataset_kind = "image"

    def __init__(self, source, scan: ScanSettings, *, windows: dict | None = None, **kwargs):
        self.scan = scan
        self._windows = dict(windows or {})
        tags = dict(kwargs.pop("header_tags", None) or {})
        tags.update(scan.imghdr_tags())
        super().__init__(source, None, header_tags=tags, **kwargs)
        from .setups import Experiment

        # what the plots read from the experiment: the image's windows only
        self.experiment = Experiment(
            {"detectors": {}, "windows": self._windows}, "single_color", name="image"
        )

    def _make_analyzer(self):
        info = self.source.info
        return LiveImage(
            self.scan,
            macro_clock_s=info.macro_clock_s,
            micro_res_s=info.micro_res_s,
            n_micro=info.n_micro,
            windows=self._windows,
        )

    def _make_trace(self, window_s: float, bin_s: float):
        return None  # an image's count rates are the analyzer's trace

    def _push(self, batch) -> None:
        self.analyzer.push(batch)
        self._count_seconds(batch.photons().macro, self.source.info.macro_clock_s)

    def table(self) -> dict:
        return {}

    def _update_qc(self, table: dict | None = None) -> None:
        with self._lock:
            snap = self.analyzer.snapshot()
        try:
            qc = imaging_qc(snap, self.scan, sync_rate_hz=1.0 / self.source.info.macro_clock_s)
        except Exception as exc:  # noqa: BLE001 - no verdict is shown as such, the run goes on
            _log.exception("imaging quality check failed")
            qc = {"ready": False, "level": "grey", "checks": [], "metrics": {}, "why": str(exc)}
        with self._lock:
            self.qc = qc

    def register(self):
        """The recording into the workspace as an *Imaging* photons dataset, its verdict and scan
        kept with it."""
        if self._dataset is not None:
            meta = getattr(self._dataset, "meta_data", None)
            if isinstance(meta, dict):
                meta["acquisition_scan"] = self.scan.to_dict()
                if self.result is not None and self.result.qc:
                    meta["acquisition_quality"] = quality_record(self.result.qc)
        return super().register()


def scan_of_file(address: str, header_json: str = "") -> tuple[ScanSettings | None, list[str]]:
    """The scan an image file describes (its ``ImgHdr_*`` tags), and what was missing.

    A ``.ptu`` on disk is read from its own header (exact tag types); a container member or other
    format from tttrlib's header JSON (*header_json*, or opened here).
    """
    from . import settings_file

    path = Path(str(address))
    if path.suffix.lower() == ".ptu" and path.exists():
        return scan_from_tags(settings_file.read_ptu_tags(path))
    text = header_json
    if not text:
        try:
            from chisurf.core.fio.staging import open_tttr

            text = open_tttr(str(address)).header.json
        except Exception:  # noqa: BLE001 - not readable: no scan
            return None, ["scan (the file's header could not be read)"]
    try:
        tags = json.loads(text).get("tags", [])
    except ValueError:
        return None, ["scan (the file's header is not JSON)"]
    return scan_from_tags(
        {t.get("name"): t.get("value") for t in tags if int(t.get("idx", -1)) < 0}
    )


def image_replay_source(
    address: str, *, speed: float = 1.0, realtime: bool = True, header_json: str = ""
) -> tuple[FileReplaySource, ScanSettings]:
    """Replay an image file of the workspace: its photons and markers at measurement speed (or
    faster), with the scan read from the file. Refuses a file that is not a scan."""
    scan, _missing = scan_of_file(address, header_json)
    if scan is None:
        raise SourceUnavailable(f"{Path(str(address)).name} is not an image: no ImgHdr tags")
    source = FileReplaySource(address, speed=speed, realtime=realtime)
    if not source.has_markers:
        raise SourceUnavailable(
            f"{Path(str(address)).name} has no scan markers: it cannot be replayed as an image"
        )
    return source, scan
