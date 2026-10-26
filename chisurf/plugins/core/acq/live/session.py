"""One recording: a source read in a worker thread, analysed live, written to a PTU as it arrives.

:class:`RecordSession` is what the Record tool starts and stops. The worker thread reads batches
from the source, pushes them into the PIE analyzer and into a PTU stream writer; the view takes
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

from .pie import BurstParameters, PieSetup, make_analyzer
from .sources import PhotonSource

_log = logging.getLogger(__name__)

__all__ = ["RecordSession", "RunResult", "RUN_NAME", "quality_record"]

#: Name of a live run inside the analysis container (``<stem>.pto/live_pie``).
RUN_NAME = "live_pie"
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


def _header(source_info, name: str):
    """A PTU header for the source's clocks (T3, MultiHarp record layout)."""
    probe = tttrlib.TTTR()
    probe.append_events(
        np.zeros(1, np.uint64), np.zeros(1, np.uint16), np.zeros(1, np.int8), np.zeros(1, np.int8)
    )
    h = probe.header
    h.set_tag("MeasDesc_GlobalResolution", float(source_info.macro_clock_s), _TY_F8)
    h.set_tag("MeasDesc_Resolution", float(source_info.micro_res_s), _TY_F8)
    h.set_tag("TTResultFormat_TTTRRecType", _REC_MULTIHARP_T3, _TY_I8)
    h.set_tag("MeasDesc_RecordingMode", 3, _TY_I8)
    h.set_tag("File_Comment", f"ChiSurf live recording: {name}", _TY_ANSI)
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
    """A source, a live PIE analysis and a PTU writer, run in one worker thread.

    Parameters
    ----------
    source : PhotonSource
    setup : PieSetup or None
        ``None`` uses :meth:`PieSetup.default_for` the source's period.
    burst : BurstParameters
    duration_s : float or None
        Stop after this much measurement time; ``None`` until :meth:`stop`.
    ptu_path : str or Path or None
        Where the photons are written while measuring; ``None`` records nothing (view only).
    name : str
        The dataset name in the workspace.
    """

    def __init__(
        self,
        source: PhotonSource,
        setup: PieSetup | None = None,
        burst: BurstParameters = BurstParameters(),
        *,
        duration_s: float | None = None,
        ptu_path: str | Path | None = None,
        name: str = "",
    ):
        self.source = source
        info = source.info
        self.setup = setup or PieSetup.default_for(info.n_micro)
        self.burst = burst
        self.duration_s = duration_s
        self.ptu_path = Path(ptu_path) if ptu_path else None
        self.name = name or datetime.datetime.now().strftime("record_%Y%m%d_%H%M%S")
        self.analyzer = make_analyzer(self.setup, info.macro_clock_s, info.n_micro, burst)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._writer = None
        self._recorder = None
        #: a device whose acquisition timer ends the run: the session does not cut its batches
        self._self_timed = bool(getattr(source, "stops_itself", False)) and duration_s is not None
        if self._self_timed:
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
            self._recorder = self.source.make_recorder(self.ptu_path, self.name)
        elif self.ptu_path is not None:
            self.ptu_path.parent.mkdir(parents=True, exist_ok=True)
            writer = tttrlib.RecordStreamWriter(_PQ_PTU)
            if not writer.create(
                str(self.ptu_path), _header(self.source.info, self.name), self.name
            ):
                raise OSError(f"cannot write {self.ptu_path}: {writer.error()}")
            writer.set_auto_checkpoint(200_000)
            self._writer = writer
        self.source.start()
        self.started_at = time.monotonic()
        self._thread = threading.Thread(target=self._run, name="record-session", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop measuring; the worker closes the open burst and the file."""
        if not self.stop_reason:
            self.stop_reason = "stopped"
        self._stop.set()
        self.source.stop()

    def wait(self, timeout: float | None = None) -> RunResult | None:
        if self._thread is not None:
            self._thread.join(timeout)
        return self.result

    # -- the worker ----------------------------------------------------------------------------
    def _run(self) -> None:
        clock = self.source.info.macro_clock_s
        t0 = None
        try:
            while not self._stop.is_set():
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
                    cut = int(np.searchsorted(batch.macro, np.uint64(limit)))
                    if cut < len(batch):
                        batch.macro, batch.micro, batch.channel = (
                            batch.macro[:cut],
                            batch.micro[:cut],
                            batch.channel[:cut],
                        )
                        self.stop_reason = "duration reached"
                        self._stop.set()
                with self._lock:
                    self.analyzer.push(batch.macro, batch.micro, batch.channel)
                    self.batches += 1
                if self._recorder is not None:
                    self._recorder.write(batch)
                if self._writer is not None and len(batch):
                    ok = self._writer.submit_events(
                        batch.macro, batch.micro, batch.channel, np.zeros(len(batch), np.int8)
                    )
                    if not ok:
                        self.dropped += 1
                if time.monotonic() - self._qc_at >= QC_INTERVAL_S:
                    self._qc_at = time.monotonic()
                    self._update_qc()
        except Exception as exc:  # noqa: BLE001 - shown in the tool; the file is still closed
            _log.exception("recording failed")
            self.error = f"{type(exc).__name__}: {exc}"
            self.stop_reason = "error"
        finally:
            self.source.stop()
            with self._lock:
                self.analyzer.finish()
                table = self.analyzer.results()
            if self._writer is not None:
                self._writer.close()
            if self._recorder is not None:
                self._recorder.close()
            self._update_qc(table)
            self.result = RunResult(
                ptu=self.ptu_path,
                table=table,
                photons=self.analyzer.n_photons,
                bursts=self.analyzer.burst_count,
                elapsed_s=self.analyzer.elapsed_s(),
                stop_reason=self.stop_reason or "finished",
                qc=self.qc,
            )

    def _update_qc(self, table: dict | None = None) -> None:
        """Re-evaluate the quality checker on the bursts so far (worker thread, not the UI's)."""
        from .qc import live_qc

        info = self.source.info
        with self._lock:
            table = table if table is not None else self.analyzer.results()
            elapsed = self.analyzer.elapsed_s()
            background = self.analyzer.background_per_s()
            trace = self.analyzer.trace_1s()
            n_photons = self.analyzer.n_photons
        try:
            qc = live_qc(
                table,
                elapsed_s=elapsed,
                background_per_s=background,
                trace=trace,
                setup=self.setup,
                macro_clock_s=info.macro_clock_s,
                micro_res_s=info.micro_res_s,
                n_micro=info.n_micro,
                n_photons=n_photons,
            )
        except Exception as exc:  # noqa: BLE001 - no verdict is shown as such, the run goes on
            _log.exception("live quality check failed")
            qc = {"ready": False, "level": "grey", "checks": [], "metrics": {}, "why": str(exc)}
        with self._lock:
            self.qc = qc

    # -- the view's side ------------------------------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        """The accumulators and health, copied under the lock (no photons)."""
        with self._lock:
            snap = self.analyzer.snapshot()
        status = self.source.status()
        snap.update(
            running=self.running,
            batches=self.batches,
            dropped=self.dropped + int(status.get("dropped", 0)),
            queued=int(status.get("queued", 0)),
            source_error=status.get("error", "") or self.error,
            stop_reason=self.stop_reason,
            wall_s=(time.monotonic() - self.started_at) if self.started_at else 0.0,
            qc=self.qc,
        )
        return snap

    # -- into the project ------------------------------------------------------------------------
    def register(self) -> RunResult | None:
        """Add the recorded PTU and its burst run to the workspace (after the run ended)."""
        result = self.result
        if result is None or result.ptu is None or not result.ptu.exists():
            return result
        from chisurf.core.datastore import store_from_rows
        from chisurf.core.plugin.workspace_input import register_result
        from chisurf.core.project.analysis import container_dir
        from chisurf.plugins.burst.burst_selection.api.io import write_container

        stream = register_result(str(result.ptu), kind="photons", name=result.ptu.name)
        uid = str(getattr(stream, "unique_identifier", "") or "")
        result.dataset_uid = uid
        if result.bursts:
            columns = list(result.table)
            rows = [
                {c: result.table[c][i].item() for c in columns}
                for i in range(len(result.table[columns[0]]))
            ]
            parameters = {
                "mode": "live_pie",
                "min_photons": self.burst.min_photons,
                "window_photons": self.burst.window_photons,
                "window_time_s": self.burst.window_time_s,
                "setup": self.setup.name,
                "prompt": list(self.setup.prompt),
                "delay": list(self.setup.delay),
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
            register_result(result.run_address, kind="bursts", result_of=uid)
        return result
