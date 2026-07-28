"""Qt-free view-model for the hidden-Markov-model tool.

Holds the trace files and settings edited through ``hmm.view.json``, runs the
Qt-free core (:mod:`...core.analysis`) and exposes the result as plot series
and HTML tables for the AutoForm view. No Qt imports: the heavy :meth:`run` is
driven from a background thread by the tool.
"""

from __future__ import annotations

import json
import logging
import pathlib

import numpy as np

from ..api.models import HmmSettings
from ..cli.main import load_trace
from ..core.analysis import fit_traces, scan_state_counts, state_segments

logger = logging.getLogger(__name__)

_VIEW_JSON = pathlib.Path(__file__).parent / "hmm.view.json"

#: Colours cycled over the states, dimmest first. Distinguishable in both
#: themes and colour-blind safe (Okabe-Ito, reordered dark to light).
STATE_COLORS = (
    "#0072B2", "#E69F00", "#009E73", "#D55E00",
    "#CC79A7", "#56B4E9", "#F0E442", "#999999",
)


def state_color(index: int) -> str:
    """Return the plot colour of state ``index``, cycling if there are many."""
    return STATE_COLORS[int(index) % len(STATE_COLORS)]


class HmmViewModel:
    """State and logic of the HMM tool (no Qt)."""

    def __init__(self) -> None:
        self._observers: list = []
        self.files: list[str] = []
        self.settings = HmmSettings()
        self.min_states = 1
        self.max_states = 6
        #: Bins shown in the trace plot; a long trace is decimated to this many
        #: points, since more than that cannot be resolved on screen anyway.
        self.max_points = 5000
        self._traces: list[np.ndarray] = []
        self._labels: list[str] = []
        self._fit = None
        self._scan = None
        self._status = "Load one or more traces, then fit."

    # -- observer ------------------------------------------------------------

    def add_observer(self, callback) -> None:
        """Register ``callback(event)``, called on every state change."""
        self._observers.append(callback)

    def notify(self, event: str = "changed") -> None:
        """Notify observers that the state changed."""
        for callback in list(self._observers):
            try:
                callback(event)
            except Exception:  # pragma: no cover - observer is caller-defined
                logger.debug("HMM view-model observer failed", exc_info=True)

    def view_spec(self):
        """Return the parsed AutoForm view spec authored in ``hmm.view.json``."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(json.loads(_VIEW_JSON.read_text()))

    # -- edited properties ---------------------------------------------------

    @property
    def sel_files(self) -> list:
        """Selected trace files (bound to the ``path_list`` section)."""
        return self.files

    @sel_files.setter
    def sel_files(self, value) -> None:
        self.files = [str(v) for v in (value or [])]
        self._traces, self._labels = [], []
        self._fit = self._scan = None
        self.notify()

    @property
    def n_states(self) -> int:
        """Number of states to fit."""
        return self.settings.n_states

    @n_states.setter
    def n_states(self, value) -> None:
        self.settings.n_states = max(1, int(value))
        self.notify()

    @property
    def covariance_type(self) -> str:
        """Emission covariance parameterisation."""
        return self.settings.covariance_type

    @covariance_type.setter
    def covariance_type(self, value) -> None:
        self.settings.covariance_type = str(value)
        self.notify()

    @property
    def time_step(self) -> float:
        """Duration of one time bin, in seconds."""
        return self.settings.time_step

    @time_step.setter
    def time_step(self, value) -> None:
        self.settings.time_step = max(float(value), 1e-12)
        self.notify()

    @property
    def n_iter(self) -> int:
        """Maximum number of EM maps."""
        return self.settings.n_iter

    @n_iter.setter
    def n_iter(self, value) -> None:
        self.settings.n_iter = max(1, int(value))
        self.notify()

    @property
    def tol(self) -> float:
        """Log-likelihood convergence threshold."""
        return self.settings.tol

    @tol.setter
    def tol(self, value) -> None:
        self.settings.tol = float(value)
        self.notify()

    @property
    def accelerate(self) -> bool:
        """Whether SQUAREM extrapolation accelerates EM."""
        return self.settings.accelerate

    @accelerate.setter
    def accelerate(self, value) -> None:
        self.settings.accelerate = bool(value)
        self.notify()

    @property
    def decode(self) -> str:
        """Decoder: the most probable path, or the most probable state per bin."""
        return self.settings.decode

    @decode.setter
    def decode(self, value) -> None:
        self.settings.decode = str(value)
        self.notify()

    @property
    def random_state(self) -> int:
        """Seed of the initialisation, so a fit is reproducible."""
        return self.settings.random_state

    @random_state.setter
    def random_state(self, value) -> None:
        self.settings.random_state = int(value)
        self.notify()

    # -- data ----------------------------------------------------------------

    def set_traces(self, traces, labels=None) -> None:
        """Set the traces to analyse directly, bypassing the file list.

        The seam other plugins use: a tool that already has a binned trace in
        memory (an intensity trace, a FRET-efficiency series) hands it over
        instead of writing a file.

        Parameters
        ----------
        traces : sequence of array-like
            One or more ``(n_bins, n_channels)`` traces.
        labels : sequence of str, optional
            Display names, parallel to ``traces``.
        """
        self._traces = [np.atleast_2d(np.asarray(t, dtype=float)) for t in traces]
        self._traces = [t.T if t.shape[0] == 1 and t.shape[1] > 1 else t for t in self._traces]
        self._labels = list(labels or [f"trace {i + 1}" for i in range(len(self._traces))])
        self._fit = self._scan = None
        self.notify()

    def load(self) -> None:
        """Read every selected file into memory (no fitting)."""
        traces, labels = [], []
        for path in self.files:
            try:
                traces.append(load_trace(path))
                labels.append(pathlib.Path(path).name)
            except Exception as exc:
                logger.warning("HMM: cannot read %s: %s", path, exc)
                self._status = f"Cannot read {pathlib.Path(path).name}: {exc}"
        self._traces, self._labels = traces, labels

    @property
    def traces(self) -> list[np.ndarray]:
        """The loaded traces, reading the selected files on first access."""
        if not self._traces and self.files:
            self.load()
        return self._traces

    # -- actions -------------------------------------------------------------

    def request_run(self) -> None:
        """Ask the host to run :meth:`run` on a background thread."""
        self.notify("start_run")

    def request_scan(self) -> None:
        """Ask the host to run :meth:`run_scan` on a background thread."""
        self.notify("start_scan")

    def run(self) -> None:
        """Fit the HMM to the loaded traces (blocking; call off the UI thread)."""
        if not self.traces:
            self._status = "No traces loaded."
            return
        try:
            self._fit = fit_traces(self.traces, self.settings)
            fit = self._fit
            self._status = (
                f"{fit.n_states} states · log L = {fit.log_likelihood:,.1f} · "
                f"BIC = {fit.bic:,.1f} · {fit.n_iterations} iterations"
                + ("" if fit.converged else " · did not converge")
            )
        except Exception as exc:
            logger.exception("HMM fit failed")
            self._fit = None
            self._status = f"Fit failed: {exc}"

    def run_scan(self) -> None:
        """Score the state-count range (blocking; call off the UI thread)."""
        if not self.traces:
            self._status = "No traces loaded."
            return
        try:
            self._scan = scan_state_counts(
                self.traces, self.settings, self.min_states, self.max_states
            )
            self._status = (
                f"BIC prefers {self._scan.best_bic} states, AIC {self._scan.best_aic}."
            )
        except Exception as exc:
            logger.exception("HMM state scan failed")
            self._scan = None
            self._status = f"Scan failed: {exc}"

    @property
    def fit(self):
        """The last :class:`...api.models.HmmFit`, or ``None``."""
        return self._fit

    def save_result(self, path: str) -> None:
        """Write the last fit to ``path`` as JSON."""
        if self._fit is None:
            raise RuntimeError("nothing to save: run a fit first")
        pathlib.Path(path).write_text(json.dumps(self._fit.to_dict(), indent=2))

    # -- view sources --------------------------------------------------------

    def info_html(self) -> str:
        """One-line status shown above the controls."""
        return f"<b>Hidden Markov model</b><br/>{self._status}"

    def _decimate(self, values: np.ndarray):
        """Return ``(index, values)`` thinned to at most :attr:`max_points`."""
        step = max(1, len(values) // max(self.max_points, 1))
        index = np.arange(0, len(values), step)
        return index, values[::step]

    def trace_series(self) -> list[dict]:
        """Series for the trace plot: the data, and the decoded state path over it."""
        traces = self._traces
        if not traces:
            return []
        data = np.concatenate(traces)
        series = []
        for channel in range(data.shape[1]):
            index, values = self._decimate(data[:, channel])
            series.append(
                {
                    "x": index * self.settings.time_step,
                    "y": values,
                    "name": f"channel {channel + 1}",
                    "color": "#888888" if data.shape[1] == 1 else state_color(channel),
                    "width": 1,
                }
            )
        if self._fit is not None:
            # The model's own view of the trace: each bin drawn at the total
            # emission mean of the state it was decoded into.
            means = np.asarray(self._fit.means).sum(axis=1)
            path = means[self._fit.state_array]
            index, values = self._decimate(path)
            series.append(
                {
                    "x": index * self.settings.time_step,
                    "y": values,
                    "name": "state path",
                    "color": "#D55E00",
                    "width": 2,
                }
            )
        return series

    def histogram_series(self) -> list[dict]:
        """Series for the intensity histogram with the fitted emissions over it."""
        traces = self._traces
        if not traces:
            return []
        total = np.concatenate(traces).sum(axis=1)
        counts, edges = np.histogram(total, bins=min(200, max(20, len(total) // 50)))
        centres = 0.5 * (edges[:-1] + edges[1:])
        series = [
            {"x": centres, "y": counts, "name": "counts", "color": "#888888", "width": 1}
        ]
        if self._fit is not None:
            width = edges[1] - edges[0]
            for summary in self._fit.summaries:
                # Total-intensity projection: means add, variances add.
                mean = float(np.sum(summary.mean))
                sigma = float(np.sqrt(np.sum(np.square(summary.std))))
                if sigma <= 0:
                    continue
                density = np.exp(-0.5 * ((centres - mean) / sigma) ** 2) / (
                    sigma * np.sqrt(2 * np.pi)
                )
                series.append(
                    {
                        "x": centres,
                        "y": density * summary.occupancy * len(total) * width,
                        "name": f"state {summary.index}",
                        "color": state_color(summary.index),
                        "width": 2,
                    }
                )
        return series

    def dwell_series(self) -> list[dict]:
        """Series for the dwell-time histogram, one curve per state."""
        if self._fit is None:
            return []
        series = []
        for index, durations in enumerate(self._fit.dwell_times):
            if len(durations) < 2:
                continue
            counts, edges = np.histogram(durations, bins=min(40, max(5, len(durations) // 5)))
            centres = 0.5 * (edges[:-1] + edges[1:])
            series.append(
                {
                    "x": centres,
                    "y": counts,
                    "name": f"state {index}",
                    "color": state_color(index),
                    "width": 2,
                    "symbol": "o",
                    "symbol_size": 6,
                }
            )
        return series

    def scan_series(self) -> list[dict]:
        """Series for the state-count scan: BIC and AIC against state count."""
        if self._scan is None:
            return []
        counts = np.asarray(self._scan.n_states, dtype=float)
        return [
            {
                "x": counts,
                "y": np.asarray(values, dtype=float),
                "name": name,
                "color": color,
                "width": 2,
                "symbol": "o",
                "symbol_size": 8,
            }
            for name, values, color in (
                ("BIC", self._scan.bic, "#0072B2"),
                ("AIC", self._scan.aic, "#E69F00"),
            )
        ]

    def states_html(self) -> str:
        """Per-state table: emission mean, width, occupancy and dwell time."""
        if self._fit is None:
            return "<i>No fit yet.</i>"
        unit = "s" if self.settings.time_step != 1.0 else "bins"
        # Short headers: the panel is narrow, and a wrapped header reads worse
        # than an abbreviation whose meaning the tooltip carries.
        rows = [
            "<tr><th>state</th><th>mean</th><th>std</th>"
            f"<th>occ.</th><th>visits</th><th>dwell ({unit})</th></tr>"
        ]
        for summary in self._fit.summaries:
            colour = state_color(summary.index)
            mean = ", ".join(f"{v:.3g}" for v in summary.mean)
            std = ", ".join(f"{v:.3g}" for v in summary.std)
            rows.append(
                f"<tr><td><span style='color:{colour}'>&#9632;</span> {summary.index}</td>"
                f"<td>{mean}</td><td>{std}</td><td>{summary.occupancy:.3f}</td>"
                f"<td>{summary.n_dwells}</td><td>{summary.mean_dwell:.4g}</td></tr>"
            )
        return "<table width='100%' cellspacing='4'>" + "".join(rows) + "</table>"

    def transitions_html(self) -> str:
        """Transition-matrix table, with rates when a time step is set."""
        if self._fit is None:
            return "<i>No fit yet.</i>"
        transmat = np.asarray(self._fit.transmat)
        rates = np.asarray(self._fit.transition_rates)
        show_rates = self.settings.time_step != 1.0
        header = "".join(f"<th>&rarr; {j}</th>" for j in range(len(transmat)))
        rows = [f"<tr><th>from \\ to</th>{header}</tr>"]
        for i, row in enumerate(transmat):
            cells = []
            for j, probability in enumerate(row):
                text = f"{probability:.4f}"
                if show_rates and i != j:
                    text += f"<br/><small>{rates[i, j]:.3g} s<sup>-1</sup></small>"
                # Shade by probability so the sticky diagonal reads at a glance.
                shade = int(255 - 120 * min(float(probability), 1.0))
                cells.append(
                    f"<td align='center' bgcolor='#{shade:02x}{shade:02x}{shade:02x}'>{text}</td>"
                )
            rows.append(f"<tr><th>{i}</th>{''.join(cells)}</tr>")
        return "<table width='100%' cellspacing='2'>" + "".join(rows) + "</table>"
