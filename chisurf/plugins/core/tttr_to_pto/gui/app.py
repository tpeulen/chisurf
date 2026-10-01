"""Native emtk TTTR <-> .pto converter: drop vendor files to pack, a .pto to unpack.

The window is the view spec ``tttr_to_pto_emtk.view.json`` drawn by
:func:`emtk.view_form.draw_sections` (the history is its ``data_table``). Only the
Help / Guide buttons, the file dialog and the file drop are handled here; the
queue, the worker and the conversions are :class:`~.model.TttrToPtoModel`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from emtk import im
from emtk.app import ImApp
from emtk.docking import DockManager, Region
from emtk.file_dialog import FileDialog
from emtk.view_form import FormState, draw_sections

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow

from .model import FILE_FILTERS, TttrToPtoModel

HERE = Path(__file__).parent
TABLE_NAME = "records"


class TttrToPtoApp(ImApp):
    """Pack vendor photon files into a .pto, or unpack a .pto, by drop or by dialog."""

    def __init__(self, converter=None, extractor=None) -> None:
        self.model = TttrToPtoModel(converter, extractor)
        spec = json.loads((HERE / "tttr_to_pto_emtk.view.json").read_text(encoding="utf-8"))
        self.sections = spec["sections"]
        self.form = FormState()
        self.dialog: FileDialog | None = None
        self.item_rects: dict[str, tuple] = {}
        self.help_window = EmTkHelpWindow(
            title="TTTR ⇄ .pto — Help", resource=HERE / "help_emtk.md", owner=self
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide_emtk.json",
            owner=self,
            wait_for_controls=True,
            get_target_rect=lambda key: self.item_rects.get(key) or self.form.rects.get(key),
        )
        self.form.on_used = self.tour.notify_used
        self.docks = DockManager(Region("conversion"))
        self.docks.add_window(
            "conversion", "TTTR ⇄ .pto", self.draw_conversion, dock="conversion"
        )
        super().__init__(self.render, continuous=True)

    # ── compatibility with the earlier app's surface ───────────────────
    @property
    def rows(self) -> list:
        return self.model.rows

    @property
    def job(self):
        return self.model.job

    @property
    def pending(self):
        return self.model.pending

    accepts = staticmethod(TttrToPtoModel.accepts)

    def poll(self) -> None:
        self.model.poll()

    def clear_history(self) -> None:
        self.model.clear_history()

    def add_paths(self, paths: Any) -> bool:
        """Queue dropped or chosen paths (see :meth:`TttrToPtoModel.add_paths`)."""
        return self.model.add_paths(paths)

    def files_dropped(self, paths: Any) -> bool:
        """Host hook: files dropped on the window. ``True`` when any was accepted."""
        return self.model.add_paths([str(p) for p in paths or []])

    on_files_dropped = files_dropped
    on_paths_dropped = files_dropped

    # ── one frame ──────────────────────────────────────────────────────
    def render(self) -> None:
        self.model.poll()
        vp = im.get_main_viewport()
        box = (*vp.pos, *vp.size)
        self.form.rects.clear()
        self.docks.draw(box)
        self._requests()
        self._draw_file_dialog()
        self.help_window.draw(box)
        self.tour.draw(*vp.size)

    def draw_conversion(self, box: Any) -> None:
        """The window: Help / Guide, the hint, the buttons, the status and the history."""
        if im.button("Guide"):
            self.tour.start()
        im.set_item_tooltip("Walk through packing, unpacking and sidecar handling.")
        self.item_rects["guide"] = im.get_item_rect()
        im.same_line()
        if im.button("Help"):
            self.help_window.show()
        im.set_item_tooltip("Read the conversion rules and verification guarantees.")
        self.item_rects["help"] = im.get_item_rect()
        im.separator()
        draw_sections(self.sections, self.model, self.form, titles=False)
        if TABLE_NAME in self.form.rects:
            self.item_rects["conversion_table"] = self.form.rects[TABLE_NAME]

    # ── the file dialog ────────────────────────────────────────────────
    def _requests(self) -> None:
        request, self.model.request = self.model.request, ""
        if request == "add" and self.dialog is None:
            self.dialog = FileDialog(
                "Add files",
                filters=FILE_FILTERS,
                directory=self.model.last_dir,
                multiselect=True,
            )

    def _draw_file_dialog(self) -> None:
        if self.dialog is None:
            return
        if im.begin(self.dialog.title):
            result = self.dialog.draw()
            if result:
                self.dialog = None
                self.model.add_paths(result)
            elif result is False:
                self.dialog = None
        im.end()

    # ── persistence ────────────────────────────────────────────────────
    def export_settings(self) -> dict:
        """What is remembered: the history (documentary) and the last folder."""
        return self.model.export_settings()

    def restore_settings(self, settings: dict) -> None:
        """Restore :meth:`export_settings`; the history is never replayed."""
        self.model.restore_settings(settings)

    def close(self) -> None:
        """Stop queued conversions; a write in progress finishes safely."""
        self.model.close()


def create_app() -> TttrToPtoApp:
    """Build the converter app (the manifest's ``entrypoints.emtk``)."""
    return TttrToPtoApp()


make_app = create_app
