"""GUI entrypoint for the N&B imaging plugin (toolbar + file drops)."""

from __future__ import annotations

import logging

from chisurf.plugins.microscopy.imaging_common.tool_base import ImagingMapTool

from .view_model import NBViewModel

logger = logging.getLogger(__name__)


class ImgPixelNBTool(ImagingMapTool):
    """Per-pixel Number & Brightness imaging tool."""

    def __init__(self, parent=None, embedded: bool = False, view_model=None, **kwargs):
        super().__init__(
            view_model or NBViewModel(),
            title="Number & Brightness",
            parent=parent,
            embedded=embedded,
            **kwargs,
        )
        toolbar = self.toolbar
        first = toolbar.actions()[0] if toolbar.actions() else None
        a_demo = toolbar.addAction("🧪 Load demo")
        a_demo.setToolTip(
            "Write and open a simulated scan whose answer is known: monomers on the left, "
            "dimers at the same intensity on the right."
        )
        a_demo.triggered.connect(self._load_demo)
        a_cal = toolbar.addAction("📐 Calibrate analog")
        a_cal.setToolTip(
            "With a static-gradient calibration file loaded and run: fit variance against "
            "mean and set the analog gain S and offset."
        )
        a_cal.triggered.connect(self.model.calibrate_analog)
        if first is not None:
            toolbar.insertAction(first, a_demo)
        from chisurf.gui.widgets.tools.help_guide import attach_help_and_guide

        attach_help_and_guide(self, toolbar, title="Number & Brightness — help", model=self.model)
        self.gate_overlay = self._connect_gates()

    def _load_demo(self) -> None:
        """Generate (or reuse) the demo photon stream and load it."""
        try:
            self.model.load_demo()
        except Exception as exc:  # noqa: BLE001 - surfaced in the panel
            logger.warning("N&B demo failed: %s", exc, exc_info=True)
            self.model.results_text = f"Demo failed: {exc}"
            self.model.notify("changed")

    def _connect_gates(self):
        """Draw the gate list on the parameter plane and re-gate the maps on an edit.

        The plane and the image are two views of the same pixels: a region drawn
        round a brightness population answers which pixels carry it, which is
        why an edit has to reach the Gated pixels map.
        """
        from chisurf.gui.widgets.roi import RegionEditor, RegionOverlay

        editor = self.auto_form.findChild(RegionEditor)
        plane = self.auto_form.section_widget(title="Parameter plane")
        if editor is None or plane is None:
            return None
        overlay = RegionOverlay(plane, lambda: self.model.gates, on_change=self._on_gates_changed)
        editor.changed.connect(self._on_gates_changed)
        editor.changed.connect(overlay.refresh)
        editor.selectionChanged.connect(overlay.select)
        overlay.refresh()
        return overlay

    def _on_model_event(self, event: str) -> None:
        """Refresh the form, and redraw the gate shapes when the gates or maps changed."""
        super()._on_model_event(event)
        overlay = getattr(self, "gate_overlay", None)
        if overlay is not None and event in ("gate", "run"):
            try:
                overlay.refresh()
            except Exception:  # noqa: BLE001 - a redraw must not break a refresh
                logger.debug("gate overlay refresh failed", exc_info=True)

    def _on_gates_changed(self) -> None:
        """A gate moved: refresh the gated map and the summary."""
        self.model.notify_gates()


__all__ = ["ImgPixelNBTool"]
