"""GUI entrypoint for the spot finder (AutoForm + view.json).

``SpotFinderTool`` hosts an :class:`~chisurf.gui.autoform.AutoForm` bound to the
Qt-free :class:`~..gui.view_model.SpotFinderViewModel`. Detection runs on a
background thread, and the field, the region list and the run table refresh when
it finishes.

The window shell is the one the MLE imaging tools already share
(:class:`~chisurf.plugins.microscopy.mle_common.tool_base.AutoFormMleTool`), so
this panel behaves like the one below it in the Imaging Tools toolbox: same
Run/Preview/Export events, same embedded mode, same shared-setup adapters.
"""

from __future__ import annotations

from qtpy import QtWidgets

from chisurf.plugins.microscopy.mle_common.tool_base import AutoFormMleTool

from .view_model import SpotFinderViewModel


class SpotFinderTool(AutoFormMleTool):
    """Spot Finder tool (AutoForm-hosted)."""

    def __init__(self, parent=None, embedded: bool = False, view_model=None):
        super().__init__(
            view_model or SpotFinderViewModel(),
            "Spot Finder",
            parent=parent,
            embedded=embedded,
            min_size=(640, 420),
        )
        self.region_overlay, self.found_overlay, self.picked_overlay = self._connect_regions()

    def _connect_regions(self):
        """Draw the analysis region on the field, and the found regions beside it.

        Two overlays, two meanings. The analysis region is a *control* —
        draggable, and every edit re-collapses the list into the one region the
        search is confined to. What was found is a *result*: each region's
        second-moment ellipse, drawn read-only, because dragging one would claim
        to edit something the detector owns.
        """
        from chisurf.gui.autoform.sections.image_browser_section import ImageBrowserWidget
        from chisurf.gui.widgets.roi import RegionEditor, RegionOverlay

        editor = self.auto_form.findChild(RegionEditor)
        canvas = self.auto_form.findChild(ImageBrowserWidget)
        if editor is None or canvas is None:
            return None, None

        regions = RegionOverlay(
            canvas, lambda: self.model.regions, on_change=self.model.apply_regions
        )
        found = RegionOverlay(canvas, self.model.region_regions, movable=False)
        # A third overlay, because a pick is neither of the other two: it is not
        # a control the user drags, and it is not yet part of the detection —
        # it is a proposal, and all of them stay visible until they are added.
        picked = RegionOverlay(canvas, self.model.picked_regions, movable=False)
        editor.changed.connect(self.model.apply_regions)
        editor.changed.connect(regions.refresh)
        editor.selectionChanged.connect(regions.select)
        regions.refresh()
        return regions, found, picked

    def _refresh_region_overlays(self) -> None:
        """Redraw both overlays — the field or the detection has changed."""
        for overlay in (self.region_overlay, self.found_overlay, self.picked_overlay):
            if overlay is not None:
                overlay.refresh()

    def handle_event(self, event: str) -> bool:
        """Preview runs on a worker; export prompts on the UI thread."""
        if event == "start_preview":
            self._start_job(self.model.preview)
            return True
        if event == "start_demo":
            self._start_job(self.model.load_demo)
            return True
        if event == "start_export":
            self._export()
            return True
        if event == "start_add_picks":
            self.model.add_picked_to_detection()
            self._refresh()
            return True
        if event == "start_clear_picks":
            self.model.clear_picked()
            self._refresh()
            return True
        if event in ("done", "preview", "results", "picked"):
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
