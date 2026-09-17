"""GUI entrypoint for the phasor-FLIM imaging plugin (toolbar + file drops)."""

from __future__ import annotations

from chisurf.plugins.microscopy.imaging_common.tool_base import ImagingMapTool

from .view_model import PhasorImgViewModel


class ImgPixelPhasorTool(ImagingMapTool):
    """Per-pixel phasor-FLIM imaging tool."""

    def __init__(self, parent=None, embedded: bool = False, view_model=None, **kwargs):
        super().__init__(
            view_model or PhasorImgViewModel(),
            title="Phasor-FLIM",
            parent=parent,
            embedded=embedded,
            **kwargs,
        )
        self.cursor_overlay = self._connect_cursors()

    def _connect_cursors(self):
        """Draw the cursor list on the phasor plane and gate the image with it.

        The phasor plot and the intensity map are two views of the same pixels:
        a cursor drawn round a lifetime cluster answers *which pixels* have that
        lifetime, which is why the edit has to reach the maps. Until the shared
        region GUI existed this tool had no interactive cursor at all — the
        ellipse lived in the analysis API and nothing could draw one.
        """
        from chisurf.gui.widgets.roi import RegionEditor, RegionOverlay

        editor = self.auto_form.findChild(RegionEditor)
        # By title, not by type: this tool has two phasor sections — the static
        # plot and the movie — and picking the first of the type attached the
        # cursors to the one the user is not looking at.
        plane = self.auto_form.section_widget(title="Phasor plot")
        if editor is None or plane is None:
            return None

        overlay = RegionOverlay(
            plane, lambda: self.model.cursors, on_change=self._on_cursors_changed
        )
        editor.changed.connect(self._on_cursors_changed)
        editor.changed.connect(overlay.refresh)
        editor.selectionChanged.connect(overlay.select)
        overlay.refresh()
        return overlay

    def _on_cursors_changed(self) -> None:
        """A cursor moved: re-gate the maps that depend on it."""
        self.model.notify_cursors()
        try:
            self.auto_form.refresh_plots()
        except Exception:  # noqa: BLE001 - a refresh must not break a drag
            pass


__all__ = ["ImgPixelPhasorTool"]
