"""FCS Correlator — two-pane navigation tool."""

from __future__ import annotations

import pathlib
import sys
from typing import Any

from qtpy import QtWidgets

from chisurf.gui import QtCore
from chisurf.gui.widgets.navigation import NavigationPanelTool
from chisurf.plugins.fcs.fcs_correlator.wizard import FileAndStepsPage

# ---------------------------------------------------------------------------
# Workflow context
# ---------------------------------------------------------------------------
from chisurf.plugins.fcs.fcs_correlator.workflow import (  # noqa: E402
    FcsWorkflow,
    FcsWorkflowContext,
)

__all__ = ["CORRELATOR_PANELS", "FcsCorrelatorTool", "FcsWorkflowContext"]


# ---------------------------------------------------------------------------
# Panel factory helpers
# ---------------------------------------------------------------------------


def _bind(tool: NavigationPanelTool, role: str, widget: QtWidgets.QWidget) -> None:
    binder = getattr(tool, "bind_workflow_panel", None)
    if callable(binder):
        binder(role, widget)


def _panel_widget(tool: NavigationPanelTool, index: int) -> QtWidgets.QWidget | None:
    if index < 0 or index >= len(tool.panels):
        return None
    wrapper = tool.panels[index].get("instance")
    if wrapper is None:
        return None
    layout = wrapper.layout()
    if layout is None or layout.count() == 0:
        return None
    item = layout.itemAt(0)
    return item.widget() if item is not None else None


# ---------------------------------------------------------------------------
# Panel factories
# ---------------------------------------------------------------------------


def _channel_def(parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
    from chisurf.plugins.fcs.fcs_channel_preset.gui.tool import FCSChannelWidget

    w = FCSChannelWidget(parent=parent)
    w.setParent(parent)
    _bind(parent, "channel_def", w)
    return w


def _files_selection(parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
    w = FileAndStepsPage(parent=parent)
    w.setParent(parent)
    _bind(parent, "files", w)
    return w


def _photon_filter(parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
    from chisurf.gui.autoform import AutoForm
    from chisurf.plugins.fcs.fcs_correlator.filter_panel import (
        FilterSettingsModel,
    )

    model = FilterSettingsModel()
    form = AutoForm(model, parent=parent)
    model._form = form
    parent._filter_model = model
    parent._filter_form = form
    _bind(parent, "filter", form)
    return form


def _correlator_panel(parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
    from chisurf.gui.autoform import AutoForm
    from chisurf.plugins.fcs.fcs_correlator.correlator_panel import (
        CorrelatorSettingsModel,
    )

    model = CorrelatorSettingsModel()
    form = AutoForm(model, parent=parent)
    model._form = form
    parent._correlator_model = model
    parent._correlator_form = form
    _bind(parent, "correlator", form)
    return form


def _fcs_merger(parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
    from chisurf.gui.autoform import AutoForm
    from chisurf.plugins.fcs.fcs_correlator.merger_panel import (
        MergerSettingsModel,
    )

    model = MergerSettingsModel()
    form = AutoForm(model, parent=parent)
    model._form = form
    parent._merger_model = model
    parent._merger_form = form
    _bind(parent, "merger", form)
    return form


# ---------------------------------------------------------------------------
# Panel definitions
# ---------------------------------------------------------------------------

CORRELATOR_PANELS = [
    {
        "name": "1. Channel Definitions",
        "icon": "\U0001f39a\ufe0f",
        "description": "Choose a detector setup and define the FCS correlation channel pairs.",
        "factory": _channel_def,
        "role": "channel_def",
    },
    {
        "name": "2. Files & Steps",
        "icon": "\U0001f4c2",
        "description": "Select TTTR files and choose processing steps.",
        "factory": _files_selection,
        "role": "files",
    },
    {
        "name": "3. Photon / Burst Filter",
        "icon": "\U0001f50d",
        "description": "Filter photons by count rate or burst selection.",
        "factory": _photon_filter,
        "role": "filter",
    },
    {
        "name": "4. Correlator",
        "icon": "\U0001f4ca",
        "description": "Set correlation parameters, compute and view FCS curves.",
        "factory": _correlator_panel,
        "role": "correlator",
    },
    {
        "name": "5. FCS Merger",
        "icon": "\U0001f517",
        "description": "Merge and save FCS correlation curves.",
        "factory": _fcs_merger,
        "role": "merger",
    },
]


# ---------------------------------------------------------------------------
# Main tool class
# ---------------------------------------------------------------------------


class FcsCorrelatorTool(NavigationPanelTool):
    """FCS Correlator — two-pane navigation tool replacing the QWizard.

    Subclasses (e.g. the merged FCS tool) may pass a custom ``panels`` list and
    ``title``; when ``panels`` is ``None`` the standalone correlator workflow
    (:data:`CORRELATOR_PANELS`) is used. The workflow-context wiring keys off the
    panel ``role`` values, so extra tool panels with unrelated roles are ignored
    by the correlator step logic and simply hosted by the shared shell.
    """

    def __init__(
        self,
        parent=None,
        *,
        panels: list[dict[str, Any]] | None = None,
        title: str = "FCS Correlator",
        initial_role: str = "files",
    ):
        self.workflow = FcsWorkflow()
        self.workflow_context = self.workflow.context
        self._workflow_panels: dict[str, QtWidgets.QWidget] = {}
        super().__init__(
            title=title,
            panels=CORRELATOR_PANELS if panels is None else panels,
            parent=parent,
            minimum_size=(950, 620),
            initial_size=(1180, 760),
            navigation_width=270,
            navigation_min_width=250,
        )
        # Reflect the default step selection (filter off, merger on) in the nav.
        self._update_step_nav_state()
        # Open on "Files & Steps" by default (the detector step is preconfigured
        # from the last-used setup); the base shell starts on row 0, which also
        # lazily loads the detector panel so its context is available.
        files_row = self._nav_row_for_role(initial_role)
        if files_row >= 0:
            self.nav_list.setCurrentRow(files_row)

    def bind_workflow_panel(self, role: str, widget: QtWidgets.QWidget) -> None:
        self._workflow_panels[role] = widget
        if role == "channel_def":
            self._bind_channel_def_panel(widget)
        elif role == "files":
            self._bind_files_panel(widget)
        self._apply_context_to_panel(role, widget)

    def _nav_row_for_role(self, role: str) -> int:
        for i, panel in enumerate(self.panels):
            if panel.get("role") == role:
                return i
        return -1

    def _set_nav_enabled(self, role: str, enabled: bool) -> None:
        """Enable or gray-out (disable) a navigation step for an optional stage."""
        row = self._nav_row_for_role(role)
        if row < 0:
            return
        item = self.nav_list.item(row)
        if item is None:
            return
        flags = item.flags()
        toggle = QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable
        item.setFlags(flags | toggle if enabled else flags & ~toggle)

    def _update_step_nav_state(self) -> None:
        """Gray out the optional Filter/Merger steps when their checkbox is off."""
        files = self._workflow_panels.get("files")
        if files is not None:
            try:
                use_filter = files.cb_photon_filter.isChecked()
                use_merger = files.cb_fcs_merger.isChecked()
            except Exception:
                use_filter = self.workflow_context.use_photon_filter
                use_merger = self.workflow_context.use_fcs_merger
        else:
            use_filter = self.workflow_context.use_photon_filter
            use_merger = self.workflow_context.use_fcs_merger
        self._set_nav_enabled("filter", use_filter)
        self._set_nav_enabled("merger", use_merger)

    def _bind_channel_def_panel(self, widget: QtWidgets.QWidget) -> None:
        try:
            widget.setup_combo.currentIndexChanged.connect(self._on_channel_setup_changed)
        except Exception:
            pass

    def _bind_files_panel(self, widget: QtWidgets.QWidget) -> None:
        try:
            widget.cb_photon_filter.toggled.connect(self._on_files_steps_changed)
            widget.cb_fcs_merger.toggled.connect(self._on_files_steps_changed)
        except Exception:
            pass
        self._update_step_nav_state()

    def _on_nav_changed(self, index: int) -> None:
        self._refresh_context()
        super()._on_nav_changed(index)
        if 0 <= index < len(self.panels):
            role = str(self.panels[index].get("role") or "")
            widget = self._panel_widget(index)
            if widget is not None:
                self._apply_context_to_panel(role, widget)

    def _panel_widget(self, index: int) -> QtWidgets.QWidget | None:
        return _panel_widget(self, index)

    def _refresh_context(self) -> None:
        chdef = self._workflow_panels.get("channel_def")
        if chdef is not None:
            try:
                setup_name = chdef.setup_combo.currentText().strip()
                self.workflow.set_setup(setup_name, getattr(chdef, "_detector_setups", {}) or {})
            except Exception:
                pass
        files = self._workflow_panels.get("files")
        if files is not None:
            try:
                self.workflow.set_files(
                    files.checked_files,
                    files.cb_photon_filter.isChecked(),
                    files.cb_fcs_merger.isChecked(),
                )
            except Exception:
                pass

    def _apply_context_to_panel(self, role: str, widget: QtWidgets.QWidget) -> None:
        if role == "filter":
            self._apply_context_to_filter(widget)
        elif role == "correlator":
            self._apply_context_to_correlator(widget)
        elif role == "merger":
            self._apply_context_to_merger(widget)

    def _apply_context_to_filter(self, widget: QtWidgets.QWidget) -> None:
        model = getattr(self, "_filter_model", None)
        if model is not None:
            self.workflow.load_files_into_filter(model)

    def _apply_context_to_correlator(self, widget: QtWidgets.QWidget) -> None:
        model = getattr(self, "_correlator_model", None)
        if model is None:
            return
        self.workflow.apply_to_correlator(model, getattr(self, "_filter_model", None))
        try:
            model._form.refresh_plots()
        except Exception:
            pass
        for w in widget.findChildren(QtWidgets.QWidget):
            if getattr(w, "AUTOFORM_REFRESH", False):
                try:
                    w.refresh()
                except Exception:
                    pass

    def _collect_expanded_files(self) -> list[str]:
        return self.workflow.expanded_files()

    def _apply_context_to_merger(self, widget: QtWidgets.QWidget) -> None:
        correlator_model = getattr(self, "_correlator_model", None)
        merger_model = getattr(self, "_merger_model", None)
        if merger_model is None or correlator_model is None:
            return
        correlations, folder = self.workflow.merger_input(correlator_model)
        if correlations:
            merger_model.set_correlations(correlations, folder)
        elif folder is not None:
            merger_model.load_correlations(folder)

    def _on_channel_setup_changed(self) -> None:
        # Re-derive the correlation context from the newly selected setup and
        # drop any stale filter selection (channels/micro-times are setup-bound).
        self._refresh_context()
        model = getattr(self, "_filter_model", None)
        if model is not None:
            try:
                model.set_tttr_objects({}, [])
            except Exception:
                pass

    def _on_files_steps_changed(self) -> None:
        files = self._workflow_panels.get("files")
        if files is not None:
            try:
                self.workflow_context.use_photon_filter = files.cb_photon_filter.isChecked()
                self.workflow_context.use_fcs_merger = files.cb_fcs_merger.isChecked()
            except Exception:
                pass
        self._update_step_nav_state()


# ---------------------------------------------------------------------------
# Plugin entrypoint
# ---------------------------------------------------------------------------

if __name__ == "plugin":
    tool = FcsCorrelatorTool()
    tool.show()

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    tool = FcsCorrelatorTool()
    tool.show()
    sys.exit(app.exec_())
