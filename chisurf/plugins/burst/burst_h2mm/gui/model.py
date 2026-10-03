"""Qt-free settings and result model behind the emtk H2MM app (card H0).

Holds what the Qt ``H2mmTool`` keeps in its widgets and on itself: the burst folder, every setting that goes into
:class:`~..api.models.H2mmSettings`, the detector-to-stream assignment, and the result of the last fit
(``result``, ``bundle`` and the bootstrap ``uncertainty``). The actions run on a snapshot of this model through
:class:`chisurf.emtk.jobs.SnapshotJob`; the numerical work is the unchanged :func:`..backend.services.run_analysis`.

Nothing here imports Qt or emtk.
"""

from __future__ import annotations

import copy
import json
import pathlib
import threading
from typing import Any, Callable

from ..api.models import H2mmSettings, StreamSettings

#: Bump in the same change that alters what this tool computes, so results written by the previous version stop
#: reading as current (shared by the Qt tool and the emtk app).
ALGORITHM_VERSION = 1

#: Engines and decoders offered (same lists, same order as the Qt tool's combos).
ENGINES = [("Fast EM (float32)", "em-float32"), ("Exact EM (float64)", "em"), ("Neural surrogate", "neural")]
DECODERS = [("Viterbi", "viterbi"), ("Jitter", "jitter"), ("FFBS", "ffbs")]
CRITERIA = ["bic", "icl"]
#: The "no third stream" entry of the acceptor-excitation choice (the Qt combo's wording).
NO_AEX = "(none)"

#: Fields saved to and loaded from a settings file.
SETTING_FIELDS = (
    "donor", "acceptor", "aex", "min_states", "max_states", "criterion",
    "patience", "engine", "restarts", "seed", "photon_hdf5", "photon_csv", "max_iter", "min_photons", "time_scale",
    "divisors", "decoder", "decoder_seed", "write_state_tttr", "state_tttr_ptu", "state_tttr_sidecar",
)


def parse_channels(text: str) -> list[int]:
    """``"0, 8"`` -> ``[0, 8]`` (empty or malformed parts are ignored)."""
    out: list[int] = []
    for part in str(text).replace(";", ",").split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            out.append(int(part))
    return out


class H2mmViewModel:
    """State and actions of the photon-by-photon HMM tool (no Qt, no emtk)."""

    def __init__(self) -> None:
        self._observers: list[Callable[[str], None]] = []
        self._cancel = threading.Event()
        #: Burst folder (``.bur`` tables, the photons they name beside them).
        self.data_folder: str = ""
        # The detector definition (the Qt tool's Channels tab, edited by the shared detector editor) and which of its
        # detectors is the donor, acceptor and (optional) acceptor-excitation stream.
        self.setup: dict = {
            "detectors": {
                "green": {"chs": [0, 8], "micro_time_ranges": [], "g_factor": 1.0, "l1": 0.0, "l2": 0.0},
                "red": {"chs": [1, 9], "micro_time_ranges": [], "g_factor": 1.0, "l1": 0.0, "l2": 0.0},
            },
            "windows": {},
            "tttr_reading": {"file_type": "SPC-130", "macro_time_resolution": 0.0, "micro_time_resolution": 0.0,
                             "micro_time_binning": 1},
        }
        self.donor: str = "green"
        self.acceptor: str = "red"
        self.aex: str = NO_AEX
        # Model selection
        self.min_states: int = 1
        self.max_states: int = 3
        self.criterion: str = "bic"
        self.patience: int = 1  # -1 = off (scan all)
        # Optimisation (defaults are the Qt tool's)
        self.engine: str = "em-float32"
        self.restarts: int = 2
        self.seed: int = 0
        self.photon_hdf5: bool = True
        self.photon_csv: bool = True
        self.max_iter: int = 500
        self.min_photons: int = 5
        self.time_scale: int = 1
        self.divisors: int = 1
        self.decoder: str = "viterbi"
        self.decoder_seed: int = 0
        self.write_state_tttr: bool = False
        self.state_tttr_ptu: bool = True
        self.state_tttr_sidecar: bool = True
        # Outcome of the last run
        self.scans: list = []  # likelihood profiles
        self.nav_burst: int = 0  # burst shown in the state-path plot
        self.dynamic_only: bool = False
        self.fingerprint: str = ""  # of the inputs + settings the shown fit was computed from
        self.result: Any = None  # H2mmResult summary
        self.bundle: Any = None  # H2mmAnalysisBundle (analysis, data, settings)
        self.uncertainty: Any = None
        self.status_text: str = "Ready"
        self.running: bool = False

    # -- observers ------------------------------------------------------------------------------------------- #
    def notify(self, event: str = "updated") -> None:
        for observer in list(self._observers):
            observer(event)

    # -- derived --------------------------------------------------------------------------------------------- #
    @property
    def analysis(self):
        """The in-memory ``H2mmAnalysis`` of the last fit (``None`` before one)."""
        return getattr(self.bundle, "analysis", None)

    # -- detector setup ---------------------------------------------------------------------------------------- #
    def detector_names(self) -> list[str]:
        """Names of the defined detectors (the donor and acceptor choices)."""
        return list(self.setup.get("detectors", {}))

    def aex_options(self) -> list[str]:
        """The acceptor-excitation choices: no third stream, or one of the detectors."""
        return [NO_AEX, *self.detector_names()]

    @property
    def file_type(self) -> str:
        """Container type from the detector definition's reading routine."""
        return str((self.setup.get("tttr_reading") or {}).get("file_type", "SPC-130"))

    def set_setup(self, settings: dict) -> None:
        """Take a new detector definition (the editor calls this on every change); keep the stream choices valid."""
        self.setup = copy.deepcopy(settings)
        names = self.detector_names()
        if self.donor not in names:
            self.donor = names[0] if names else ""
        if self.acceptor not in names:
            self.acceptor = names[1] if len(names) > 1 else (names[0] if names else "")
        if self.aex not in names:
            self.aex = NO_AEX
        self.notify("setup")

    def _stream(self, name: str) -> StreamSettings:
        info = (self.setup.get("detectors") or {}).get(name, {})
        ranges = [(int(a), int(b)) for a, b in info.get("micro_time_ranges", [])]
        return StreamSettings(name=name or "stream", channels=[int(c) for c in info.get("chs", [])], micro_time_ranges=ranges)

    def streams(self) -> list[StreamSettings]:
        """Donor, acceptor and optional acceptor-excitation stream (the Qt tool's ``_detector_streams``)."""
        streams = [self._stream(self.donor), self._stream(self.acceptor)]
        if self.aex and self.aex != NO_AEX and self.aex in self.setup.get("detectors", {}):
            streams.append(self._stream(self.aex))
        return streams

    def build_settings(self) -> H2mmSettings:
        """The backend settings these fields describe (what ``H2mmTool._gather_settings`` builds from its widgets)."""
        return H2mmSettings(
            streams=self.streams(),
            min_states=int(self.min_states),
            max_states=max(int(self.max_states), int(self.min_states)),
            criterion=self.criterion,
            n_restarts=int(self.restarts),
            seed=int(self.seed),
            photon_hdf5=bool(self.photon_hdf5),
            photon_csv=bool(self.photon_csv),
            max_iter=int(self.max_iter),
            min_photons=int(self.min_photons),
            time_scale=int(self.time_scale),
            divisors=int(self.divisors),
            file_type=self.file_type,
            engine=self.engine or "em",
            decoder=self.decoder or "viterbi",
            decoder_seed=int(self.decoder_seed),
            write_state_tttr=bool(self.write_state_tttr),
            state_tttr_ptu=bool(self.state_tttr_ptu),
            state_tttr_sidecar=bool(self.state_tttr_sidecar),
            patience=None if int(self.patience) < 0 else int(self.patience),
        )

    def nav_bursts(self) -> list[int]:
        """Bursts the state-path plot can show: all of them, or only the dynamic ones."""
        ana = self.analysis
        if ana is None or self.bundle is None or self.bundle.data is None:
            return []
        if self.dynamic_only:
            dyn = [int(t.burst) for t in ana.transitions]
            dyn = sorted(set(dyn))
            if dyn:
                return dyn
        return list(range(int(self.bundle.data.n_bursts)))

    def rate_rows(self) -> list[dict]:
        """Rows of the rate table: every transition i -> j with its rate and mean waiting time (empty before a fit)."""
        import numpy as np

        from . import result_view

        rates = result_view.rate_matrix(self.analysis)
        if rates is None:
            return []
        rows = []
        for i in range(rates.shape[0]):
            for j in range(rates.shape[0]):
                if i != j:
                    k = float(rates[i, j])
                    wait = (1e3 / k) if np.isfinite(k) and k > 0 else float("nan")
                    rows.append({"transition": f"S{i} -> S{j}", "rate": f"{k:.1f}", "time": f"{wait:.3g}"})
        return rows

    def state_rows(self) -> list[dict]:
        """Rows of the state table: E and occupancy per state (empty before a fit)."""
        ana = self.analysis
        if ana is None:
            return []
        pops = getattr(ana, "posterior_populations", None)
        if pops is None or len(pops) != len(ana.fret):
            pops = ana.populations
        return [
            {"state": f"S{i}", "efficiency": f"{float(e):.3f}", "population": f"{float(p):.3f}"}
            for i, (e, p) in enumerate(zip(ana.fret, pops))
        ]

    def can_run(self) -> str:
        """Why Run is unavailable (empty when it is available); the Qt tool's wording for the missing folder."""
        if not self.data_folder or not pathlib.Path(self.data_folder).is_dir():
            return "Select a folder of .bur files first."
        if not self._stream(self.donor).channels or not self._stream(self.acceptor).channels:
            return "Define the donor and the acceptor detector (routing channels) first."
        return ""

    # -- actions (run on a snapshot through SnapshotJob) ------------------------------------------------------ #
    def input_files(self) -> list:
        """Everything the fit reads: the burst tables and the raw photons they name."""
        from chisurf.core.fio.fluorescence.burst_manifest import source_inputs

        if not self.data_folder:
            return []
        tables = sorted(pathlib.Path(self.data_folder).glob("**/*.bur"))
        return tables + list(source_inputs(self.data_folder))

    def analysis_fingerprint(self, settings) -> str:
        """Fingerprint of the inputs, the settings, the read context and the code (the Qt tool's)."""
        from chisurf.core.runtime import analysis_cache

        return analysis_cache.fingerprint(
            self.input_files(),
            {"settings": settings, "_read_context": analysis_cache.photon_read_context()},
            extra=analysis_cache.algorithm_tag("h2mm", ALGORITHM_VERSION, "tttrlib"),
        )

    def compute(self, force: bool = False) -> None:
        """Fit every state count of the scan (the work of ``H2mmTool._fit_worker``); raises on a stop or an error.

        A fit whose burst files and settings are identical to the one shown is kept (Run says so); ``force`` refits
        (Restart). The restarts are seeded, so a forced refit reproduces the answer; change the seed to resample.
        """
        from ..backend.services import run_analysis, write_result_tables

        problem = self.can_run()
        if problem:
            raise ValueError(problem)
        self._cancel.clear()
        settings = self.build_settings()
        fingerprint = self.analysis_fingerprint(settings)
        if not force and self.result is not None and fingerprint == self.fingerprint:
            self.status_text = "Unchanged - kept the previous H2MM fit (Restart refits it)."
            self.notify("unchanged")
            return

        def progress(done, total, fits):
            if self._cancel.is_set():
                raise InterruptedError("The H2MM fit was stopped.")
            self.status_text = f"Fitting ... {int(done)}/{total} state counts done"
            self.notify("progress")

        result, bundle = run_analysis(settings, analysis_folder=str(self.data_folder), progress=progress)
        if getattr(settings, "write_photons", True):
            try:
                write_result_tables(result, bundle, pathlib.Path(self.data_folder) / "h2mm")
            except Exception as exc:  # disk / permission path: the fit itself succeeded
                self.status_text = f"Fitted, but the tables could not be written: {exc}"
        self.result, self.bundle, self.uncertainty, self.scans = result, bundle, None, []
        self.fingerprint = fingerprint
        self.nav_burst = 0
        seed = (result.settings_applied or {}).get("seed")
        self.status_text = (
            f"Selected {result.n_states} states ({result.criterion.upper()}) from {result.n_bursts} bursts / "
            f"{result.n_photons} photons" + (f" (seed {seed})" if seed is not None else "")
        )
        if result.posterior_populations:
            self.status_text += " - occupancy " + ", ".join(f"{x:.3f}" for x in result.posterior_populations)
        self.notify("result")

    def restart(self) -> None:
        """Refit even when nothing changed."""
        self.compute(force=True)

    def bootstrap(self, n_boot: int = 20) -> None:
        """Bootstrap the selected model over bursts (the Qt tool's ``_uncertainty_worker``)."""
        from ..core.analysis import bootstrap_uncertainty

        if self.bundle is None:
            raise ValueError("Run a fit before estimating uncertainty.")
        self._cancel.clear()
        ana, data, settings = self.bundle.analysis, self.bundle.data, self.bundle.settings

        def progress(done, total):
            if self._cancel.is_set():
                raise InterruptedError("The bootstrap was stopped.")
            self.status_text = f"Bootstrapping ... {int(done)}/{int(total)} resamples"
            self.notify("progress")

        unc = bootstrap_uncertainty(
            data, int(ana.best.n_states), n_boot=n_boot, engine=getattr(settings, "engine", "em"), n_restarts=1,
            max_iter=300, donor_streams=getattr(ana, "donor_streams", (0,)),
            acceptor_streams=getattr(ana, "acceptor_streams", (1,)), aex_streams=getattr(ana, "aex_streams", None),
            progress=progress,
        )
        self.uncertainty = unc
        self.status_text = f"Uncertainty from {unc.n_boot} bootstrap resamples ({unc.ci[0]:.0f}-{unc.ci[1]:.0f}% CI)"
        self.notify("uncertainty")

    def ll_scan(self, n_points: int = 25) -> None:
        """Profile the log-likelihood of every state's E (and S) (the Qt tool's ``_llscan_worker``)."""
        from ..core.analysis import profile_likelihood

        if self.bundle is None:
            raise ValueError("Run a fit before the likelihood scan.")
        self._cancel.clear()
        ana, data = self.bundle.analysis, self.bundle.data

        def progress(done, total):
            if self._cancel.is_set():
                raise InterruptedError("The likelihood scan was stopped.")
            self.status_text = f"Likelihood scan ... {int(done)}/{int(total)} evaluations"
            self.notify("progress")

        scans = profile_likelihood(
            data, ana.best.model, donor_streams=getattr(ana, "donor_streams", (0,)),
            acceptor_streams=getattr(ana, "acceptor_streams", (1,)), aex_streams=getattr(ana, "aex_streams", None),
            n_points=n_points, progress=progress,
        )
        self.scans = list(scans or [])
        self.status_text = (f"Likelihood scan: {len(self.scans)} parameter profiles" if self.scans
                            else "Likelihood scan: nothing to profile")
        self.notify("scans")

    def dwell_table(self):
        """The per-dwell table of the shown fit (what ``h2mm_dwells.csv`` holds), or ``None``."""
        bundle = self.bundle
        meta = getattr(bundle, "meta", None)
        if bundle is None or meta is None:
            return None
        from ..core.decays import colour_groups
        from ..core.export import build_dwell_table

        ana = bundle.analysis
        micro_ns = getattr(bundle, "micro_time_ns", None)
        return build_dwell_table(bundle.data, meta, ana.dwells, ana.base_time_s,
                                 stream_groups=colour_groups(ana, bundle.settings), micro_time_ns=(micro_ns or None))

    def export_dwells(self, path: str | pathlib.Path) -> int:
        """Write the dwell table as CSV; returns the number of dwells."""
        from chisurf.core.datastore import row_count, write_csv_table

        table = self.dwell_table()
        if table is None or row_count(table) == 0:
            raise ValueError("No dwells to export: run a fit first.")
        write_csv_table(pathlib.Path(path), table, delimiter=",")
        return int(row_count(table))

    def stop(self) -> None:
        """Ask a running fit to stop at its next progress checkpoint."""
        self._cancel.set()

    # -- settings file ---------------------------------------------------------------------------------------- #
    def settings_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in SETTING_FIELDS}

    def save_settings(self, path: str | pathlib.Path) -> None:
        pathlib.Path(path).write_text(json.dumps(self.settings_dict(), indent=2), encoding="utf-8")

    def load_settings(self, path: str | pathlib.Path) -> None:
        data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        for name in SETTING_FIELDS:
            if name in data:
                setattr(self, name, type(getattr(self, name))(data[name]))
        self.notify("settings")
