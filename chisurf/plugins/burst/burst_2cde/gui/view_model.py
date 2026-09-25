"""Qt-free view-model behind the FRET-2CDE / ALEX-2CDE tool.

Holds the source folder, the 2CDE settings, and the last computed dataframe,
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
from chisurf.plugins.burst.burst_2cde.core import computation as core

try:
    from chisurf.plugins.burst.burst_selection.api.features import proximity_ratio
except Exception:  # pragma: no cover
    proximity_ratio = None

ALGORITHM_VERSION = 1
logger = logging.getLogger(__name__)


class TwoCdeViewModel:
    """Toolkit-free view model for 2CDE analysis."""

    def __init__(self) -> None:
        self.folder: str = ""
        self.variant: str = "fret"
        self.kernel: str = "laplace"
        self.tau_us: float = 100.0
        self.donor_channels_text: str = "0,8"
        self.acceptor_channels_text: str = "1,9"
        self.file_type: str = "SPC-130"

        self.df: Any | None = None
        self.last_computed_variant: str = "fret"
        self.status_text: str = ""
        self.is_running: bool = False
        self.is_locked: bool = False

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
                logger.warning("TwoCdeViewModel observer failed", exc_info=True)

    @staticmethod
    def parse_channels(text: str) -> list[int]:
        return [int(x) for x in str(text).split(",") if x.strip()]

    @property
    def donor_channels(self) -> list[int]:
        try:
            return self.parse_channels(self.donor_channels_text)
        except Exception:
            return []

    @property
    def acceptor_channels(self) -> list[int]:
        try:
            return self.parse_channels(self.acceptor_channels_text)
        except Exception:
            return []

    def set_folder(self, folder: str | pathlib.Path) -> None:
        self.folder = str(folder).strip()
        self.notify("folder")

    def settings(self) -> dict[str, Any]:
        return {
            "variant": self.variant,
            "kernel": self.kernel,
            "tau_us": float(self.tau_us),
            "donor_channels": self.donor_channels,
            "acceptor_channels": self.acceptor_channels,
            "file_type": self.file_type.strip(),
        }

    def fingerprint_params(self) -> dict[str, Any]:
        params = dict(self.settings())
        params["_read_context"] = analysis_cache.photon_read_context()
        return params

    def input_files(self) -> list[pathlib.Path]:
        folder = self.folder.strip()
        if not folder:
            return []
        tables = [
            f
            for d in sorted(pathlib.Path(folder).glob("bi4_bur"))
            for f in sorted(d.glob("*"))
            if f.is_file()
        ]
        return tables + list(source_inputs(folder))

    def analysis_fingerprint(self) -> str:
        return analysis_cache.fingerprint(
            self.input_files(),
            self.fingerprint_params(),
            extra=analysis_cache.algorithm_tag("2cde", ALGORITHM_VERSION, "tttrlib"),
        )

    def set_result(self, df: Any, variant: str) -> None:
        self.df = df
        self.last_computed_variant = variant
        col = core.column_for_variant(variant)
        vals = numeric_column(df, col)
        finite = np.isfinite(vals)
        self.status_text = f"{col}: {int(finite.sum())} / {row_count(df)} bursts valid"
        self.notify("result")

    def get_plot_data(self) -> dict[str, Any] | None:
        if self.df is None:
            return None
        col = core.column_for_variant(self.last_computed_variant)
        vals = numeric_column(self.df, col)
        finite = np.isfinite(vals)
        e = proximity_ratio(self.df) if proximity_ratio is not None else None
        if e is not None:
            e = np.asarray(e, dtype=float)
            m = finite & np.isfinite(e)
            return {
                "kind": "scatter",
                "x": e[m],
                "y": vals[m],
                "xlabel": "FRET efficiency (proximity ratio)",
                "ylabel": col,
                "valid": int(finite.sum()),
                "total": row_count(self.df),
            }
        else:
            if not np.any(finite):
                return None
            y, x = np.histogram(vals[finite], bins=40)
            return {
                "kind": "hist",
                "x": 0.5 * (x[:-1] + x[1:]),
                "y": y,
                "xlabel": col,
                "ylabel": "Counts",
                "valid": int(finite.sum()),
                "total": row_count(self.df),
            }


__all__ = ["TwoCdeViewModel", "ALGORITHM_VERSION"]
