"""Custom AutoForm sections for the Burst IRF & Background tool.

Three bespoke Qt widgets are registered here: the detector channel-definition
page (``irf_bg_channels``), the compute / send-to-MLE action bar (``irf_bg_run``)
and the per-detector results table (``irf_bg_results``). The IRF plot is a
declarative ``plot`` section in ``irf_bg.view.json`` and the file list is the
general ``path_list`` section. The widgets own only Qt concerns and drive the
Qt-free :class:`~..view_model.IrfBackgroundViewModel`. Imported (registered) by
``gui.tool``.

Mirrors ``tttr_count_rate_analysis/gui/sections.py``.
"""

from __future__ import annotations

import logging

from qtpy import QtCore, QtWidgets

from chisurf.gui.autoform.sections.registry import register_section

logger = logging.getLogger(__name__)


def _tool_button(text: str, tooltip: str, slot) -> QtWidgets.QToolButton:
    """Build a configured ``QToolButton`` (emoji label + tooltip) in one call."""
    btn = QtWidgets.QToolButton()
    btn.setText(text)
    btn.setToolTip(tooltip)
    btn.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
    btn.clicked.connect(slot)
    return btn


# ---------------------------------------------------------------------------
# irf_bg_channels — detector channel-definition page
# ---------------------------------------------------------------------------


@register_section("irf_bg_channels")
def irf_bg_channels(model, target=None, **options):
    """AutoForm factory for the detector channel-definition page."""
    from chisurf.gui.widgets.wizard.tttr_channeldefinition import DetectorWizardPage

    page = DetectorWizardPage(
        show_edit_json=False,
        show_save=False,
        show_setups_file=True,
        show_setup_selection=True,
        show_help=True,
        show_tttr_reading=True,
        show_tables=True,
        show_add_inputs=True,
    )

    def _detectors() -> dict:
        try:
            return page.get_settings().get("detectors", {})
        except Exception:
            logger.warning("irf-bg: reading detectors failed", exc_info=True)
            return {}

    # Inject the detectors source into the Qt-free model, and expose the page so
    # the burst-analysis shell can push shared channel definitions into it.
    model.channels_provider = _detectors
    model.detector_wizard_page = page
    return page


# ---------------------------------------------------------------------------
# irf_bg_run — compute + send-to-MLE action bar
# ---------------------------------------------------------------------------


@register_section("irf_bg_run")
def irf_bg_run(model, target=None, **options):
    """AutoForm factory for the Compute / Send-to-MLE action bar."""
    return _RunSection(model)


class _RunSection(QtWidgets.QWidget):
    """Compute + Send-to-MLE action bar for the IRF/background extraction."""

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self._model = model

        bar = QtWidgets.QHBoxLayout(self)
        bar.setContentsMargins(2, 2, 2, 2)
        bar.addWidget(
            _tool_button(
                "🌙 Compute",
                "Extract per-detector IRF and background from the non-burst photons.",
                self._compute,
            )
        )
        bar.addWidget(
            _tool_button(
                "🎯 Send to MLE",
                "Feed the extracted IRF and background to the burst-MLE lifetime fit "
                "(available inside the Burst Analysis workflow).",
                self._send_to_mle,
            )
        )
        bar.addStretch(1)
        self._status = QtWidgets.QLabel("Load files, define detectors, then compute.")
        self._status.setWordWrap(True)
        bar.addWidget(self._status, 1)

    def _compute(self) -> None:
        reason = self._model.can_compute()
        if reason is not None:
            QtWidgets.QMessageBox.warning(self, "Cannot compute", reason)
            return
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            self._model.compute()
        except Exception as exc:  # noqa: BLE001
            QtWidgets.QMessageBox.critical(self, "Error", str(exc))
            return
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        n = len(self._model.results_rows())
        self._status.setText(f"Extracted IRF + background for {n} detector(s).")

    def _send_to_mle(self) -> None:
        if not self._model.has_results():
            QtWidgets.QMessageBox.warning(
                self, "No results", "Compute the IRF and background first."
            )
            return
        # Walk up the parent chain to a host that accepts the patterns (the
        # burst-analysis workflow shell); fall back to an informative message.
        host = self.parent()
        while host is not None and not hasattr(host, "apply_irf_background_to_mle"):
            host = host.parent()
        if host is None:
            QtWidgets.QMessageBox.information(
                self,
                "Send to MLE",
                "Open this tool inside the Burst Analysis workflow to feed the "
                "MLE lifetime fit. The IRF/background patterns are available via "
                "the tool's model for scripted use.",
            )
            return
        try:
            count = host.apply_irf_background_to_mle(self._model.mle_patterns())
        except Exception as exc:  # noqa: BLE001
            QtWidgets.QMessageBox.critical(self, "Error", str(exc))
            return
        self._status.setText(f"Sent IRF + background to MLE for {count} detector(s).")


# ---------------------------------------------------------------------------
# irf_bg_results — per-detector results table
# ---------------------------------------------------------------------------


@register_section("irf_bg_results")
def irf_bg_results(model, target=None, **options):
    """AutoForm factory for the per-detector results table."""
    return _ResultsSection(model)


class _ResultsSection(QtWidgets.QWidget):
    """Read-only per-detector IRF/background results table."""

    _HEADERS = ["Detector", "Background (kHz)", "Prompt (ns)", "Non-burst", "Burst"]

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self._model = model
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)

        self._table = QtWidgets.QTableWidget()
        self._table.setColumnCount(len(self._HEADERS))
        self._table.setHorizontalHeaderLabels(self._HEADERS)
        self._table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self._table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        layout.addWidget(self._table)

        self._model.add_observer(self._on_model_event)

    def _on_model_event(self, event: str) -> None:
        if event in ("computed", "files"):
            self._refresh()

    def _refresh(self) -> None:
        rows = self._model.results_rows()
        self._table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            values = [
                row["detector"],
                f"{row['background_khz']:.3f}",
                f"{row['prompt_ns']:.3f}",
                f"{row['n_bg']:d}",
                f"{row['n_burst']:d}",
            ]
            for c, val in enumerate(values):
                self._table.setItem(r, c, QtWidgets.QTableWidgetItem(val))


__all__ = ["irf_bg_channels", "irf_bg_run", "irf_bg_results"]
