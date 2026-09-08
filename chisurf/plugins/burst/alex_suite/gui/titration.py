"""The titration step: a concentration series of FRET histograms.

An :class:`~chisurf.gui.autoform.AutoForm` over ``titration.view.json`` bound to
the Qt-free
:class:`~chisurf.plugins.burst.alex_suite.gui.titration_view_model.TitrationViewModel`,
plus one custom section for the Fit/Export buttons — the run button carries the
object name the workflow shell's *Next* and ⏩ look for, so the titration takes
part in the pipeline walk like every other step.
"""

from __future__ import annotations

import logging

from qtpy import QtCore, QtWidgets

from chisurf.gui.autoform import AutoForm
from chisurf.gui.autoform.sections.registry import register_section

from .titration_view_model import TitrationViewModel

logger = logging.getLogger("chisurf.plugins.burst")

#: Burst tables the file chooser offers.
BURST_FILTER = "Burst tables (*.bur *.pto *.csv *.txt);;All files (*)"


@register_section("alex_titration_run")
def alex_titration_run(model, target=None, **options):
    """AutoForm factory for the titration Fit / Export button row."""
    return _RunSection(model)


class _RunSection(QtWidgets.QWidget):
    """Fit and Export buttons for the titration panel."""

    def __init__(self, model, parent=None):
        """Build the button row bound to *model*."""
        super().__init__(parent)
        self._model = model
        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(2, 2, 2, 2)

        # ``toolAction_run`` is the shell's contract for "this step's primary
        # action"; naming it anything else silently drops the step out of the
        # Next/fast-forward walk.
        self.run_button = QtWidgets.QToolButton(self)
        self.run_button.setObjectName("toolAction_run")
        self.run_button.setText("📈 Fit series")
        self.run_button.setToolTip(
            "Histogram every concentration, fit them together with shared "
            "population positions, and fit the binding isotherm."
        )
        self.run_button.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.run_button.clicked.connect(model.run)
        row.addWidget(self.run_button)

        self.export_button = QtWidgets.QToolButton(self)
        self.export_button.setText("💾 Export CSV")
        self.export_button.setToolTip(
            "Write the stack, the fitted curves, the populations and the "
            "isotherm as one CSV."
        )
        self.export_button.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.export_button.clicked.connect(self._export)
        row.addWidget(self.export_button)
        row.addStretch(1)

    def _export(self) -> None:
        """Ask for a path and write the result there."""
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export titration", "titration.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            written = self._model.export_csv(path)
        except Exception as exc:
            logger.warning(f"ALEX Suite: titration export failed — {exc}")
            return
        logger.info(f"Titration exported to {written}")


class TitrationPanel(QtWidgets.QWidget):
    """The titration step of the ALEX Suite."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        """Build the panel and wire the Qt dialogs the model asks for."""
        super().__init__(parent)
        self._workflow = parent
        self.model = TitrationViewModel()
        # The model stays Qt-free: it asks for files through a callback rather
        # than opening a dialog itself, so the same object drives a script.
        self.model.request_files = self._choose_files

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        # The spec comes from the model's ``view_spec`` (titration.view.json).
        self.auto_form = AutoForm(self.model)
        # The step is a page, not a dashboard: the table, the settings, the two
        # plots and the numbers are all wanted at once and do not fit a panel's
        # height. Scrolling keeps them in one readable column; the alternative
        # the dock area gives — a tab bar — hides the plots behind the settings,
        # which is precisely the layout this workflow exists to avoid.
        scroll = QtWidgets.QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        scroll.setWidget(self.auto_form)
        layout.addWidget(scroll)
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

    def set_corrections(self, *, gamma: float | None = None,
                        beta: float | None = None) -> None:
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
            self, "Add burst files (one per concentration)", "", BURST_FILTER)
        return list(paths)

    def _on_model_event(self, event: str) -> None:
        """Refresh the form when the model changes."""
        try:
            self.auto_form.sync_fields()
        except Exception:
            logger.warning("Titration: field sync failed", exc_info=True)
        try:
            self.auto_form.refresh_plots()
        except Exception:
            logger.warning("Titration: plot refresh failed", exc_info=True)


__all__ = ["TitrationPanel", "TitrationViewModel"]
