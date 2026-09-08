"""Qt-free view-model behind the accurate-FRET tool.

Holds the settings the AutoForm binds to, runs the Qt-free calibration from
:mod:`chisurf.plugins.burst.accurate_fret.core`, and exposes the tables and plot
series that ``accurate_fret.view.json`` reads.
"""

from __future__ import annotations

import logging
from concurrent.futures import CancelledError
import pathlib
from collections.abc import Callable

import numpy as np

from chisurf.core.datastore import column_names

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
        # ── the setup and the dyes: where the photophysics comes from ──
        self.setup_name: str = ""
        self.donor_dye: str = ""
        self.acceptor_dye: str = ""
        self.kappa2: float = 2.0 / 3.0
        self.refractive_index: float = 1.33
        #: ``{window: {...}}`` of the selected detector setup (empty = raw channels).
        self.detectors: dict[str, dict] = {}
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
        self._dyes: list = []
        self._dye_pair = None
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
        self._map_columns()
        self._result = None
        missing = [k for k in ("i_dd", "i_da")
                   if not getattr(self, f"column_{k}")]
        head = (
            f"{pathlib.Path(path).name}: "
            f"{len(next(iter(self._columns.values())))} bursts, "
            f"{len(self._columns)} columns."
        )
        if not missing:
            self.results_text = head + " Press Calibrate."
        elif not self._has_detector_columns():
            # Distinguish "I could not guess the names" from "the numbers are
            # not in this table": no hand-mapping can fix the second, and
            # telling someone to map a column that does not exist sends them
            # looking through a combo box that cannot contain the answer.
            self.results_text = (
                head + " This burst search has **no per-detector columns** — it "
                "was run without detector definitions, so there is no donor or "
                "acceptor signal in it to map. Set the detectors in the setup "
                "step and search again, or pick a burst table that has them."
            )
        else:
            self.results_text = head + f" Please map {', '.join(missing)} by hand."
        self.notify("file")

    def _has_detector_columns(self) -> bool:
        """Whether the loaded table splits its photons by detector at all."""
        from chisurf.core.fluorescence.burst.table import DETECTOR_ROLE_WORDS

        words = tuple(DETECTOR_ROLE_WORDS)
        return any(
            any(word in str(name).lower() for word in words)
            for name in self._columns
        )

    def load_from_ndxplorer(self) -> str:
        """Take the burst columns from an open ndX window.

        The usual workflow: bursts are already selected and plotted in ndX,
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
            return "ndX is not available."
        windows = find_ndx_windows()
        if not windows:
            return "No open ndX window found."
        data = getattr(getattr(windows[-1], "data_source", None), "data", None)
        if data is None:
            return "The ndX window holds no burst data."
        columns: dict[str, np.ndarray] = {}
        for name in column_names(data):
            try:
                values = np.asarray(data[name], dtype=float).ravel()
            except Exception:
                continue
            if values.size and np.any(np.isfinite(values)):
                columns[str(name)] = values
        if not columns:
            return "No numeric burst columns in the ndX window."
        self._columns = columns
        self.filename = "<ndX>"
        self._map_columns()
        self._result = None
        self.notify("file")
        return f"Loaded {len(next(iter(columns.values())))} bursts from ndX."

    def column_names(self) -> list[str]:
        """Column names of the loaded table (for the column pickers)."""
        return ["", *self._columns.keys()]

    # ── the setup: which detection windows exist ──
    def apply_setup_settings(self, payload: dict) -> None:
        """Adopt a detector setup's named windows.

        The shared setup hook. Its windows say which detection channels the
        measurement has, which is used twice: their names help recognise the
        burst-table columns (a table written with site-specific channel names
        still maps itself), and they name the detectors when the optical model
        supplies the calibration prior.

        Parameters
        ----------
        payload : dict
            ``{"name": <setup>, "detectors": {...}}`` from the setup picker.
        """
        self.detectors = dict((payload or {}).get("detectors") or {})
        self.setup_name = str((payload or {}).get("name") or "")
        self.load_calibration_from_setup()
        if self._columns:
            self._map_columns()
        self.notify("setup")

    def load_calibration_from_setup(self) -> bool:
        """Seed the photophysics fields from the setup's stored calibration.

        A correction factor belongs to the instrument, so once a setup has been
        calibrated every later session on that setup should start from the
        measured numbers rather than the defaults. Only the fields this tool
        owns are seeded — the factors themselves are what the run determines.

        Returns
        -------
        bool
            Whether the setup carried a calibration.
        """
        if not self.setup_name:
            return False
        from chisurf.core.data_io.detector_setups import get_setup_calibration

        values = (get_setup_calibration(self.setup_name) or {}).get("values") or {}
        if not values:
            return False
        for key, attr in (("r0", "forster_radius"), ("bg_dd", "background_dd"),
                          ("bg_da", "background_da"), ("bg_aa", "background_aa"),
                          ("phi_d", "quantum_yield_donor"),
                          ("phi_a", "quantum_yield_acceptor")):
            value = values.get(key)
            if value is not None and np.isfinite(float(value)):
                setattr(self, attr, float(value))
        return True

    def save_calibration_to_setup(self) -> str:
        """Store the calibration just determined on the selected detector setup.

        The hand-off to every other tool: burst analysis, PDA and the filter
        calculator all pick a detector setup already, and can read the factors
        back with
        :func:`chisurf.core.data_io.detector_setups.get_setup_calibration`.

        Returns
        -------
        str
            A status message.
        """
        if self._result is None:
            return "Nothing to store — run a calibration first."
        if not self.setup_name:
            return "Pick a detector setup first — the calibration is stored on it."
        from chisurf.core.data_io.detector_setups import set_setup_calibration
        from chisurf.core.fluorescence.fret.calibration import calibration_to_setup

        payload = calibration_to_setup(
            self._result.calibration.calibration,
            uncertainties=getattr(self._result.calibration, "uncertainties", None),
        )
        if not set_setup_calibration(self.setup_name, payload):
            return f"No detector setup named {self.setup_name!r} to store the calibration on."
        return f"Calibration stored on setup {self.setup_name!r}; other tools read it from there."

    def _window_hints(self) -> dict:
        """Column-name fragments per channel role, from the setup's windows.

        A window called ``green`` marks the donor channel, ``red`` the FRET
        channel and ``yellow`` the acceptor-excitation channel — the convention
        the detector setups use.
        """
        keywords = {
            "i_dd": ("green", "donor"),
            "i_da": ("red", "acceptor", "fret"),
            "i_aa": ("yellow", "delayed"),
        }
        hints: dict[str, list[str]] = {}
        for window in self.detectors:
            low = str(window).strip().lower()
            for role, words in keywords.items():
                if any(word in low for word in words):
                    hints.setdefault(role, []).append(low)
                    break
        return hints

    def _map_columns(self) -> None:
        """Fill the four channel combos from the loaded columns."""
        guess = _core.guess_columns(self._columns, self._window_hints())
        self.column_i_dd = guess.get("i_dd", "")
        self.column_i_da = guess.get("i_da", "")
        self.column_i_aa = guess.get("i_aa", "")
        self.column_tau_f = guess.get("tau_f", "")

    # ── the dyes: where the photophysics comes from ──
    def dye_names(self) -> list[str]:
        """Names of the dyes the database can describe (for the dye pickers)."""
        if not self._dyes:
            from chisurf.core.fluorescence.fret.dyes import list_dyes

            self._dyes = list_dyes()
        return ["", *[d.name for d in self._dyes]]

    def apply_dye_selection(self) -> str:
        """Take R0, the quantum yields and tau_D(0) from the selected dye pair.

        The indirect route to the database: the user picks two dyes, and the
        numbers that are properties of the dyes rather than of the data follow —
        R0 computed from the stored emission and absorption spectra, the quantum
        yields and (when curated) the donor lifetime. Anything the database
        cannot answer is left untouched rather than defaulted, and the report
        says which is which.

        Returns
        -------
        str
            A status message.
        """
        if not (self.donor_dye and self.acceptor_dye):
            return "Pick a donor and an acceptor dye."
        from chisurf.core.fluorescence.fret.dyes import fret_pair

        pair = fret_pair(self.donor_dye, self.acceptor_dye,
                         kappa2=self.kappa2, refractive_index=self.refractive_index)
        self._dye_pair = pair
        if pair is None:
            self.results_text = "The dye pair could not be resolved in the database."
            self.notify("error")
            return self.results_text
        if pair.forster_radius:
            self.forster_radius = float(pair.forster_radius)
        if pair.donor.quantum_yield:
            self.quantum_yield_donor = float(pair.donor.quantum_yield)
        if pair.acceptor.quantum_yield:
            self.quantum_yield_acceptor = float(pair.acceptor.quantum_yield)
        if pair.donor.lifetime:
            self.donor_lifetime = float(pair.donor.lifetime)
        self.results_text = pair.summary()
        self.notify("dyes")
        return f"{pair.donor.name} → {pair.acceptor.name}: R0 = " + (
            f"{pair.forster_radius:.1f} Å" if pair.forster_radius else "not in the database"
        )

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
        # The setup names the detectors; without it the light path's own order is used.
        windows = self._window_hints()
        if windows.get("i_dd"):
            prior["green_detector"] = windows["i_dd"][0]
        if windows.get("i_da"):
            prior["red_detector"] = windows["i_da"][0]
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
        except CancelledError:
            # The user pressed Cancel: the progress callback raised through the
            # calibration. Let it out rather than reporting it as a failure --
            # a cancelled run has no result *and* nothing went wrong.
            self._result = None
            self.notify("error")
            raise
        except Exception as exc:
            logger.debug("calibration failed", exc_info=True)
            self._result = None
            self.results_text = f"Calibration failed: {exc}"
            self.notify("error")
            return False
        if progress:
            progress(1.0, "Done")
        self.results_text = self._result.calibration.report()
        self._write_container()
        self._publish_parameters()
        self.notify("result")
        return True

    def _publish_parameters(self) -> None:
        """Put the calibration's numbers in the Global View, as parameters.

        α, β, γ, δ, R_0 and each population's E and distance become
        ``FittingParameter``s that a fit can be *linked* to, so a downstream
        model stops carrying a re-typed copy of a number this window owns. In
        place on a re-run, so those links survive it.
        """
        try:
            from chisurf.plugins.burst.accurate_fret.parameters import (
                register_calibration_parameters,
            )

            register_calibration_parameters(self._result)
        except Exception:
            # Publishing is a convenience; a calibration is not lost over it.
            logger.debug("could not publish the calibration parameters",
                         exc_info=True)

    def _write_container(self) -> None:
        """Record the corrected values beside the photons they came from.

        Not on an explicit export: an accurate ``E`` is only accurate with
        respect to the α, β, γ, δ and R₀ it was computed with, so a run whose
        calibration is only in the window is a run whose numbers cannot be
        checked afterwards. ``export_csv`` puts the factors in ``#`` comment
        lines, which is readable and not queryable, and only if someone
        remembers to press Save.

        A failure here must not lose the result the user is looking at.
        """
        if self._result is None or not self.filename or self.filename.startswith("<"):
            return
        from chisurf.plugins.burst.accurate_fret import core as _c

        try:
            _c.write_container(
                self.filename, self._result,
                # The inputs that decide the answer, so a re-run with the same
                # ones replaces this rather than adding beside it.
                parameters={
                    "donor_lifetime": self.donor_lifetime,
                    "forster_radius": self.forster_radius,
                    "linker_sigma": self.linker_sigma,
                    "background": [self.background_dd, self.background_da,
                                   self.background_aa],
                    "gamma_source": self.gamma_source,
                    "n_bootstrap": self.n_bootstrap,
                    "use_priors": self.use_priors,
                    "max_fret_populations": self.max_fret_populations,
                    "min_population": self.min_population,
                },
            )
        except Exception:
            logger.debug("could not write the container", exc_info=True)

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
        """Push the posterior factors into an open ndX window.

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
            return "ndX is not available."
        windows = find_ndx_windows()
        if not windows:
            return "No open ndX window found."
        for window in windows:
            mapping = push_calibration_to_ndx(window, self._result.calibration.calibration)
        return f"Pushed {len(mapping)} constants to {len(windows)} ndX window(s)."

    def export_csv(self, path: str) -> None:
        """Write the per-burst accurate values (with the calibration header) to *path*."""
        if self._result is None:
            raise ValueError("There is nothing to export.")
        _core.export_csv(path, self._result)
