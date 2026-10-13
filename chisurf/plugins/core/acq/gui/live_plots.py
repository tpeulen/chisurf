"""Live plots of the native acquisition window, driven by pipeline snapshots.

:class:`LivePlots` is the *model* of ``live_plots.view.json``: every per-plot
control of the legacy Qt tool (decay channel map, correlation channel pairs,
count-rate binning and "Set to mean", MCS bin width, update frequency, macro-time
plot type) is a declared attribute of it. It never touches the pipeline's
photons: the only input is :meth:`LivePlots.set_snapshot`, fed with
:meth:`~chisurf.plugins.core.acq.pipeline.AcquisitionPipeline.snapshot` (the
thread-safe crossing). Settings that the pipeline fixes at construction (routing
channels, correlation pairs, MCS bin width) reach it through
:meth:`LivePlots.apply_to_config`; the rest act on the display.

The plots are emtk ``implot`` plots, drawn by :meth:`LivePlots.draw_plot`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
N_CURVES = 4
_DEFAULT_CHANNELS = (8, 0, 9, 1)

#: persisted settings and their defaults (name -> default)
DEFAULTS: dict[str, Any] = {
    "decay_log_y": False,
    "decay_every": 1,
    "corr_log_x": True,
    "corr_every": 1,
    "rate_all_show": False,
    "rate_log_y": False,
    "rate_rolling": True,
    "rate_window": 500,
    "rate_binning": 1,
    "rate_every": 1,
    "mcs_bin_width_ms": 1.0,
    "mcs_rollaround_s": 1.0,
    "mcs_every": 5,
    "mcs_manual_y": False,
    "mcs_y_min": 0.0,
    "mcs_y_max": 100.0,
    "macro_show": True,
    "macro_type": "dt",
    "macro_every": 1,
}
for _i in range(N_CURVES):
    DEFAULTS[f"decay_ch{_i}"] = _DEFAULT_CHANNELS[_i]
    DEFAULTS[f"decay_show{_i}"] = _i < 3
    DEFAULTS[f"corr_a{_i}"] = -1
    DEFAULTS[f"corr_b{_i}"] = -1
    DEFAULTS[f"corr_show{_i}"] = _i == 0
    DEFAULTS[f"rate_ch{_i}"] = -1 if _i == 0 else _DEFAULT_CHANNELS[_i]
    DEFAULTS[f"rate_show{_i}"] = _i == 0

_COLOURS = [
    (0.12, 0.47, 0.71, 1.0),
    (0.84, 0.15, 0.16, 1.0),
    (0.17, 0.63, 0.17, 1.0),
    (0.58, 0.40, 0.74, 1.0),
    (0.2, 0.2, 0.2, 1.0),
]


def _coerce(name: str, value: Any) -> Any:
    """Return *value* in the type of the default of *name*."""
    default = DEFAULTS[name]
    if isinstance(default, bool):
        return bool(value)
    if isinstance(default, int):
        return int(value)
    if isinstance(default, float):
        return float(value)
    return str(value)


class LivePlots:
    """Settings, derived series and drawing of the five live acquisition plots."""

    # The scalar settings (set from ``DEFAULTS``; the per-curve ``*_ch{i}`` /
    # ``*_show{i}`` ones are read by name).
    decay_log_y: bool
    decay_every: int
    corr_log_x: bool
    corr_every: int
    rate_all_show: bool
    rate_log_y: bool
    rate_rolling: bool
    rate_window: int
    rate_binning: int
    rate_every: int
    mcs_bin_width_ms: float
    mcs_rollaround_s: float
    mcs_every: int
    mcs_manual_y: bool
    mcs_y_min: float
    mcs_y_max: float
    macro_show: bool
    macro_type: str
    macro_every: int

    def __init__(self) -> None:
        """Build with the legacy tool's defaults and no data."""
        for name, value in DEFAULTS.items():
            setattr(self, name, value)
        self.sections = json.loads((HERE / "live_plots.view.json").read_text("utf-8"))["sections"]
        for tab in ("decay", "correlation", "count_rate", "mcs", "macrotime"):
            setattr(self, f"tab_{tab}", True)
        self.snapshot: dict[str, Any] | None = None
        self.tac_dt_ns = 0.004069
        self.serial = 0
        self.mean_lines: dict[int, float] = {}
        self.series: dict[str, list[tuple[str, np.ndarray, np.ndarray]]] = {}
        self.drawn: dict[str, list[tuple[str, np.ndarray, np.ndarray]]] = {}
        self._seen: dict[str, int] = {}
        self._config_channels: tuple[int, ...] = tuple(
            getattr(self, f"decay_ch{i}") for i in range(N_CURVES)
        )

    # -- declared-control hooks ---------------------------------------------- #
    def enabled(self, _action: str) -> bool:
        """Every live-plot action is always available."""
        return True

    def qc_text(self) -> str:
        """Burst count and phasor of the last snapshot."""
        snap = self.snapshot
        if not snap:
            return "Bursts: - | Phasor: -"
        phasor = snap.get("phasor")
        ph = "-" if not phasor else f"g={phasor[0]:.3f}, s={phasor[1]:.3f}"
        bursts = snap.get("burst_count")
        return f"Bursts: {'-' if bursts is None else bursts} | Phasor: {ph}"

    def _set_mean(self, index: int) -> None:
        """Remember the mean of the displayed rate of curve *index* (4 = all channels)."""
        for label, _x, y in self.series.get("rate", []):
            if label == self._rate_label(index) and len(y):
                self.mean_lines[index] = float(np.mean(y))

    def set_mean_0(self) -> None:
        """Mean line for count-rate curve 0."""
        self._set_mean(0)

    def set_mean_1(self) -> None:
        """Mean line for count-rate curve 1."""
        self._set_mean(1)

    def set_mean_2(self) -> None:
        """Mean line for count-rate curve 2."""
        self._set_mean(2)

    def set_mean_3(self) -> None:
        """Mean line for count-rate curve 3."""
        self._set_mean(3)

    def set_mean_4(self) -> None:
        """Mean line for the all-channels count-rate curve."""
        self._set_mean(4)

    def clear_mean_lines(self) -> None:
        """Remove all mean lines."""
        self.mean_lines.clear()

    # -- persistence / pipeline coupling ---------------------------------- #
    def export_settings(self) -> dict[str, Any]:
        """Return every persisted setting as plain JSON data."""
        return {name: getattr(self, name) for name in DEFAULTS}

    def restore_settings(self, settings: dict[str, Any]) -> None:
        """Restore known, well-typed settings; unknown or malformed keys are ignored."""
        for name, value in (settings or {}).items():
            if name in DEFAULTS:
                try:
                    setattr(self, name, _coerce(name, value))
                except (TypeError, ValueError):
                    continue

    def correlation_pairs(self) -> tuple[tuple[int, int, int], ...]:
        """``(curve, a, b)`` of every enabled correlation curve (curve 0 at least)."""
        pairs = tuple(
            (i, int(getattr(self, f"corr_a{i}")), int(getattr(self, f"corr_b{i}")))
            for i in range(N_CURVES)
            if getattr(self, f"corr_show{i}")
        )
        return pairs or ((0, -1, -1),)

    def apply_to_config(self, config: Any) -> Any:
        """Write the pipeline-side settings into a ``PipelineConfig`` before it is built."""
        config.channels = tuple(int(getattr(self, f"decay_ch{i}")) for i in range(N_CURVES))
        config.correlation_pairs = self.correlation_pairs()
        config.mcs_bin_width_ms = float(self.mcs_bin_width_ms)
        config.mcs_rollaround_ms = float(self.mcs_rollaround_s) * 1000.0
        self._config_channels = tuple(config.channels)
        res = float(getattr(config, "microtime_resolution_s", 0.0) or 0.0)
        if res > 0:
            self.tac_dt_ns = res * 1e9
        return config

    # -- data ------------------------------------------------------------------ #
    def clear(self) -> None:
        """Forget all data (not the settings)."""
        self.snapshot, self.serial = None, 0
        self.series, self.drawn, self._seen = {}, {}, {}
        self.mean_lines.clear()

    def set_snapshot(self, snapshot: dict[str, Any] | None) -> None:
        """Take a pipeline snapshot and refresh every plot that is due."""
        if snapshot is None:
            self.clear()
            return
        self.snapshot = snapshot
        self.serial += 1
        self._fp = self._fingerprint()
        for name, every in (
            ("decay", self.decay_every),
            ("correlation", self.corr_every),
            ("rate", self.rate_every),
            ("mcs", self.mcs_every),
            ("macro", self.macro_every),
        ):
            if name not in self.series or self.serial % max(1, int(every)) == 0:
                self.series[name] = getattr(self, f"_build_{name}")(snapshot)
                self._seen[name] = self.serial

    def _fingerprint(self) -> tuple:
        """Display settings whose change must redraw immediately (not the update rates)."""
        return tuple(v for k, v in self.export_settings().items() if not k.endswith("_every"))

    def refresh(self) -> None:
        """Rebuild all series after a display setting changed (the snapshot is unchanged)."""
        fp = self._fingerprint()
        if self.snapshot is not None and fp != getattr(self, "_fp", fp):
            for name in ("decay", "correlation", "rate", "mcs", "macro"):
                self.series[name] = getattr(self, f"_build_{name}")(self.snapshot)
        self._fp = fp

    def _build_decay(self, snap: dict) -> list:
        out = []
        for i, decay in enumerate(snap.get("decay_data", [])[:N_CURVES]):
            if getattr(self, f"decay_show{i}"):
                y = np.asarray(decay, dtype=float)
                out.append(
                    (f"ch {self._config_channels[i]}", np.arange(len(y)) * self.tac_dt_ns, y)
                )
        return out

    def _build_correlation(self, snap: dict) -> list:
        out = []
        for result, pair in zip(
            snap.get("correlation_results", []), snap.get("correlation_pairs", [])
        ):
            if result is None:
                continue
            idx, a, b = pair
            out.append((f"{a} x {b}", np.asarray(result[0], float), np.asarray(result[1], float)))
        return out

    def _rate_label(self, index: int) -> str:
        if index == 4:
            return "all"
        ch = int(getattr(self, f"rate_ch{index}"))
        return "all" if ch < 0 else f"ch {ch}"

    def _rate_index(self, channel: int, n_data: int) -> int | None:
        if channel < 0:
            return n_data - 1
        return self._config_channels.index(channel) if channel in self._config_channels else None

    def _build_rate(self, snap: dict) -> list:
        t = np.asarray(snap.get("count_rate_times", []), dtype=float)
        data = snap.get("count_rate_data", [])
        out = []
        wanted = [
            (i, int(getattr(self, f"rate_ch{i}")))
            for i in range(N_CURVES)
            if getattr(self, f"rate_show{i}")
        ]
        if self.rate_all_show:
            wanted.append((4, -1))
        for i, channel in wanted:
            k = self._rate_index(channel, len(data))
            if k is None or k >= len(data):
                continue
            y = np.asarray(data[k], dtype=float)
            x = t[: len(y)]
            if self.rate_rolling:
                n = max(1, int(self.rate_window))
                x, y = x[-n:], y[-n:]
            x, y = _bin(x, y, int(self.rate_binning))
            out.append((self._rate_label(i), x, y))
        return out

    def _build_mcs(self, snap: dict) -> list:
        trace = snap.get("mcs_trace")
        return (
            []
            if trace is None
            else [("MCS", np.asarray(trace[0], float), np.asarray(trace[1], float))]
        )

    def _build_macro(self, snap: dict) -> list:
        if not self.macro_show:
            return []
        diffs = np.asarray(snap.get("macrotime_data", []), dtype=float)
        stamps = np.asarray(snap.get("macrotime_times", []), dtype=float)
        if self.macro_type == "absolute":
            return [("t", np.arange(len(stamps), dtype=float), stamps)]
        return [("dt", stamps, diffs)]

    # -- drawing ----------------------------------------------------------------- #
    def draw_plot(self, section: dict, _model: Any, _state: Any, width: float) -> None:
        """Custom-section callback: draw the plot named by ``section['key']``."""
        from emtk import im, implot

        name = section["key"]
        self.refresh()
        spec = {
            "live_decay": ("decay", "Time (ns)", "Counts", False, self.decay_log_y),
            "live_correlation": ("correlation", "Lag (ms)", "G", self.corr_log_x, False),
            "live_count_rate": (
                "rate",
                "Macro time (s)",
                "Count rate (cps)",
                False,
                self.rate_log_y,
            ),
            "live_mcs": ("mcs", "Time (ms)", "Counts", False, False),
            "live_macrotime": (
                "macro",
                "Time (s)" if self.macro_type == "dt" else "Photon index",
                "dt (s)" if self.macro_type == "dt" else "Macro time (s)",
                False,
                False,
            ),
        }[name]
        key, xl, yl, logx, logy = spec
        series = self.series.get(key, [])
        self.drawn[key] = series
        height = max(160.0, float(im.get_content_region_avail()[1]) - 4.0)
        if implot.begin_plot(f"##{name}", (-1.0, height), implot.FLAGS_NO_TITLE):
            implot.setup_axes(xl, yl)
            if logx:
                implot.setup_axis_scale(implot.AXIS_X1, implot.SCALE_LOG10)
            if logy:
                implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
            if key == "mcs" and self.mcs_manual_y:
                implot.setup_axis_limits(
                    implot.AXIS_Y1, self.mcs_y_min, self.mcs_y_max, implot.COND_ALWAYS
                )
            for label, x, y in series:
                if len(x) and len(y):
                    if logy:
                        y = np.where(y > 0, y, np.nan)
                    implot.plot_line(label, x, y)
            if key == "rate":
                for index, mean in self.mean_lines.items():
                    implot.plot_inf_lines(
                        f"mean {self._rate_label(index)}",
                        [mean],
                        flags=implot.INF_LINES_FLAGS_HORIZONTAL,
                    )
            implot.end_plot()


def _bin(x: np.ndarray, y: np.ndarray, size: int) -> tuple[np.ndarray, np.ndarray]:
    """Average *size* consecutive points; a partial last bin is dropped."""
    if size <= 1 or len(y) < size:
        return x, y
    n = (len(y) // size) * size
    return x[:n].reshape(-1, size).mean(axis=1), y[:n].reshape(-1, size).mean(axis=1)


def stream_words(
    pipeline: Any,
    words: Any,
    events: Any,
    *,
    every: int = 8,
    chunk: int = 64,
    cancel: Any = None,
    pause_s: float = 0.0,
) -> None:
    """Push *words* through *pipeline* and publish a snapshot every *every* chunks.

    Runs on the worker thread (the pipeline is single-threaded); ``pipeline.snapshot()``
    builds plain data there and ``events.put(("snapshot", data))`` is the only
    crossing to the GUI thread. A final ``("result", ...)`` is left to the caller.
    """
    import time

    for n, start in enumerate(range(0, len(words), chunk), 1):
        if (cancel is not None and cancel.is_set()) or pipeline.stop_reason:
            break
        pipeline.push(words[start : start + chunk])
        if n % max(1, every) == 0:
            events.put(("snapshot", pipeline.snapshot()))
        if pause_s:
            time.sleep(pause_s)
