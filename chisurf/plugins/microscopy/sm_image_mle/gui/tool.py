"""GUI entrypoint for the molecule-wise MLE tool (AutoForm + view.json).

``SmImageMleTool`` hosts an :class:`~chisurf.gui.autoform.AutoForm` bound to the
Qt-free :class:`~...gui.view_model.MoleculeMleViewModel`. The heavy analysis
(``view_model.run``) runs on a background thread so the UI never blocks, and the
segmentation image / molecule table refresh when it finishes.

The window shell is provided by
:class:`~chisurf.plugins.microscopy.mle_common.tool_base.AutoFormMleTool`; this tool adds
the segmentation-preview and molecule-table-export UI-thread events. ``embedded``
is accepted for API uniformity.
"""

from __future__ import annotations

from qtpy import QtWidgets

from chisurf.plugins.microscopy.mle_common.tool_base import AutoFormMleTool

from .view_model import MoleculeMleViewModel


class SmImageMleTool(AutoFormMleTool):
    """Molecule-wise MLE tool (AutoForm-hosted)."""

    def __init__(self, parent=None, embedded: bool = False, view_model=None):
        super().__init__(
            view_model or MoleculeMleViewModel(),
            "Molecule-wise MLE",
            parent=parent,
            embedded=embedded,
            min_size=(640, 420),
        )

    def handle_event(self, event: str) -> bool:
        """Segmentation preview runs on a worker; export prompts on the UI thread."""
        if event == "start_preview":
            self._start_job(self.model.preview_segmentation)
            return True
        if event == "start_export":
            self._export()
            return True
        return False

    def _export(self) -> None:
        """Prompt for a path and export the molecule table (UI thread)."""
        if not self.model.has_results():
            self.model.status_text = "No molecules to export."
            self._refresh()
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export molecule table", "molecules.tsv", "Tables (*.tsv *.csv)"
        )
        if path:
            self.model.export_results(path)


__all__ = ["SmImageMleTool"]
