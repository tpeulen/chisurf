"""Native emtk colocalization tool (settings form, coefficient table, channel maps, intensity scatter and profiles from ``coloc_emtk.view.json``)."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from emtk import im
from emtk.docking import Region, Split

from ...imaging_emtk.app_base import ImagingToolApp
from ...imaging_emtk.editors import DetectorEditorMixin, PlaneMixin
from ...imaging_emtk.plane import PlanePanel, PlaneRegions
from ...imaging_emtk.views import ImagePanel
from .model import IMAGE_FILE_FILTER, ColocModel

HERE = Path(__file__).parent


class ColocApp(DetectorEditorMixin, PlaneMixin, ImagingToolApp):
    """Pearson, Manders, Li, Spearman, Costes and object coincidence of a pair of channels of one image."""

    GUI_DIR = HERE
    SPEC = "coloc_emtk.view.json"
    TITLE = "Colocalization"
    HELP_TITLE = "Colocalization - Help"
    ROLE = "img_coloc"
    CANCELLABLE = False
    LAYOUT = Split("h", 0.34, Region("settings"), Region("views"))
    DIALOGS = {
        "open": ("Open image", "open", IMAGE_FILE_FILTER, "open_path"),
        "export": ("Export colocalization results", "save", "CSV (*.csv)", "write_export"),
        "save_regions": ("Save regions", "save", "JSON (*.json)", "save_regions"),
        "load_regions": ("Load regions", "open", "JSON (*.json)", "load_regions"),
    }
    OUTCOMES = {"file": "filename", "computed": "run_coloc"}

    def __init__(self, model: ColocModel | None = None, coordinator: Any = None) -> None:
        self.coordinator = coordinator
        self.editor = None
        self._editor_busy = False
        self.planes: dict[str, Any] = {}
        self.region_lists: dict[str, Any] = {}
        self._pending: dict = {}
        super().__init__(model or ColocModel())
        m = self.model
        self.form.custom["channels"] = lambda section, mm, st, w: self._draw_channels(section)
        self.form.custom["plane"] = lambda section, mm, st, w: self._draw_plane(section)
        self.form.custom["region_list"] = lambda section, mm, st, w: self._draw_region_list(section)
        panel = PlanePanel("coloc_scatter", collection=lambda: m.gates, image=m.histogram_image, extent=m.gate_extent,
                           x_label="Channel A intensity", y_label="Channel B intensity", on_change=m.gates_edited, transpose=True,
                           empty="No scatter yet. Choose an image and press Run.", tooltip="Joint histogram: A horizontal, B vertical. Drag the blue region handles; right-drag pans while painting.",
                           paint=lambda ia, ib: m.paint("gate_paint", ib, ia) if False else self._paint_gate(ia, ib), painting=lambda: bool(m.paint_gate) and not m.busy)
        regions = PlaneRegions(lambda: m.gates, m.gate_extent, lambda kind: m.request_dialog(kind), m.gates_edited)
        self.add_plane("gates", panel, regions)
        self.channel_a_panel = ImagePanel("coloc_a")
        self.channel_b_panel = ImagePanel("coloc_b")
        self.panels["Channel A"], self.panels["Channel B"] = self.channel_a_panel, self.channel_b_panel
        m.tab_titles_list = tuple(t for t, w in self.windows.items() if w.get("dock") == "views") + ("Detectors",)
        m.view_tab = m.tab_titles_list[0]
        self._make_editor()
        m.tab_titles_list = tuple(t for t, w in self.windows.items() if w.get("dock") == "views")
        self.model.has_host = coordinator is not None

    def _paint_gate(self, ia: int, ib: int) -> None:
        self.model.paint("gate_paint", ia, ib)

    # -- the channel maps with the region brush ---------------------------------------------------- #
    def _draw_channels(self, section: dict) -> None:
        m = self.model
        width = max(100.0, im.get_content_region_avail()[0] / 2.0 - 8.0)
        x, y = im.get_cursor_screen_pos()
        height = max(120.0, im.get_content_region_avail()[1] - 4.0)
        for i, (panel, title, array) in enumerate(((self.channel_a_panel, "Channel A", m.image_a()), (self.channel_b_panel, "Channel B", m.image_b()))):
            im.begin_child((x + i * (width + 8.0), y, width, height), clip=True, child_id=f"coloc_ch{i}")
            im.text(title)
            panel.canvas.image_label = title
            if array is None:
                from ...imaging_emtk.views import muted

                muted("No image yet. Choose an image and press Run.")
            else:
                brush = (lambda p: m.paint("roi_mask", int(p[1]), int(p[2])) if not m.busy else None) if (i == 0 and m.paint_roi) else None
                panel.canvas.colormap = m.colormap if m.colormap in ("magma", "inferno", "viridis", "gray") else panel.canvas.colormap
                panel.canvas.draw(array, pick_enabled=brush is not None, analysis_editable=False, selection=(m.roi_mask if i == 0 else None), selection_version=m.mask_version,
                                  on_brush=brush)
                m.colormap = panel.canvas.colormap
                self.item_rects[title] = tuple(panel.canvas.rect or (0, 0, 0, 0))
            im.end_child()
        if (m.dirty_roi or m.dirty_gate) and not im.is_mouse_down(0):
            m.end_stroke()
        self.item_rects["Channels"] = self.item_rects.get("Channel A", (0, 0, 0, 0))

    def _draw_window(self, panel: dict) -> None:
        super()._draw_window(panel)
        if self.model.dirty_gate and not im.is_mouse_down(0):
            self.model.end_stroke()

    # -- hub contract ---------------------------------------------------------------------------- #
    def start(self, method: str = "compute_job", *args: Any) -> bool:
        self.model.run_coloc()
        return self.job.busy

    def apply_setup_settings(self, payload: dict) -> None:
        if self.job.busy or self.model.busy:
            self._pending["setup"] = copy.deepcopy(payload)
            return
        self.model.apply_setup_settings(payload)
        self._sync_editor(payload)
        self.request_frame()

    def apply_pipeline_context(self, payload: dict) -> None:
        if self.job.busy or self.model.busy:
            self._pending["pipeline"] = dict(payload)
            return
        self.model.apply_pipeline_context(payload)
        self.request_frame()

    def apply_calibration(self, payload: dict) -> None:
        """Colocalization has no calibration input."""

    def _draw_main(self, box: tuple) -> None:
        if self._pending and not (self.job.busy or self.model.busy):
            pending, self._pending = dict(self._pending), {}
            if "setup" in pending:
                self.apply_setup_settings(pending["setup"])
            if "pipeline" in pending:
                self.apply_pipeline_context(pending["pipeline"])
        super()._draw_main(box)
        if self.editor is not None:
            self.editor.draw_dialogs(box)

    def _on_event(self, event: str) -> None:
        super()._on_event(event)
        if event == "view" and self.model.view_tab in self.windows:
            self.docks.focus(self.model.view_tab)

    def export_settings(self) -> dict:
        state = self.model.export_settings()
        state["docks"] = self.docks.state()
        return state

    def restore_settings(self, state: dict) -> None:
        if self.job.busy or not isinstance(state, dict):
            return
        self.model.restore_settings(state)
        self._sync_editor()
        if state.get("docks"):
            self.docks.restore(state["docks"])

    def close(self) -> None:
        super().close()


def make_app(coordinator=None) -> ColocApp:
    """Factory named by the manifest's ``entrypoints.emtk``."""
    from chisurf.emtk.i18n import install

    install()
    return ColocApp(coordinator=coordinator)
