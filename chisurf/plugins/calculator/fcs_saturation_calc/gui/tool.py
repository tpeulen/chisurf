"""Tool GUI for FCS Saturation Calculator."""

from __future__ import annotations

import collections
import math
import os

import numpy as np
from qtpy import QtCore, QtWidgets

from chisurf.core.fluorescence.fcs.saturation import (
    DARK_RATE_UNITS,
    compute_bunching_factor,
    excitation_rate_peak,
    fit_single_component,
    integrated_excitation_rate,
    photon_flux,
)
from chisurf.core.models.fcs.kinetics import KineticSaturationTerms
from chisurf.gui.autoform import AutoForm
from chisurf.gui.widgets.tools.chisurf_dock_tool import ChisurfDockTool
from chisurf.plugins.calculator.fcs_saturation_calc.core import (
    calculate_fcs_curves,
    compute_power_sweep_curves,
    volume_expansion,
)


class SaturationCalculatorTool(ChisurfDockTool):
    """GUI tool for the FCS saturation calculator.

    Renders the scheme with AutoForm and plots the unperturbed against the
    saturated FCS curve. The scheme itself is an arbitrary N-state system: the
    tool never assumes which state is a triplet, an isomer or a ground state, it
    only plots one curve per state using whatever labels the scheme carries.
    """

    UNIT_FACTORS = DARK_RATE_UNITS

    SCHEME_PRESETS = {
        "Two-state (ground + excited)": "two_state.json",
        "Rhodamine 6G (3-state, triplet)": "rhodamine_3state.json",
        "Cyanine 5 (4-state, isomer + triplet)": "cyanine_4state.json",
        "Oxazine 1 (3-state, triplet)": "oxazine_3state.json",
        "Custom": None,
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("FCS Saturation Calculator")

        # Default state
        self.saturation = KineticSaturationTerms(name="saturation")
        self.saturation._power.value = 0.2
        self._include_bunching = True
        self._rate_unit = "1/us"
        self._scheme_preset = "Rhodamine 6G (3-state, triplet)"

        # Plot toggles: one per state, plus the excitation and total-emission
        # curves. Kept as a set of state indices so an N-state scheme needs no
        # new attributes.
        self._show_power_profile = True
        self._show_fluorescence_profile = True
        self._hidden_states: set[int] = set()
        self._normalize_fcs = False
        self._show_gaussian_fit = True
        self._sweep_cache = None
        self._curve_cache: collections.OrderedDict = collections.OrderedDict()
        self._curves_key = None
        self._sweep_series_key = None
        self._profile_key = None
        self._repaint_timer = QtCore.QTimer(self)
        self._repaint_timer.setSingleShot(True)
        self._repaint_timer.timeout.connect(self._repaint_plots)

        # Setup toolbar
        toolbar = QtWidgets.QToolBar()
        toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)

        a_run = toolbar.addAction("▶ Compute")
        a_run.setToolTip("Run FCS saturation calculation with current kinetics and parameters.")
        a_run.triggered.connect(self._on_compute)

        self.add_toolbar_guide(toolbar, resource="guide.json", model=self)
        self.add_toolbar_help(
            toolbar, resource="help.md", title="FCS Saturation — Help", model=self
        )
        self.toolbar = toolbar
        self.addToolBar(toolbar)

        # Load default photophysical scheme template
        self._scheme_lifetime_rate = None
        self.load_scheme_from_file("rhodamine_3state.json")
        # Restore saved user session settings if present in ~/.chisurf
        self.load_user_settings()

        # Loading the scheme above already ran a compute, and these assignments
        # throw its results away -- so the staleness guards have to be cleared
        # with them, or the recompute below returns early into empty series.
        self._fcs_curves_series = []
        self._volume_power_series = []
        self._tau_d_power_series = []
        self._volume_profile_series = []
        self._fcs_residual_series = []
        self._info_summary = ""
        self._invalidate()
        self._update_curves()

        self.form = AutoForm(self)
        self.setCentralWidget(self.form)

        # Re-trigger curve calculations on form rebuilds/resizes
        self.form.rebuilt.connect(self._on_changed)

    @property
    def show_power_profile(self) -> bool:
        """Whether the excitation intensity profile I(r) is plotted."""
        return self._show_power_profile

    @show_power_profile.setter
    def show_power_profile(self, val: bool) -> None:
        """Toggle the excitation intensity profile and refresh the plots."""
        self._show_power_profile = bool(val)
        self._on_changed()

    @property
    def show_state_profiles(self) -> bool:
        """Whether the per-state population profiles P_i(r) are plotted."""
        return not self._hidden_states

    @show_state_profiles.setter
    def show_state_profiles(self, val: bool) -> None:
        """Show or hide every state's population profile."""
        self._hidden_states = set() if val else set(range(self.saturation.n_states))
        self._on_changed()

    @property
    def show_fluorescence_profile(self) -> bool:
        """Whether the total fluorescence profile F(r) is plotted."""
        return self._show_fluorescence_profile

    @show_fluorescence_profile.setter
    def show_fluorescence_profile(self, val: bool) -> None:
        """Toggle the total fluorescence profile and refresh the plots."""
        self._show_fluorescence_profile = bool(val)
        self._on_changed()

    @property
    def show_gaussian_fit(self) -> bool:
        """Whether the naive single-component Gaussian fit is overlaid."""
        return self._show_gaussian_fit

    @show_gaussian_fit.setter
    def show_gaussian_fit(self, val: bool) -> None:
        """Toggle the single-component reference fit and refresh."""
        self._show_gaussian_fit = bool(val)
        self._invalidate()
        self._on_changed()

    @property
    def normalize_fcs(self) -> bool:
        """Whether the FCS curves are normalized to G(0) = 1."""
        return self._normalize_fcs

    @normalize_fcs.setter
    def normalize_fcs(self, val: bool) -> None:
        """Toggle G(0) normalisation of the FCS curves."""
        self._normalize_fcs = bool(val)
        self._on_changed()

    @property
    def fcs_residual_series(self) -> list[dict]:
        """Residual of the saturated curve against the naive single-component fit."""
        self._update_curves()
        return getattr(self, "_fcs_residual_series", [])

    @property
    def volume_profile_series(self) -> list[dict]:
        """Recompute and return the radial volume profile plot series."""
        self._update_volume_profile()
        return self._volume_profile_series

    def scheme_names(self) -> list[str]:
        """Names of the shipped photophysical scheme presets."""
        return list(self.SCHEME_PRESETS)

    @property
    def scheme_preset(self) -> str:
        """Return the active photophysical scheme preset name."""
        return getattr(self, "_scheme_preset", "Rhodamine 6G (3-state, triplet)")

    @scheme_preset.setter
    def scheme_preset(self, val: str) -> None:
        if val not in self.SCHEME_PRESETS or val == getattr(self, "_scheme_preset", None):
            return
        self._scheme_preset = val
        filename = self.SCHEME_PRESETS.get(val)
        if filename:
            self.load_scheme_from_file(filename)

    def load_scheme_from_file(self, filename: str) -> None:
        """Load a photophysical scheme JSON into the saturation parameter group."""
        import json

        if os.path.isabs(filename) or os.path.exists(filename):
            path = filename
        else:
            schemes_dir = os.path.join(os.path.dirname(__file__), "..", "schemes")
            path = os.path.join(schemes_dir, filename)
        if not os.path.exists(path):
            return
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        n_states = int(data.get("n_states", 2))
        self.saturation.n_states = n_states
        self.saturation._custom_state_labels = data.get("state_labels", None)
        self.saturation._custom_state_names = data.get("state_names", None)
        self._scheme_lifetime_rate = data.get("lifetime_rate", None)
        if "rate_unit" in data:
            self._rate_unit = data["rate_unit"]
            self.saturation.dark_unit = data["rate_unit"]

        if "brightness" in data:
            b_arr = data["brightness"]
            params = getattr(self.saturation.brightness, "_brightness", [])
            for i, b_val in enumerate(b_arr):
                if i < len(params):
                    params[i].value = float(b_val)

        # Zero every transition first, in both matrices, so a transition the
        # scheme does not mention stays absent instead of surviving from the
        # previous scheme.
        for group, key_rates, key_matrix in (
            (self.saturation.dark, "dark_rates", "dark_matrix"),
            (self.saturation.exc, "exc_rates", "exc_matrix"),
        ):
            rates_map = group.rates_by_name()
            for p in rates_map.values():
                p.value = 0.0
            if key_rates in data:
                for r_name, r_val in data[key_rates].items():
                    if r_name in rates_map:
                        rates_map[r_name].value = float(r_val)
            elif key_matrix in data and len(data[key_matrix]) == n_states**2:
                group.set_rate_matrix(
                    np.asarray(data[key_matrix], dtype=float).reshape((n_states, n_states))
                )

        if data.get("dye") and not self.saturation.dye:
            self.saturation.apply_dye(data["dye"], lifetime_rate=self._scheme_lifetime_rate)

        if hasattr(self, "form") and self.form:
            self.form.rebuild()
        self._on_changed()

    def save_scheme_to_file(self, filepath: str) -> None:
        """Persist the current photophysical scheme as JSON."""
        import json

        dark_dict = {
            name: float(p.value)
            for name, p in self.saturation.dark.rates_by_name().items()
            if float(p.value) != 0.0
        }
        exc_dict = {
            name: float(p.value)
            for name, p in self.saturation.exc.rates_by_name().items()
            if float(p.value) != 0.0
        }
        b_arr = [float(p.value) for p in getattr(self.saturation.brightness, "_brightness", [])]

        data = {
            "name": self._scheme_preset,
            "n_states": self.saturation.n_states,
            "state_labels": self.saturation.state_labels,
            "state_descriptions": self.saturation.state_descriptions,
            "rate_unit": self._rate_unit,
            "dark_rates": dark_dict,
            "exc_rates": exc_dict,
            "brightness": b_arr,
            "lifetime_rate": getattr(self, "_scheme_lifetime_rate", None),
        }
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def get_user_settings_path(self) -> str:
        """Return the per-user settings JSON path for this tool."""
        try:
            import chisurf.core.settings

            base_dir = (
                chisurf.core.settings.get_path("settings") / "plugins" / "fcs_saturation_calc"
            )
        except Exception:
            import pathlib

            base_dir = pathlib.Path.home() / ".chisurf" / "plugins" / "fcs_saturation_calc"
        base_dir.mkdir(parents=True, exist_ok=True)
        return str(base_dir / "settings.json")

    def save_user_settings(self) -> None:
        """Persist the current tool settings to the per-user settings file."""
        import json

        try:
            path = self.get_user_settings_path()
            dark_matrix = [float(v) for v in np.asarray(self.saturation.dark.rate_matrix()).ravel()]
            brightness_arr = [
                float(v) for v in np.asarray(self.saturation.brightness.array).ravel()
            ]
            data = {
                "power_mW": float(self.saturation._power.value),
                "extinction": float(self.saturation.extinction),
                "w_r_nm": float(self.w_r_nm),
                "w_z_nm": float(self.w_z_nm),
                "D_um2s": float(self.D_um2s),
                "N": float(self.N),
                "rate_unit": self._rate_unit,
                "include_bunching": self._include_bunching,
                "scheme_preset": self._scheme_preset,
                "normalize_fcs": self._normalize_fcs,
                "n_states": self.saturation.n_states,
                "dark_matrix": dark_matrix,
                "brightness": brightness_arr,
                "wavelength_nm": float(self.wavelength_nm),
                "dye": self.saturation.dye,
                "exc_matrix": [
                    float(v) for v in np.asarray(self.saturation.exc.rate_matrix()).ravel()
                ],
                "show_power_profile": self._show_power_profile,
                "show_fluorescence_profile": self._show_fluorescence_profile,
                "hidden_states": sorted(self._hidden_states),
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as exc:
            import logging

            logging.warning(f"Failed to save user settings: {exc}")

    def load_user_settings(self) -> None:
        """Restore the last saved tool settings from the per-user settings file."""
        import json

        try:
            path = self.get_user_settings_path()
            if not os.path.exists(path):
                return
            with open(path, encoding="utf-8") as f:
                data = json.load(f)

            if "n_states" in data:
                self.saturation.n_states = int(data["n_states"])
            if "power_mW" in data:
                self.saturation._power.value = float(data["power_mW"])
            if "extinction" in data:
                self.saturation._extinction.value = float(data["extinction"])
            if "w_r_nm" in data:
                self.saturation._w_r.value = float(data["w_r_nm"])
            if "w_z_nm" in data:
                self.saturation._w_z.value = float(data["w_z_nm"])
            if "D_um2s" in data:
                self.saturation._D.value = float(data["D_um2s"])
            if "N" in data:
                self.saturation._N.value = float(data["N"])
            if "rate_unit" in data:
                self._rate_unit = str(data["rate_unit"])
            if "include_bunching" in data:
                self._include_bunching = bool(data["include_bunching"])
            if "scheme_preset" in data:
                self._scheme_preset = str(data["scheme_preset"])
            if "normalize_fcs" in data:
                self._normalize_fcs = bool(data["normalize_fcs"])
            if "dark_matrix" in data and len(data["dark_matrix"]) == self.saturation.n_states**2:
                n = self.saturation.n_states
                mat_2d = np.asarray(data["dark_matrix"], dtype=float).reshape((n, n))
                self.saturation.dark.set_rate_matrix(mat_2d)
            if "brightness" in data:
                params = getattr(self.saturation.brightness, "_brightness", [])
                for i, b_val in enumerate(data["brightness"]):
                    if i < len(params):
                        params[i].value = float(b_val)
            if "wavelength_nm" in data:
                self.saturation._wavelength.value = float(data["wavelength_nm"])
            if data.get("dye"):
                self.saturation._dye_name = str(data["dye"])
            if "exc_matrix" in data and len(data["exc_matrix"]) == self.saturation.n_states**2:
                n = self.saturation.n_states
                self.saturation.exc.set_rate_matrix(
                    np.asarray(data["exc_matrix"], dtype=float).reshape((n, n))
                )
            if "show_power_profile" in data:
                self._show_power_profile = bool(data["show_power_profile"])
            if "show_fluorescence_profile" in data:
                self._show_fluorescence_profile = bool(data["show_fluorescence_profile"])
            if "hidden_states" in data:
                self._hidden_states = {int(i) for i in data["hidden_states"]}
        except Exception as exc:
            import logging

            logging.warning(f"Failed to load user settings: {exc}")

    def closeEvent(self, event):
        """Persist user settings when the tool window is closed."""
        self.save_user_settings()
        super().closeEvent(event)

    @property
    def rate_unit(self) -> str:
        """Return the unit the dark-rate parameters are displayed in."""
        return self._rate_unit

    @rate_unit.setter
    def rate_unit(self, new_unit: str) -> None:
        if new_unit not in self.UNIT_FACTORS or new_unit == self._rate_unit:
            return
        old_factor = self.UNIT_FACTORS.get(self._rate_unit, 1e3)
        new_factor = self.UNIT_FACTORS[new_unit]
        scale = old_factor / new_factor
        self._rate_unit = new_unit
        self.saturation.dark_unit = new_unit

        try:
            dark_rates = [r * scale for r in self.saturation.dark.rates]
            self.saturation.dark.rates = dark_rates
        except Exception:
            pass
        self._on_changed()

    @property
    def power_mW(self) -> float:
        """Return the excitation power in mW."""
        return float(self.saturation._power.value)

    @power_mW.setter
    def power_mW(self, value: float) -> None:
        self.saturation._power.value = max(0.0, float(value))
        self._on_changed()

    @property
    def wavelength_nm(self) -> float:
        """Return the excitation wavelength in nm."""
        return float(self.saturation.wavelength_nm)

    @wavelength_nm.setter
    def wavelength_nm(self, value: float) -> None:
        """Set the excitation wavelength and re-read epsilon if a dye is chosen."""
        self.saturation._wavelength.value = float(value)
        if self.saturation.dye:
            self.saturation.apply_dye(self.saturation.dye)
        self._on_changed()

    @property
    def dye(self) -> str:
        """Name of the MMFDB dye the extinction coefficient was read from."""
        return self.saturation.dye

    @dye.setter
    def dye(self, name: str) -> None:
        """Read epsilon at the excitation wavelength from the MMFDB dye repository."""
        self.saturation.apply_dye(name)
        self._on_changed()

    def dye_names(self) -> list[str]:
        """List the dyes MMFDB can supply an absorption spectrum for."""
        return self.saturation.dye_names()

    @property
    def include_bunching(self) -> bool:
        """Return whether the photokinetic bunching factor is included."""
        return self._include_bunching

    @include_bunching.setter
    def include_bunching(self, value: bool) -> None:
        self._include_bunching = bool(value)
        self._on_changed()

    @property
    def fcs_curves_series(self) -> list[dict]:
        """Recompute and return the unperturbed vs saturated FCS plot series."""
        self._update_curves()
        return self._fcs_curves_series

    @property
    def volume_power_series(self) -> list[dict]:
        """Recompute and return the volume-vs-power sweep plot series."""
        self._update_power_sweep()
        return self._volume_power_series

    @property
    def tau_d_power_series(self) -> list[dict]:
        """Recompute and return the diffusion-time-vs-power sweep plot series."""
        self._update_power_sweep()
        return self._tau_d_power_series

    @property
    def w_r_nm(self) -> float:
        """Return the radial beam waist in nm."""
        return self.saturation.w_r_nm

    @property
    def w_z_nm(self) -> float:
        """Return the axial beam waist in nm."""
        return self.saturation.w_z_nm

    @property
    def D_um2s(self) -> float:
        """Return the diffusion coefficient in um^2/s."""
        return self.saturation.D_um2s

    @property
    def N(self) -> float:
        """Return the number of molecules in the detection volume."""
        return self.saturation.N

    def view_spec(self):
        """Provide AutoForm with the layout."""
        import os

        from chisurf.core.dataspec import load_view_spec

        view_path = os.path.join(os.path.dirname(__file__), "view.json")
        return load_view_spec(view_path)

    def info_text(self) -> str:
        """HTML summary of calculation results."""
        if not self._info_summary:
            return "<p style='color: palette(mid);'><i>Click <b>▶ Compute</b> in the toolbar to run the calculation.</i></p>"
        return self._info_summary

    def _on_compute(self):
        """Run the FCS saturation calculation and refresh the plots at once.

        An explicit action repaints immediately rather than on the coalescing
        timer, so pressing Compute is never a no-op that lands a frame later.
        """
        timer = getattr(self, "_repaint_timer", None)
        if timer is not None:
            timer.stop()
        self._update_curves()
        self._repaint_plots()

    #: Cached curves, keyed by every input that changes them. The power slider
    #: is meant to be dragged, so an update has to stay well inside a frame.
    _CURVE_CACHE_SIZE = 512

    #: Repaint coalescing window (ms) -- about 40 frames per second.
    _REPAINT_INTERVAL_MS = 25

    @staticmethod
    def _scheme_key(ext, wavelength, dark_m, exc_m, bright_arr, w_r, w_z, D_val):
        """Hashable identity of everything a curve depends on except the power."""
        return (
            round(float(ext), 6),
            round(float(wavelength), 6),
            tuple(np.asarray(dark_m, dtype=float).ravel().tolist()),
            tuple(np.asarray(exc_m, dtype=float).ravel().tolist()),
            tuple(np.asarray(bright_arr, dtype=float).ravel().tolist()),
            round(float(w_r), 6),
            round(float(w_z), 6),
            round(float(D_val), 9),
        )

    @staticmethod
    def _sweep_ceiling(power_mW: float) -> float:
        """Upper power of the sweep, rounded up to a decade.

        The sweep's own default upper bound is ``max(50, 2*power)``, which moves
        with the power and would both invalidate the cache on every step and make
        the x-axis crawl while the slider is dragged. Snapping to a decade keeps
        the axis still and the cache warm for a whole decade of travel.
        """
        target = max(50.0, float(power_mW) * 2.0)
        return float(10.0 ** math.ceil(math.log10(target)))

    def _update_power_sweep(self):
        """Recompute power sweep dependence curves (Volume and tau_D vs Power)."""
        try:
            dark_m = self.saturation.dark_matrix_hz
            exc_m = self.saturation.exc.rate_matrix()
            bright_arr = self.saturation.brightness.array
            power_mW = float(self.power_mW)
            ext = float(self.saturation.extinction)
            w_r = float(self.w_r_nm)
            w_z = float(self.w_z_nm)
            D_val = float(self.D_um2s)
            wavelength = float(self.wavelength_nm)
        except Exception:
            return

        # The sweep costs ~30 ms -- four times everything else in an update --
        # and the only thing the current power changes about it is where the red
        # marker sits. Keying the cache on everything *but* the power is what
        # makes dragging the power slider feel live.
        if (power_mW, self._scheme_key(ext, wavelength, dark_m, exc_m, bright_arr,
                                       w_r, w_z, D_val)) == getattr(self, "_sweep_series_key", None):
            return
        self._sweep_series_key = (
            power_mW,
            self._scheme_key(ext, wavelength, dark_m, exc_m, bright_arr, w_r, w_z, D_val),
        )
        ceiling = self._sweep_ceiling(power_mW)
        key = (
            self._scheme_key(ext, wavelength, dark_m, exc_m, bright_arr, w_r, w_z, D_val),
            ceiling,
        )
        cached = self._sweep_cache
        if cached is not None and cached[0] == key:
            powers_mW, v_rel, tau_d = cached[1]
        else:
            powers_mW, v_rel, tau_d = compute_power_sweep_curves(
                power_mW=ceiling,
                extinction=ext,
                dark_matrix=dark_m,
                exc_matrix=exc_m,
                brightness=bright_arr,
                w_r_nm=w_r,
                w_z_nm=w_z,
                D_um2s=D_val,
                wavelength_nm=wavelength,
            )
            self._sweep_cache = (key, (powers_mW, v_rel, tau_d))

        curr_v = float(np.interp(power_mW, powers_mW, v_rel))
        curr_tau = float(np.interp(power_mW, powers_mW, tau_d))

        self._volume_power_series = [
            {"name": "V_eff / V_0", "x": powers_mW, "y": v_rel, "color": "cyan", "width": 2},
            {
                "name": "Current Power",
                "x": [power_mW],
                "y": [curr_v],
                "color": "red",
                "symbol": "o",
                "symbol_size": 9,
                "no_line": True,
            },
        ]

        self._tau_d_power_series = [
            {"name": "τ_D (ms)", "x": powers_mW, "y": tau_d, "color": "magenta", "width": 2},
            {
                "name": "Current Power",
                "x": [power_mW],
                "y": [curr_tau],
                "color": "red",
                "symbol": "o",
                "symbol_size": 9,
                "no_line": True,
            },
        ]

    def _update_volume_profile(self):
        """Recompute 1D radial profiles of laser intensity and state populations.

        A no-op when nothing it depends on has changed: the plot series are
        properties that recompute on read and ``refresh_plots`` reads every one
        of them, so without this a slider step runs the pipeline several times.
        """
        from chisurf.plugins.calculator.fcs_saturation_calc.core import compute_volume_profile

        try:
            dark_m = self.saturation.dark_matrix_hz
            exc_m = self.saturation.exc.rate_matrix()
            bright_arr = self.saturation.brightness.array
            power_mW = float(self.power_mW)
            ext = float(self.saturation.extinction)
            w_r = float(self.w_r_nm)
            w_z = float(self.w_z_nm)
            labels = self.saturation.state_labels
            wavelength = float(self.wavelength_nm)
        except Exception:
            return

        key = (self._scheme_key(ext, wavelength, dark_m, exc_m, bright_arr, w_r, w_z, 0.0),
               round(power_mW, 9), tuple(labels), tuple(sorted(self._hidden_states)),
               self._show_power_profile, self._show_fluorescence_profile)
        if key == getattr(self, "_profile_key", None):
            return
        self._profile_key = key

        prof = compute_volume_profile(
            power_mW=power_mW,
            extinction=ext,
            dark_matrix=dark_m,
            exc_matrix=exc_m,
            brightness=bright_arr,
            w_r_nm=w_r,
            w_z_nm=w_z,
            state_labels=labels,
            wavelength_nm=wavelength,
        )

        r_nm = prof["r_nm"]
        k_exc_norm = prof["k_exc_norm"]
        P_states = prof["P_states"]
        emission = prof["emission"]
        lbls = prof["labels"]

        palette = ["#42a5f5", "#66bb6a", "#ab47bc", "#ffa726", "#26a69a", "#ec407a"]
        series = []

        if self._show_power_profile:
            series.append(
                {
                    "name": "Excitation k_exc(r) / peak",
                    "x": r_nm,
                    "y": k_exc_norm,
                    "color": "cyan",
                    "width": 2,
                }
            )

        # One curve per state, whatever the scheme is. No state is special here.
        for i in range(P_states.shape[0]):
            if i in self._hidden_states:
                continue
            lbl = lbls[i] if i < len(lbls) else str(i + 1)
            series.append(
                {
                    "name": f"P{i + 1} ({lbl})",
                    "x": r_nm,
                    "y": P_states[i],
                    "color": palette[i % len(palette)],
                    "width": 2,
                }
            )

        if self._show_fluorescence_profile:
            series.append(
                {
                    "name": "Emission Σ Q_i P_i(r)",
                    "x": r_nm,
                    "y": emission,
                    "color": "yellow",
                    "width": 2.5,
                    "dash": "dash",
                }
            )

        self._volume_profile_series = series

    def _update_curves(self):
        """Recompute the FCS curve series from the current scheme and optics."""
        try:
            dark_m = self.saturation.dark_matrix_hz
            exc_m = self.saturation.exc.rate_matrix()
            bright_arr = self.saturation.brightness.array
            power_mW = float(self.power_mW)
            ext = float(self.saturation.extinction)
            wavelength = float(self.wavelength_nm)
            w_r = float(self.w_r_nm)
            w_z = float(self.w_z_nm)
            D_val = float(self.D_um2s)
            N_val = float(self.N)
        except Exception as exc:
            self._info_summary = f"<p style='color:red;'><b>Error:</b> {exc}</p>"
            return

        state_key = (
            self._scheme_key(ext, wavelength, dark_m, exc_m, bright_arr, w_r, w_z, D_val),
            round(power_mW, 9), round(N_val, 9), bool(self._include_bunching),
            bool(self._normalize_fcs),
        )
        if state_key == getattr(self, "_curves_key", None):
            return
        self._curves_key = state_key

        # N and the baseline only scale the finished curve, so they stay out of
        # the key: changing them must not throw away a numerical integration.
        curve_key = (
            self._scheme_key(ext, wavelength, dark_m, exc_m, bright_arr, w_r, w_z, D_val),
            round(power_mW, 9),
            bool(self._include_bunching),
        )
        cached = self._curve_cache.get(curve_key)
        if cached is None:
            cached = calculate_fcs_curves(
                power_mW=power_mW,
                extinction=ext,
                dark_matrix=dark_m,
                exc_matrix=exc_m,
                brightness=bright_arr,
                w_r_nm=w_r,
                w_z_nm=w_z,
                D_um2s=D_val,
                N=1.0,
                include_bunching=self._include_bunching,
                wavelength_nm=wavelength,
            )
            self._curve_cache[curve_key] = cached
            while len(self._curve_cache) > self._CURVE_CACHE_SIZE:
                self._curve_cache.pop(next(iter(self._curve_cache)))
        else:
            # Refresh its recency so a slider dragged back and forth over the
            # same span keeps hitting instead of evicting itself.
            self._curve_cache.move_to_end(curve_key)
        tau_ms, g_unpert_1, g_sat_1 = cached
        g_unpert = g_unpert_1 / N_val
        g_sat = g_sat_1 / N_val
        if self._normalize_fcs:
            g0_u = g_unpert[0] if len(g_unpert) > 0 and g_unpert[0] != 0 else 1.0
            g0_s = g_sat[0] if len(g_sat) > 0 and g_sat[0] != 0 else 1.0
            y_unpert = g_unpert / g0_u
            y_sat = g_sat / g0_s
        else:
            y_unpert = g_unpert
            y_sat = g_sat

        self._fcs_curves_series = [
            {"name": "Unperturbed Gaussian", "x": tau_ms, "y": y_unpert, "color": "blue"},
            {"name": "Saturated", "x": tau_ms, "y": y_sat, "color": "red"},
        ]

        # What an experimenter would fit, not knowing the volume has stopped
        # being Gaussian. Overlaying it is the only way the second, faster
        # component saturation introduces becomes visible: the amplitude drop
        # otherwise dominates the plot and the shape change hides inside it.
        self._apparent = None
        self._fcs_residual_series = []
        if self._show_gaussian_fit and power_mW > 0.0:
            tau_s = tau_ms * 1e-3
            bunching = (
                compute_bunching_factor(
                    excitation_rate_peak(power_mW * 1e-3, ext, w_r * 1e-9, wavelength * 1e-9),
                    dark_m, exc_m, bright_arr, tau_s,
                )
                if self._include_bunching
                else np.ones_like(tau_s)
            )
            diffusion = np.asarray(g_sat) / np.where(bunching > 0, bunching, 1.0)
            tau_d_s, structure, fitted, rms = fit_single_component(
                tau_s, diffusion, w_r * 1e-9, w_z * 1e-9, D_val * 1e-12
            )
            self._apparent = (tau_d_s, structure, rms)
            shown = fitted * bunching * (diffusion[0] if diffusion.size else 1.0)
            if self._normalize_fcs and shown[0] != 0:
                shown = shown / shown[0]
            self._fcs_curves_series.insert(
                1,
                {"name": "1-component Gaussian fit", "x": tau_ms, "y": shown,
                 "color": "#9e9e9e", "width": 2, "dash": "dash"},
            )
            # The deviation is a few times 1e-3 of the amplitude -- invisible on
            # a linear plot next to a curve of order 1, and obvious the moment it
            # is plotted on its own. This is how the distortion is diagnosed on
            # real data, so it is what the tool should show.
            reference = y_sat if self._normalize_fcs else np.asarray(y_sat)
            self._fcs_residual_series = [
                {"name": "saturated − 1-component fit", "x": tau_ms,
                 "y": np.asarray(reference) - shown, "color": "#ff7043", "width": 2},
                {"name": "zero", "x": tau_ms, "y": np.zeros_like(tau_ms),
                 "color": "#607d8b", "width": 1, "dash": "dash"},
            ]

        self._update_power_sweep()
        self._update_volume_profile()

        # Every number below comes from the same core module the curves do --
        # duplicating the constants here is how the panel and the physics drift.
        power_W = power_mW * 1e-3
        wavelength_m = wavelength * 1e-9
        flux = photon_flux(power_W, wavelength_m)
        k_exc_int = integrated_excitation_rate(power_W, ext, wavelength_m)
        k_exc_0 = excitation_rate_peak(power_W, ext, w_r * 1e-9, wavelength_m)
        v_rel = volume_expansion(
            power_mW=power_mW,
            extinction=ext,
            dark_matrix=dark_m,
            exc_matrix=exc_m,
            brightness=bright_arr,
            w_r_nm=w_r,
            w_z_nm=w_z,
            wavelength_nm=wavelength,
        )
        dye_note = f" (ε from MMFDB: {self.dye})" if self.dye else ""
        self._info_summary = (
            f"<h4>FCS saturation summary</h4>"
            f"<table border='0' cellspacing='4'>"
            f"<tr><td><b>Power P<sub>total</sub>:</b></td>"
            f"<td>{power_mW:.4g} mW at λ = {wavelength:.0f} nm</td></tr>"
            f"<tr><td><b>Photon flux Φ<sub>total</sub>:</b></td>"
            f"<td>{flux:.3g} photons/s</td></tr>"
            f"<tr><td><b>ε(λ):</b></td><td>{ext:.4g} M⁻¹cm⁻¹{dye_note}</td></tr>"
            f"<tr><td><b>Area-integrated rate k<sub>exc,int</sub>:</b></td>"
            f"<td>{k_exc_int:.3g} m²/s</td></tr>"
            f"<tr><td><b>Peak focal rate k<sub>exc</sub>(0,0):</b></td>"
            f"<td><b>{k_exc_0 / 1e6:.4g} µs⁻¹</b></td></tr>"
            f"<tr><td><b>Unperturbed G(0):</b></td><td>{g_unpert[0]:.4g}</td></tr>"
            f"<tr><td><b>Saturated G(0):</b></td><td>{g_sat[0]:.4g}</td></tr>"
            f"<tr><td><b>Volume expansion V<sub>eff</sub>/V<sub>0</sub>:</b></td>"
            f"<td><b>{v_rel:.3f}×</b></td></tr>"
            f"{self._apparent_rows(D_val, w_r)}"
            f"</table>"
            f"<p><i>N is overestimated by exactly this factor if the curve is fitted "
            f"with an unsaturated Gaussian model.</i></p>"
        )

    def _apparent_rows(self, D_um2s: float, w_r_nm: float) -> str:
        """Summary rows for the naive single-component fit, when one was made."""
        if not self._apparent:
            return ""
        tau_d_s, structure, rms = self._apparent
        true_tau_d = (w_r_nm * 1e-9) ** 2 / (4.0 * D_um2s * 1e-12)
        verdict = (
            "<span style='color:#c62828;'>a single component no longer describes "
            "this curve — the volume is not Gaussian</span>"
            if rms > 2.5e-3
            else "one component still describes it"
        )
        return (
            f"<tr><td><b>Apparent &tau;<sub>D</sub> (naive fit):</b></td>"
            f"<td><b>{tau_d_s * 1e6:.1f} µs</b> against a true "
            f"{true_tau_d * 1e6:.1f} µs — <b>{tau_d_s / true_tau_d:.2f}×</b> too slow</td></tr>"
            f"<tr><td><b>Fit residual:</b></td><td>{rms:.1e} — {verdict}</td></tr>"
        )

    def _on_changed(self):
        """Recompute and schedule a repaint.

        The model update is ~1 ms thanks to the caches, but repainting the four
        plots costs ~20 ms, so a dragged slider would queue repaints faster than
        Qt can serve them. Coalescing them onto one timer keeps the curve
        responsive: every drag step recomputes, and the paint happens at most
        once per interval with the newest data.
        """
        self._update_curves()
        if not hasattr(self, "form"):
            return
        timer = getattr(self, "_repaint_timer", None)
        if timer is None:
            self._repaint_plots()
            return
        timer.start(self._REPAINT_INTERVAL_MS)

    def _invalidate(self) -> None:
        """Forget the staleness guards so the next update really recomputes."""
        self._curves_key = None
        self._sweep_series_key = None
        self._profile_key = None

    def _repaint_plots(self) -> None:
        """Redraw every plot from the current series."""
        if hasattr(self, "form"):
            try:
                self.form.refresh_plots()
            except Exception:
                pass
