"""The model behind the page: one loaded measurement, its settings and results.

``view.json`` binds to the attributes and actions of :class:`Session`; the plots
read :attr:`Session.bursts` and :attr:`Session.qc`. Nothing here draws.

The analysis itself is :func:`chisurf.plugins.burst.fret_check.jobs.analyse`, run as a job
(:mod:`emtk.jobs`): in a page in a Web Worker, on a desktop in a thread, so
the window keeps drawing and shows progress; the session only sends settings
and takes the results in (:meth:`Session.poll`, once a frame). With
``runner="sync"`` -- tests, and interpreters without threads -- the job runs
inline. The measurement itself stays with the job (the worker's cache): the
page holds the results, not the photons.
"""
from __future__ import annotations

import csv
import io
import json
import pathlib

import numpy as np

from .. import jobs
from ..detect import Experiment, Window
from ..pipeline import BurstSettings, Bursts
from ..qc import FLAG_NAMES, QCReport

JOB = "chisurf.plugins.burst.fret_check.jobs:analyse"


def _threads_available() -> bool:
    import sys  # noqa: PLC0415

    return sys.platform != "emscripten"


def default_runner() -> str:
    """``"jobs"`` where a worker or a thread can take the work, else ``"sync"``."""
    try:
        from emtk import jobs as emtk_jobs  # noqa: PLC0415
    except ImportError:
        return "sync"
    return "jobs" if emtk_jobs.in_browser() or _threads_available() else "sync"

__all__ = ["Session"]


def _ints(text: str) -> list[int]:
    return [int(t) for t in str(text).replace(";", ",").split(",") if t.strip()]


def _window(text: str) -> tuple[int, int]:
    a, b = str(text).split("-", 1)
    return int(a), int(b)


class Session:
    def __init__(self, runner: str | None = None) -> None:
        #: ``"jobs"`` (worker / thread) or ``"sync"`` (inline).
        self.runner = runner or default_runner()
        self.path: str | None = None
        #: What identifies the measurement for the job (path or example).
        self.key: str = ""
        self._source: dict = {}
        self.job = None
        self.busy = False
        #: Job progress, 0-1, or ``None`` while not yet reported.
        self.progress = None
        self._worker_has = ""
        self.exp: Experiment | None = None
        self.bursts: Bursts | None = None
        self.qc: QCReport | None = None
        self.corrected: dict | None = None
        self.status = "Drop a TTTR file (PTU, HT3, SPC, SM, PTO, ...) on the window."
        self.version = 0  # bumped on every new result; plots cache on it
        # Settings (view.json).
        self.mode = "simple"
        self.excitation = "cw"
        self.donor_channels = ""
        self.acceptor_channels = ""
        self.donor_window = ""
        self.acceptor_window = ""
        s = BurstSettings()
        self.min_photons = s.min_photons
        self.m = s.m
        self.T_us = s.T * 1e6
        self.cde_tau_us = s.cde_tau * 1e6
        self.auto_calibrate = False
        self.gamma, self.alpha, self.delta, self.beta = 1.0, 0.0, 0.0, 1.0
        self.drop_flagged = False
        #: Effective observation volume for the concentration estimate, fL.
        self.v_eff_fl = 1.0
        #: Demo data (``chisurf.plugins.burst.fret_check.sim``): the chosen example.
        self.demo = ""
        #: Start of the 10 s stretch the time-trace window shows, s.
        self.trace_start_s = 0.0
        #: Per channel ``(edges, counts)`` of the micro time (or alternation phase).
        self.micro_hist: dict = {}
        self.trace_rates: dict = {}
        self.trace_bin_s = 1e-3
        self.trace_bursts = np.zeros((0, 2))
        #: Set by the app: ``download(name, bytes, mime)``, Help and Guide.
        self.download = None
        self.on_help = None
        self.on_guide = None

    # -- view.json sources -------------------------------------------------- #
    def file_info(self) -> str:
        if self.exp is None:
            if self.busy and self.path:
                name = self.path if self.path.startswith("simulated") else pathlib.Path(self.path).name
                size = self._dropped_size()
                note = f" ({size / 2**20:,.0f} MB, read from disk in chunks)" if size else ""
                return f"{name}{note}\nanalysing in the background -- the page stays usable"
            return "No file loaded."
        e = self.exp
        name = (self.path if self.path and self.path.startswith("simulated") else
                pathlib.Path(self.path).name if self.path else "")
        lines = [
            f"{name}",
            f"{e.container} · {e.n_photons:,} photons · {e.duration_s:.1f} s",
            f"Detected: {e.kind}",
        ]
        if e.unassigned_channels:
            lines.append(f"Unassigned: {', '.join(map(str, e.unassigned_channels))}")
        lines += [f"! {w}" for w in e.warnings]
        lines += [f"note: {n}" for n in e.notes]
        return "\n".join(lines)

    def _dropped_size(self):
        """The size of a large dropped file the page keeps only as a handle."""
        try:
            from emtk.web.page import dropped_by_reference  # noqa: PLC0415
        except ImportError:
            return None
        return dropped_by_reference(self.path) if self.path else None

    def enabled(self, name: str) -> bool:
        if name in ("export_csv", "export_report", "export_pdf"):
            return self.bursts is not None
        if name in ("run", "redetect"):
            return self.exp is not None and not self.busy
        if name in ("simulate",):
            return not self.busy
        if name == "cancel":
            return self.busy
        return True

    # -- loading ------------------------------------------------------------ #
    def open(self, path: str) -> None:
        """Analyse a file (it goes to the job once; re-runs reuse it there)."""
        self.path = str(path)
        self._start(key=f"file:{self.path}", source={"path": self.path}, fresh=True)

    def _start(self, key: str, source: dict, fresh: bool = False, redetect: bool = False) -> None:
        """Send one analysis to the job, or run it inline (``runner="sync"``)."""
        if self.job is not None and not self.job.done:
            self.job.cancel()
            self._worker_has = ""
        if fresh:
            self.key, self._source = key, dict(source)
            self.exp = None
            self.trace_start_s = 0.0
        params = {"key": self.key, **self._source, "redetect": bool(redetect),
                  "settings": dict(self.burst_settings().__dict__), "v_eff_fl": float(self.v_eff_fl),
                  "correct": self.mode == "advanced",
                  "factors": {"gamma": float(self.gamma), "alpha": float(self.alpha),
                              "delta": float(self.delta), "beta": float(self.beta)},
                  "auto_calibrate": bool(self.auto_calibrate)}
        if self.mode == "advanced" and self.exp is not None and not fresh and not redetect:
            params["experiment"] = jobs.experiment_to_dict(self._experiment_from_settings())
        self.busy, self.progress = True, None
        self.status = "Analysing ..."
        if self.runner == "sync":
            try:
                self._take(jobs.analyse(self._report, **params), fresh or redetect)
            except Exception as exc:  # noqa: BLE001 - shown, not swallowed
                self._failed(str(exc))
            return
        from emtk import jobs as emtk_jobs  # noqa: PLC0415

        files = []
        path = self._source.get("path")
        if path and self._worker_has != self.key:
            files = [path]          # the file goes to the worker once
        self.job = emtk_jobs.start(JOB, params, files=files)
        self._job_detects = fresh or redetect
        self._worker_has = self.key

    def _report(self, fraction=None, message=None) -> None:
        if fraction is not None:
            self.progress = float(fraction)
        if message is not None:
            self.status = f"{message} ..."

    def poll(self) -> bool:
        """Take in a finished job; ``True`` while one runs (the app keeps drawing)."""
        job = self.job
        if job is None:
            return False
        if not job.done:
            self.progress = job.progress
            self.status = f"{job.message} ..."
            return True
        self.job = None
        if job.error:
            if job.cancelled:
                self.busy, self.progress = False, None
                self.status = "Cancelled."
                self._worker_has = ""
            else:
                self._failed(job.error.strip().splitlines()[-1])
            return False
        try:
            self._take(job.result, self._job_detects)
        except Exception as exc:  # noqa: BLE001
            self._failed(str(exc))
        return False

    def cancel(self) -> None:
        if self.job is not None and not self.job.done:
            self.job.cancel()

    def wait(self, timeout: float = 600.0) -> None:
        """Block until the running job is in (scripts and tests)."""
        import time  # noqa: PLC0415

        end = time.time() + timeout
        while self.poll() and time.time() < end:
            time.sleep(0.02)

    def _failed(self, message: str) -> None:
        self.busy, self.progress = False, None
        self.status = f"Error: {message}"
        self.version += 1

    def _take(self, result: dict, detected: bool) -> None:
        """A job's results into the session."""
        self.exp = jobs.experiment_from_dict(result["experiment"])
        if detected:
            self.exp = jobs.experiment_from_dict(result["detected"])
            self._settings_from_experiment()
        self.bursts = jobs.bursts_from_dict(result["bursts"])
        self.qc = jobs.qc_from_dict(result["qc"])
        corrected = result.get("corrected")
        self.corrected = None if not corrected else {
            "E": jobs.unpack(corrected["E"]), "S": jobs.unpack(corrected["S"])}
        if self.auto_calibrate and result.get("factors"):
            for k, v in result["factors"].items():
                setattr(self, k, float(v))
        tr = result["trace"]
        self.trace_bin_s = float(tr["bin_s"])
        self.trace_rates = {k: jobs.unpack(v).astype(float) for k, v in tr["rates"].items()}
        self.trace_bursts = jobs.unpack(tr["bursts"])
        self.micro_hist = {int(c): (jobs.unpack(h["edges"]), jobs.unpack(h["counts"]))
                           for c, h in result["micro"].items()}
        #: Whether the job read the file through a read-only mount of the
        #: user's File (a page's worker) rather than a copy.
        self.file_mounted = bool(result.get("file_mounted"))
        self.chunked = bool(result.get("chunked"))
        self.busy, self.progress = False, None
        self.status = f"{self.bursts.n} bursts · QC: {self.qc.level.upper()}"
        self.version += 1

    def demo_names(self) -> list:
        from ..sim import SCENARIOS  # noqa: PLC0415

        return [s.name for s in SCENARIOS]

    def simulate(self) -> None:
        """Simulate the chosen example and analyse it like a file."""
        from ..sim import SCENARIOS  # noqa: PLC0415

        sc = next((s for s in SCENARIOS if s.name == self.demo), SCENARIOS[0])
        self.demo = sc.name
        self.path = f"simulated: {sc.name}"
        self._start(key=f"sim:{sc.name}", source={"scenario": sc.name}, fresh=True)

    def show_help(self) -> None:
        if self.on_help:
            self.on_help()

    def start_guide(self) -> None:
        if self.on_guide:
            self.on_guide()

    def _settings_from_experiment(self) -> None:
        e = self.exp
        self.excitation = e.excitation
        self.donor_channels = ", ".join(map(str, e.donor_channels))
        self.acceptor_channels = ", ".join(map(str, e.acceptor_channels))
        win = {w.name: w for w in e.windows}
        self.donor_window = f"{win['donor'].start}-{win['donor'].stop}" if "donor" in win else ""
        self.acceptor_window = f"{win['acceptor'].start}-{win['acceptor'].stop}" if "acceptor" in win else ""

    def _experiment_from_settings(self) -> Experiment:
        """The experiment with the Channels window's edits applied."""
        import copy  # noqa: PLC0415

        e = copy.deepcopy(self.exp)
        e.donor_channels = _ints(self.donor_channels)
        e.acceptor_channels = _ints(self.acceptor_channels)
        e.excitation = self.excitation
        if self.excitation == "alternating":
            d, a = _window(self.donor_window), _window(self.acceptor_window)
            e.windows = [Window("donor", *d), Window("acceptor", *a)]
        else:
            e.windows = []
        e.polarization = len(e.donor_channels) == 2 and len(e.acceptor_channels) == 2
        if e.polarization:
            e.donor_pol, e.acceptor_pol = list(e.donor_channels), list(e.acceptor_channels)
        return e

    # -- actions ------------------------------------------------------------ #
    def redetect(self) -> None:
        if self.key:
            self._start(self.key, self._source, redetect=True)

    def burst_settings(self) -> BurstSettings:
        return BurstSettings(min_photons=int(self.min_photons), m=int(self.m),
                             T=float(self.T_us) * 1e-6, cde_tau=float(self.cde_tau_us) * 1e-6)

    def run(self) -> None:
        """Analyse again with the current settings (the measurement stays with the job)."""
        if self.key:
            self._start(self.key, self._source)

    def duration_s(self) -> float:
        return float(self.exp.duration_s) if self.exp else 0.0

    # -- the burst table ---------------------------------------------------- #
    def table(self) -> dict:
        """Every per-burst column: the analysis, the corrected E/S, the QC flags."""
        cols = self.bursts.columns()
        if self.corrected:
            cols["FRET Efficiency"] = self.corrected["E"]
            if self.corrected["S"] is not None:
                cols["Stoichiometry (corrected)"] = self.corrected["S"]
        cols["QC flags"] = self.qc.flags.astype(float)
        for bit, name in FLAG_NAMES.items():
            cols[f"QC {name}"] = ((self.qc.flags & bit) != 0).astype(float)
        if self.drop_flagged:
            keep = self.qc.flags == 0
            cols = {k: np.asarray(v)[keep] for k, v in cols.items()}
        return cols

    # -- results for plots -------------------------------------------------- #
    def es(self) -> tuple[np.ndarray, np.ndarray | None]:
        """E and S to plot: corrected when available, QC-flagged dropped on request."""
        b = self.bursts
        e, s = (self.corrected["E"], self.corrected["S"]) if self.corrected else (b.E, b.S)
        if self.drop_flagged and self.qc is not None:
            keep = self.qc.flags == 0
            e = e[keep]
            s = None if s is None else s[keep]
        return e, s

    # -- export ------------------------------------------------------------- #
    def burst_csv(self) -> bytes:
        cols = self.table()
        buf = io.StringIO()
        w = csv.writer(buf)
        names = list(cols)
        w.writerow(names)
        arrays = [np.asarray(cols[n]) for n in names]
        for i in range(len(arrays[0]) if arrays else 0):
            w.writerow([f"{a[i]:.6g}" if np.issubdtype(a.dtype, np.floating) else int(a[i]) for a in arrays])
        return buf.getvalue().encode()

    def report(self) -> dict:
        return {"file": pathlib.Path(self.path).name if self.path else None,
                "experiment": self.exp.as_dict(),
                "burst_settings": self.burst_settings().__dict__,
                "qc": self.qc.as_dict()}

    def _stem(self) -> str:
        if not self.path:
            return "bursts"
        if self.path.startswith("simulated: "):
            return "simulated_" + "".join(ch if ch.isalnum() else "_" for ch in self.path[11:]).strip("_")
        return pathlib.Path(self.path).stem

    def export_csv(self) -> None:
        if self.bursts is not None and self.download:
            self.download(f"{self._stem()}.bursts.csv", self.burst_csv(), "text/csv")

    def export_report(self) -> None:
        if self.qc is not None and self.download:
            self.download(f"{self._stem()}.qc.json", json.dumps(self.report(), indent=1).encode(),
                          "application/json")

    def export_pdf(self) -> None:
        """The one-page PDF report: histograms, background, every report value."""
        if self.qc is not None and self.bursts is not None and self.download:
            from chisurf.plugins.burst.fret_check.report import build_pdf_report

            self.download(f"{self._stem()}.report.pdf", build_pdf_report(self),
                          "application/pdf")
