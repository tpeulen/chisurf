"""Qt-free view-model behind the Burst Fusion tool.

Holds the source folder, the fusion settings and the last analysis, and exposes
the plot/table/summary accessors the ``fusion.view.json`` layout binds to. All
computation lives in :mod:`..core.fusion`; this class only decides *when* to run
it and how to phrase the result.

The split between the two buttons is the point of the tool:

* **Analyze** runs on the burst *table* alone. It is fast, touches no photons,
  and answers "what would this threshold do?" — the ``P_same`` curve, the
  window it implies, and what happens to the burst count, the photon counts and
  the proximity ratio. A threshold is meant to be tried several times here.
* **Write fused folder** reopens the photon streams and emits the new burst
  folder. That is the slow, irreversible half, and it is deliberately a separate
  press.
"""

from __future__ import annotations

import logging
import pathlib
from collections.abc import Callable
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

_VIEW_JSON = pathlib.Path(__file__).parent / "fusion.view.json"

#: Colours of the before/after overlays. Grey is "as selected", blue "as fused",
#: kept consistent across the three comparison plots.
_BEFORE = "#9e9e9e"
_AFTER = "#1f77b4"
_MARK = "#d62728"


class FusionViewModel:
    """State and logic of the Burst Fusion tool (no Qt)."""

    def view_spec(self):
        """Resolve AutoForm's view spec from the authored ``fusion.view.json``."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_VIEW_JSON)

    def __init__(self) -> None:
        from ..api.models import FusionSettings

        self.folder: str = ""
        self.settings = FusionSettings()

        #: Detector definition supplied by the embedding workflow (channel page).
        #: Without it the fused folder falls back to the source folder's manifest.
        self.detectors: dict[str, Any] = {}
        self.windows: dict[str, Any] = {}
        #: Called with the written folder so an embedding workflow can point its
        #: downstream steps at the fused bursts instead of the original ones.
        self.folder_written: Callable[[str], None] | None = None

        self._analysis = None
        self._status = "Select a burst-analysis folder and press Analyze."
        self._written: str = ""
        #: The burst tables actually written, read back so the "after" curves stop
        #: being a preview: the emitted bursts contain the photons *between* the
        #: fragments as well, which the table-level preview cannot know about.
        self._emitted: list | None = None
        self._observers: list[Callable[[str], None]] = []

    # ── bound settings (flat, so the view spec stays declarative) ───────
    @property
    def threshold(self) -> float:
        """Same-molecule probability required to fuse two bursts."""
        return float(self.settings.threshold)

    @threshold.setter
    def threshold(self, value: float) -> None:
        self.settings.threshold = float(value)
        self._invalidate()

    @property
    def max_gap_ms(self) -> float:
        """Hard ceiling on the gap fusion may bridge (ms; 0 = none)."""
        return float(self.settings.max_gap_ms)

    @max_gap_ms.setter
    def max_gap_ms(self, value: float) -> None:
        self.settings.max_gap_ms = float(value)
        self._invalidate()

    @property
    def max_group(self) -> int:
        """Largest number of bursts one fused burst may contain (0 = no limit)."""
        return int(self.settings.max_group)

    @max_group.setter
    def max_group(self, value: int) -> None:
        self.settings.max_group = int(value)
        self._invalidate()

    @property
    def tau_min_ms(self) -> float:
        """Shortest lag of the P_same estimate, in milliseconds."""
        return float(self.settings.tau_min_s * 1e3)

    @tau_min_ms.setter
    def tau_min_ms(self, value: float) -> None:
        self.settings.tau_min_s = max(float(value), 1e-6) * 1e-3
        self._invalidate()

    @property
    def tau_max_ms(self) -> float:
        """Longest lag of the P_same estimate, in milliseconds."""
        return float(self.settings.tau_max_s * 1e3)

    @tau_max_ms.setter
    def tau_max_ms(self, value: float) -> None:
        self.settings.tau_max_s = max(float(value), 1e-3) * 1e-3
        self._invalidate()

    @property
    def n_bins(self) -> int:
        """Number of logarithmic lag bins of the P_same estimate."""
        return int(self.settings.n_bins)

    @n_bins.setter
    def n_bins(self, value: int) -> None:
        self.settings.n_bins = int(value)
        self._invalidate()

    @property
    def min_pairs(self) -> int:
        """Burst pairs a lag bin needs before it may end the fusion window."""
        return int(self.settings.min_pairs)

    @min_pairs.setter
    def min_pairs(self, value: int) -> None:
        self.settings.min_pairs = int(value)
        self._invalidate()

    @property
    def pool_measurements(self) -> bool:
        """Estimate one P_same curve for the whole folder rather than per file."""
        return bool(self.settings.pool_measurements)

    @pool_measurements.setter
    def pool_measurements(self, value: bool) -> None:
        self.settings.pool_measurements = bool(value)
        self._invalidate()

    @property
    def write_source_companion(self) -> bool:
        """Also record the grouping beside the original bursts (``fg4``)."""
        return bool(self.settings.write_source_companion)

    @write_source_companion.setter
    def write_source_companion(self, value: bool) -> None:
        self.settings.write_source_companion = bool(value)

    # ── observers ──────────────────────────────────────────────────────
    def add_observer(self, callback: Callable[[str], None]) -> None:
        """Register *callback*, called with an event name on every change."""
        self._observers.append(callback)

    def notify(self, event: str = "changed") -> None:
        """Notify observers that the model changed."""
        for callback in list(self._observers):
            try:
                callback(event)
            except Exception:
                logger.debug("burst fusion: observer failed", exc_info=True)

    def _invalidate(self) -> None:
        """Drop a stale analysis when a setting that shaped it changed."""
        if self._analysis is not None:
            self._analysis = None
            self._emitted = None
            self._status = "Settings changed — press Analyze."
            self.notify("invalidated")

    # ── folder ─────────────────────────────────────────────────────────
    def set_folder(self, folder: str) -> None:
        """Point the tool at a burst-analysis folder."""
        folder = str(folder or "")
        if folder == self.folder:
            return
        self.folder = folder
        self._analysis = None
        self._emitted = None
        self._written = ""
        self._status = "Press Analyze to estimate the same-molecule probability."
        self.notify("folder")

    def update(self) -> None:
        """AutoForm hook: a bound field wrote to the model."""
        self.notify("changed")

    # ── actions ────────────────────────────────────────────────────────
    def can_run(self) -> str | None:
        """Return ``None`` when a run is possible, else the reason it is not."""
        if not self.folder:
            return "Select a burst-analysis folder first."
        if not pathlib.Path(self.folder).is_dir():
            return f"Not a folder: {self.folder}"
        return None

    def analyze(self) -> None:
        """Estimate ``P_same`` and the fusion the current threshold implies."""
        reason = self.can_run()
        if reason is not None:
            raise ValueError(reason)
        from ..core.fusion import analyze

        self._analysis = analyze(pathlib.Path(self.folder), self.settings)
        self._emitted = None
        stats = self._analysis.statistics
        self._status = (
            f"{stats['n_bursts_before']} -> {stats['n_bursts_after']} bursts; "
            f"gaps fused up to {self._analysis.tau_used_s * 1e3:.3f} ms."
        )
        logger.info("Burst fusion: %s", self._status)
        self.notify("analyzed")

    def write(self) -> str:
        """Write the fused bursts as a new burst folder and return its path."""
        if self._analysis is None:
            self.analyze()
        from ..core.fusion import write_fused_analysis

        result = write_fused_analysis(
            self._analysis,
            detectors=self.detectors or None,
            windows=self.windows or None,
        )
        self._written = str(result["output_folder"])
        self._emitted = self._read_written(result.get("bur_files") or [])
        self._status = f"Fused bursts written to {self._written}"
        logger.info("Burst fusion: %s", self._status)
        if callable(self.folder_written):
            try:
                self.folder_written(self._written)
            except Exception:
                logger.warning("burst fusion: folder handoff failed", exc_info=True)
        self.notify("written")
        return self._written

    def _read_written(self, paths) -> list | None:
        """Read the emitted burst tables back, so the plots show what was written."""
        from chisurf.core.fio.fluorescence.burst import read_bur_file

        from ..core.fusion import data_rows

        frames = []
        for path in paths:
            try:
                frames.append(data_rows(read_bur_file(path)))
            except Exception:
                logger.warning("burst fusion: could not read back %s", path, exc_info=True)
                return None
        return frames or None

    def _fused_frames(self) -> tuple[str, list]:
        """The frames the "after" curves are drawn from, and what to call them.

        Before writing, the fused side is the table-level preview: the fragments'
        own photons, summed. After writing it is the emitted table, which also
        counts the photons *between* the fragments — a fused burst is one
        interval on disk. The label says which is on screen, because the two
        genuinely differ and the difference is the cost of fusing.
        """
        if self._emitted:
            return "fused (written)", self._emitted
        return "fused (preview)", [m.fused for m in self._analysis.measurements]

    def has_analysis(self) -> bool:
        """Whether an analysis has been run for the current settings."""
        return self._analysis is not None

    @property
    def written_folder(self) -> str:
        """The fused folder written by the last run (empty before the first)."""
        return self._written

    @property
    def analysis(self):
        """The last :class:`~..api.models.FusionAnalysis`, or ``None``."""
        return self._analysis

    # ── AutoForm accessors ─────────────────────────────────────────────
    def status_text(self) -> str:
        """One-line status for the info block."""
        if self._analysis is None:
            return f"<i>{self._status}</i>"
        window = self._analysis.window
        stats = self._analysis.statistics
        lines = [
            f"<b>P(same molecule) &ge; {window.threshold:.2f}</b> holds out to "
            f"<b>{window.tau_max_s * 1e3:.3f} ms</b>"
            + ("" if window.resolved else " <span style='color:#d62728'>(never crossed — "
               "the curve stays above the threshold over the whole lag range)</span>"),
        ]
        if stats["gap_capped"]:
            lines.append(
                f"Capped at the <b>{self.settings.max_gap_ms:g} ms</b> gap ceiling, so bursts "
                f"further apart than that stay separate."
            )
        lines.append(
            f"<b>{stats['n_bursts_before']} &rarr; {stats['n_bursts_after']}</b> bursts "
            f"({stats['n_fused_groups']} fused, largest {stats['largest_group']} fragments)."
        )
        if self._written:
            lines.append(f"Written to <code>{self._written}</code>")
        return "<br/>".join(lines)

    def p_same_series(self) -> list[dict]:
        """``P_same`` vs lag, with the threshold and the fused window marked."""
        if self._analysis is None:
            return []
        window = self._analysis.window
        tau_ms = np.asarray(window.tau_s, dtype=float) * 1e3
        p = np.asarray(window.p_same, dtype=float)
        finite = np.isfinite(p)
        series = [
            {
                "x": tau_ms[finite],
                "y": p[finite],
                "name": "P(same molecule)",
                "color": _AFTER,
                "width": 2,
            },
            {
                "x": np.array([tau_ms[0], tau_ms[-1]]),
                "y": np.full(2, window.threshold),
                "name": f"threshold {window.threshold:.2f}",
                "color": _MARK,
                "width": 1,
                "style": "dash",
            },
        ]
        used = self._analysis.tau_used_s * 1e3
        if used > 0:
            series.append(
                {
                    "x": np.array([used, used]),
                    "y": np.array([0.0, 1.0]),
                    "name": f"fused up to {used:.3g} ms",
                    "color": _MARK,
                    "width": 2,
                    "style": "dot",
                }
            )
        return series

    def _histogram(self, values, bins, limits) -> tuple:
        """Unit-area histogram of the finite entries of *values*."""
        values = np.asarray(values, dtype=float)
        values = values[np.isfinite(values)]
        edges = np.linspace(limits[0], limits[1], bins + 1)
        centers = 0.5 * (edges[:-1] + edges[1:])
        if values.size == 0:
            return centers, np.zeros(bins)
        density, _ = np.histogram(values, bins=edges, density=True)
        return centers, density

    def _sides(self):
        """``(label, colour, frames)`` for the before and after side of a plot."""
        after_label, after_frames = self._fused_frames()
        return (
            ("as selected", _BEFORE, [m.source for m in self._analysis.measurements]),
            (after_label, _AFTER, after_frames),
        )

    def _column_series(self, column: str, limits, bins: int = 60, log: bool = False):
        """Before/after histogram overlay of one burst-table column."""
        if self._analysis is None:
            return []
        import pandas as pd

        out = []
        for name, colour, frames in self._sides():
            values = pd.concat(frames, ignore_index=True)
            if column not in values.columns:
                continue
            numbers = pd.to_numeric(values[column], errors="coerce").to_numpy(dtype=float)
            if log:
                numbers = np.log10(np.clip(numbers, 1e-3, None))
            centers, density = self._histogram(numbers, bins, limits)
            out.append({"x": centers, "y": density, "name": name, "color": colour, "width": 2})
        return out

    def proximity_series(self) -> list[dict]:
        """Proximity-ratio histogram before and after fusion."""
        if self._analysis is None:
            return []
        import pandas as pd

        from ..core.fusion import proximity_ratios

        out = []
        for name, colour, frames in self._sides():
            frame = pd.concat(frames, ignore_index=True)
            values = proximity_ratios(frame)
            if values is None:
                continue
            centers, density = self._histogram(values, 60, (-0.1, 1.1))
            out.append({"x": centers, "y": density, "name": name, "color": colour, "width": 2})
        return out

    def photon_series(self) -> list[dict]:
        """Photons-per-burst histogram (log10) before and after fusion."""
        return self._column_series("Number of Photons", (0.5, 4.5), bins=60, log=True)

    def duration_series(self) -> list[dict]:
        """Burst-duration histogram (log10 ms) before and after fusion."""
        return self._column_series("Duration (ms)", (-2.0, 3.0), bins=60, log=True)

    def group_size_series(self) -> list[dict]:
        """How many fused bursts contain 1, 2, 3 … original bursts."""
        if self._analysis is None:
            return []
        sizes = np.concatenate(
            [
                np.bincount(np.asarray(m.labels, dtype=int))
                for m in self._analysis.measurements
                if len(m.labels)
            ]
        ) if self._analysis.measurements else np.zeros(0)
        if sizes.size == 0:
            return []
        top = int(sizes.max())
        counts = np.bincount(sizes.astype(int), minlength=top + 1)[1:]
        return [
            {
                "x": np.arange(1, top + 1, dtype=float),
                "y": counts.astype(float),
                "name": "fused bursts",
                "color": _AFTER,
                "width": 2,
            }
        ]

    def summary_rows(self) -> list[dict]:
        """The before/after table: one row per observable the user judges by.

        Read off the same frames the plots use, so the table and the histograms
        cannot disagree about whether the "after" side is the preview or what was
        actually written.
        """
        if self._analysis is None:
            return []
        import pandas as pd

        from ..core.fusion import proximity_ratios

        stats = self._analysis.statistics
        (_, _, before_frames), (_, _, after_frames) = self._sides()
        before = pd.concat(before_frames, ignore_index=True)
        after = pd.concat(after_frames, ignore_index=True)

        def _finite(frame, column):
            if column not in frame.columns:
                return np.zeros(0)
            values = pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=float)
            return values[np.isfinite(values)]

        def _row(name, before_value, after_value, unit=""):
            def _text(value):
                if isinstance(value, float):
                    return "—" if not np.isfinite(value) else f"{value:.4g}"
                return str(value)

            return {
                "quantity": name,
                "before": _text(before_value),
                "after": _text(after_value),
                "unit": unit,
            }

        def _pair(name, column, unit="", statistic="mean"):
            values = [_finite(before, column), _finite(after, column)]
            function = np.median if statistic == "median" else np.mean
            numbers = [float(function(v)) if v.size else float("nan") for v in values]
            return _row(name, numbers[0], numbers[1], unit)

        ratios = []
        for frame in (before, after):
            values = proximity_ratios(frame)
            values = np.asarray(values, dtype=float) if values is not None else np.zeros(0)
            ratios.append(values[np.isfinite(values)])

        return [
            _row("Bursts", len(before), len(after)),
            _row(
                "Proximity ratio (mean)",
                float(ratios[0].mean()) if ratios[0].size else float("nan"),
                float(ratios[1].mean()) if ratios[1].size else float("nan"),
            ),
            _row(
                "Proximity ratio (std)",
                float(ratios[0].std()) if ratios[0].size else float("nan"),
                float(ratios[1].std()) if ratios[1].size else float("nan"),
            ),
            _pair("Photons per burst (mean)", "Number of Photons"),
            _pair("Photons per burst (median)", "Number of Photons", statistic="median"),
            _pair("Duration (mean)", "Duration (ms)", "ms"),
            _pair("Count rate (mean)", "Count Rate (KHz)", "kHz"),
            _row("Fused groups", "—", stats["n_fused_groups"]),
            _row("Largest fused burst", "—", f"{stats['largest_group']} fragments"),
            _row("Bursts fused", "—", f"{stats['fused_fraction'] * 100:.1f} %"),
            _row(
                "Fused window",
                f"{self._analysis.window.tau_max_s * 1e3:.4g} ms",
                f"{self._analysis.tau_used_s * 1e3:.4g} ms",
            ),
        ]


__all__ = ["FusionViewModel"]
