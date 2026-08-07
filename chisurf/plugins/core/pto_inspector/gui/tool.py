"""GUI entry point for the ``.pto`` inspector (toolbar + AutoForm + guided tour).

The toolbar carries the three verbs the panels cannot: open a file, check the
file's integrity, and **open the tool that performs the selected step**. The last
one is why this tool exists beside the panels rather than being a dialog — a
container tells you a burst table was made by a burst search, and until now there
was nothing to press.
"""

from __future__ import annotations

import logging

from qtpy import QtCore, QtWidgets

from chisurf.gui.autoform import AutoForm
from chisurf.gui.widgets.tools.chisurf_dock_tool import ChisurfDockTool

from .view_model import PtoInspectorViewModel

logger = logging.getLogger(__name__)


class PtoInspectorTool(ChisurfDockTool):
    """Inspect one photon container: what is in it, how it got there, and the numbers."""

    tool_settings_name = "PtoInspectorTool"

    #: Model events, re-emitted so they are always handled on the GUI thread.
    modelEvent = QtCore.Signal(str)

    def __init__(self, parent=None, embedded: bool = False, view_model=None, **kwargs):
        super().__init__(parent)
        self._embedded = bool(embedded)
        self.model = view_model or PtoInspectorViewModel()
        self.setWindowTitle("PTO inspector")
        self.setMinimumSize(1100, 700)

        toolbar = QtWidgets.QToolBar()
        toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
        a_open = toolbar.addAction("📂 Open")
        a_open.setToolTip("Open a .pto container.")
        a_open.triggered.connect(self._browse)
        a_reload = toolbar.addAction("🔄 Reload")
        a_reload.setToolTip("Re-read the file, picking up anything written since.")
        a_reload.triggered.connect(self._reload)
        a_verify = toolbar.addAction("🔍 Verify")
        a_verify.setToolTip(
            "Check every recorded checksum against the stored bytes. "
            '"Restorable" without verification is only "probably restorable".'
        )
        a_verify.triggered.connect(self._verify)
        self._a_tool = toolbar.addAction("▶ Open tool")
        self._a_tool.setToolTip(
            "Open the tool that performs the selected artifact's operation."
        )
        self._a_tool.triggered.connect(self.open_tool)
        self._a_tool.setEnabled(False)
        a_export = toolbar.addAction("💾 Export")
        a_export.setToolTip("Write the selected payload out as CSV, or extract it as it is.")
        a_export.triggered.connect(self._export)
        self.add_toolbar_guide(toolbar, resource="guide.json")
        self.add_toolbar_help(toolbar, resource="help.md", title="PTO containers — help")
        self.toolbar = toolbar
        self.addToolBar(toolbar)

        self.auto_form = AutoForm(self.model)
        self.setCentralWidget(self.auto_form)
        self.modelEvent.connect(self._handle_model_event)
        self.model.add_observer(self.modelEvent.emit)
        self.restore_window_geometry()
        self._refresh()

    # -- host actions ---------------------------------------------------------

    def _browse(self) -> None:
        """Ask for a container and open it."""
        from chisurf.gui.widgets.general import get_filename

        path = get_filename(
            description="Open a photon container",
            file_type="Photon containers (*.pto);;All files (*)",
        )
        if path:
            self.model.set_filename(str(path))

    def _reload(self) -> None:
        """Re-open the current file."""
        self.model.reload()

    def _verify(self) -> None:
        """Check every checksum and report the verdict."""
        from chisurf.gui.dialogs import ChiSurfMessageBox

        verdict = self.model.verify()
        ChiSurfMessageBox.information(self, "Integrity", verdict)

    def open_tool(self) -> None:
        """Open the tool that performs the selected artifact's operation.

        A container records the operation, never the program. The manifests carry
        the inverse (``operation_types``), so this is a lookup rather than a
        hard-coded table — and a step no installed tool claims says so plainly
        instead of silently doing nothing.
        """
        from chisurf.gui.dialogs import ChiSurfMessageBox

        item = self.model.selected
        if item is None:
            return
        manifests = self.model.tool_manifests()
        if not manifests:
            ChiSurfMessageBox.information(
                self,
                "No tool for this step",
                f"Nothing installed claims the operation “{item.operation or '—'}”.\n\n"
                "It was probably computed by another program. The settings in the "
                "details panel are still the whole recipe.",
            )
            return
        manifest = manifests[0]
        if len(manifests) > 1:
            names = [m.display_name or m.id for m in manifests]
            chosen, ok = QtWidgets.QInputDialog.getItem(
                self, "Open tool", f"Several tools perform “{item.operation}”:", names, 0, False
            )
            if not ok:
                return
            manifest = manifests[names.index(chosen)]
        self._launch(manifest)

    def _launch(self, manifest) -> None:
        """Instantiate and show a plugin's GUI entrypoint, handing it the file."""
        import importlib

        from chisurf.gui.dialogs import ChiSurfMessageBox

        entry = getattr(manifest.entrypoints, "gui", "") or ""
        if not entry or ":" not in entry:
            ChiSurfMessageBox.information(
                self,
                "No window for this tool",
                f"“{manifest.display_name or manifest.id}” performs this step but has "
                "no GUI entry point — it runs headlessly (CLI or RPC).",
            )
            return
        module_path, attr = entry.rsplit(":", 1)
        try:
            widget_class = getattr(importlib.import_module(module_path), attr)
            widget = widget_class()
        except Exception as exc:
            logger.debug("launching %s failed", entry, exc_info=True)
            ChiSurfMessageBox.warning(
                self, "Could not open the tool", f"{manifest.display_name or manifest.id}: {exc}"
            )
            return
        # Hand over the container the user is looking at, when the tool can take
        # one. Opening the right tool on the wrong file is barely better than not
        # opening it, and every tool that reads a measurement has one of these.
        for setter in ("set_filename", "set_path", "load_file"):
            fn = getattr(getattr(widget, "model", widget), setter, None)
            if callable(fn) and self.model.filename:
                try:
                    fn(self.model.filename)
                    break
                except Exception:
                    logger.debug("%s.%s(%s) failed", entry, setter, self.model.filename,
                                 exc_info=True)
        try:
            from chisurf.core.plugin.registry import apply_manifest_statefulness

            apply_manifest_statefulness(widget, manifest)
        except Exception:
            logger.debug("statefulness for %s failed", manifest.id, exc_info=True)
        widget.show()
        widget.raise_()
        widget.activateWindow()
        self._opened = widget  # keep a reference, or Qt collects the window

    def _export(self) -> None:
        """Write the selected payload out."""
        from chisurf.gui.dialogs import ChiSurfMessageBox
        from chisurf.gui.widgets.general import save_file

        item = self.model.selected
        if item is None:
            return
        if item.is_tabular:
            path = save_file(
                description=f"Export {item.name}", file_type="CSV (*.csv);;All files (*)"
            )
            if not path:
                return
            store = self.model.current_store()
            if store is None:
                return
            from chisurf.core.datastore import write_csv_table

            write_csv_table(str(path), store, delimiter=",")
            ChiSurfMessageBox.information(self, "Exported", f"Wrote {path}")
            return
        path = save_file(description=f"Extract {item.name}", file_type="All files (*)")
        if not path:
            return
        inspection = self.model.inspection
        if inspection is None:
            return
        inspection.measurement.extract(item.uid, str(path))
        ChiSurfMessageBox.information(self, "Extracted", f"Wrote {path}")

    # -- model events ---------------------------------------------------------

    def _handle_model_event(self, event: str) -> None:
        """React to a view-model change on the GUI thread."""
        if event == "open_tool":
            self.open_tool()
            return
        self._refresh()

    def _refresh(self) -> None:
        """Re-read every live section and update the toolbar's enabled state."""
        try:
            self.auto_form.refresh_plots()
        except Exception:
            logger.debug("refreshing the form failed", exc_info=True)
        item = self.model.selected
        self._a_tool.setEnabled(bool(item and self.model.tool_manifests()))
        self.statusBar().showMessage(self.model.status)

    # -- drag & drop ----------------------------------------------------------

    def on_paths_dropped(self, paths) -> None:
        """Open the first dropped container."""
        for path in paths:
            if str(path).lower().endswith(".pto"):
                self.model.set_filename(str(path))
                return

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        """Close the container before the window goes away."""
        self.model.close()
        super().closeEvent(event)
