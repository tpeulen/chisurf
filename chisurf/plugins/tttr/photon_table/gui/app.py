"""Native emtk Photon Table: the photons of a TTTR file, a page at a time.

Both windows -- the file and its summary, the navigation, page fields, channel
filter and the table of photons -- are the view spec ``photon_table_emtk.view.json``
drawn by :func:`emtk.view_form.draw_sections`; the table is its ``data_table``.
Only the Help / Guide buttons, the file dialog and the load progress are drawn
here. All state and work is in :class:`~.model.PhotonTableViewModel`; the file is
read on a :class:`~chisurf.emtk.jobs.SnapshotJob`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from emtk import im
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog
from emtk.view_form import FormState, draw_sections

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.emtk.jobs import SnapshotJob

from .model import TTTR_FILTERS, PhotonTableViewModel

HERE = Path(__file__).parent
TABLE_NAME = "rows"


class PhotonTableApp(ImApp):
    """Inspect the photons of a TTTR file in a table."""

    def __init__(self, model: PhotonTableViewModel | None = None) -> None:
        self.model = model or PhotonTableViewModel()
        self.job = SnapshotJob(self.model)
        spec = json.loads((HERE / "photon_table_emtk.view.json").read_text(encoding="utf-8"))
        self.panels = {p["name"]: p for p in spec["sections"]}
        self.form = FormState()
        self.dialog: FileDialog | None = None
        self.item_rects: dict[str, tuple] = {}
        self._reported_error = ""
        self.help_window = EmTkHelpWindow(
            title="Photon Table — Help", resource=HERE / "help.md", owner=self
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            owner=self,
            wait_for_controls=True,
            get_target_rect=lambda key: self.item_rects.get(key) or self.form.rects.get(key),
        )
        self.form.on_used = self.tour.notify_used
        self.docks = DockManager(Split("h", 0.34, Region("file"), Region("photons")))
        self.docks.add_window("file", "TTTR file", self.draw_file, dock="file", closable=True)
        self.docks.add_window(
            "photons", "Photons", self.draw_photons, dock="photons", closable=True
        )
        super().__init__(self.render, continuous=True)

    # ── loading ────────────────────────────────────────────────────────
    def load_file(self, path: str) -> bool:
        """Read *path* on a worker thread; refused while another load runs."""
        if self.job.busy:
            return False
        self._reported_error = ""
        return self.job.start("load_path", str(path))

    def files_dropped(self, paths: Any) -> bool:
        """Host hook: a dropped TTTR file is opened (the first one)."""
        paths = [str(p) for p in paths or []]
        return bool(paths) and self.load_file(paths[0])

    on_files_dropped = files_dropped
    on_paths_dropped = files_dropped

    # ── one frame ──────────────────────────────────────────────────────
    def render(self) -> None:
        self.job.poll()
        self.model.busy = self.job.busy
        if self.job.error and self.job.error != self._reported_error:
            self._reported_error = self.job.error
            self.model.notice = f"Could not open the file: {self.job.error}"
        vp = im.get_main_viewport()
        box = (*vp.pos, *vp.size)
        self.form.rects.clear()
        self.docks.draw(box)
        self._requests()
        self._draw_file_dialog()
        self.help_window.draw(box)
        self.tour.draw(*vp.size)

    # ── windows ────────────────────────────────────────────────────────
    def draw_file(self, box: Any) -> None:
        """The left window: Open, Copy, Help, Guide and the file summary."""
        draw_sections(self.panels["file"]["sections"][:1], self.model, self.form, titles=False)
        if im.button("Guide"):
            self.tour.start()
        im.set_item_tooltip("A step-by-step walk through the tool.")
        self.item_rects["guide"] = im.get_item_rect()
        im.same_line()
        if im.button("Help"):
            self.help_window.show()
        im.set_item_tooltip("The short help page.")
        self.item_rects["help"] = im.get_item_rect()
        im.separator()
        x0, y0 = im.get_cursor_screen_pos()
        draw_sections(self.panels["file"]["sections"][1:], self.model, self.form, titles=False)
        x1, y1 = im.get_cursor_screen_pos()
        # the summary block, as a target for the guided tour (an info line records no rect)
        self.item_rects["file_summary"] = (
            x0,
            y0,
            max(im.get_content_region_avail()[0], 1.0),
            max(y1 - y0, 1.0),
        )
        if self.job.busy:
            im.text_disabled("Loading the photons...")

    def draw_photons(self, box: Any) -> None:
        """The right window: navigation, page fields, channel filter and the table."""
        draw_sections(self.panels["photons"]["sections"], self.model, self.form, titles=False)
        if TABLE_NAME in self.form.rects:
            self.item_rects["photon_table"] = self.form.rects[TABLE_NAME]

    # ── Open and Copy ──────────────────────────────────────────────────
    def _requests(self) -> None:
        """Act on the model's ``request``: open the file dialog, or copy the rows."""
        request, self.model.request = self.model.request, ""
        if request == "open" and self.dialog is None:
            self.dialog = FileDialog(
                "Open TTTR file", filters=TTTR_FILTERS, directory=self.model.drop_directory()
            )
        elif request == "copy" and self.model.loaded:
            im.set_clipboard_text(self.model.copy_text())
            self.model.notice = f"Copied {len(self.model.rows)} rows to the clipboard."

    def _draw_file_dialog(self) -> None:
        if self.dialog is None:
            return
        if im.begin(self.dialog.title):
            result = self.dialog.draw()
            if result:
                self.dialog = None
                self.load_file(result[0])
            elif result is False:
                self.dialog = None
        im.end()

    # ── persistence ────────────────────────────────────────────────────
    def export_settings(self) -> dict:
        """What is remembered: the page size and the last file."""
        return self.model.export_settings()

    def restore_settings(self, settings: dict) -> None:
        """Restore :meth:`export_settings`."""
        self.model.restore_settings(settings)

    def close(self) -> None:
        """Detach the model's observers."""
        self.model._observers.clear()


def make_app() -> PhotonTableApp:
    """Build the Photon Table app (the manifest's ``entrypoints.emtk``)."""
    return PhotonTableApp()
