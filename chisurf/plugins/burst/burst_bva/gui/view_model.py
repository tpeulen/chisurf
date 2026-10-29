"""Qt-free view-model behind the Burst Variance Analysis (BVA) tool.

Holds the source folder, BVA settings, and last computed BVA results,
and produces the plot coordinates for EMTK immediate-mode rendering.
"""

from __future__ import annotations

import logging
import pathlib
from typing import Any, Callable

import numpy as np

from chisurf.core.datastore import numeric_column, row_count
from chisurf.core.fio.fluorescence.burst_manifest import source_inputs
from chisurf.core.fluorescence.excitation import WindowsPreflightMixin
from chisurf.core.runtime import analysis_cache
from chisurf.plugins.burst.burst_bva.core import computation as core
from chisurf.plugins.burst.burst_bva.core import windows

ALGORITHM_VERSION = 1
logger = logging.getLogger(__name__)


class BvaViewModel(WindowsPreflightMixin):
    """Toolkit-free view model for BVA analysis.

    The excitation-window pre-flight (:class:`WindowsPreflightMixin`) holds the donor and acceptor
    micro-time ranges against the excitation pulses of the measurements each run reads; *Use
    detected windows* takes the detected gates into the ranges (the burst table does not depend
    on them, so the next run reproduces the analysis with them).
    """

    def __init__(self) -> None:
        self.data_folder: pathlib.Path | None = None
        self.analysis_folder: pathlib.Path | None = None
        self.file_type: str = "SPC-130"

        # Parameters
        self.window_length: float = 0.01
        self.photons_per_slice: int = 10
        self.bins_x: int = 51
        self.bins_y: int = 51
        self.show_static_line: bool = True
        self.auto_update: bool = True

        # Channels
        self.donor_channels_text: str = "0,8"
        self.acceptor_channels_text: str = "1,9"
        self.donor_micro_time_ranges: list[tuple[int, int]] = [(0, 32768)]
        self.acceptor_micro_time_ranges: list[tuple[int, int]] = [(0, 32768)]
        #: The setup the pair was picked from (``{name: {chs, micro_time_ranges}}``) and the names
        #: of the donor and acceptor detectors in it: its detectors on the same routing channels
        #: are checked with the pair (PIE's prompt/delayed split of one detector).
        self.setup_detectors: dict[str, dict] = {}
        self.pair_names: tuple[str, str] = ("donor", "acceptor")

        # The excitation-window pre-flight of the last run (one line per measurement).
        self.windows_check = None
        self.windows_warnings: list[str] = []
        self._checked: tuple[str, dict] | None = None

        # State and results
        self.df: Any | None = None
        self.burst_df: Any | None = None
        self.tttrs: Any | None = None
        self.status_text: str = "Ready"
        self.is_running: bool = False
        #: A run was skipped as unchanged: Restart is what recomputes it.
        self.restart_attention: bool = False

        self._observers: list[Callable[[str], None]] = []

    def add_observer(self, callback: Callable[[str], None]) -> None:
        if callback not in self._observers:
            self._observers.append(callback)

    def remove_observer(self, callback: Callable[[str], None]) -> None:
        if callback in self._observers:
            self._observers.remove(callback)

    def on_param_edited(self, *_args) -> None:
        """A spin field committed an analysis parameter (view-form ``call`` hook)."""
        self.notify("param")

    def on_bins_edited(self, *_args) -> None:
        """A spin field committed a bin count (view-form ``call`` hook)."""
        self.notify("bins")

    def notify(self, event: str = "change") -> None:
        for obs in list(self._observers):
            try:
                obs(event)
            except Exception:
                logger.warning("BvaViewModel observer failed", exc_info=True)

    @staticmethod
    def parse_channels(text: str) -> list[int]:
        return [int(x) for x in str(text).split(",") if x.strip()]

    @property
    def donor_channels(self) -> list[int]:
        try:
            return self.parse_channels(self.donor_channels_text)
        except Exception:
            return [0, 8]

    @property
    def acceptor_channels(self) -> list[int]:
        try:
            return self.parse_channels(self.acceptor_channels_text)
        except Exception:
            return [1, 9]

    def _drop_bursts(self) -> None:
        """Forget the burst table read for the previous input.

        Both runs reuse ``burst_df``/``tttrs`` instead of re-reading; kept across a
        folder change, the next run computed the new folder's BVA on the old bursts.
        """
        self.burst_df = self.tttrs = self.df = None
        self.windows_check, self.windows_warnings, self._checked = None, [], None

    def set_folder(self, folder: str | pathlib.Path | None) -> None:
        if folder is None or not str(folder).strip():
            new = None
        else:
            new = pathlib.Path(folder)
        if new != self.analysis_folder:
            self._drop_bursts()
        self.data_folder = self.analysis_folder = new
        self.notify("folder")

    def apply_channel_settings(self, settings: dict) -> None:
        """Take a workflow's detector definition: the green/donor and red/acceptor detectors' channels and
        micro-time ranges, and the file type (the burst workflow hands its setup over this way)."""
        from chisurf.core.fluorescence.burst.table import fret_detectors

        settings = dict(settings or {})
        found = fret_detectors(settings)
        detectors = dict(settings.get("detectors") or {})
        self.setup_detectors = {str(k): dict(v) for k, v in detectors.items() if isinstance(v, dict)}
        names = list(self.pair_names)
        for i, role in enumerate(("donor", "acceptor")):
            if role in found:
                names[i] = next((n for n, d in self.setup_detectors.items() if d == found[role]),
                                names[i])
        self.pair_names = (names[0], names[1])
        for role in ("donor", "acceptor"):
            if role in found:
                d = found[role]
                setattr(self, f"{role}_channels_text", ",".join(str(c) for c in d.get("chs", [])))
                setattr(self, f"{role}_micro_time_ranges", d.get("micro_time_ranges", [(0, 32768)]))
        file_type = (settings.get("tttr_reading") or {}).get("file_type")
        if file_type:
            self.file_type = file_type
        self.notify("detector_settings")

    def set_file_type(self, file_type: str) -> None:
        """Change the photon-file type the bursts are read with (drops the read table)."""
        if file_type != self.file_type:
            self._drop_bursts()
        self.file_type = file_type
        self.notify("file_type")

    def bva_settings(self) -> dict[str, Any]:
        return {
            "donor_channels": self.donor_channels,
            "donor_micro_time_ranges": self.donor_micro_time_ranges,
            "acceptor_channels": self.acceptor_channels,
            "acceptor_micro_time_ranges": self.acceptor_micro_time_ranges,
            "minimum_window_length": float(self.window_length),
            "number_of_photons_per_slice": int(self.photons_per_slice),
            "file_type": self.file_type.strip(),
        }

    # -- the excitation windows against the data (the shared pre-flight) ---------------------- #
    def preflight_setup(self) -> dict:
        """The detectors BVA applies: the donor and acceptor streams as setup gates, with the
        setup's detectors that share their routing channels."""
        donor, acceptor = self.pair_names
        return {
            "detectors": windows.preflight_detectors(
                {
                    donor: (self.donor_channels, self.donor_micro_time_ranges),
                    acceptor: (self.acceptor_channels, self.acceptor_micro_time_ranges),
                },
                self.setup_detectors,
            )
        }

    def take_preflight_setup(self, setup: dict) -> None:
        """The user took the detected gates: they become the donor and acceptor ranges of the
        next run (inclusive, as BVA applies them)."""
        detectors = setup.get("detectors") or {}
        for role, name in zip(("donor", "acceptor"), self.pair_names):
            gates = (detectors.get(name) or {}).get("micro_time_ranges")
            if gates:
                setattr(self, f"{role}_micro_time_ranges", windows.from_setup_gates(gates))
        self.windows_warnings, self._checked = [], None
        self.status_text = "Micro-time ranges from the data: " + "; ".join(
            f"{role} " + ", ".join(f"{lo}:{hi}" for lo, hi in getattr(self, f"{role}_micro_time_ranges"))
            for role in ("donor", "acceptor")
        ) + "."
        self.notify("channel")

    def check_windows(self, tttrs: Any) -> tuple[str, dict]:
        """The pre-flight of the current ranges on every measurement in *tttrs*: ``(key,
        checks)`` for :meth:`set_window_checks` (not repeated while the ranges are unchanged)."""
        detectors = self.preflight_setup()["detectors"]
        key = repr(sorted(detectors.items()))
        if self._checked is not None and self._checked[0] == key:
            return self._checked
        return key, windows.window_checks(dict(tttrs or {}), detectors)

    def set_window_checks(self, checked: tuple[str, dict] | None) -> None:
        """Show *checked*: the first measurement whose ranges do not match (else the first note)."""
        self._checked = checked
        checks = dict((checked or ("", {}))[1])
        detectors = self.preflight_setup()["detectors"]
        self.windows_warnings = windows.window_warnings({}, detectors, checks=checks)
        found = [c for c in checks.values() if c is not None]
        self.windows_check = next((c for c in found if c.mismatch), next(iter(found), None))

    def windows_check_text(self) -> str:
        """The verdict line, naming the measurement when several were read."""
        if not self.windows_warnings:
            return super().windows_check_text()
        more = len(self.windows_warnings) - 1
        return self.windows_warnings[0] + (f" (+{more} more measurement(s))" if more > 0 else "")

    def fingerprint_params(self, settings: dict[str, Any]) -> dict[str, Any]:
        params = dict(settings)
        params["_read_context"] = analysis_cache.photon_read_context()
        return params

    def input_files(self) -> list[pathlib.Path]:
        folder = self.analysis_folder
        if folder is None:
            return []
        tables = [
            f
            for d in sorted(pathlib.Path(folder).glob("bi4_bur"))
            for f in sorted(d.glob("*"))
            if f.is_file()
        ]
        return tables + list(source_inputs(folder))

    def analysis_fingerprint(self, settings: dict[str, Any]) -> str:
        return analysis_cache.fingerprint(
            self.input_files(),
            self.fingerprint_params(settings),
            extra=analysis_cache.algorithm_tag("bva", ALGORITHM_VERSION, "tttrlib"),
        )

    def set_result(self, burst_df: Any, tttrs: Any, df_v: Any) -> None:
        self.burst_df = burst_df
        self.tttrs = tttrs
        self.df = df_v
        x, _ = self.valid_bursts(df_v)
        total = row_count(df_v)
        self.status_text = f"Done – {x.size} bursts with Std > 0 on {total} total"
        if self.windows_warnings:
            self.status_text += " – see the excitation-window check above"
        self.notify("result")

    @staticmethod
    def valid_bursts(table: Any) -> tuple[np.ndarray, np.ndarray]:
        std = numeric_column(table, "Proximity Ratio Std")
        keep = std > 0.0
        return numeric_column(table, "Proximity Ratio Mean")[keep], std[keep]

    @staticmethod
    def average_histogram(
        counts: np.ndarray, x_edges: np.ndarray, y_edges: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        y = y_edges[:-1] + np.diff(y_edges) / 2
        y2 = y * y
        mean = np.full(counts.shape[0], np.nan)
        sd = np.full(counts.shape[0], np.nan)
        for i in range(counts.shape[0]):
            c = counts[i]
            s = c.sum()
            if s == 0:
                continue
            m1 = c @ y / s
            m2 = c @ y2 / s
            mean[i] = m1
            sd[i] = np.sqrt(max(m2 - m1 * m1, 0.0)) / np.sqrt(s)
        return mean, sd

    def get_plot_data(self) -> dict[str, Any] | None:
        # Static line is always available
        n_photons = self.photons_per_slice
        if n_photons < 0:
            n_photons = 100
        x_axis = np.linspace(0, 1, 131)
        mean_sim, std_sim = core.compute_static_bva_line(
            x_axis,
            number_of_photons_per_slice=n_photons,
        )

        res: dict[str, Any] = {
            "static_x": mean_sim,
            "static_y": std_sim,
            "has_data": False,
        }

        if self.df is None:
            return res

        x, y = self.valid_bursts(self.df)
        if x.size == 0:
            return res

        range_x = (-0.05, 1.05)
        range_y = (-0.01, 0.44)
        hist, x_edges, y_edges = np.histogram2d(
            x,
            y,
            bins=(self.bins_x, self.bins_y),
            range=[range_x, range_y],
        )
        mean, sd = self.average_histogram(hist, x_edges, y_edges)
        x_centers = (x_edges[:-1] + x_edges[1:]) / 2

        # Valid finite profile points
        valid_prof = np.isfinite(mean) & np.isfinite(sd) & (sd > 0.0)

        res.update(
            {
                "has_data": True,
                "scatter_x": x,
                "scatter_y": y,
                "profile_x": x_centers[valid_prof],
                "profile_mean": mean[valid_prof],
                "profile_sd": sd[valid_prof],
                "n_valid": x.size,
                "n_total": row_count(self.df),
            }
        )
        return res


__all__ = ["BvaViewModel", "ALGORITHM_VERSION"]
