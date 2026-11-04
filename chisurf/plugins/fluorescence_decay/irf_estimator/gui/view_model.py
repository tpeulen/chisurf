"""IRF extraction workflow and plot data, independent of any GUI toolkit.

The tool extracts an IRF from what it is given -- a fluorescence decay (blind), a reference dye of
known lifetime, a scatter, or the photons outside the bursts -- with
:mod:`..core.extraction`, the implementation Burst MLE and Burst IRF & Background call too. A
tool that took its IRF from here hands its histograms over (:meth:`IRFViewModel.receive_source`),
so this window shows and tunes the same extraction.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from ..api.models import IRFEstimationResult, IRFEstimationSettings
from ..core.estimation import estimate_irf

#: Where the IRF is taken from, as the Source field offers them.
SOURCES = [
    ("blind", "Blind"),
    ("reference", "Reference dye"),
    ("scatter", "Scatter"),
    ("non_burst", "Non-burst"),
]
PROMPT_MODELS = [("gaussian", "Gaussian"), ("skewed", "Skewed"), ("experimental", "Measured")]


class IRFViewModel:
    def __init__(self):
        self.dt = 1.0
        self.window_length = 11
        self.polyorder = 3
        self.rl_iterations = 500
        self.regularization = 3
        self.manual_background = 0.0
        self.use_range_selection = False
        self.range_bounds = [0.0, 100.0]
        self.auto_update_enabled = False
        self.decay_data_original = None
        self.channel_axis = None
        self.result = None
        self.current_file_path = None
        self.current_dataset = None
        self.source_text = "No data loaded"
        self.status = "Ready"
        #: What the decay is (:data:`SOURCES`): the extraction that runs on it.
        self.source = "blind"
        #: The data holds two halves, VV then VH (a reference dye's rotation is read from them).
        self.vv_vh = False
        #: Reference dye: its lifetime (0: fitted to its tail) and the listed one the fit is
        #: checked against; its rotational correlation time (0: from the two polarisations).
        self.reference_tau_ns = 0.0
        self.listed_tau_ns = 4.0
        self.reference_rho_ns = 0.0
        self.dye = ""
        #: The measurement(s) the received source is of (its source line names them).
        self.source_name = ""
        #: Photons outside the bursts: the pulse fitted to the prompt.
        self.irf_model = "gaussian"
        #: ``[start, stop)`` bins of the detector's gate in each half (``None``: all of it).
        self.gate = None
        #: A scatter's buffer, counts on the same bins at the scatter's time (``None``: the floor).
        self.buffer = None
        #: The extraction of the last estimate (:class:`..core.extraction.IrfResult`).
        self.extraction = None

    def source_choices(self):
        """(value, label) pairs of the Source field."""
        return list(SOURCES)

    def irf_model_choices(self):
        """(value, label) pairs of the IRF model field."""
        return list(PROMPT_MODELS)

    @property
    def decay_data(self):
        if self.decay_data_original is None:
            return None
        return np.maximum(self.decay_data_original - self.manual_background, 0.0)

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
        """The status line's time-axis label: range, span, bin width and channel count."""
        axis = self.channel_axis
        if axis is None or len(axis) < 2:
            return "Time axis: Not available"
        lo, hi = float(np.min(axis)), float(np.max(axis))
        return f"Time: {lo:.2f} to {hi:.2f} ns (\u0394 = {hi - lo:.2f} ns, dt = {self.dt:.4f} ns, {len(axis)} pts)"

    def result_rows(self):
        """``(label, text)`` of the results panel, ``N/A`` before an estimate."""
        r = self.result
        x = self.extraction
        if self.source != "blind":
            info = x.info if x is not None else {}
            kind = dict(SOURCES)[self.source] + (f", {self.dye}" if self.dye else "")
            rows = [("Source", "N/A" if x is None else f"{kind}: {self.source_name or self.source_text}")]
            if self.source == "reference":
                rows.append(("Dye lifetime", "N/A" if x is None else f"{info['tau_ns']:.3f} ns ({info['tau_how']})"))
                rho = info.get("rho_ns")
                rows.append(("Rotation (ρ)", "N/A" if x is None else ("none" if rho is None else f"{rho:.3f} ns")))
            rows.append(("IRF counts", "N/A" if x is None else " | ".join(f"{c:.0f}" for c in x.counts)))
            return rows
        return [
            ("Lifetime (\u03c4)", "N/A" if r is None else f"{r.lifetime_ns:.4f} ns"),
            ("Decay Rate (k)", "N/A" if r is None else f"{r.decay_rate_ns:.6f} ns\u207b\u00b9"),
            ("Amplitude (A)", "N/A" if r is None else f"{r.amplitude:.2f}"),
            ("Offset (C)", "N/A" if r is None else f"{r.offset:.2f}"),
        ]

    def settings(self, quick=False):
        return IRFEstimationSettings(
            window_length=int(self.window_length),
            polyorder=int(self.polyorder),
            rl_iterations=50 if quick else int(self.rl_iterations),
            regularization=int(self.regularization),
            manual_background=float(self.manual_background),
            use_range_selection=self.use_range_selection,
            range_bounds=list(self.range_bounds),
        )

    def load_data(self, values, dt=1.0, time_axis=None, source="Dataset"):
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
        self.source_name = ""
        self.result = None
        self.range_bounds = [0.0, float(len(values) - 1)]
        self.status = f"Loaded {len(values)} channels."

    def load_example(self) -> None:
        """The demo affordance: the seeded VV/VH decay, loaded and estimated."""
        from chisurf.plugins.fluorescence_decay.irf_estimator.demo import load_into

        load_into(self)

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
        self.manual_background = float(
            np.median(self.decay_data_original[int(0.9 * len(values)) :])
        )

    def load_dataset(self, dataset: Any):
        if hasattr(dataset, "x") and hasattr(dataset, "y"):
            self.load_data(
                dataset.y, time_axis=dataset.x, source=getattr(dataset, "name", "Dataset")
            )
        elif hasattr(dataset, "data"):
            self.load_data(
                dataset.data,
                dt=getattr(dataset, "dt", 1.0),
                source=getattr(dataset, "name", "Dataset"),
            )
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
        self.take(self.compute(quick))
        self.status = "IRF estimation completed."
        return self.result

    def take(self, result):
        """Keep *result* of :meth:`compute` as the estimate shown, saved and transferred."""
        self.result = result
        self.extraction = getattr(result, "extraction", None)

    def halves(self):
        """The loaded data as its polarisations: VV and VH, or the one curve."""
        data = np.asarray(self.decay_data_original, dtype=float)
        if self.vv_vh and data.size >= 2 and data.size % 2 == 0:
            return [data[: data.size // 2], data[data.size // 2 :]]
        return [data]

    def compute(self, quick=False):
        """The IRF of the loaded data by :attr:`source` (thread-safe: reads, never writes, the model).

        ``blind`` is the tool's original estimate (truncated exponential + Richardson-Lucy with
        the parameters above); the others are :mod:`..core.extraction`, the IRF every consumer
        takes. Returns an :class:`~..api.models.IRFEstimationResult` (the IRF, both halves when
        the data has two) carrying the extraction as ``extraction``.
        """
        if self.source == "blind":
            # The canonical core applies manual background once; pass the measured data.
            return estimate_irf(
                self.decay_data_original.copy(), self.dt, self.settings(quick), self.channel_axis.copy()
            )
        from ..core import extraction as X

        parts = self.halves()
        name = self.source_name or self.source_text or "the loaded data"
        if self.source == "reference":
            found = X.irf_from_reference(
                parts[0], parts[1] if len(parts) > 1 else None, self.dt,
                tau_ns=float(self.reference_tau_ns) or None,
                listed_tau_ns=float(self.listed_tau_ns) or None,
                rho_ns=float(self.reference_rho_ns) or None,
                window=self.gate, name=name, dye=self.dye,
            )
        elif self.source == "scatter":
            found = X.irf_from_scatter(parts, buffer=self.buffer, window=self.gate, name=name)
        elif self.source == "non_burst":
            found = X.irf_from_prompt(
                parts, model=self.irf_model, window=self.gate, baseline_quantile=0.2, name=name
            )
        else:
            raise ValueError(f"Unknown IRF source {self.source!r}.")
        tau = float(found.info.get("tau_ns") or 0.0)
        result = IRFEstimationResult(
            irf=np.hstack(found.halves).tolist(),
            params={"A": 0.0, "C": 0.0, "k": 0.0, "k_per_ns": 1.0 / tau if tau else 0.0},
            time_axis=(np.arange(len(found.irf)) * self.dt).tolist(),
            dt=self.dt,
            lifetime_ns=tau,
            decay_rate_ns=1.0 / tau if tau else 0.0,
            amplitude=0.0,
            offset=0.0,
        )
        result.extraction = found
        return result

    def receive_source(self, payload: dict) -> None:
        """Take what another tool extracted its IRF from (Burst MLE's ``irf_inputs``): the same
        histograms, bin width, gate and source, so :meth:`estimate` gives the same IRF.

        ``kind`` (``reference`` / ``scatter`` / ``non_burst``), ``vv``, ``vh``, ``dt_ns``,
        ``window``; ``name``, ``dye``, ``listed_tau_ns``, ``model``, ``buffer`` where they apply.
        """
        vv = np.asarray(payload["vv"], dtype=float)
        vh = np.asarray(payload.get("vh", vv), dtype=float)
        dt = float(payload.get("dt_ns") or 1.0)
        self.load_data(np.hstack([vv, vh]), dt=dt, source=str(payload.get("name") or ""))
        self.vv_vh = True
        self.source = str(payload.get("kind") or "reference")
        window = payload.get("window")
        self.gate = tuple(int(v) for v in window) if window is not None else None
        self.buffer = [np.asarray(b, dtype=float) for b in payload["buffer"]] if payload.get("buffer") else None
        self.dye = str(payload.get("dye") or "")
        self.source_name = str(payload.get("name") or "")
        self.listed_tau_ns = float(payload.get("listed_tau_ns") or self.listed_tau_ns)
        self.reference_tau_ns = float(payload.get("tau_ns") or 0.0)
        self.reference_rho_ns = float(payload.get("rho_ns") or 0.0)
        self.irf_model = str(payload.get("model") or self.irf_model)
        self.manual_background = 0.0
        self.current_file_path = None
        origin = str(payload.get("origin") or "Burst MLE")
        detector = payload.get("detector")
        self.source_text = f"{origin}{' ' + str(detector) if detector else ''}: {payload.get('name') or self.source}"
        self.status = f"Loaded the {dict(SOURCES)[self.source].lower()} of {origin}."

    def plot_series(self):
        if self.decay_data_original is None:
            return []
        result = [{"name": "Measured Decay", "x": self.channel_axis, "y": self.decay_data_original}]
        if self.manual_background > 0:
            result.append(
                {
                    "name": f"BG Corrected (BG={self.manual_background:.1f})",
                    "x": self.channel_axis,
                    "y": np.maximum(self.decay_data, 0.1),
                    "dashed": True,
                }
            )
        if self.result is not None:
            irf = np.asarray(self.result.irf)
            if self.source != "blind":
                # each half scaled to its data's peak, both on the loaded axis
                parts, out = self.halves(), []
                for data, part in zip(parts, np.split(irf, len(parts))):
                    out.append(part * (float(data.max()) / float(part.max())) if part.max() > 0 else part)
                scaled = np.hstack(out)
                result.append(
                    {
                        "name": "Extracted IRF (scaled)",
                        "x": self.channel_axis,
                        "y": np.where(scaled >= 1.0, scaled, np.nan),
                    }
                )
                return result
            maximum = float(irf.max())
            if maximum > 0:
                scaled = irf * float(self.decay_data.max()) / maximum
                # Below one count the scaled IRF is not drawn, so the log axis
                # is not stretched down to the deconvolution's vanishing tails.
                result.append(
                    {
                        "name": "Estimated IRF (scaled)",
                        "x": self.channel_axis,
                        "y": np.where(scaled >= 1.0, scaled, np.nan),
                    }
                )
            from chisurf.core.fluorescence.tcspc.irf_estimation import (
                generate_truncated_exponential,
                partial_convolution_fft,
            )

            kernel = generate_truncated_exponential(
                np.arange(len(irf)) * self.dt,
                {"A": 1.0, "C": 0.0, "k": self.result.params["k_per_ns"], "t0": 0.0},
            )
            kernel = np.maximum(kernel, 0.0)
            if kernel.sum() > 0:
                kernel /= kernel.sum()
                forward = (
                    partial_convolution_fft(irf.reshape(-1, 1), kernel, axis=0)[:, 0]
                    + self.result.params["C"]
                )
                result.append(
                    {
                        "name": "IRF \u2297 Exp (Forward Model)",
                        "x": self.channel_axis,
                        "y": forward,
                        "dashed": True,
                    }
                )
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

        reader = TCSPCReader(
            dt=self.result.dt,
            rep_rate=10.0,
            is_vv_vh=True,
            g_factor=1.0,
            polarization="V",
            use_header=False,
            matrix_columns=(),
            rebin=(1, 1),
        )
        metadata = {
            "source": "irf_estimator",
            "dt": self.result.dt,
            "g_factor": 1.0,
            "polarization": "V",
        }
        curves = []
        for channel in ("VV", "VH"):
            curve = DataCurve(
                x=self.channel_axis.copy(),
                y=self.irf_data.copy(),
                name=f"Estimated IRF {channel}",
                load_filename_on_init=False,
            )
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
