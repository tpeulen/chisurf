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

from chisurf.core.datastore import column_names, concat_stores, numeric_column, row_count
from chisurf.core.fluorescence.excitation import WindowsPreflightMixin, format_ranges

from ..api.models import FusionAnalysis

logger = logging.getLogger(__name__)

_VIEW_JSON = pathlib.Path(__file__).parent / "fusion.view.json"

#: Colours of the before/after overlays. Grey is "as selected", blue "as fused",
#: kept consistent across the three comparison plots.
_BEFORE = "#9e9e9e"
_AFTER = "#1f77b4"
_MARK = "#d62728"


class FusionViewModel(WindowsPreflightMixin):
    """State and logic of the Burst Fusion tool (no Qt)."""

    def view_spec(self):
        """Resolve AutoForm's view spec from the authored ``fusion.view.json``."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_VIEW_JSON)

    def __init__(self) -> None:
        from ..api.models import FusionSettings

        self.folder: str = ""
        #: The folder the current state belongs to; see :meth:`set_folder`.
        self._folder_applied: str = ""
        self.settings = FusionSettings()
        #: The loaded demo's record (path + declared truth), or ``None``.
        self._demo: dict | None = None

        #: Detector definition supplied by the embedding workflow (channel page).
        #: Without it the fused folder falls back to the source folder's manifest.
        self.detectors: dict[str, Any] = {}
        self.windows: dict[str, Any] = {}
        #: The definition the writer will regenerate the bursts with (the given one, or a legacy
        #: folder's recorded one), as resolved for the window pre-flight; ``None`` before.
        self._preflight_definition: dict[str, Any] | None = None
        #: The shared window check on the first measurement of the run (``None`` before one).
        self.windows_check = None
        #: Called with the written folder so an embedding workflow can point its
        #: downstream steps at the fused bursts instead of the original ones.
        self.folder_written: Callable[[str], None] | None = None

        self._analysis: FusionAnalysis | None = None
        self._status = "Select a burst-analysis folder and press Estimate (or Run)."
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
            self._status = "Settings changed — press Estimate (or Run)."
            self.notify("invalidated")

    # ── the demo ───────────────────────────────────────────────────────
    def load_demo(self, progress: Callable[[float, str], None] | None = None) -> str:
        """Generate (or reuse) the demo measurement and select its burst folder.

        The tour has to be walkable by someone who has not brought data yet, and
        fusion in particular cannot be judged without a number to check the
        result against — so the demo is a simulated measurement whose molecule
        count and split fraction are *declared*, put through the real burst
        search.

        Returns
        -------
        str
            The demo's burst run (``<analysis container>/<run>``).
        """
        from ..demo import demo_detectors, make_demo, read_demo

        result = read_demo(make_demo(progress=progress))
        # The demo enters the workspace as real data does: its photons a dataset, its burst search
        # a run of that dataset's analysis container -- and the tool fuses that run.
        run = demo_run(result)
        self._demo = dict(result, folder=run)
        # A run carries no detector setup (the workflow's channel definition supplies it): the
        # demo's own is set, so the fused bursts can be regenerated from its photons.
        self.detectors = dict(demo_detectors())
        self.windows = {}
        self.set_folder(run)
        self.notify("demo")
        return run

    @property
    def demo(self) -> dict | None:
        """Ground truth of the loaded demo, or ``None`` for a real folder."""
        if self._demo is None:
            return None
        if str(self._demo.get("folder", "")) != str(self.folder):
            return None
        return dict(self._demo)

    # ── folder ─────────────────────────────────────────────────────────
    def set_folder(self, folder: str) -> None:
        """Point the tool at a burst-analysis folder.

        Compared against what was last *applied*, not against ``self.folder``:
        AutoForm writes the bound attribute and only then calls this, so a guard
        on ``self.folder`` sees the new value already in place, returns early,
        and leaves the previous folder's analysis on screen under the new
        folder's name.
        """
        folder = str(folder or "")
        self.folder = folder
        if folder == self._folder_applied:
            return
        self._folder_applied = folder
        self._analysis = None
        self._emitted = None
        self._written = ""
        self.windows_check = None
        self._preflight_definition = None
        self._status = "Press Estimate to compute the same-molecule probability."
        self.notify("folder")

    def update(self) -> None:
        """AutoForm hook: a bound field wrote to the model."""
        self.notify("changed")

    # ── actions ────────────────────────────────────────────────────────
    def can_run(self) -> str | None:
        """Return ``None`` when a run is possible, else the reason it is not."""
        from ..core.fusion import is_run_source

        if not self.folder:
            return "Pick a burst run in the Input section first."
        if is_run_source(self.folder):
            from chisurf.core.fio.analysis_path import split_container_path

            container, _run = split_container_path(self.folder)
            return (
                None
                if container is not None and container.is_file()
                else (f"Not found: {self.folder}")
            )
        if not pathlib.Path(self.folder).is_dir():
            return f"Not a folder: {self.folder}"
        return None

    def analyze(self, cancel_check=None) -> FusionAnalysis:
        """Estimate ``P_same`` and the fusion the current threshold implies (and return it)."""
        reason = self.can_run()
        if reason is not None:
            raise ValueError(reason)
        from ..core.fusion import analyze

        analysis = analyze(
            pathlib.Path(self.folder),
            self.settings,
            **({"cancel_check": cancel_check} if callable(cancel_check) else {}),
        )
        self._analysis = analysis
        self._emitted = None
        self.check_windows(analysis)
        stats = analysis.statistics
        self._status = (
            f"{stats['n_bursts_before']} -> {stats['n_bursts_after']} bursts; "
            f"gaps fused up to {analysis.tau_used_s * 1e3:.3f} ms."
        )
        logger.info("Burst fusion: %s", self._status)
        self.notify("analyzed")
        return analysis

    def fuse(self) -> str:
        """Fuse and write in one action — what *running* this step means.

        The step's primary action has to be the one that produces its output.
        Estimating the probability changes nothing on disk and hands nothing to
        the later steps, so a workflow in which "run" only estimated would leave
        a user who pressed Run and moved on analysing the *un-fused* bursts,
        with no sign that the step had not taken effect.
        """
        self.analyze()
        return self.write()

    def write(self) -> str:
        """Write the fused bursts (a new run of the container, or a legacy folder) and return
        its address."""
        analysis = self._analysis if self._analysis is not None else self.analyze()
        from ..core.fusion import write_fused_analysis, write_fused_runs

        if analysis.sources:
            # A run of the project's analysis container: the fused bursts are a new run of it.
            result = write_fused_runs(
                analysis, detectors=self.detectors or None, windows=self.windows or None
            )
            self._written = str(result["output_folder"])
            self._emitted = self._read_runs(result.get("runs") or [])
            self._register_runs(result.get("runs") or [])
        else:
            result = write_fused_analysis(
                analysis,
                detectors=self.detectors or None,
                windows=self.windows or None,
            )
            self._written = str(result["output_folder"])
            self._emitted = self._read_written(result.get("bur_files") or [])
        self._status = f"Fused bursts written to {self._written}"
        for warning in result.get("warnings") or []:
            self._status += f" Warning: {warning}"
        logger.info("Burst fusion: %s", self._status)
        if callable(self.folder_written):
            try:
                self.folder_written(self._written)
            except Exception:
                logger.warning("burst fusion: folder handoff failed", exc_info=True)
        self.notify("written")
        return self._written

    # ── the excitation windows against the photons (the shared pre-flight) ──
    def check_windows(self, analysis: FusionAnalysis | None = None) -> str | None:
        """Hold the windows the fused bursts will be regenerated with against the first
        measurement's micro time; the line for the status (``None``: fine or nothing to check)."""
        from ..core.fusion import preflight_source

        analysis = analysis if analysis is not None else self._analysis
        source = (
            preflight_source(
                analysis, detectors=self.detectors or None, windows=self.windows or None
            )
            if analysis is not None
            else None
        )
        if source is None:
            self.windows_check = None
            self._preflight_definition = None
            return None
        self._preflight_definition = {
            "detectors": source["detectors"],
            "windows": source["windows"],
        }
        return self.run_windows_preflight(source["tttr"])

    def preflight_setup(self) -> dict:
        """The definition the writer uses, for the shared window pre-flight.

        No channel width is given: the writer applies the windows as raw channels of the
        measurement, so that is how they are checked.
        """
        definition = self._preflight_definition or {
            "detectors": self.detectors,
            "windows": self.windows,
        }
        return {
            "detectors": dict(definition.get("detectors") or {}),
            "windows": dict(definition.get("windows") or {}),
        }

    def take_preflight_setup(self, setup: dict) -> None:
        """Regenerate the fused bursts with the detected windows (and opened gates)."""
        self.detectors = dict(setup.get("detectors") or {})
        self.windows = {k: [int(v[0]), int(v[1])] for k, v in (setup.get("windows") or {}).items()}
        self._preflight_definition = {"detectors": self.detectors, "windows": self.windows}
        self._status = "Windows from the data: " + format_ranges(self.windows)
        self.notify("changed")

    def _read_runs(self, runs) -> list | None:
        """Read the fused runs back the way every burst tool reads a run (the plots show them)."""
        from chisurf.core.fio.fluorescence.burst import _read_burst_analysis_from_container

        frames = []
        for run in runs:
            try:
                frames.append(_read_burst_analysis_from_container(pathlib.Path(run))[0])
            except Exception:
                logger.warning("burst fusion: could not read back %s", run, exc_info=True)
                return None
        return frames or None

    @staticmethod
    def _register_runs(runs) -> None:
        """The fused runs enter the workspace as children of the photon dataset they belong to
        (whose analysis container they are in); outside a session nothing is registered."""
        from chisurf.core.fio.analysis_path import split_container_path
        from chisurf.core.plugin.workspace_input import register_result
        from chisurf.core.project.analysis import is_derived

        for run in runs:
            container, _name = split_container_path(run)
            owner = container.parent.name if container is not None and is_derived(container) else ""
            try:
                register_result(run, kind="bursts", result_of="" if owner == "_" else owner)
            except Exception:  # noqa: BLE001 - the run is written; only its row is missing
                logger.warning(
                    "burst fusion: could not add %s to the workspace", run, exc_info=True
                )

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
        """Return the frames the "after" curves are drawn from, and what to call them.

        Before writing, the fused side is the table-level preview: the fragments'
        own photons, summed. After writing it is the emitted table, which also
        counts the photons *between* the fragments — a fused burst is one
        interval on disk. The label says which is on screen, because the two
        genuinely differ and the difference is the cost of fusing.
        """
        if self._emitted:
            return "fused (written)", self._emitted
        if self._analysis is None:
            return "fused (preview)", []
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
        """Status for the info block, with the demo's truth when one is loaded."""
        demo = self._demo_line()
        # The verdict itself is the info line under this block; the status names it, once.
        windows = (
            f"<br/>Warning: {self.windows_check_text().split(':', 1)[0]} -- see below."
            if self.windows_check_offer
            else ""
        )
        if self._analysis is None:
            return demo + f"<i>{self._status}</i>" + windows
        window = self._analysis.window
        stats = self._analysis.statistics
        lines = [
            f"<b>P(same molecule) &ge; {window.threshold:.2f}</b> holds out to "
            f"<b>{window.tau_max_s * 1e3:.3f} ms</b>"
            + (
                ""
                if window.resolved
                else " <span style='color:#d62728'>(never crossed — "
                "the curve stays above the threshold over the whole lag range)</span>"
            ),
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
        elif self._status.startswith("Windows from the data"):
            lines.append(self._status)
        return demo + "<br/>".join(lines) + windows

    def _demo_line(self) -> str:
        """Return the loaded demo's declared truth, or an empty string for real data.

        Kept at the top of the status block on purpose: the whole value of the
        demo is that the number the analysis should be approaching is on screen
        beside the number it reports.
        """
        demo = self.demo
        if demo is None:
            return ""
        from ..demo import describe

        return f"{describe(demo)}<br/>"

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

        out = []
        for name, colour, frames in self._sides():
            values = concat_stores(frames)
            if column not in column_names(values):
                continue
            numbers = numeric_column(values, column)
            if log:
                numbers = np.log10(np.clip(numbers, 1e-3, None))
            centers, density = self._histogram(numbers, bins, limits)
            out.append({"x": centers, "y": density, "name": name, "color": colour, "width": 2})
        return out

    def proximity_series(self) -> list[dict]:
        """Proximity-ratio histogram before and after fusion."""
        if self._analysis is None:
            return []

        from ..core.fusion import proximity_ratios

        out = []
        for name, colour, frames in self._sides():
            frame = concat_stores(frames)
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
        sizes = (
            np.concatenate(
                [
                    np.bincount(np.asarray(m.labels, dtype=int))
                    for m in self._analysis.measurements
                    if len(m.labels)
                ]
            )
            if self._analysis.measurements
            else np.zeros(0)
        )
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
        """Return the before/after table: one row per observable the user judges by.

        Read off the same frames the plots use, so the table and the histograms
        cannot disagree about whether the "after" side is the preview or what was
        actually written.
        """
        if self._analysis is None:
            return []

        from ..core.fusion import proximity_ratios

        stats = self._analysis.statistics
        (_, _, before_frames), (_, _, after_frames) = self._sides()
        before = concat_stores(before_frames)
        after = concat_stores(after_frames)

        def _finite(frame, column):
            if column not in column_names(frame):
                return np.zeros(0)
            values = numeric_column(frame, column)
            return values[np.isfinite(values)]

        def _row(name, before_value, after_value):
            """Return one table row.

            The unit belongs in the name, not in a column of its own: only two of
            eleven rows have one, so the column was mostly empty and cost the
            panel width it does not have to spare.
            """

            def _text(value):
                if isinstance(value, float):
                    return "—" if not np.isfinite(value) else f"{value:.4g}"
                return str(value)

            return {
                "quantity": name,
                "before": _text(before_value),
                "after": _text(after_value),
            }

        def _pair(name, column, statistic="mean"):
            values = [_finite(before, column), _finite(after, column)]
            function = np.median if statistic == "median" else np.mean
            numbers = [float(function(v)) if v.size else float("nan") for v in values]
            return _row(name, numbers[0], numbers[1])

        ratios = []
        for frame in (before, after):
            values = proximity_ratios(frame)
            values = np.asarray(values, dtype=float) if values is not None else np.zeros(0)
            ratios.append(values[np.isfinite(values)])

        return [
            _row("Bursts", row_count(before), row_count(after)),
            _row(
                "PR mean",
                float(ratios[0].mean()) if ratios[0].size else float("nan"),
                float(ratios[1].mean()) if ratios[1].size else float("nan"),
            ),
            _row(
                "PR width (std)",
                float(ratios[0].std()) if ratios[0].size else float("nan"),
                float(ratios[1].std()) if ratios[1].size else float("nan"),
            ),
            _pair("Photons (mean)", "Number of Photons"),
            _pair("Photons (med)", "Number of Photons", statistic="median"),
            _pair("Duration (ms)", "Duration (ms)"),
            _pair("Rate (kHz)", "Count Rate (KHz)"),
            _row("Fused groups", "—", stats["n_fused_groups"]),
            _row("Largest fused", "—", f"{stats['largest_group']} frag."),
            _row("Bursts fused", "—", f"{stats['fused_fraction'] * 100:.1f} %"),
            _row(
                "Window, ms",
                f"{self._analysis.window.tau_max_s * 1e3:.4g}",
                f"{self._analysis.tau_used_s * 1e3:.4g}",
            ),
        ]


__all__ = ["FusionViewModel"]


def demo_run(demo: dict) -> str:
    """Put the demo into the workspace and return its burst run's address.

    The photons (the demo's ``.ht3``) become a dataset; the burst search the demo ran becomes a run
    of that dataset's analysis container (photons linked), the run row its child. Outside a session
    the container is still written -- in this process's analysis folder -- and its run returned.
    """
    from chisurf.core.fio.classify import container_entries
    from chisurf.core.fio.fluorescence.burst import read_bur_file
    from chisurf.core.fio.fluorescence.burst_container import deinterleave_bursts
    from chisurf.core.plugin.workspace_input import register_result
    from chisurf.core.project.analysis import container_dir
    from chisurf.plugins.burst.burst_selection.api.io import write_container

    folder = pathlib.Path(str(demo["folder"]))
    photons = pathlib.Path(str(demo["source"]))
    uid = ""
    try:
        stream = register_result(str(photons), kind="photons", name=photons.name)
        uid = str(getattr(stream, "unique_identifier", "") or "")
    except Exception:  # noqa: BLE001 - no session: the run is still written and fused
        logger.debug("burst fusion: demo photons not added to the workspace", exc_info=True)
    bur = sorted((folder / "bi4_bur").glob("*.bur"))[0]
    container = write_container(
        photons,
        deinterleave_bursts(read_bur_file(bur)),
        parameters={"demo": folder.name},
        out_dir=container_dir(uid),
        run=folder.name,
        raw_data="sidecar",
    )
    runs = [address for kind, address in container_entries(container) if kind == "bursts"]
    run = next((r for r in runs if r.endswith(folder.name)), runs[-1])
    if uid:
        try:
            register_result(run, kind="bursts", result_of=uid)
        except Exception:  # noqa: BLE001 - the run exists; only its row is missing
            logger.debug("burst fusion: demo run not added to the workspace", exc_info=True)
    return run
