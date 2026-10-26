"""One recording: a source read in a worker thread, analysed live, written to a PTU as it arrives.

:class:`RecordSession` is what the Record tool starts and stops. The worker thread reads batches
from the source, pushes them into the live burst analyzer (tttrlib's ``StreamingBurstAnalyzer``,
or its stand-in; the measurement type is the :class:`~.setups.Experiment`'s preset) and into the
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


def _header(source_info, name: str, settings: dict | None = None):
    """A PTU header for the source's clocks (T3, MultiHarp record layout), with the run's
    acquisition settings document in the ``ChiSurf_AcquisitionSettings`` tag when given."""
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
    if settings:
        h.set_tag(CHISURF_SETTINGS_TAG, settings_file.dumps(settings), _TY_ANSI)
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
    ):
        self.source = source
        info = source.info
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
        self.analyzer = self.experiment.analyzer(info.macro_clock_s, info.micro_res_s, info.n_micro)
        #: total photons per whole second of the run (the checker's stability trace)
        self._per_second = np.zeros(0, dtype=np.int64)
        self._first_macro: int | None = None
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
            extra = (
                {CHISURF_SETTINGS_TAG: settings_file.dumps(self.settings)}
                if self.settings
                else None
            )
            self._recorder = self.source.make_recorder(self.ptu_path, self.name, extra=extra)
        elif self.ptu_path is not None:
            self.ptu_path.parent.mkdir(parents=True, exist_ok=True)
            writer = tttrlib.RecordStreamWriter(_PQ_PTU)
            if not writer.create(
                str(self.ptu_path), _header(self.source.info, self.name, self.settings), self.name
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
                    self.analyzer.push_np(batch.macro, batch.micro, batch.channel.astype(np.int32))
                    self._count_seconds(batch.macro, clock)
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
                self.analyzer.flush()
                table = self.table()
            if self._writer is not None:
                self._writer.close()
            if self._recorder is not None:
                self._recorder.close()
            self._update_qc(table)
            snap = self.analyzer.snapshot()
            self.result = RunResult(
                ptu=self.ptu_path,
                table=table,
                photons=int(snap["photons"]),
                bursts=int(snap["bursts"]),
                elapsed_s=float(snap["elapsed_s"]),
                stop_reason=self.stop_reason or "finished",
                qc=self.qc,
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
            reader = reader_for_kind("photons")
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
            reader = reader_for_kind("photons")
            photons = reader.make_dataset(str(result.ptu))
            photons.data_reader = reader
        photons.name = result.ptu.name
        uid = str(getattr(photons, "unique_identifier", "") or "")
        result.dataset_uid = uid
        datasets = [photons]
        if result.bursts:
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
