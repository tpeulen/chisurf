"""One recording: a source read in a worker thread, analysed live, written to a PTU as it arrives.

:class:`RecordSession` is what the Record tool starts and stops. The worker thread reads batches
from the source, pushes them into the live burst analyzer (tttrlib's ``StreamingBurstAnalyzer``;
the measurement type is the :class:`~.setups.Experiment`'s preset) and into the
recording; the view takes
:meth:`RecordSession.snapshot` at its own pace (about 5 Hz) and never touches photons. When the run
ends -- its duration reached, the source exhausted, or :meth:`stop` -- the open burst is closed,
the PTU is finished, and :meth:`RecordSession.register` puts the result into the project: the PTU
as a photons dataset (linked or embedded by the project's *Add as* setting) and the bursts as a
run in that dataset's analysis container, a child row of it in the workspace.
"""

from __future__ import annotations

import datetime
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import tttrlib

from . import settings_file
from .settings_file import CHISURF_SETTINGS_TAG
from .setups import Experiment, default_setup
from .sources import PhotonSource

_log = logging.getLogger(__name__)

__all__ = ["RecordSession", "RunResult", "RUN_NAME", "quality_record"]

#: Name of a live run inside the analysis container (``<stem>.pto/live_bursts``).
RUN_NAME = "live_bursts"
#: How often the quality checker re-evaluates the run while it is measured.
QC_INTERVAL_S = 2.0

_PQ_PTU = 0  # tttrlib container type of PicoQuant PTU
_TY_F8 = 0x20000008
_TY_I8 = 0x10000008
_TY_ANSI = 0x4001FFFF
_REC_MULTIHARP_T3 = 0x00010304  # PicoQuant T3 record layout shared by HydraHarp v2 / MultiHarp


@dataclass
class RunResult:
    """What a finished recording left: the PTU, its bursts, and the workspace rows if registered."""

    ptu: Path | None
    table: dict[str, np.ndarray]
    photons: int
    bursts: int
    elapsed_s: float
    stop_reason: str
    dataset_uid: str = ""
    run_address: str = ""
    qc: dict | None = None
    analysis_complete: bool = True


_TY_BOOL = 0x00000008


#: Photons a µs-ALEX run keeps for its live window check.
ALEX_SAMPLE_PHOTONS = 2_000_000


def _tag_type(value) -> int:
    """The PicoQuant tag type of a typed header value."""
    if isinstance(value, bool):
        return _TY_BOOL
    if isinstance(value, (int, np.integer)):
        return _TY_I8
    if isinstance(value, float):
        return _TY_F8
    return _TY_ANSI


def _header(source_info, name: str, settings: dict | None = None, tags: dict | None = None):
    """A PTU header for the source's clocks (T3, MultiHarp record layout), with the run's
    acquisition settings document in the ``ChiSurf_AcquisitionSettings`` tag when given, and the
    extra typed *tags* (a scan's ``ImgHdr_*``)."""
    probe = tttrlib.TTTR()
    probe.append_events(
        np.zeros(1, np.uint64), np.zeros(1, np.uint16), np.zeros(1, np.int8), np.zeros(1, np.int8)
    )
    h = probe.header
    h.set_tag("MeasDesc_GlobalResolution", float(source_info.macro_clock_s), _TY_F8)
    h.set_tag("MeasDesc_Resolution", float(source_info.micro_res_s), _TY_F8)
    # The micro-time channels of one laser period and the laser (sync) rate: without them readers
    # take one channel per period (period == dt) and every lifetime fit of the recording fails.
    n_micro = int(getattr(source_info, "n_micro", 0) or 0)
    if n_micro > 0:
        h.set_tag("MeasDesc_NumberMicrotimes", n_micro, _TY_I8)
        h.set_tag("TTResult_SyncRate", int(round(1.0 / (n_micro * float(source_info.micro_res_s)))), _TY_I8)
    h.set_tag("TTResultFormat_TTTRRecType", _REC_MULTIHARP_T3, _TY_I8)
    h.set_tag("MeasDesc_RecordingMode", 3, _TY_I8)
    h.set_tag("File_Comment", f"ChiSurf live recording: {name}", _TY_ANSI)
    if settings:
        h.set_tag(CHISURF_SETTINGS_TAG, settings_file.dumps(settings), _TY_ANSI)
    for key, value in (tags or {}).items():
        h.set_tag(key, value if not isinstance(value, np.integer) else int(value), _tag_type(value))
    return h


def quality_record(qc: dict) -> dict:
    """The verdict as stored with a run: overall light and every check (JSON-safe)."""
    return {
        "checker": "fret_check",
        "level": qc.get("level", "grey"),
        "checks": [
            {k: str(c.get(k, "")) for k in ("name", "light", "value", "detail", "action")}
            for c in qc.get("checks", [])
        ],
    }


class RecordSession:
    """A source, a live burst analysis and a recording, run in one worker thread.

    Parameters
    ----------
    source : PhotonSource
    experiment : Experiment or None
        Setup, preset and burst rule; ``None`` is PIE with the default setup for the source's
        period.
    duration_s : float or None
        Stop after this much measurement time; ``None`` until :meth:`stop`.
    ptu_path : str or Path or None
        Where the photons are written while measuring; ``None`` records nothing (view only).
    name : str
        The dataset name in the workspace.
    settings : dict or None
        The run's acquisition settings document (``live.settings_file``), written into the
        recording's header as the ``ChiSurf_AcquisitionSettings`` tag so the measurement can be
        repeated from the file alone.
    """

    def __init__(
        self,
        source: PhotonSource,
        experiment: Experiment | None = None,
        *,
        duration_s: float | None = None,
        ptu_path: str | Path | None = None,
        name: str = "",
        embed: bool = True,
        settings: dict | None = None,
        header_tags: dict | None = None,
        trace_window_s: float = 1.0,
        trace_bin_s: float = 1e-3,
    ):
        self.source = source
        info = source.info
        #: typed tags the recording's header carries besides the settings (a scan's ImgHdr_*)
        self.header_tags = dict(header_tags or {})
        self.header_tags["ChiSurf_InterruptMarkers"] = (
            'v2: special marker 13=analysis pause,14=end pause; analysis remains incomplete; raw photons recorded; TCSPC clock and '
            'illumination unchanged; external markers must be disabled; timestamps are '
            'last observed source ticks at the acknowledged batch boundary; timer includes pauses')
        self.experiment = experiment or Experiment(
            default_setup("pie", info.n_micro), "pie", name="default PIE"
        )
        self.duration_s = duration_s
        self.ptu_path = Path(ptu_path) if ptu_path else None
        self.name = name or datetime.datetime.now().strftime("record_%Y%m%d_%H%M%S")
        #: store the recording inside the project (a fresh recording's default) or link it
        self.embed = bool(embed)
        self.settings = settings
        self._dataset = None  # the photons dataset, built (hashed) by the worker at stop
        self.analyzer = self._make_analyzer()
        #: the running mirrored trace (last ``trace_window_s`` s in ``trace_bin_s`` bins)
        self.trace = self._make_trace(trace_window_s, trace_bin_s)
        #: total photons per whole second of the run (the checker's stability trace)
        self._per_second = np.zeros(0, dtype=np.int64)
        self._first_macro: int | None = None
        #: µs-ALEX: the first photons' macro times and channels, for the live window check (the
        #: alternation is in the macro time, which the analyzer's decays do not carry)
        self._alex_parts: list[tuple[np.ndarray, np.ndarray]] = []
        self._alex_count = 0
        self._lock = threading.Lock()
        self._trace_config_lock = threading.Lock()
        self._pending_trace = None
        self._analysis = None
        self._last_snapshot = self.analyzer.snapshot()
        self._stop = threading.Event()
        self._source_stop_lock = threading.Lock()
        self._source_stopped = False
        self._pause_requested = threading.Event()
        self.paused = False
        self.paused_photons = 0
        # One immutable snapshot: (count, first tick, last tick).
        self._received = (0, None, None)
        self._analysis_gap = False
        self.pause_error = ""
        self._last_seen_macro = 0
        self._reserved_marker_seen = False
        self._interrupt_used = False
        self._thread: threading.Thread | None = None
        self._writer = None
        self._recorder = None
        #: a device whose acquisition timer ends the run: the session does not cut its batches
        #: (a simulated source that accepts a duration ends its generation there, like a timer)
        self._self_timed = duration_s is not None and (
            bool(getattr(source, "stops_itself", False)) or hasattr(source, "duration_s")
        )
        if self._self_timed and hasattr(source, "duration_s"):
            source.duration_s = duration_s
        self.batches = 0
        self.dropped = 0
        self.stop_reason = ""
        self.error = ""
        self.result: RunResult | None = None
        self.started_at: float | None = None
        #: the quality checker's latest verdict (``live.qc.live_qc``), refreshed every QC_INTERVAL_S
        self.qc: dict | None = None
        self._qc_at = 0.0

    #: what the recording becomes in the workspace (the linked reader of this kind reads it)
    dataset_kind = "photons"

    def _make_analyzer(self):
        """The live analysis: the experiment's burst analyzer."""
        info = self.source.info
        return self.experiment.analyzer(info.macro_clock_s, info.micro_res_s, info.n_micro)

    def _make_trace(self, window_s: float, bin_s: float):
        """The running smFRET trace of the experiment's preset (donor up, acceptor down)."""
        from .trace import LiveTrace, trace_streams

        exp = self.experiment
        streams = trace_streams(exp.setup, exp.preset, donor=exp.donor, acceptor=exp.acceptor,
                                prompt=exp.prompt, delay=exp.delay)
        return LiveTrace(streams, macro_clock_s=self.source.info.macro_clock_s,
                         window_s=window_s, bin_s=bin_s,
                         alex_period_s=exp.alex_period_s if exp.preset == "alex" else None)

    def set_trace(self, window_s: float, bin_s: float) -> None:
        """Change the running trace's span and bin width (it starts over)."""
        if self.trace is not None:
            # Never wait on a stalled analyzer from the UI. The worker applies the
            # most recent request immediately before its next batch.
            with self._trace_config_lock:
                self._pending_trace = (window_s, bin_s)

    def _push(self, batch) -> None:
        """Feed one batch to the live analysis (called under the lock): photons only."""
        photons = batch.photons()
        self.analyzer.push_np(photons.macro, photons.micro, photons.channel.astype(np.int32))
        if self.trace is not None:
            self.trace.push(photons.macro, photons.micro, photons.channel)
        self._count_seconds(photons.macro, self.source.info.macro_clock_s)
        if self.experiment.preset == "alex" and self._alex_count < ALEX_SAMPLE_PHOTONS:
            self._alex_parts.append((np.array(photons.macro, copy=True),
                                     np.array(photons.channel, copy=True)))
            self._alex_count += len(photons.macro)

    def _capture_batch(self, batch) -> None:
        """Capture-path safety hook, independent of optional analysis."""

    def _flush_analysis(self) -> None:
        with self._lock:
            self.analyzer.flush()

    def _analyze_batch(self, batch) -> None:
        with self._trace_config_lock:
            pending, self._pending_trace = self._pending_trace, None
        with self._lock:
            if pending is not None and self.trace is not None:
                self.trace.configure(*pending)
            self._push(batch)
            self.batches += 1
        if time.monotonic() - self._qc_at >= QC_INTERVAL_S:
            self._qc_at = time.monotonic()
            self._update_qc()

    def alex_photons(self) -> tuple[np.ndarray, np.ndarray]:
        """µs-ALEX runs: ``(macro times, routing channels)`` of the first photons (up to
        :data:`ALEX_SAMPLE_PHOTONS`) -- what the live window check folds; empty otherwise."""
        with self._lock:
            parts = list(self._alex_parts)
        if not parts:
            return np.zeros(0, np.uint64), np.zeros(0, np.int8)
        return (np.concatenate([p[0] for p in parts]), np.concatenate([p[1] for p in parts]))

    # -- control --------------------------------------------------------------------------------
    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        """Open the PTU, start the source and the worker thread."""
        if self.running:
            return
        if self.ptu_path is not None and hasattr(self.source, "make_recorder"):
            # a device records its own raw records, header and all
            self.ptu_path.parent.mkdir(parents=True, exist_ok=True)
            extra = dict(self.header_tags)
            if self.settings:
                extra[CHISURF_SETTINGS_TAG] = settings_file.dumps(self.settings)
            self._recorder = self.source.make_recorder(
                self.ptu_path, self.name, extra=extra or None
            )
        elif self.ptu_path is not None:
            self.ptu_path.parent.mkdir(parents=True, exist_ok=True)
            writer = tttrlib.RecordStreamWriter(_PQ_PTU)
            if not writer.create(
                str(self.ptu_path),
                _header(self.source.info, self.name, self.settings, self.header_tags),
                self.name,
            ):
                raise OSError(f"cannot write {self.ptu_path}: {writer.error()}")
            writer.set_auto_checkpoint(200_000)
            self._writer = writer
        self.source.start()
        from .bounded_analysis import BoundedAnalysis
        self._analysis = BoundedAnalysis(self._analyze_batch, self._flush_analysis,
                                         capacity=16, max_batch_events=500_000)
        self.started_at = time.monotonic()
        self._thread = threading.Thread(target=self._run, name="record-session", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop measuring; the worker closes the open burst and the file."""
        if not self.stop_reason:
            self.stop_reason = "stopped"
        self._stop.set()

    def _stop_source(self):
        """Stop the underlying source once, including natural and requested stops."""
        with self._source_stop_lock:
            if self._source_stopped:
                return
            self._source_stopped = True
            self.source.stop()

    def pause(self) -> bool:
        """Pause live analysis at a batch boundary; raw recording and the TCSPC clock continue.

        The source keeps draining. Illumination and the hardware timer are unchanged.
        External markers must be disabled so software markers cannot be misidentified.
        """
        self.pause_error = ""
        if not self.running or self._stop.is_set():
            self.pause_error = "No active recording."
            return False
        device = getattr(self.source, "device", None)
        if device is not None:
            try:
                if int(device.get_parameter("marker_enable", -1)) != 0:
                    raise ValueError("Disable external markers before pausing live analysis.")
            except Exception as exc:
                self.pause_error = f"Cannot reserve interruption markers: {exc}"
                return False
        if self._reserved_marker_seen:
            self.pause_error = "The input uses reserved marker 13 or 14; analysis pause is unavailable."
            return False
        self._pause_requested.set()
        return True

    def resume(self) -> bool:
        """End the marked pause; analysis stays incomplete while raw recording continues."""
        if not self.running or self._stop.is_set():
            return False
        self._pause_requested.clear()
        return True

    def _write_batch(self, batch) -> None:
        """Submit every saved event and surface a writer refusal as data loss."""
        if self._recorder is not None:
            if not self._recorder.write(batch):
                raise OSError("The device PTU writer refused an event batch.")
        if self._writer is not None and len(batch):
            events = batch.event if batch.event is not None else np.zeros(len(batch), np.int8)
            if not self._writer.submit_events(batch.macro, batch.micro, batch.channel, events):
                self.dropped += 1
                raise OSError("The PTU writer refused an event batch.")
        # Count accepted source photons independently of optional live analysis.
        photons = batch.photons()
        if len(photons):
            count, first, _last = self._received
            first = int(photons.macro[0]) if first is None else first
            self._received = (count + len(photons), first, int(photons.macro[-1]))

    def _interrupt_marker(self, channel: int) -> None:
        """Write a real PTU special event; never feed software markers to burst analysis."""
        from .sources import PhotonBatch

        raw = None
        if self._recorder is not None:
            import phacq

            raw = np.zeros(1, dtype=phacq.EVENT_DTYPE)
            raw["macro_time"] = self._last_seen_macro
            raw["channel"] = channel
            raw["flags"] = phacq.kEventFlagMarker
        self._write_batch(PhotonBatch(
            np.array([self._last_seen_macro], np.uint64), np.zeros(1, np.uint16),
            np.array([channel], np.int8), raw=raw, event=np.ones(1, np.int8)))

    def wait(self, timeout: float | None = None) -> RunResult | None:
        if self._thread is not None:
            self._thread.join(timeout)
        return self.result

    # -- the worker ----------------------------------------------------------------------------
    def _run(self) -> None:
        clock = self.source.info.macro_clock_s
        t0 = None
        drain_deadline = None
        collision_error = None
        capture_error = None

        def capture_safety(batch):
            nonlocal capture_error
            if capture_error is not None:
                return
            try:
                self._capture_batch(batch)
            except Exception as exc:
                capture_error = f"Capture safety failed: {type(exc).__name__}: {exc}"
                self._analysis_gap = True
                if self._analysis is not None:
                    self._analysis.disable(capture_error)
                self._stop.set()

        try:
            while True:
                if self._stop.is_set():
                    if drain_deadline is None:
                        self._stop_source()
                        if not getattr(self.source, "drain_after_stop", False):
                            break
                        drain_deadline = time.monotonic() + 5.0
                    if self.source.finished:
                        break
                    if time.monotonic() >= drain_deadline:
                        raise TimeoutError("Source did not drain after stop; buffered events may be lost.")
                requested = self._pause_requested.is_set()
                if requested != self.paused:
                    self._interrupt_marker(13 if requested else 14)
                    self._interrupt_used = True
                    if requested:
                        self._analysis_gap = True
                        if self._analysis is not None:
                            self._analysis.disable("Live analysis paused and cannot resume in this run; raw recording continues.")
                    self.paused = requested
                batch = self.source.read(timeout=0.2)
                if batch is None:
                    if self.source.finished:
                        default = "duration reached" if self._self_timed else "source finished"
                        self.stop_reason = self.stop_reason or default
                        break
                    continue
                if t0 is None and len(batch):
                    t0 = int(batch.macro[0])
                if self.duration_s is not None and t0 is not None and not self._self_timed:
                    limit = t0 + int(self.duration_s / clock)
                    if len(batch) and batch.macro[-1] >= limit:
                        self.stop_reason = "duration reached"
                        self._stop.set()
                if len(batch):
                    self._last_seen_macro = int(batch.macro[-1])
                if batch.event is not None:
                    reserved = (batch.event != 0) & np.isin(batch.channel, [13, 14])
                    if np.any(reserved):
                        self._reserved_marker_seen = True
                        if (self._interrupt_used or self._pause_requested.is_set()) and collision_error is None:
                            # Preserve this and all buffered batches before reporting the collision.
                            collision_error = "Hardware marker collides with interruption markers 13/14."
                            self._analysis_gap = True
                            if self._analysis is not None:
                                self._analysis.disable(collision_error)
                            self._stop.set()
                if collision_error:
                    self._write_batch(batch)
                    capture_safety(batch)
                    continue
                if self.paused:
                    # A pause is an analysis gap, never a raw recording gap.
                    self._write_batch(batch)
                    capture_safety(batch)
                    self.paused_photons += len(batch.photons())
                    continue
                # Preserve this batch before running any live analysis.  This does not by itself
                # make the synchronous analyzer overload-safe; a bounded analysis worker is still
                # needed to keep slow analysis from delaying subsequent reads.
                self._write_batch(batch)
                capture_safety(batch)
                if capture_error is not None:
                    continue
                if self._analysis is not None and not self._analysis.submit(batch):
                    self._analysis_gap = True
            if collision_error or capture_error:
                raise ValueError("; ".join(e for e in (collision_error, capture_error) if e))
        except Exception as exc:  # noqa: BLE001 - shown in the tool; the file is still closed
            _log.exception("recording failed")
            self.error = f"{type(exc).__name__}: {exc}"
            self.stop_reason = "error"
        finally:
            def finalization_error(stage, exc):
                _log.exception("%s failed", stage)
                detail = f"{stage}: {type(exc).__name__}: {exc}"
                self.error = f"{self.error}; {detail}" if self.error else detail
                self.stop_reason = "error"

            # Close the recording before running fallible analysis finalization.  A broken
            # analyzer must not strand submitted raw records in an open writer.
            try:
                self._stop_source()
            except Exception as exc:
                finalization_error("source stop", exc)
            for label, writer in (("PTU writer close", self._writer),
                                  ("device recorder close", self._recorder)):
                if writer is not None:
                    try:
                        closed = writer.close()
                        if closed is False:
                            error = getattr(writer, "error", None)
                            detail = error() if callable(error) else error
                            raise OSError(f"writer refused to close: {detail or 'unknown error'}")
                    except Exception as exc:
                        finalization_error(label, exc)
            try:
                source_status = self.source.status()
                source_error = source_status.get("error", "")
                source_dropped = int(source_status.get("dropped", 0))
                if source_error or source_dropped:
                    detail = f"Source error: {source_error}" if source_error else ""
                    if source_dropped:
                        detail += ("; " if detail else "") + f"Source reported {source_dropped} overflow/loss event(s)."
                    self.error = f"{self.error}; {detail}" if self.error else detail
                    self.stop_reason = "error"
                    self._analysis_gap = True
            except Exception as exc:
                finalization_error("source status", exc)
                self._analysis_gap = True
            analysis_finished = self._analysis is None or self._analysis.finish()
            if not analysis_finished:
                self._analysis_gap = True
            analysis_complete = not bool(self.error) and not self._analysis_gap
            table = {}
            snap = {"photons": 0, "bursts": 0, "elapsed_s": 0.0}
            try:
                if self._analysis is not None and self._analysis._thread.is_alive():
                    snap = dict(self._last_snapshot)
                else:
                    with self._lock:
                        self.analyzer.flush()
                        table = self.table()
                        snap = self.analyzer.snapshot()
            except Exception as exc:
                finalization_error("analysis finalization", exc)
                analysis_complete = False
                table = {}
            if analysis_complete:
                try:
                    self._update_qc(table)
                except Exception as exc:
                    finalization_error("quality finalization", exc)
                    analysis_complete = False
            if not analysis_complete:
                self.qc = {"ready": False, "level": "grey", "checks": [], "metrics": {},
                           "why": (self.error or (self._analysis.reason if self._analysis else "") or
                                   "Live analysis has a paused interval; raw recording continues throughout.")}
            self.result = RunResult(
                ptu=self.ptu_path,
                table=table,
                photons=int(snap["photons"]),
                bursts=int(snap["bursts"]),
                elapsed_s=float(snap["elapsed_s"]),
                stop_reason=self.stop_reason or "finished",
                qc=self.qc,
                analysis_complete=analysis_complete,
            )
            self._dataset = self._photon_dataset()

    def _photon_dataset(self):
        """The recording as a photons dataset, the way a dropped file becomes one: its link (size
        and sha256, hashed here in the worker), embedded when the run is stored in the project, read
        by the experiment that reads photons."""
        ptu = self.ptu_path
        if ptu is None or not ptu.exists():
            return None
        try:
            from chisurf.core.experiments.linked import reader_for_kind
            from chisurf.core.project.links import add_link

            link = add_link(str(ptu))
            if self.embed:
                link = {**link, "embedded": True}  # stored in the project at its next save
            reader = reader_for_kind(self.dataset_kind)
            dataset = reader.make_dataset(str(ptu), link=link)
            dataset.data_reader = reader
            dataset.name = ptu.name
            return dataset
        except Exception:  # noqa: BLE001 - register() falls back to the plain address
            _log.exception("building the recording's dataset failed")
            return None

    def table(self) -> dict:
        """The burst table as stored: the analyzer's columns, then ``First File`` / ``Last File``
        (one file per run)."""
        table = dict(self.analyzer.table())
        n = len(table.get("First Photon", ()))
        table["First File"] = np.zeros(n, np.int64)
        table["Last File"] = np.zeros(n, np.int64)
        return table

    def _count_seconds(self, macro, clock: float) -> None:
        if len(macro) == 0:
            return
        if self._first_macro is None:
            self._first_macro = int(macro[0])
        second = ((macro.astype(np.int64) - self._first_macro) * clock).astype(np.int64)
        counts = np.bincount(second)
        if counts.size > self._per_second.size:
            self._per_second = np.concatenate(
                [self._per_second, np.zeros(counts.size - self._per_second.size, np.int64)]
            )
        self._per_second[: counts.size] += counts

    def trace_1s(self) -> tuple[np.ndarray, np.ndarray]:
        """Total count rate in 1 s bins: bin centres (s) and kHz (the last bin is partial)."""
        n = self._per_second.size
        return np.arange(n) + 0.5, self._per_second.astype(float) * 1e-3

    def _update_qc(self, table: dict | None = None) -> None:
        """Re-evaluate the quality checker on the bursts so far (worker thread, not the UI's)."""
        from .qc import live_qc

        info = self.source.info
        with self._lock:
            table = table if table is not None else self.analyzer.table()
            snap = self.analyzer.snapshot()
            trace = self.trace_1s()
        try:
            qc = live_qc(
                table,
                self.experiment,
                elapsed_s=float(snap["elapsed_s"]),
                background_cps=snap["background_cps"],
                trace=trace,
                macro_clock_s=info.macro_clock_s,
                micro_res_s=info.micro_res_s,
                n_micro=info.n_micro,
                n_photons=int(snap["photons"]),
            )
        except Exception as exc:  # noqa: BLE001 - no verdict is shown as such, the run goes on
            _log.exception("live quality check failed")
            qc = {"ready": False, "level": "grey", "checks": [], "metrics": {}, "why": str(exc)}
        with self._lock:
            self.qc = qc

    # -- the view's side ------------------------------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        """The accumulators and health, copied under the lock (no photons)."""
        if self._lock.acquire(blocking=False):
            try:
                snap = self.analyzer.snapshot()
                if self.trace is not None:
                    snap["live_trace"] = self.trace.snapshot()
                self._last_snapshot = snap
            finally:
                self._lock.release()
        else:
            snap = dict(self._last_snapshot)
        status = self.source.status()
        source_error = status.get("error", "")
        source_dropped = int(status.get("dropped", 0))
        health_error = self.error or (f"Source error: {source_error}" if source_error else "")
        if source_dropped and "overflow/loss" not in health_error:
            health_error += ("; " if health_error else "") + f"Source reported {source_dropped} overflow/loss event(s)."
        warning = self._analysis.reason if self._analysis else ""
        received, first, last = self._received
        raw_elapsed = ((last - first) * self.source.info.macro_clock_s
                       if first is not None else 0.0)
        snap.update(
            running=self.running,
            received_photons=received,
            received_elapsed_s=raw_elapsed,
            paused=self.paused,
            paused_photons=self.paused_photons,
            analysis_gap=self._analysis_gap or bool(self._analysis and self._analysis.reason),
            analysis_warning=warning,
            batches=self.batches,
            dropped=self.dropped + int(status.get("dropped", 0)),
            queued=int(status.get("queued", 0)),
            source_error=health_error,
            stop_reason=self.stop_reason,
            wall_s=(time.monotonic() - self.started_at) if self.started_at else 0.0,
            qc=({"ready": False, "level": "grey", "checks": [], "metrics": {},
                 "why": health_error or warning or "Live analysis has a paused interval; raw recording continues throughout."}
                if self._analysis_gap or warning or self.error or status.get("error") or status.get("dropped") else self.qc),
        )
        return snap

    # -- into the project ------------------------------------------------------------------------
    def register(self) -> RunResult | None:
        """Add the recording and its burst run to the workspace (after the run ended): the photons
        dataset (embedded in the project or linked), its burst run -- written into the dataset's
        analysis container -- as its child, through the shell's API like a dropped file."""
        result = self.result
        if result is None or result.ptu is None or not result.ptu.exists():
            return result
        from chisurf.core.datastore import store_from_rows
        from chisurf.core.experiments.linked import reader_for_kind
        from chisurf.core.project.analysis import container_dir
        from chisurf.plugins.burst.burst_selection.api.io import write_container

        from .project import add_to_workspace

        photons = self._dataset
        if photons is None:  # hashing failed in the worker: link the file plainly
            reader = reader_for_kind(self.dataset_kind)
            photons = reader.make_dataset(str(result.ptu))
            photons.data_reader = reader
        photons.name = result.ptu.name
        uid = str(getattr(photons, "unique_identifier", "") or "")
        result.dataset_uid = uid
        datasets = [photons]
        if result.bursts and result.analysis_complete:
            columns = list(result.table)
            rows = [
                {c: result.table[c][i].item() for c in columns}
                for i in range(len(result.table[columns[0]]))
            ]
            exp = self.experiment
            parameters = {
                "mode": "live",
                "preset": exp.preset,
                "min_photons": exp.burst.min_photons,
                "window_photons": exp.burst.window_photons,
                "window_time_s": exp.burst.window_time_s,
                "setup_name": exp.name,
                "setup": exp.setup,
            }
            if result.qc:
                # The quality checker's verdict at stop, kept with the run's provenance.
                parameters["quality"] = quality_record(result.qc)
            container = write_container(
                result.ptu,
                store_from_rows(rows, columns),
                parameters=parameters,
                algorithm="sliding_window",
                out_dir=container_dir(uid),
                raw_data="sidecar",
                run=RUN_NAME,
            )
            result.run_address = f"{container}/{RUN_NAME}"
            runs = reader_for_kind("bursts")
            run = runs.make_dataset(result.run_address, result_of=uid)
            run.data_reader = runs
            datasets.append(run)
        add_to_workspace(datasets, f"Adding {result.ptu.name}")
        return result
