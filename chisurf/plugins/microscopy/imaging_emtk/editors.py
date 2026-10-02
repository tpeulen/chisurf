"""Mixins the imaging apps share: the embedded detector editor, and planes with region lists."""

from __future__ import annotations

import copy
from typing import Any

from chisurf.plugins.emtk_layout import layout_spec  # noqa: F401 - re-exported for apps that lay out their spec


class DetectorEditorMixin:
    """The detector / channel editor of the Setup tool as a "Detectors" window (needs ``self.model._windows()`` and ``apply_setup_settings``)."""

    editor: Any = None
    _editor_busy: bool = False

    def _make_editor(self) -> None:
        """The detector / channel editor of the Setup tool, embedded as the "Detectors" window."""
        try:
            from chisurf.core.setup_channel_definition import ChannelDefinition
            from chisurf.emtk.channel_definition import ChannelDefinitionWidget
        except Exception:  # the editor is optional: the tool computes the channel-0 window without it
            return
        self.editor = ChannelDefinitionWidget(model=ChannelDefinition(self._editor_settings()), on_changed=self._editor_changed)
        self.editor.on_used = self.tour.notify_used
        self.docks.add_window("Detectors", "Detectors", lambda box: self._draw_editor(), dock="views", closable=False)
        self.windows["Detectors"] = {"title": "Detectors", "dock": "views"}

    def _editor_settings(self) -> dict:
        """What the editor shows: the detector windows this tool computes (the channel-0 window when none were set)."""
        detectors = {}
        for name, det in self.model._windows().items():
            detectors[name] = {"chs": list(det.get("chs", [0])), "micro_time_ranges": [list(r) for r in (det.get("micro_time_ranges") or [])],
                               "g_factor": 1.0, "l1": 0.0, "l2": 0.0}
        return {"windows": {}, "detectors": detectors,
                "tttr_reading": {"file_type": "PTU", "macro_time_resolution": 50.0, "micro_time_resolution": 50.0, "micro_time_binning": 1}}

    def _editor_changed(self, settings: dict) -> None:
        """A window or detector was edited: the tool computes the new windows on its next run."""
        if self._editor_busy:
            return
        self.model.apply_setup_settings(copy.deepcopy(settings))
        self.model.status_line = "Detector windows changed. Press Run to recompute."

    def _draw_editor(self) -> None:
        if self.editor is not None:
            self.editor.draw()
            self.item_rects.update({f"detectors.{k}": v for k, v in self.editor.item_rects.items()})
            if self.editor.item_rects.get("section_detectors"):
                self.item_rects["Detectors"] = self.editor.item_rects["section_detectors"]

    def _sync_editor(self, payload: dict | None = None) -> None:
        """Show the windows the model computes in the detector editor (without answering with a change)."""
        if self.editor is None:
            return
        self._editor_busy = True
        try:
            self.editor.load_definition(copy.deepcopy(payload) if payload else self._editor_settings())
        except Exception:  # an editor that cannot take the payload keeps its own windows
            pass
        finally:
            self._editor_busy = False



class PlaneMixin:
    """Plane views and the region lists that edit what they show (spec sections ``plane`` and ``region_list``)."""

    def add_plane(self, name: str, panel: Any, regions: Any = None) -> None:
        """Register a plane view (and the region list that edits what it shows) under the name a spec section refers to."""
        self.planes[name] = panel
        if regions is not None:
            self.region_lists[name] = regions

    def _draw_plane(self, section: dict) -> None:
        name = str(section.get("options", {}).get("name", section.get("title", "")))
        panel = self.planes[name]
        panel.draw(self.model.colormap)
        self.model.colormap = panel.canvas.colormap
        if panel.rect[2] > 0:
            self.item_rects[str(section.get("title", name))] = panel.rect

    def _draw_region_list(self, section: dict) -> None:
        from emtk import im as _im

        name = str(section.get("options", {}).get("name", section.get("title", "")))
        controls = self.region_lists[name]
        controls.draw()
        summary = getattr(self.model, str(section.get("options", {}).get("summary", "")), None)
        if callable(summary):
            _im.text_wrapped(summary())
        if section.get("options", {}).get("clear", True):
            if _im.button(f"Clear all##{name}"):
                self.model.clear_regions()
            _im.set_item_tooltip("Remove every region; all pixels are selected again.")
            self.item_rects[f"{name}.clear"] = _im.get_item_rect()

