"""Write the CSV files the old ALEX-Suite wrote, from this workflow's bursts.

Not the storage format — the analysis is stored in the `.pto` container and the
burst companions beside it, exactly as in the PIE workflow. This is the bridge
for the spreadsheets, plotting templates and scripts people already have, which
read five specific files with five specific section headers.

Rendered by the EMTK app in :mod:`.app` (:class:`LegacyExportApp`); this class
keeps the export logic and the workflow hand-off.
"""

from __future__ import annotations

import logging
import pathlib

from qtpy import QtWidgets

logger = logging.getLogger("chisurf.plugins.burst")


class LegacyExportPanel(QtWidgets.QWidget):
    """Pick a burst file and write the ALEX-Suite five-file export."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        """Build the export panel."""
        super().__init__(parent)
        self._workflow = parent
        self._bur_files: list[pathlib.Path] = []
        self._status_text = "No bursts yet — run the burst search first."

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        from emtk.qt_host import ControlHost

        from .app import WINDOW_BG, LegacyExportApp

        self.app = LegacyExportApp(self)
        self.host = ControlHost(self.app, background=WINDOW_BG[:3])
        layout.addWidget(self.host, 1)

    # ── workflow hand-off ───────────────────────────────────────────────

    def set_burst_files(self, files) -> None:
        """Adopt the burst files the pipeline produced."""
        self._bur_files = [pathlib.Path(p) for p in files]
        gui = getattr(self.app, "export_gui", None)
        if gui is not None and gui.selected_index >= len(self._bur_files):
            gui.selected_index = max(0, len(self._bur_files) - 1)
        if self._bur_files:
            self._status_text = f"{len(self._bur_files)} burst file(s) available."
        if hasattr(self, "host"):
            self.host.update()

    # ── the action ──────────────────────────────────────────────────────

    def run(self) -> None:
        """Write the export from the choices on screen (the app's mirrors)."""
        gui = getattr(self.app, "export_gui", None)
        if gui is None:
            return
        files = gui.files()
        source = files[gui.selected_index] if files else ""
        self.run_export(
            source=source,
            sample=gui.sample_text,
            buffer=gui.buffer_text,
            parts=dict(gui.parts),
        )

    def run_export(self, source: str, sample: str, buffer: str, parts: dict) -> None:
        """Write the export beside the chosen burst file."""
        if not source:
            self._status_text = "Pick a burst file first."
            if hasattr(self, "host"):
                self.host.update()
            return
        from chisurf.plugins.burst.alex_suite.api.histograms import es_histograms
        from chisurf.plugins.burst.alex_suite.api.legacy_export import (
            LegacyExport,
            Metadata,
            write_legacy_export,
        )

        path = pathlib.Path(source)
        try:
            histograms = es_histograms(path)
            burst_table = None
            if parts.get("original_bursts"):
                from chisurf.core.fluorescence.burst.table import read_burst_table

                burst_table = read_burst_table(path)
            written = write_legacy_export(
                path.with_suffix(""),
                histograms,
                metadata=Metadata(sample_name=sample, buffer=buffer),
                parts=LegacyExport(**{key: bool(v) for key, v in parts.items()}),
                burst_table=burst_table,
            )
        except Exception as exc:
            logger.warning(f"ALEX Suite: legacy export failed — {exc}")
            self._status_text = f"Export failed: {exc}"
            if hasattr(self, "host"):
                self.host.update()
            return
        names = ", ".join(p.name for p in written)
        self._status_text = f"Wrote {len(written)} file(s) in {path.parent}: {names}"
        logger.info(f"ALEX-Suite export: {len(written)} file(s) in {path.parent}")
        if hasattr(self, "host"):
            self.host.update()


__all__ = ["LegacyExportPanel"]
