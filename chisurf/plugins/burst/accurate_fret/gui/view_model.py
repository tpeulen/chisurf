"""Qt-free view-model behind the accurate-FRET tool.

Holds the settings the AutoForm binds to, runs the Qt-free calibration from
:mod:`chisurf.plugins.burst.accurate_fret.core`, and exposes the tables and plot
series that ``accurate_fret.view.json`` reads.
"""

from __future__ import annotations

import logging
import pathlib
from collections.abc import Callable

import numpy as np

from .. import core as _core

logger = logging.getLogger(__name__)

_VIEW_JSON = pathlib.Path(__file__).parent / "accurate_fret.view.json"

#: Colour per burst class in the E-S / E-tau scatter plots.
_CLASS_STYLE = {
    -2: ("acceptor-only", "#ff9040"),
    -1: ("donor-only", "#40c060"),
    0: ("FRET 0", "#4488ff"),
    1: ("FRET 1", "#cc55cc"),
    2: ("FRET 2", "#22cccc"),
    3: ("FRET 3", "#cccc22"),
}


class AccurateFretViewModel:
    """State and logic of the accurate-FRET calibration tool (no Qt)."""

    def __init__(self) -> None:
        #: The authored view spec (also the anchor for view-relative resources).
        self._view_json = _VIEW_JSON
        # ── data source ──
        self.filename: str = ""
        self.column_i_dd: str = ""
        self.column_i_da: str = ""
        self.column_i_aa: str = ""
        self.column_tau_f: str = ""
        # ── photophysics / instrument ──
        self.donor_lifetime: float = 4.0
        self.forster_radius: float = 52.0
        self.linker_sigma: float = 6.0
        self.background_dd: float = 0.0
        self.background_da: float = 0.0
        self.background_aa: float = 0.0
        # ── procedure ──
        self.gamma_source: str = "auto"
        self.use_priors: bool = True
        self.lightpath_name: str = ""
        self.quantum_yield_donor: float = 1.0
        self.quantum_yield_acceptor: float = 1.0
        self.detection_green: float = 1.0
        self.detection_red: float = 1.0
        self.max_fret_populations: int = 3
        self.min_population: int = 20
        self.n_bootstrap: int = 50
        self.show_dynamic_line: bool = True
        self.max_points: int = 5000
        # ── runtime ──
        self._columns: dict[str, np.ndarray] = {}
        self._result: _core.CalibrationResult | None = None
        self._lightpaths: list[dict] = []
        self.results_text: str = (
            "Load a burst table (or drop one), map the channel columns and press Calibrate."
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
                logger.debug("accurate-FRET observer failed", exc_info=True)

    def view_spec(self):
        """Resolve the AutoForm view spec from the authored view.json."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_VIEW_JSON)

    # ── data source ──
    def set_filename(self, path: str) -> None:
        """Load a burst table and auto-map its channel columns.

        Parameters
        ----------
        path : str
            Burst table (delimited text or ``.npz``).
        """
        path = str(path or "")
        if not path:
            return
        self.filename = path
        try:
            self._columns = _core.read_burst_table(path)
        except Exception as exc:
            self._columns = {}
            self.results_text = f"Could not read {pathlib.Path(path).name}: {exc}"
            self.notify("error")
            return
        guess = _core.guess_columns(self._columns)
        self.column_i_dd = guess.get("i_dd", "")
        self.column_i_da = guess.get("i_da", "")
        self.column_i_aa = guess.get("i_aa", "")
        self.column_tau_f = guess.get("tau_f", "")
        self._result = None
        missing = [k for k in ("i_dd", "i_da") if k not in guess]
        self.results_text = (
            f"{pathlib.Path(path).name}: {len(next(iter(self._columns.values())))} bursts, "
            f"{len(self._columns)} columns."
            + (f" Please map {', '.join(missing)} by hand." if missing else " Press Calibrate.")
        )
        self.notify("file")

    def load_from_ndxplorer(self) -> str:
        """Take the burst columns from an open ndXplorer window.

        The usual workflow: bursts are already selected and plotted in ndXplorer,
        so the calibration should run on exactly those columns instead of a file
        exported in between.

        Returns
        -------
        str
            A status message.
        """
        try:
            from chisurf.plugins.ndxplorer.calibration_bridge import find_ndx_windows
        except Exception:
            return "ndXplorer is not available."
        windows = find_ndx_windows()
        if not windows:
            return "No open ndXplorer window found."
        data = getattr(getattr(windows[-1], "data_source", None), "data", None)
        if data is None:
            return "The ndXplorer window holds no burst data."
        columns: dict[str, np.ndarray] = {}
        for name in list(getattr(data, "columns", data.keys() if hasattr(data, "keys") else [])):
            try:
                values = np.asarray(data[name], dtype=float).ravel()
            except Exception:
                continue
            if values.size and np.any(np.isfinite(values)):
                columns[str(name)] = values
        if not columns:
            return "No numeric burst columns in the ndXplorer window."
        self._columns = columns
        self.filename = "<ndXplorer>"
        guess = _core.guess_columns(columns)
        self.column_i_dd = guess.get("i_dd", "")
        self.column_i_da = guess.get("i_da", "")
        self.column_i_aa = guess.get("i_aa", "")
        self.column_tau_f = guess.get("tau_f", "")
        self._result = None
        self.notify("file")
        return f"Loaded {len(next(iter(columns.values())))} bursts from ndXplorer."

    def column_names(self) -> list[str]:
        """Column names of the loaded table (for the column pickers)."""
        return ["", *self._columns.keys()]

    def lightpath_names(self) -> list[str]:
        """Names of the saved light paths usable as the optics prior."""
        if not self._lightpaths:
            self._lightpaths = _core.list_lightpaths()
        return ["", *[str(lp.get("name") or lp["operation_id"]) for lp in self._lightpaths]]

    def refresh_lightpaths(self) -> None:
        """Re-read the saved light paths from MMFDB."""
        self._lightpaths = _core.list_lightpaths()
        self.notify("changed")

    # ── the run ──
    def _channel(self, column: str):
        """Return the named column as an array, or None when unmapped."""
        if not column or column not in self._columns:
            return None
        return np.asarray(self._columns[column], dtype=float)

    def _lightpath_argument(self) -> dict | None:
        """Build the ``lightpath`` prior argument for the selected light path."""
        if not self.lightpath_name:
            return None
        entry = next(
            (lp for lp in self._lightpaths
             if str(lp.get("name") or lp["operation_id"]) == self.lightpath_name),
            None,
        )
        if entry is None:
            return None
        try:
            prior = _core.lightpath_prior(entry["operation_id"])
        except Exception as exc:
            logger.debug("light-path prior failed", exc_info=True)
            self.results_text = f"Light path could not be read: {exc}"
            return None
        prior["qy_d"] = float(self.quantum_yield_donor)
        prior["qy_a"] = float(self.quantum_yield_acceptor)
        prior["gG"] = float(self.detection_green)
        prior["gR"] = float(self.detection_red)
        return prior

    def can_run(self) -> str | None:
        """Return ``None`` when a calibration can run, else why it cannot."""
        if self._channel(self.column_i_dd) is None:
            return "The donor channel (I_DD) column is not mapped."
        if self._channel(self.column_i_da) is None:
            return "The FRET channel (I_DA) column is not mapped."
        return None

    def compute(self, progress: Callable[[float, str], None] | None = None) -> bool:
        """Run the automatic calibration on the mapped columns.

        Parameters
        ----------
        progress : callable, optional
            ``progress(fraction, text)`` callback for the host status bar.

        Returns
        -------
        bool
            True when a calibration was produced.
        """
        reason = self.can_run()
        if reason:
            self.results_text = reason
            self.notify("error")
            return False
        if progress:
            progress(0.1, "Reading columns")
        i_dd = self._channel(self.column_i_dd)
        i_da = self._channel(self.column_i_da)
        i_aa = self._channel(self.column_i_aa)
        tau_f = self._channel(self.column_tau_f)
        if progress:
            progress(0.3, "Calibrating")
        try:
            self._result = _core.calibrate(
                i_dd, i_da, i_aa, tau_f,
                donor_lifetime=self.donor_lifetime, forster_radius=self.forster_radius,
                linker_sigma=self.linker_sigma,
                background=(self.background_dd, self.background_da, self.background_aa),
                gamma_source=self.gamma_source, n_bootstrap=self.n_bootstrap,
                lightpath=self._lightpath_argument(), use_priors=self.use_priors,
                max_fret_populations=self.max_fret_populations,
                min_population=self.min_population,
            )
        except Exception as exc:
            logger.debug("calibration failed", exc_info=True)
            self._result = None
            self.results_text = f"Calibration failed: {exc}"
            self.notify("error")
            return False
        if progress:
            progress(1.0, "Done")
        self.results_text = self._result.calibration.report()
        self.notify("result")
        return True

    # ── tables / text ──
    def factor_rows(self) -> list[dict]:
        """Correction-factor table rows."""
        return self._result.factor_rows() if self._result else []

    def population_rows(self) -> list[dict]:
        """Return the population table rows."""
        return self._result.population_rows() if self._result else []

    def results_html(self) -> str:
        """Render the run report as pre-formatted HTML for the info panel."""
        text = (self.results_text or "").replace("&", "&amp;").replace("<", "&lt;")
        return f"<pre style='margin:0'>{text}</pre>"

    @property
    def result(self):
        """The last :class:`~..core.CalibrationResult` (or None)."""
        return self._result

    # ── plot series ──
    def _subsample(self, n: int) -> np.ndarray:
        """Return indices of at most ``max_points`` bursts, evenly spread over the data."""
        if n <= int(self.max_points):
            return np.arange(n)
        return np.linspace(0, n - 1, int(self.max_points)).astype(int)

    def _class_series(self, x, y, *, symbol_size: int = 4) -> list[dict]:
        """Split ``x``/``y`` into one scatter series per burst class."""
        result = self._result
        if result is None:
            return []
        idx = self._subsample(len(result.labels))
        labels = result.labels[idx]
        x, y = np.asarray(x)[idx], np.asarray(y)[idx]
        series = []
        for value in np.unique(labels):
            name, colour = _CLASS_STYLE.get(int(value), (f"population {value}", "#999999"))
            m = (labels == value) & np.isfinite(x) & np.isfinite(y)
            if not np.any(m):
                continue
            series.append({
                "x": x[m], "y": y[m], "name": name, "color": colour,
                "symbol": "o", "symbol_size": symbol_size, "no_line": True, "width": 0,
            })
        return series

    def es_series(self) -> list[dict]:
        """E-S scatter, one series per automatically found burst class."""
        result = self._result
        if result is None or result.stoichiometry is None:
            return []
        return self._class_series(result.efficiency, result.stoichiometry)

    def e_tau_series(self) -> list[dict]:
        """E vs donor-lifetime scatter with the static (and dynamic) FRET line."""
        result = self._result
        if result is None or result.tau_f is None:
            return []
        series = self._class_series(result.tau_f, result.efficiency)
        if result.line is not None:
            series.append({
                "x": result.line.tau_f, "y": result.line.efficiency,
                "name": "static FRET line", "color": "#ffffff", "width": 2,
            })
        if self.show_dynamic_line and result.dynamic_line is not None:
            series.append({
                "x": result.dynamic_line.tau_f, "y": result.dynamic_line.efficiency,
                "name": "dynamic FRET line", "color": "#ff5555", "width": 2, "style": "dash",
            })
        return series

    def efficiency_histogram(self) -> list[dict]:
        """Accurate-efficiency histogram of the doubly labelled bursts."""
        result = self._result
        if result is None:
            return []
        e = result.efficiency[result.labels >= 0]
        e = e[np.isfinite(e)]
        if e.size < 2:
            return []
        counts, edges = np.histogram(e, bins=60, range=(-0.1, 1.1))
        centres = 0.5 * (edges[1:] + edges[:-1])
        return [{"x": centres, "y": counts.astype(float), "name": "accurate E",
                 "color": "#4488ff", "width": 2}]

    # ── session / export ──
    def register_in_session(self) -> str:
        """Publish the calibration as a session-wide, linkable pseudo-fit.

        Makes the factors available as link targets for every other fit, so one
        calibration can be shared across datasets (global analysis).

        Returns
        -------
        str
            A status message.
        """
        if self._result is None:
            return "Nothing to register — run a calibration first."
        from chisurf.core.fluorescence.fret.calibration import register_calibration

        register_calibration(self._result.calibration.calibration, name="Calibration")
        return "Calibration registered in the session (linkable from any fit)."

    def push_to_ndxplorer(self) -> str:
        """Push the posterior factors into an open ndXplorer window.

        Returns
        -------
        str
            A status message.
        """
        if self._result is None:
            return "Nothing to push — run a calibration first."
        try:
            from chisurf.plugins.ndxplorer.calibration_bridge import (
                find_ndx_windows,
                push_calibration_to_ndx,
            )
        except Exception:
            return "ndXplorer is not available."
        windows = find_ndx_windows()
        if not windows:
            return "No open ndXplorer window found."
        for window in windows:
            mapping = push_calibration_to_ndx(window, self._result.calibration.calibration)
        return f"Pushed {len(mapping)} constants to {len(windows)} ndXplorer window(s)."

    def export_csv(self, path: str) -> None:
        """Write the per-burst accurate values (with the calibration header) to *path*."""
        if self._result is None:
            raise ValueError("There is nothing to export.")
        _core.export_csv(path, self._result)
