"""Qt-free model of the 2D-FLCS tool.

:class:`_FlcModel` holds the settings the declarative view edits, the loaded photon
stream and IRF, and the results the plots show. The work the Qt tool used to do in
its button handlers (opening a stream, simulating one, running the analysis with
the lifetime inversion, the L-curve, the species correlation and the 1D-MEM) is here
as plain methods, so the Qt tool and the native emtk app (``gui/app.py``, which
runs them on a :class:`chisurf.emtk.jobs.SnapshotJob`) share one implementation.
"""

from __future__ import annotations

import logging
import pathlib
from typing import Any

import numpy as np

from chisurf.core.fio.staging import TTTR_FILE_FILTER
from chisurf.core.math.regularization import LCurveData

from .client import FlcClient

_GUI_DIR = pathlib.Path(__file__).parent
logger = logging.getLogger(__name__)

#: Photon-stream dialog filter (Qt-style), shared with the Qt tool.
PHOTON_FILE_FILTER = TTTR_FILE_FILTER


class _FlcModel:
    """Settings model consumed by the declarative AutoForm view."""

    def __init__(self) -> None:
        """Initialize default 2D-FLCS settings and result buffers."""
        self.dT_ms = 1.0
        self.ddT_ms = 2.0
        self.tmin_ns = 0.0
        self.tmax_ns = 12.5
        self.max_bins = 80
        self.fit_mode = "nnls"
        self.n_components = 40
        self.tau_min_ns = 0.3
        self.tau_max_ns = 8.0
        self.log10_reg = 0.0
        self.irf_mode = "synthetic"
        self.irf_center_ns = 0.5
        self.irf_fwhm_ns = 0.15
        self.irf_shape = 0.0
        self.compute_dynamics = True
        self.n_casc = 25
        self.run_1d_mem = False
        self.mem_reg = 1000.0
        self.mem_mi_type = 0
        self.gaussian_components = 2
        self.irf_rise_scan = False
        self.run_global_mem = False
        self.n_lags = 6
        self.colormap = "viridis"
        self.sim_tau1_ns = 1.0
        self.sim_tau2_ns = 3.0
        self.sim_k12 = 30.0
        self.sim_k21 = 10.0
        self.sim_intensity_cps = 20000.0
        self.sim_time_s = 60.0
        self._lifetime: dict[str, np.ndarray] | None = None
        self._correlation: list[dict[str, Any]] | None = None
        self._mem1d: dict[str, np.ndarray] | None = None
        self._spectrum_img: np.ndarray | None = None
        self._residual_img: np.ndarray | None = None
        self._lcurve_data: LCurveData | None = None
        self._irf_preview: dict[str, np.ndarray] | None = None
        # The loaded photon stream, the active IRF and what the analysis produced
        # (the Qt tool kept these on the window).
        self.client: FlcClient | None = None
        self.tttr = None
        self.tttr_path: str | None = None
        self.irf = None
        self.irf_time_ns = None
        self.irf_file = None
        self.irf_file_time_ns = None
        self.irf_path: str | None = None
        self.spectrum2d = None
        self.kinetics = None
        # Window state of a drawn (native) host; the Qt tool ignores these.
        self.status_text = "Open a TTTR file to begin."
        self.error_text = ""
        self.busy = False
        self.dialog = ""
        self.folder = ""
        self._observers: list = []
        #: Called with every status line (the Qt tool shows it in its status bar).
        self.on_status = None

    # -- observers and status -------------------------------------------- #
    def add_observer(self, callback) -> None:
        """Register ``callback(event)`` for :meth:`notify`."""
        self._observers.append(callback)

    def notify(self, event: str = "updated") -> None:
        """Tell every observer that *event* happened."""
        for callback in list(self._observers):
            callback(event)

    def _status(self, text: str) -> None:
        """Set the status line, tell the observers and the Qt status bar."""
        self.status_text = text
        self.notify("status")
        if self.on_status is not None:
            self.on_status(text)

    def status_line(self) -> str:
        """Return the error, else the running job's message, else the last status."""
        return self.error_text or self.status_text

    def get_client(self) -> FlcClient:
        """Return the RPC client, creating the in-process one on first use."""
        if self.client is None:
            self.client = FlcClient()
        return self.client

    def view_spec(self):
        """Return the declarative AutoForm view spec."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_GUI_DIR / "flc_2d.view.json")

    def spectrum_image(self) -> np.ndarray | None:
        """Return the 2D lifetime-lifetime map."""
        return self._spectrum_img

    def residual_image(self) -> np.ndarray | None:
        """Return the 2D fit residual map."""
        return self._residual_img

    def irf_series(self) -> list[dict[str, Any]]:
        """Return decay and active IRF preview plot series."""
        if not self._irf_preview:
            return []
        series = [
            {
                "x": self._irf_preview["t"],
                "y": self._irf_preview["decay"],
                "color": "y",
                "name": "decay",
            }
        ]
        if "irf" in self._irf_preview:
            series.append(
                {
                    "x": self._irf_preview["t"],
                    "y": self._irf_preview["irf"],
                    "color": "c",
                    "name": "IRF",
                }
            )
        return series

    def lcurve_data(self) -> LCurveData | None:
        """Return 1D inversion L-curve diagnostics."""
        return self._lcurve_data

    def lifetime_series(self) -> list[dict[str, Any]]:
        """Return lifetime-distribution plot series."""
        series: list[dict[str, Any]] = []
        if self._lifetime:
            series.append(
                {
                    "x": self._lifetime["tau"],
                    "y": self._lifetime["amp"],
                    "color": "y",
                    "width": 2,
                    "name": "lifetime distribution",
                }
            )
        if self._mem1d:
            series.append(
                {
                    "x": self._mem1d["tau"],
                    "y": self._mem1d["amp"],
                    "color": "g",
                    "width": 2,
                    "name": "1D-MEM",
                }
            )
            if "gauss" in self._mem1d:
                series.append(
                    {
                        "x": self._mem1d["tau"],
                        "y": self._mem1d["gauss"],
                        "color": "r",
                        "width": 1,
                        "name": "Gaussian fit",
                    }
                )
        return series

    def correlation_series(self) -> list[dict[str, Any]]:
        """Return species-correlation plot series."""
        return self._correlation or []


    # -- what the native window needs ------------------------------------ #
    def enabled(self, name: str) -> bool:
        """Whether the field or action *name* is usable now.

        Everything is greyed while a worker runs (it works on a snapshot, so an
        edit would be lost); Run additionally needs a photon stream.
        """
        if self.busy:
            return False
        if name == "request_run":
            return self.tttr is not None
        return True

    def request_open(self) -> None:
        """Button action: ask the window for a photon-stream file dialog."""
        self.dialog = "open_tttr"

    def request_open_irf(self) -> None:
        """Button action: ask the window for an IRF file dialog."""
        self.dialog = "open_irf"

    def request_simulate(self) -> None:
        """Button action: announce that a stream should be simulated."""
        self.notify("start_simulate")

    def request_run(self) -> None:
        """Button action: announce that the analysis should run."""
        self.notify("start_run")

    def request_help(self) -> None:
        """Button action: ask the window to show the help."""
        self.notify("show_help")

    def request_guide(self) -> None:
        """Button action: ask the window to start the guided tour."""
        self.notify("start_tour")

    def export_settings(self) -> dict:
        """Return the settings to keep between sessions."""
        state = {name: getattr(self, name) for name in PERSISTED_SCALARS}
        state["folder"] = self.folder
        return state

    def restore_settings(self, state: dict) -> None:
        """Adopt settings from :meth:`export_settings`; a value of the wrong type is ignored."""
        for name in PERSISTED_SCALARS:
            if name not in state:
                continue
            current = getattr(self, name)
            value = state[name]
            try:
                if isinstance(current, bool):
                    value = bool(value)
                elif isinstance(current, int):
                    value = int(value)
                elif isinstance(current, float):
                    value = float(value)
                else:
                    value = str(value)
            except (TypeError, ValueError):
                continue
            setattr(self, name, value)
        self.folder = str(state.get("folder", self.folder) or "")

    # -- loading ---------------------------------------------------------- #
    @staticmethod
    def tttr_from_payload(payload: dict[str, Any]):
        """Reconstruct ``TttrData`` from an RPC payload."""
        from .. import api

        return api.TttrData(
            macro_times=np.asarray(payload.get("macro_times", []), dtype=np.int64),
            micro_times=np.asarray(payload.get("micro_times", []), dtype=np.int64),
            routing_channels=np.asarray(payload.get("routing_channels", []), dtype=np.int64),
            macro_time_resolution_s=float(payload["macro_time_resolution_s"]),
            micro_time_resolution_ns=float(payload["micro_time_resolution_ns"]),
            n_microtime_channels=int(payload["n_microtime_channels"]),
        )

    def open_tttr(self, path: str) -> None:
        """Open a TTTR file through the RPC client (raises when it cannot be read)."""
        self.error_text = ""
        self.tttr = self.tttr_from_payload(self.get_client().load_tttr(path, include_arrays=True))
        self.tttr_path = path
        data = self.tttr
        if data.micro_time_resolution_ns:
            self.tmax_ns = round(data.n_microtime_channels * data.micro_time_resolution_ns, 3)
        self._status(
            f"Loaded {pathlib.Path(path).name}: {data.n_photons:,} photons, "
            f"{data.n_microtime_channels} TCSPC channels @ {data.micro_time_resolution_ns:.4g} ns"
        )

    def open_irf(self, path: str) -> None:
        """Open an IRF TTTR file through the RPC client (raises when it cannot be read)."""
        self.error_text = ""
        irf_data = self.tttr_from_payload(self.get_client().load_tttr(path, include_arrays=True))
        n_channels = irf_data.n_microtime_channels
        hist = np.bincount(
            np.clip(np.asarray(irf_data.micro_times).astype(np.int64), 0, n_channels - 1),
            minlength=n_channels,
        )[:n_channels].astype(float)
        self.irf_file = hist
        self.irf_file_time_ns = np.arange(n_channels) * (irf_data.micro_time_resolution_ns or 1.0)
        self.irf_path = path
        self.irf_mode = "file"
        self._status(f"Loaded IRF from {pathlib.Path(path).name} ({n_channels} channels)")

    def set_irf(self, irf: np.ndarray, irf_time_ns: np.ndarray) -> None:
        """Set the IRF directly for tests and scripts."""
        self.irf_file = np.asarray(irf, dtype=float)
        self.irf_file_time_ns = np.asarray(irf_time_ns, dtype=float)
        self.irf_mode = "file"

    def resolve_irf(self, resolution_ns: float, n_channels: int, micro_times: np.ndarray) -> None:
        """Resolve the active IRF according to the selected mode."""
        from .. import api

        time_ns = np.arange(int(n_channels)) * resolution_ns
        if self.irf_mode == "file":
            self.irf = self.irf_file
            self.irf_time_ns = self.irf_file_time_ns
        elif self.irf_mode == "synthetic":
            self.irf = api.make_synthetic_irf(
                time_ns, self.irf_center_ns, self.irf_fwhm_ns, shape=self.irf_shape
            )
            self.irf_time_ns = time_ns
        elif self.irf_mode == "detect":
            idx = np.asarray(micro_times).astype(np.int64)
            idx = idx[(idx >= 0) & (idx < n_channels)]
            decay = np.bincount(idx, minlength=n_channels)[:n_channels].astype(float)
            self.irf = api.detect_irf(
                decay, time_ns, fwhm_ns=self.irf_fwhm_ns, shape=self.irf_shape
            )
            self.irf_time_ns = time_ns
        else:
            self.irf = None
            self.irf_time_ns = None

    def simulate(self) -> None:
        """Generate a synthetic photon stream and load it as the active dataset.

        Raises
        ------
        Exception
            Whatever the simulator raises; the state is left as it was.
        """
        from .. import api

        self.error_text = ""
        rate_matrix = np.array([[0.0, self.sim_k12], [self.sim_k21, 0.0]], dtype=float)
        self._status("Simulating photon stream...")
        t_step_ns, n_channels = 0.004, 3127
        sim_time = np.arange(n_channels) * t_step_ns
        sim_irf = api.make_synthetic_irf(
            sim_time, self.irf_center_ns, self.irf_fwhm_ns, shape=self.irf_shape
        )
        stream = api.simulate_stream(
            rate_matrix,
            [self.sim_tau1_ns, self.sim_tau2_ns],
            [self.sim_intensity_cps, self.sim_intensity_cps],
            total_time_s=self.sim_time_s,
            irf=sim_irf,
            irf_time_ns=sim_time,
            tstep_ns=t_step_ns,
            n_microtime_channels=n_channels,
            seed=1,
        )
        self.tttr = api.TttrData(
            macro_times=stream.macro_times,
            micro_times=stream.micro_times,
            routing_channels=np.zeros(stream.macro_times.size, dtype=np.int64),
            macro_time_resolution_s=stream.macro_time_resolution_s,
            micro_time_resolution_ns=stream.micro_time_resolution_ns,
            n_microtime_channels=stream.n_microtime_channels,
        )
        self.tttr_path = None
        self.tmax_ns = round(stream.n_microtime_channels * stream.micro_time_resolution_ns, 3)
        self._status(
            f"Simulated {self.tttr.n_photons:,} photons "
            f"(tau={self.sim_tau1_ns:g}/{self.sim_tau2_ns:g} ns, "
            f"k12={self.sim_k12:g} k21={self.sim_k21:g}/s). Press Run."
        )

    # -- analysis --------------------------------------------------------- #
    @staticmethod
    def _estimate_populations(spec: dict[str, Any], peaks: np.ndarray) -> np.ndarray:
        """Estimate equilibrium populations from a lifetime distribution."""
        tau = np.asarray(spec["tau_grid"], dtype=float)
        amp = np.clip(np.asarray(spec["amplitudes"], dtype=float), 0.0, None)
        split = float(np.sqrt(peaks[0] * peaks[1]))
        area = amp * tau
        p_short = float(area[tau < split].sum())
        p_long = float(area[tau >= split].sum())
        total = p_short + p_long
        if total <= 0:
            return np.array([0.5, 0.5])
        return np.array([p_short, p_long]) / total

    def run_lcurve(self, micro: np.ndarray, data: Any, method: str) -> None:
        """Compute and store L-curve diagnostics through RPC."""
        payload = self.get_client().lifetime_lcurve(
            micro,
            n_microtime_bins=data.n_microtime_channels,
            micro_time_resolution_ns=data.micro_time_resolution_ns or 1.0,
            tau_range=(self.tau_min_ns, self.tau_max_ns),
            n_components=self.n_components,
            irf=self.irf,
            irf_time_ns=self.irf_time_ns,
            method=method,
        )
        self._lcurve_data = LCurveData(
            reg=np.asarray(payload["reg"], dtype=float),
            residual_norm=np.asarray(payload["residual_norm"], dtype=float),
            solution_norm=np.asarray(payload["solution_norm"], dtype=float),
            corner_index=int(payload["corner_index"]),
        )

    def update_irf_preview(self, micro: np.ndarray, data: Any, resolution_ns: float) -> None:
        """Update normalized decay and IRF preview data."""
        idx = micro[(micro >= 0) & (micro < data.n_microtime_channels)]
        decay_hist = np.bincount(idx, minlength=data.n_microtime_channels).astype(float)
        t_full = np.arange(data.n_microtime_channels) * resolution_ns
        preview = {"t": t_full, "decay": decay_hist / (decay_hist.max() or 1.0)}
        if self.irf is not None:
            irf_on_t = np.interp(
                t_full,
                np.asarray(self.irf_time_ns, dtype=float),
                np.asarray(self.irf, dtype=float),
                left=0.0,
                right=0.0,
            )
            preview["irf"] = irf_on_t / (irf_on_t.max() or 1.0)
        self._irf_preview = preview

    def run(self) -> None:
        """Run the current 2D-FLCS analysis on the loaded photon stream."""
        if self.tttr is None:
            return
        from .. import api

        self.error_text = ""
        data = self.tttr
        macro = np.ascontiguousarray(data.macro_times)
        order = np.argsort(macro, kind="stable")
        macro = macro[order].astype(np.int64)
        micro = np.ascontiguousarray(data.micro_times)[order].astype(np.int64)
        resolution_ns = data.micro_time_resolution_ns or 1.0
        t_min = max(1, int(round(self.tmin_ns / resolution_ns)))
        t_max = max(t_min + 1, int(round(self.tmax_ns / resolution_ns)))
        lag_ticks = max(1, int(round(self.dT_ms * 1e-3 / data.macro_time_resolution_s)))
        window_ticks = max(1, int(round(self.ddT_ms * 1e-3 / data.macro_time_resolution_s)))
        reg = None if self.log10_reg == 0.0 else 10.0**self.log10_reg

        self.resolve_irf(resolution_ns, data.n_microtime_channels, micro)

        self._status("Building 2D-FDC...")
        out = self.get_client().correlate(
            macro,
            micro,
            dT=lag_ticks,
            ddT=window_ticks,
            tMin=t_min,
            tMax=t_max,
            logt_imax=60,
            max_bins=256,
        )
        mat = np.asarray(out["mat_lin"], dtype=float)
        time_ns = (np.asarray(out["mat_lin_t"], dtype=float) + 1) * resolution_ns

        self._status("Inverting 2D spectrum...")
        try:
            spec2d = self.get_client().fit(
                mat,
                time_ns,
                mode=("mem" if self.fit_mode == "mem" else "tikhonov"),
                tau_range=(self.tau_min_ns, self.tau_max_ns),
                n_components=min(self.n_components, 32),
                irf=self.irf,
                irf_time_ns=self.irf_time_ns,
                reg=reg,
                max_bins=self.max_bins,
            )
            self.spectrum2d = spec2d
            self._spectrum_img = np.asarray(spec2d["spectrum"], dtype=float)
            residual = np.asarray(spec2d.get("residual", []), dtype=float)
            self._residual_img = residual if residual.size else None
        except Exception as exc:  # noqa: BLE001
            logger.warning("2D spectrum failed: %s", exc)
            self.spectrum2d = None
            self._spectrum_img = np.log1p(mat) if mat.size else None
            self._residual_img = None

        self._status("Resolving lifetimes...")
        method = "tikhonov" if self.fit_mode == "tikhonov" else "nnls"
        spec = self.get_client().lifetime_spectrum(
            micro,
            n_microtime_bins=data.n_microtime_channels,
            micro_time_resolution_ns=resolution_ns,
            tau_range=(self.tau_min_ns, self.tau_max_ns),
            n_components=self.n_components,
            irf=self.irf,
            irf_time_ns=self.irf_time_ns,
            method=method,
            reg=reg,
        )
        self._lifetime = {
            "tau": np.asarray(spec["tau_grid"], dtype=float),
            "amp": np.asarray(spec["amplitudes"], dtype=float),
        }
        peaks = np.sort(np.asarray(spec.get("peak_lifetimes", []), dtype=float))

        try:
            self.run_lcurve(micro, data, method)
        except Exception as exc:  # noqa: BLE001
            logger.warning("L-curve failed: %s", exc)
            self._lcurve_data = None

        self.update_irf_preview(micro, data, resolution_ns)
        self._correlation = []

        if self.compute_dynamics and peaks.size >= 2:
            self.run_dynamics(api, macro, micro, data, resolution_ns, peaks, spec)

        if not self._correlation:
            peaks_txt = ", ".join(f"{peak:.2f}" for peak in peaks)
            self._status(f"Resolved lifetimes: tau = {peaks_txt} ns")

        self.run_optional_mem(api, macro, micro, t_min, t_max, resolution_ns)

    def run_dynamics(
        self,
        api,
        macro: np.ndarray,
        micro: np.ndarray,
        data: Any,
        resolution_ns: float,
        peaks: np.ndarray,
        spec: dict[str, Any],
    ) -> None:
        """Compute species-resolved correlations and kinetics."""
        self._status("Computing species correlation...")
        try:
            patterns = api.species_decay_patterns(
                peaks[:2],
                data.n_microtime_channels,
                resolution_ns,
                irf=self.irf,
                irf_time_ns=self.irf_time_ns,
            )
            dyn = api.species_correlation(
                macro,
                micro,
                patterns,
                None,
                data.macro_time_resolution_s,
                n_microtime_bins=data.n_microtime_channels,
                n_casc=int(self.n_casc),
            )
            series = []
            for index, values in dyn.correlation.auto.items():
                series.append(
                    {"x": dyn.correlation.lag_s, "y": values, "color": "c", "name": f"auto {index}"}
                )
            for (i, j), values in dyn.correlation.cross.items():
                series.append(
                    {
                        "x": dyn.correlation.lag_s,
                        "y": values,
                        "color": "m",
                        "name": f"cross {i}-{j}",
                    }
                )
            self._correlation = series
            message = "tau = " + ", ".join(f"{peak:.2f}" for peak in peaks) + " ns"
            populations = self._estimate_populations(spec, peaks[:2])
            try:
                kinetics = api.rate_matrix_kinetics(
                    dyn.correlation, n_states=2, populations=populations
                )
                self.kinetics = kinetics
                rate_sum = float(kinetics.relaxation_rates[0])
                message += f"; relaxation {kinetics.relaxation_times_s[0] * 1e3:.1f} ms"
                message += f" (k12+k21={rate_sum:.1f}/s)"
            except Exception as exc:  # noqa: BLE001
                logger.warning("rate-matrix fit failed: %s", exc)
                relax = dyn.relaxation.get("relaxation_time_s")
                if relax:
                    message += f"; relaxation {relax * 1e3:.1f} ms"
            self._status(message)
        except Exception as exc:  # noqa: BLE001
            logger.warning("dynamics failed: %s", exc)

    def run_optional_mem(
        self,
        api,
        macro: np.ndarray,
        micro: np.ndarray,
        t_min: int,
        t_max: int,
        resolution_ns: float,
    ) -> None:
        """Run optional 1D-MEM analysis and Gaussian decomposition."""
        self._mem1d = None
        if not self.run_1d_mem:
            return
        self._status("Building 1D-FDC + 1D-MEM...")
        try:
            fdc1d = api.one_d_fdc(macro, micro, tMin=t_min, tMax=t_max, max_bins=400)
            t1d_ns = fdc1d["lin_t"].astype(float) * resolution_ns
            if self.irf_rise_scan and self.irf is not None:
                rise = api.search_irf_rise(
                    fdc1d["lin"],
                    t1d_ns,
                    self.irf,
                    self.irf_time_ns,
                    tau_range=(self.tau_min_ns, self.tau_max_ns),
                    n_components=self.n_components,
                    mem_kwargs={"reg": self.mem_reg, "mi_type": int(self.mem_mi_type)},
                )
                tau_grid, amplitudes = rise.tau_grid, rise.averaged
            else:
                mem = api.lifetime_spectrum_mem(
                    fdc1d["lin"],
                    t1d_ns,
                    tau_range=(self.tau_min_ns, self.tau_max_ns),
                    n_components=self.n_components,
                    irf=self.irf,
                    irf_time_ns=self.irf_time_ns,
                    reg=self.mem_reg,
                    mi_type=int(self.mem_mi_type),
                )
                tau_grid, amplitudes = mem.tau_grid, mem.amplitudes
            self._mem1d = {"tau": tau_grid, "amp": amplitudes}
            gaussian = api.fit_gaussian_components(
                tau_grid, amplitudes, int(self.gaussian_components)
            )
            self._mem1d["gauss"] = gaussian.model
        except Exception as exc:  # noqa: BLE001
            logger.warning("1D-MEM failed: %s", exc)


#: The alias the native app and the tests use.
FlcModel = _FlcModel

#: Scalar settings kept between sessions (attributes of the model).
PERSISTED_SCALARS = (
    "dT_ms",
    "ddT_ms",
    "tmin_ns",
    "tmax_ns",
    "max_bins",
    "fit_mode",
    "n_components",
    "tau_min_ns",
    "tau_max_ns",
    "log10_reg",
    "irf_mode",
    "irf_center_ns",
    "irf_fwhm_ns",
    "irf_shape",
    "compute_dynamics",
    "n_casc",
    "run_1d_mem",
    "mem_reg",
    "mem_mi_type",
    "gaussian_components",
    "irf_rise_scan",
    "run_global_mem",
    "n_lags",
    "colormap",
    "sim_tau1_ns",
    "sim_tau2_ns",
    "sim_k12",
    "sim_k21",
    "sim_intensity_cps",
    "sim_time_s",
)
