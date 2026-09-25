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
from chisurf.core.runtime import analysis_cache
from chisurf.plugins.burst.burst_bva.core import computation as core

ALGORITHM_VERSION = 1
logger = logging.getLogger(__name__)


class BvaViewModel:
    """Toolkit-free view model for BVA analysis."""

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

        # State and results
        self.df: Any | None = None
        self.burst_df: Any | None = None
        self.tttrs: Any | None = None
        self.status_text: str = "Ready"
        self.is_running: bool = False

        self._observers: list[Callable[[str], None]] = []

    def add_observer(self, callback: Callable[[str], None]) -> None:
        if callback not in self._observers:
            self._observers.append(callback)

    def remove_observer(self, callback: Callable[[str], None]) -> None:
        if callback in self._observers:
            self._observers.remove(callback)

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

    def set_folder(self, folder: str | pathlib.Path | None) -> None:
        if folder is None or not str(folder).strip():
            self.data_folder = None
            self.analysis_folder = None
        else:
            p = pathlib.Path(folder)
            self.data_folder = p
            self.analysis_folder = p
        self.notify("folder")

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
