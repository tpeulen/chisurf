"""Qt-free core of the legacy export: the plan of what a container becomes, and the two writers.

The *plan* is the point of this plugin: the legacy folder is a lossy, positional
rendering of the container (see :mod:`chisurf.core.fio.fluorescence.legacy_export`),
so the user should see before pressing the button which run becomes which
``<ending>4`` companion -- and which analysis has no registered ending and will
be skipped.
"""

from __future__ import annotations

import logging
import pathlib
from typing import Any

__all__ = [
    "export_alex_csvs",
    "export_burst_folder",
    "export_plan",
]

logger = logging.getLogger(__name__)


def export_plan(path: str | pathlib.Path) -> list[dict[str, Any]]:
    """One row per run of the container: what the export writes for it.

    Delegates to :func:`chisurf.core.fio.fluorescence.legacy_export.plan_legacy`
    so the preview and the writer share their rules and cannot drift.
    """
    from chisurf.core.fio.fluorescence.legacy_export import plan_legacy

    return plan_legacy(path)


def export_burst_folder(
    path: str | pathlib.Path, out_dir: str | pathlib.Path | None = None
) -> list[pathlib.Path]:
    """Unpack the container at *path* into the Seidel/Margarita burst folder.

    Delegates to :func:`chisurf.core.fio.fluorescence.legacy_export.export_legacy`
    -- the one implementation. Returns every file written.
    """
    from chisurf.core.fio.fluorescence.legacy_export import export_legacy

    return export_legacy(path, out_dir)


def export_alex_csvs(
    burst_table: str | pathlib.Path,
    stem: str | pathlib.Path,
    *,
    sample: str = "",
    buffer: str = "",
    parts: tuple[str, ...] = ("meta", "hist_E", "hist_S", "hist_2D"),
) -> list[pathlib.Path]:
    """Write the five ALEX-Suite CSVs beside *stem* from a burst table or ``.pto`` run.

    *burst_table* may be a ``.bur`` table or a run inside a container
    (``m000.pto/<run>``); :func:`~chisurf.plugins.burst.alex_suite.api.histograms.es_histograms`
    opens either.
    """
    from chisurf.plugins.burst.alex_suite.api.histograms import es_histograms
    from chisurf.plugins.burst.alex_suite.api.legacy_export import (
        LegacyExport,
        Metadata,
        write_legacy_export,
    )

    pathlib.Path(stem).parent.mkdir(parents=True, exist_ok=True)
    selected = LegacyExport(
        **{
            field: part in parts
            for part, field in (
                ("meta", "metadata"),
                ("hist_E", "e_histogram"),
                ("hist_S", "s_histogram"),
                ("hist_2D", "histogram_2d"),
                ("original_bursts", "original_bursts"),
            )
        }
    )
    burst_table_columns = None
    if selected.original_bursts:
        from chisurf.core.fluorescence.burst.table import read_burst_table

        burst_table_columns = read_burst_table(burst_table)
    return write_legacy_export(
        stem,
        es_histograms(burst_table),
        metadata=Metadata(sample_name=sample, buffer=buffer),
        parts=selected,
        burst_table=burst_table_columns,
    )
