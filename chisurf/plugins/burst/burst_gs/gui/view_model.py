"""Qt-free view-model behind the Gopich-Szabo tool.

Holds the settings the AutoForm binds to, runs the Qt-free analysis from
:mod:`chisurf.plugins.burst.burst_gs.core`, and exposes the tables, plot series
and report text that ``burst_gs.view.json`` reads.
"""

from __future__ import annotations

import logging
from concurrent.futures import CancelledError
import pathlib
from collections.abc import Callable

import numpy as np

from .. import core as _core

logger = logging.getLogger(__name__)

_VIEW_JSON = pathlib.Path(__file__).parent / "burst_gs.view.json"


class BurstGsViewModel:
    """State and logic of the photon-by-photon kinetics tool (no Qt)."""

    def __init__(self) -> None:
        #: The authored view spec (also the anchor for view-relative resources).
        self._view_json = _VIEW_JSON

        # ── data source ──
        self.bur_files: list[str] = []
        self.data_dir: str = ""
        self.file_type: str = "auto"
        self.donor_channels: str = "0, 8"
        self.acceptor_channels: str = "1, 9"
        self.macro_time_resolution_ns: float = 0.0
        self.min_photons: int = 10
        self.max_bursts: int = 0

        # ── simulation (so the tool is usable and testable with no files) ──
        self.use_simulation: bool = False
        self.sim_k_forward: float = 3000.0
        self.sim_k_backward: float = 1000.0
        self.sim_e1: float = 0.25
        self.sim_e2: float = 0.75
        self.sim_photon_rate_khz: float = 50.0
        self.sim_n_bursts: int = 200
        self.sim_photons_per_burst: int = 200
        self.sim_seed: int = 1

        # ── model ──
        self.n_states: int = 2
        self.initial_rate: float = 1000.0
        self.fix_efficiencies: bool = False
        self.method: str = "nelder-mead"
        self.max_iterations: int = 2000

        # ── extras ──
        self.scan_transition_time: bool = False
        self.transit_points: int = 40
        self.decode_states: bool = False
        self.cross_check_h2mm: bool = False

        # ── runtime ──
        self._bursts = None
        self._analysis: _core.GsAnalysis | None = None
        self.results_text: str = (
            "Drop .bur burst tables (or tick Simulate) and press Fit.\n\n"
            "This fits kinetic rates directly to the arrival time and colour of "
            "every photon, so it resolves exchange faster than any bin."
        )
        self._observers: list[Callable[[str], None]] = []

    # ── observer hook ──
    def add_observer(self, cb: Callable[[str], None]) -> None:
        """Register *cb* to be called with an event name on every change."""
        self._observers.append(cb)

    def notify(self, event: str = "changed") -> None:
        """Notify observers that the state changed."""
        for cb in list(self._observers):
            try:
                cb(event)
            except Exception:
                logger.debug("burst-GS observer failed", exc_info=True)

    def view_spec(self):
        """Resolve the AutoForm view spec from the authored view.json."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_VIEW_JSON)

    # ── choices ──
    @property
    def method_options(self) -> list[str]:
        """Optimisers offered in the form."""
        return ["nelder-mead", "l-bfgs-b"]

    @property
    def file_type_options(self) -> list[str]:
        """TTTR container types offered in the form."""
        return ["auto", "SPC-130", "SPC-600_256", "PTU", "HT3", "HDF"]

    # ── results ──
    @property
    def analysis(self) -> _core.GsAnalysis | None:
        """The most recent analysis, if any."""
        return self._analysis

    def can_run(self) -> str:
        """Return why a run is not possible, or an empty string when it is."""
        if self.use_simulation:
            return ""
        if not self.bur_files:
            return "Add at least one .bur burst table, or tick Simulate."
        if int(self.n_states) < 2:
            return "A kinetic fit needs at least two states."
        return ""

    def _parse_channels(self, text: str) -> list[int]:
        """Parse a comma-separated channel list, ignoring anything unparsable."""
        out: list[int] = []
        for part in str(text or "").replace(";", ",").split(","):
            part = part.strip()
            if not part:
                continue
            try:
                out.append(int(part))
            except ValueError:
                continue
        return out

    def load(self) -> str:
        """Load (or simulate) the photons, returning a status message."""
        if self.use_simulation:
            self._bursts = _core.simulate_two_state(
                k_forward=float(self.sim_k_forward),
                k_backward=float(self.sim_k_backward),
                efficiencies=(float(self.sim_e1), float(self.sim_e2)),
                photon_rate=float(self.sim_photon_rate_khz) * 1e3,
                n_bursts=int(self.sim_n_bursts),
                photons_per_burst=int(self.sim_photons_per_burst),
                seed=int(self.sim_seed),
            )
            self._info = {
                "source": "simulation",
                "n_bursts": len(self._bursts),
                "n_photons": self._bursts.n_photons,
                "true_k_forward": float(self.sim_k_forward),
                "true_k_backward": float(self.sim_k_backward),
                "true_efficiencies": [float(self.sim_e1), float(self.sim_e2)],
            }
            return f"Simulated {len(self._bursts)} bursts, {self._bursts.n_photons:,} photons."

        streams = [
            {"name": "donor", "channels": self._parse_channels(self.donor_channels)},
            {"name": "acceptor", "channels": self._parse_channels(self.acceptor_channels)},
        ]
        data_dir = self.data_dir or str(pathlib.Path(self.bur_files[0]).parent)
        resolution = float(self.macro_time_resolution_ns) * 1e-9
        self._bursts, self._info = _core.load_photons(
            self.bur_files,
            data_dir,
            streams=streams,
            file_type=self.file_type,
            macro_time_resolution=resolution if resolution > 0 else None,
            min_photons=int(self.min_photons),
            max_bursts=int(self.max_bursts),
        )
        return (
            f"Loaded {self._info['n_bursts']} bursts, "
            f"{self._info['n_photons']:,} photons "
            f"({self._info['photons_per_stream'][0]:,} donor, "
            f"{self._info['photons_per_stream'][1]:,} acceptor)."
        )

    def compute(self, progress: Callable[[float, str], None] | None = None) -> bool:
        """Load and fit; returns whether an analysis was produced."""
        try:
            message = self.load()
        except Exception as exc:
            logger.debug("loading photons failed", exc_info=True)
            self._analysis = None
            self.results_text = f"Could not load the photons: {exc}"
            self.notify("computed")
            return False

        if progress is not None:
            progress(0.01, message)
        try:
            n = int(self.n_states)
            self._analysis = _core.analyse(
                self._bursts,
                n_states=n,
                initial_rates=np.full(n * (n - 1), float(self.initial_rate)),
                initial_efficiencies=np.linspace(0.2, 0.8, n),
                fix_efficiencies=bool(self.fix_efficiencies),
                method=str(self.method),
                max_iterations=int(self.max_iterations),
                scan_transition_time=bool(self.scan_transition_time),
                transit_points=int(self.transit_points),
                decode_states=bool(self.decode_states),
                cross_check_h2mm=bool(self.cross_check_h2mm),
                info=self._info,
                progress=progress,
            )
        except CancelledError:
            # The user pressed Cancel: the progress callback raised through the
            # fit. Let it out rather than reporting it as a failure -- a
            # cancelled run has no result *and* nothing went wrong.
            self._analysis = None
            self.notify("computed")
            raise
        except Exception as exc:
            logger.debug("the Gopich-Szabo fit failed", exc_info=True)
            self._analysis = None
            self.results_text = f"The fit failed: {exc}"
            self.notify("computed")
            return False

        self.results_text = self._analysis.report()
        self.notify("computed")
        return True

    # ── view sources ──
    def results_html(self) -> str:
        """Return the report as pre-formatted HTML for the ``info`` section.

        A method, not a property: ``InfoWidget`` only calls a source it finds
        callable and silently falls back to empty text otherwise.
        """
        import html

        return f"<pre style='margin:0'>{html.escape(self.results_text)}</pre>"

    def rate_rows(self) -> list[dict]:
        """Rows of the fitted-rate table."""
        if self._analysis is None:
            return []
        matrix = self._analysis.fit.rate_matrix
        n = matrix.shape[0]
        rows: list[dict] = []
        for source in range(n):
            for target in range(n):
                if source == target:
                    continue
                rate = float(matrix[target, source])
                rows.append(
                    {
                        "transition": f"{source + 1} → {target + 1}",
                        "rate": f"{rate:,.1f}",
                        "time": f"{1e6 / rate:,.2f}" if rate > 0 else "—",
                    }
                )
        return rows

    def state_rows(self) -> list[dict]:
        """Rows of the per-state table (efficiency and equilibrium population)."""
        if self._analysis is None:
            return []
        from chisurf.core.fluorescence.kinetics import equilibrium_populations

        fit = self._analysis.fit
        populations = equilibrium_populations(fit.rate_matrix)
        rows: list[dict] = []
        for i, efficiency in enumerate(np.atleast_1d(fit.efficiencies)):
            rows.append(
                {
                    "state": str(i + 1),
                    "efficiency": f"{float(efficiency):.4f}",
                    "population": f"{float(populations[i]):.4f}",
                }
            )
        return rows

    def transit_series(self) -> list[dict]:
        """Plot series for the transition-time scan."""
        if self._analysis is None or self._analysis.transit_times.size == 0:
            return []
        times = np.asarray(self._analysis.transit_times, dtype=float) * 1e6
        delta = np.asarray(self._analysis.transit_delta, dtype=float)
        series = [
            {
                "x": times.tolist(),
                "y": delta.tolist(),
                "name": "finite transition",
                "color": "#4c9be8",
                "width": 2,
                "symbol": "o",
                "symbol_size": 5,
            },
            {
                # The instantaneous model is the baseline the scan is measured
                # against, so it is a horizontal line at exactly zero.
                "x": [float(times.min()), float(times.max())],
                "y": [0.0, 0.0],
                "name": "instantaneous",
                "color": "#c0c0c0",
                "width": 1,
            },
        ]
        return series

    def efficiency_series(self) -> list[dict]:
        """Plot series showing the fitted states on the efficiency axis."""
        if self._analysis is None:
            return []
        from chisurf.core.fluorescence.kinetics import equilibrium_populations

        fit = self._analysis.fit
        efficiencies = np.atleast_1d(np.asarray(fit.efficiencies, dtype=float))
        if efficiencies.size == 0:
            return []
        populations = equilibrium_populations(fit.rate_matrix)
        colors = ["#4c9be8", "#e8734c", "#4ce88a", "#c04ce8", "#e8d24c"]
        out: list[dict] = []
        for i, (efficiency, population) in enumerate(zip(efficiencies, populations)):
            out.append(
                {
                    "x": [float(efficiency), float(efficiency)],
                    "y": [0.0, float(population)],
                    "name": f"state {i + 1}",
                    "color": colors[i % len(colors)],
                    "width": 4,
                }
            )
        return out

    def export_csv(self, path: str) -> None:
        """Write the fitted parameters (and any scan) to a CSV file.

        Parameters
        ----------
        path : str
            Destination file.
        """
        if self._analysis is None:
            raise ValueError("run a fit before exporting")
        lines = ["quantity,value"]
        matrix = self._analysis.fit.rate_matrix
        n = matrix.shape[0]
        for source in range(n):
            for target in range(n):
                if source != target:
                    lines.append(f"k_{source + 1}{target + 1}_per_s,{matrix[target, source]:.6g}")
        for i, efficiency in enumerate(np.atleast_1d(self._analysis.fit.efficiencies)):
            lines.append(f"E_{i + 1},{float(efficiency):.6g}")
        lines.append(f"log_likelihood,{self._analysis.fit.log_likelihood:.6g}")
        lines.append(f"bic,{self._analysis.fit.bic:.6g}")
        lines.append(f"n_photons,{self._analysis.fit.n_photons}")
        lines.append(f"n_bursts,{self._analysis.fit.n_bursts}")
        if self._analysis.transit_times.size:
            lines.append("")
            lines.append("transit_time_s,delta_log_likelihood")
            for t, d in zip(self._analysis.transit_times, self._analysis.transit_delta):
                lines.append(f"{t:.6g},{d:.6g}")
        pathlib.Path(path).write_text("\n".join(lines) + "\n")


__all__ = ["BurstGsViewModel"]
