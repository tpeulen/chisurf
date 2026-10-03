"""Qt-free settings and result model behind the emtk H2MM app (card H0).

Holds what the Qt ``H2mmTool`` keeps in its widgets and on itself: the burst folder, every setting that goes into
:class:`~..api.models.H2mmSettings`, the detector-to-stream assignment, and the result of the last fit
(``result``, ``bundle`` and the bootstrap ``uncertainty``). The actions run on a snapshot of this model through
:class:`chisurf.emtk.jobs.SnapshotJob`; the numerical work is the unchanged :func:`..backend.services.run_analysis`.

Nothing here imports Qt or emtk.
"""

from __future__ import annotations

import json
import pathlib
import threading
from typing import Any, Callable

from ..api.models import H2mmSettings, StreamSettings

#: Engines and decoders offered (same lists, same order as the Qt tool's combos).
ENGINES = [("Fast EM (float32)", "em-float32"), ("Exact EM (float64)", "em"), ("Neural surrogate", "neural")]
DECODERS = [("Viterbi", "viterbi"), ("Jitter", "jitter"), ("FFBS", "ffbs")]
CRITERIA = ["bic", "icl"]

#: Fields saved to and loaded from a settings file.
SETTING_FIELDS = (
    "donor_channels", "acceptor_channels", "aex_channels", "file_type", "min_states", "max_states", "criterion",
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
        # Channels per stream (routing channels, comma separated): the detector page of the Qt tool, as text.
        self.donor_channels: str = "0, 8"
        self.acceptor_channels: str = "1, 9"
        self.aex_channels: str = ""
        self.file_type: str = "SPC-130"
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

    def build_settings(self) -> H2mmSettings:
        """The backend settings these fields describe (what ``H2mmTool._gather_settings`` builds from its widgets)."""
        streams = [
            StreamSettings("donor", parse_channels(self.donor_channels), []),
            StreamSettings("acceptor", parse_channels(self.acceptor_channels), []),
        ]
        aex = parse_channels(self.aex_channels)
        if aex:
            streams.append(StreamSettings("aex", aex, []))
        return H2mmSettings(
            streams=streams,
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
        if not parse_channels(self.donor_channels) or not parse_channels(self.acceptor_channels):
            return "Give the donor and the acceptor routing channels."
        return ""

    # -- actions (run on a snapshot through SnapshotJob) ------------------------------------------------------ #
    def compute(self) -> None:
        """Fit every state count of the scan (the work of ``H2mmTool._fit_worker``); raises on a stop or an error."""
        from ..backend.services import run_analysis, write_result_tables

        problem = self.can_run()
        if problem:
            raise ValueError(problem)
        self._cancel.clear()
        settings = self.build_settings()

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
        self.result, self.bundle, self.uncertainty = result, bundle, None
        seed = (result.settings_applied or {}).get("seed")
        self.status_text = (
            f"Selected {result.n_states} states ({result.criterion.upper()}) from {result.n_bursts} bursts / "
            f"{result.n_photons} photons" + (f" (seed {seed})" if seed is not None else "")
        )
        if result.posterior_populations:
            self.status_text += " - occupancy " + ", ".join(f"{x:.3f}" for x in result.posterior_populations)
        self.notify("result")

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
