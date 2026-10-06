"""The ALEX-Suite CSV export without a toolkit: pick a burst table, write the five files the old program wrote.

Not the storage format: the analysis lives in the ``.pto`` container and the burst companions beside it, exactly as
in the PIE workflow. This is the bridge for the spreadsheets, plotting templates and scripts that read five specific
files with five specific section headers. Drawn by :class:`..gui.app.LegacyExportGui` (which reads ``_bur_files``,
``_status_text`` and calls :meth:`LegacyExportModel.run_export`); used by the native hub and the legacy Qt panel.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("chisurf.plugins.burst")


class LegacyExportModel:
    """The burst tables offered for export, the last outcome, and the export itself."""

    def __init__(self) -> None:
        self.bur_files: list[Path] = []
        self.status_text = "No bursts yet - run the burst search first."
        #: What the last :meth:`run_export` wrote.
        self.written: list[Path] = []

    # The view's names (``LegacyExportGui`` predates this model and reads these).
    @property
    def _bur_files(self) -> list[Path]:
        return self.bur_files

    @property
    def _status_text(self) -> str:
        return self.status_text

    def set_burst_files(self, files) -> None:
        """Adopt the burst tables the pipeline produced (``.bur`` files or ``.pto`` runs)."""
        self.bur_files = [Path(p) for p in files or ()]
        if self.bur_files:
            self.status_text = f"{len(self.bur_files)} burst file(s) available."

    def run_export(self, source: str, sample: str, buffer: str, parts: dict) -> list[Path]:
        """Write the export beside *source*; return the written paths (empty on failure, reason in the status)."""
        self.written = []
        if not source:
            self.status_text = "Pick a burst file first."
            return []
        from chisurf.plugins.burst.alex_suite.api.histograms import es_histograms
        from chisurf.plugins.burst.alex_suite.api.legacy_export import LegacyExport, Metadata, write_legacy_export

        path = Path(source)
        try:
            histograms = es_histograms(path)
            burst_table = None
            if parts.get("original_bursts"):
                from chisurf.core.fluorescence.burst.table import read_burst_table

                burst_table = read_burst_table(path)
            written = write_legacy_export(
                _export_stem(path),
                histograms,
                metadata=Metadata(sample_name=sample, buffer=buffer),
                parts=LegacyExport(**{key: bool(v) for key, v in parts.items()}),
                burst_table=burst_table,
            )
        except Exception as exc:  # noqa: BLE001 - shown in the step
            logger.warning(f"ALEX Suite: legacy export failed - {exc}")
            self.status_text = f"Export failed: {exc}"
            return []
        self.written = [Path(p) for p in written]
        folder = self.written[0].parent if self.written else path.parent
        self.status_text = f"Wrote {len(self.written)} file(s) in {folder}: " + ", ".join(p.name for p in self.written)
        logger.info(f"ALEX-Suite export: {len(self.written)} file(s) in {folder}")
        return self.written


def _export_stem(path: Path) -> Path:
    """Where the five files go: beside a ``.bur`` file, or beside the ``.pto`` a container run lives in.

    A run inside a container (``m000.pto/sliding_window_All 0.1500#60``) is not a folder on disk; the export is
    written next to the container, named after it and the run.
    """
    for parent in [path, *path.parents]:
        if parent.suffix.lower() == ".pto":
            run = path.relative_to(parent).as_posix().replace("/", "_").replace(" ", "_").replace("#", "_")
            return parent.parent / (parent.stem + (f"_{run}" if run and run != "." else ""))
    return path.with_suffix("")


__all__ = ["LegacyExportModel"]
