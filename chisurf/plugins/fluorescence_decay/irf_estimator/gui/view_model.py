"""Qt-free IRF estimation workflow and plot data."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from ..api.models import IRFEstimationSettings
from ..core.estimation import estimate_irf


class IRFViewModel:
    def __init__(self):
        self.dt = 1.
        self.window_length = 11
        self.polyorder = 3
        self.rl_iterations = 500
        self.regularization = 3
        self.manual_background = 0.
        self.use_range_selection = False
        self.range_bounds = [0., 100.]
        self.auto_update_enabled = False
        self.decay_data_original = None
        self.channel_axis = None
        self.result = None
        self.current_file_path = None
        self.current_dataset = None
        self.source_text = "No data loaded"
        self.status = "Ready"

    @property
    def decay_data(self):
        if self.decay_data_original is None:
            return None
        return np.maximum(self.decay_data_original - self.manual_background, 0.)

    @property
    def irf_data(self):
        return np.asarray(self.result.irf) if self.result is not None else None

    def set_bin_width(self, value):
        """Recalibrate time units without changing the estimated per-channel IRF."""
        value = float(value)
        if not np.isfinite(value) or value <= 0:
            raise ValueError("Bin width must be finite and positive.")
        self.dt = value
        if self.channel_axis is not None:
            self.channel_axis = self.channel_axis[0] + np.arange(len(self.channel_axis)) * value
        if self.result is not None:
            ratio = value / self.result.dt
            self.result.lifetime_ns *= ratio
            self.result.decay_rate_ns /= ratio
            self.result.params["k_per_ns"] /= ratio
            self.result.dt = value
            self.result.time_axis = (np.arange(len(self.result.irf)) * value).tolist()

    def time_axis_text(self):
        """The Qt status bar's permanent time-axis label."""
        axis = self.channel_axis
        if axis is None or len(axis) < 2:
            return "Time axis: Not available"
        lo, hi = float(np.min(axis)), float(np.max(axis))
        return f"Time: {lo:.2f} to {hi:.2f} ns (\u0394 = {hi - lo:.2f} ns, dt = {self.dt:.4f} ns, {len(axis)} pts)"

    def result_rows(self):
        """``(label, text)`` of the Qt results group, ``N/A`` before an estimate."""
        r = self.result
        return [
            ("Lifetime (\u03c4)", "N/A" if r is None else f"{r.lifetime_ns:.4f} ns"),
            ("Decay Rate (k)", "N/A" if r is None else f"{r.decay_rate_ns:.6f} ns\u207b\u00b9"),
            ("Amplitude (A)", "N/A" if r is None else f"{r.amplitude:.2f}"),
            ("Offset (C)", "N/A" if r is None else f"{r.offset:.2f}"),
        ]

    def settings(self, quick=False):
        return IRFEstimationSettings(window_length=int(self.window_length), polyorder=int(self.polyorder), rl_iterations=50 if quick else int(self.rl_iterations), regularization=int(self.regularization), manual_background=float(self.manual_background), use_range_selection=self.use_range_selection, range_bounds=list(self.range_bounds))

    def load_data(self, values, dt=1., time_axis=None, source="Dataset"):
        values = np.asarray(values, dtype=float)
        if values.ndim == 2 and values.shape[1] >= 2:
            time_axis, values = values[:, 0], values[:, 1]
        if values.ndim != 1 or len(values) < 2 or not np.isfinite(values).all():
            raise ValueError("Expected at least two finite intensity samples.")
        if time_axis is None:
            time_axis = np.arange(len(values)) * float(dt)
        axis = np.asarray(time_axis, dtype=float)
        if axis.shape != values.shape or not np.isfinite(axis).all() or np.any(np.diff(axis) <= 0):
            raise ValueError("Time values must be finite and strictly increasing.")
        self.dt = float(np.mean(np.diff(axis)))
        if self.dt <= 0:
            raise ValueError("Bin width must be positive.")
        self.decay_data_original = values.copy()
        self.channel_axis = axis.copy()
        self.result = None
        self.range_bounds = [0., float(len(values) - 1)]
        self.status = f"Loaded {len(values)} channels."

    def load_file(self, path):
        from ..backend.services import load_decay_handler

        response = load_decay_handler(str(path))
        if not response["ok"]:
            raise ValueError(response["error"])
        data = response["result"]
        values = data["intensity"]
        self.load_data(values, dt=data["dt"], source=Path(path).name)
        self.current_file_path = str(path)
        self.source_text = str(path)
        self.manual_background = float(np.median(self.decay_data_original[int(.9 * len(values)):]))

    def load_dataset(self, dataset: Any):
        if hasattr(dataset, "x") and hasattr(dataset, "y"):
            self.load_data(dataset.y, time_axis=dataset.x, source=getattr(dataset, "name", "Dataset"))
        elif hasattr(dataset, "data"):
            self.load_data(dataset.data, dt=getattr(dataset, "dt", 1.), source=getattr(dataset, "name", "Dataset"))
        else:
            raise ValueError("Dataset needs x/y or data arrays.")
        self.current_dataset = dataset
        self.current_file_path = getattr(dataset, "filename", None)
        experiment = getattr(dataset, "experiment", None)
        experiment = getattr(experiment, "name", "Uncategorized") if experiment else "Uncategorized"
        self.source_text = f"Dataset: {experiment} - {getattr(dataset, 'name', 'Unnamed')}"

    def estimate(self, quick=False):
        if self.decay_data_original is None:
            raise ValueError("Load a decay before estimating an IRF.")
        # The canonical core applies manual background once; pass the measured data.
        self.result = estimate_irf(self.decay_data_original.copy(), self.dt, self.settings(quick), self.channel_axis.copy())
        self.status = "IRF estimation completed."
        return self.result

    def plot_series(self):
        if self.decay_data_original is None:
            return []
        result = [{"name": "Measured Decay", "x": self.channel_axis, "y": self.decay_data_original}]
        if self.manual_background > 0:
            result.append({"name": f"BG Corrected (BG={self.manual_background:.1f})", "x": self.channel_axis,
                           "y": np.maximum(self.decay_data, .1), "dashed": True})
        if self.result is not None:
            irf = np.asarray(self.result.irf)
            maximum = float(irf.max())
            if maximum > 0:
                scaled = irf * float(self.decay_data.max()) / maximum
                # As the Qt plot: below one count the scaled IRF is not drawn, so the log axis
                # is not stretched down to the deconvolution's vanishing tails.
                result.append({"name": "Estimated IRF (scaled)", "x": self.channel_axis,
                               "y": np.where(scaled >= 1., scaled, np.nan)})
            from chisurf.core.fluorescence.tcspc.irf_estimation import generate_truncated_exponential, partial_convolution_fft

            kernel = generate_truncated_exponential(np.arange(len(irf)) * self.dt, {"A": 1., "C": 0., "k": self.result.params["k_per_ns"], "t0": 0.})
            kernel = np.maximum(kernel, 0.)
            if kernel.sum() > 0:
                kernel /= kernel.sum()
                forward = partial_convolution_fft(irf.reshape(-1, 1), kernel, axis=0)[:, 0] + self.result.params["C"]
                result.append({"name": "IRF \u2297 Exp (Forward Model)", "x": self.channel_axis, "y": forward,
                               "dashed": True})
        return result

    def save(self, path):
        if self.result is None:
            raise ValueError("Estimate an IRF before saving.")
        from ..backend.services import save_irf_handler

        response = save_irf_handler(str(path), self.result.irf, self.result.dt)
        if not response["ok"]:
            raise ValueError(response["error"])
        saved = response["result"]["path"]
        self.status = f"IRF saved to {saved}."
        return Path(saved)

    def transfer(self, sink=None):
        if self.result is None:
            raise ValueError("Estimate an IRF before transferring it.")
        from chisurf.core.data import DataCurve, ExperimentDataCurveGroup
        from chisurf.core.experiments.tcspc.reader import TCSPCReader
        from chisurf.emtk.datasets import register_dataset

        reader = TCSPCReader(dt=self.result.dt, rep_rate=10., is_vv_vh=True, g_factor=1., polarization="V", use_header=False, matrix_columns=(), rebin=(1, 1))
        metadata = {"source": "irf_estimator", "dt": self.result.dt, "g_factor": 1., "polarization": "V"}
        curves = []
        for channel in ("VV", "VH"):
            curve = DataCurve(x=self.channel_axis.copy(), y=self.irf_data.copy(), name=f"Estimated IRF {channel}", load_filename_on_init=False)
            curve.meta_data.update(metadata)
            curve.data_reader = reader
            curves.append(curve)
        group = ExperimentDataCurveGroup(curves)
        group.name = "Estimated IRF"
        group.meta_data.update(metadata)
        group.data_reader = reader
        (sink or register_dataset)(group)
        self.status = "Estimated IRF registered as a ChiSurf dataset."
        return group
