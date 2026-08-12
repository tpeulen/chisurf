"""GUI entrypoint for the molecule-wise MLE tool (AutoForm + view.json).

``RegionMleTool`` hosts an :class:`~chisurf.gui.autoform.AutoForm` bound to the
Qt-free :class:`~...gui.view_model.RegionMleViewModel`. The heavy analysis
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

from .view_model import RegionMleViewModel


class RegionMleTool(AutoFormMleTool):
    """Region MLE tool (AutoForm-hosted)."""

    def __init__(self, parent=None, embedded: bool = False, view_model=None):
        super().__init__(
            view_model or RegionMleViewModel(),
            "Region MLE",
            parent=parent,
            embedded=embedded,
            min_size=(640, 420),
        )
        self.region_overlay, self.molecule_overlay = self._connect_regions()

    # ── regions: the one drawn, and the ones measured ──────────────────
    def _connect_regions(self):
        """Draw the analysis region on the image, and the molecules beside it.

        Two overlays on the same canvas, and they mean different things. The
        analysis region is a *control*: draggable, and every edit re-collapses
        the list into the single region the segmentation is confined to. The
        molecules are a *result*: the second-moment ellipse of each measured
        object, drawn read-only, because a drag there would claim to edit
        something the analysis owns.
        """
        from chisurf.gui.autoform.sections.image_browser_section import ImageBrowserWidget
        from chisurf.gui.widgets.roi import RegionEditor, RegionOverlay

        editor = self.auto_form.findChild(RegionEditor)
        canvas = self.auto_form.findChild(ImageBrowserWidget)
        if editor is None or canvas is None:
            return None, None

        regions = RegionOverlay(canvas, lambda: self.model.regions,
                                on_change=self.model.apply_regions)
        molecules = RegionOverlay(canvas, self.model.molecule_regions, movable=False)
        editor.changed.connect(self.model.apply_regions)
        editor.changed.connect(regions.refresh)
        editor.selectionChanged.connect(regions.select)
        regions.refresh()
        return regions, molecules

    def _refresh_region_overlays(self) -> None:
        """Redraw both overlays — the image or the molecule set has changed."""
        for overlay in (self.region_overlay, self.molecule_overlay):
            if overlay is not None:
                overlay.refresh()

    def handle_event(self, event: str) -> bool:
        """Run the preview and the demo on a worker; prompt for export on the UI thread."""
        if event == "start_preview":
            self._start_job(self.model.preview_regions)
            return True
        if event == "start_demo":
            self._start_job(self.model.load_demo)
            return True
        if event == "start_export":
            self._export()
            return True
        if event in ("done", "preview", "results"):
            # A new segmentation means new measured molecules to outline; the
            # canvas may also have swapped to another file's image.
            self._refresh_region_overlays()
        return False

    def _export(self) -> None:
        """Prompt for a path and export the region table (UI thread)."""
        if not self.model.has_results():
            self.model.status_text = "No regions to export."
            self._refresh()
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export region table", "regions.tsv", "Tables (*.tsv *.csv)"
        )
        if path:
            self.model.export_results(path)


__all__ = ["RegionMleTool"]
