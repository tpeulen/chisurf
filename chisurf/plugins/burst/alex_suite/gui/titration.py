"""The titration step: a concentration series of FRET histograms.

Rendered by the EMTK app in :mod:`.app` (:class:`TitrationApp`) over the
Qt-free
:class:`~chisurf.plugins.burst.alex_suite.gui.titration_view_model.TitrationViewModel`,
which keeps every setting, the series table, the fit and the two plot sources.
The model stays toolkit-free: it asks for files through a callback rather than
opening a dialog itself, so the same object drives a script.
"""

from __future__ import annotations

import logging

from qtpy import QtWidgets

from .titration_view_model import TitrationViewModel

logger = logging.getLogger("chisurf.plugins.burst")

#: Burst tables the file chooser offers.
BURST_FILTER = "Burst tables (*.bur *.pto *.csv *.txt);;All files (*)"


class TitrationPanel(QtWidgets.QWidget):
    """The titration step of the ALEX Suite."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        """Build the panel and wire the Qt dialogs the model asks for."""
        super().__init__(parent)
        self._workflow = parent
        self.model = TitrationViewModel()

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        from emtk.qt_host import ControlHost

        from .app import WINDOW_BG, TitrationApp

        self.app = TitrationApp(self)
        self.host = ControlHost(self.app, background=WINDOW_BG[:3])
        layout.addWidget(self.host, 1)
        self.model.add_observer(self._on_model_event)

    # ── workflow hand-off ───────────────────────────────────────────────

    def set_burst_files(self, files) -> None:
        """Seed the series from the burst files the pipeline produced.

        Seeded only while the table is empty: once concentrations have been
        typed, a context refresh must not replace them.
        """
        if self.model.rows or not files:
            return
        self.model.add_files([str(p) for p in files])

    def set_corrections(self, *, gamma: float | None = None, beta: float | None = None) -> None:
        """Adopt γ/β from the Accurate FRET step."""
        if gamma is not None:
            self.model.gamma = float(gamma)
        if beta is not None:
            self.model.beta = float(beta)
        self.model.notify("changed")

    # ── Qt bits the model delegates ─────────────────────────────────────

    def _choose_files(self) -> list[str]:
        """Open the burst-file chooser and return the selection."""
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "Add burst files (one per concentration)", "", BURST_FILTER
        )
        return list(paths)

    def export_csv(self) -> None:
        """Ask for a path and write the result there."""
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export titration", "titration.csv", "CSV (*.csv)"
        )
        if not path:
            return
        try:
            written = self.model.export_csv(path)
        except Exception as exc:
            logger.warning(f"ALEX Suite: titration export failed — {exc}")
            return
        logger.info(f"Titration exported to {written}")

    def _on_model_event(self, event: str) -> None:
        """Repaint the canvas when the model changes."""
        if hasattr(self, "host"):
            self.host.update()


__all__ = ["TitrationPanel", "TitrationViewModel"]
