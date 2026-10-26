"""Native emtk Photon Table: the photons of a photon stream, a page at a time.

Both windows -- the file and its summary, the navigation, page fields, channel
and kind filters and the table of records -- are the view spec
``photon_table_emtk.view.json`` drawn by :func:`emtk.view_form.draw_sections`; the
table is its ``data_table``. The Kind column's colours are filled in here from
``core/record_kinds.yaml`` (:func:`kind_backgrounds`). The input is the Datasets
workspace: the generated Input section (the manifest's ``accepts[].from_workspace``)
and :func:`receive_photons`. Only the Help / Guide buttons and the load progress are
drawn here. All state and work is in :class:`~.model.PhotonTableViewModel`; the file is
read on a :class:`~chisurf.emtk.jobs.SnapshotJob`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from emtk import im
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.i18n import tr
from emtk.view_form import FormState, draw_sections

from chisurf.core.plugin.workspace_input import input_section, spec_for
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.emtk.jobs import SnapshotJob
from chisurf.plugins.emtk_layout import action_button, window_size

from ..core.model import record_kinds
from .model import PhotonTableViewModel

HERE = Path(__file__).parent
TABLE_NAME = "rows"
#: The table column that names a record's kind.
KIND_COLUMN = "kind"


def kind_backgrounds() -> dict[str, str]:
    """``{cell text: "#rrggbb"}`` of the Kind column: each declared kind's colour.

    A kind's colour is a category of the shell's colour vocabulary
    (``chisurf/emtk/task_colors.yaml``); its ``fill`` is the same in the dark and
    the light theme and the table draws the cell text in the ink that contrasts
    with it. The English label and the translated one both map to the colour.
    """
    from chisurf.emtk.task_colors import categories

    palette = categories()
    out: dict[str, str] = {}
    for kind in record_kinds():
        entry = palette.get(kind.colour or "")
        if not entry:
            continue
        fill = str(entry["dark"]["fill"])
        out[kind.label] = fill
        out[tr(kind.label)] = fill
    return out


def _colour_kind_column(spec: dict) -> None:
    """Give the spec's Kind column its ``background`` map (:func:`kind_backgrounds`)."""
    for panel in spec.get("sections", []):
        for section in panel.get("sections", []):
            for column in (section.get("options") or {}).get("columns", []):
                if column.get("key") == KIND_COLUMN:
                    column["background"] = kind_backgrounds()


class PhotonTableApp(ImApp):
    """Inspect the photons of a photon stream of the workspace in a table."""

    def __init__(self, model: PhotonTableViewModel | None = None) -> None:
        self.model = model or PhotonTableViewModel()
        self.job = SnapshotJob(self.model)
        spec = json.loads((HERE / "photon_table_emtk.view.json").read_text(encoding="utf-8"))
        _colour_kind_column(spec)
        self.window_size = window_size(spec, (1100, 720))
        self.panels = {p["name"]: p for p in spec["sections"]}
        self.form = FormState()
        manifest = json.loads((HERE.parent / "manifest.json").read_text(encoding="utf-8"))
        found = spec_for(manifest)
        #: The Input section: the workspace's photon streams.
        self.input_sections = [input_section(found[1])] if found else []
        self.model.workspace_input_app = self
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
        self.model.workspace_input_on_used = self.tour.notify_used
        self.docks = DockManager(Split("h", 0.34, Region("file"), Region("photons")))
        self.docks.add_window(
            "file",
            "Photon stream",
            self.draw_file,
            dock="file",
            closable=True,
            tooltip=str(self.panels["file"].get("description", "")),
        )
        self.docks.add_window(
            "photons",
            "Records",
            self.draw_photons,
            dock="photons",
            closable=True,
            tooltip=str(self.panels["photons"].get("description", "")),
        )
        super().__init__(self.render, continuous=True)

    # ── loading ────────────────────────────────────────────────────────
    def load_file(self, path: str) -> bool:
        """Read the photon stream *path* (a file or a container's stream) on a worker thread;
        refused while another load runs."""
        if self.job.busy:
            return False
        self._reported_error = ""
        return self.job.start("load_path", str(path))

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
        self.help_window.draw(box)
        self.tour.draw(*vp.size)

    # ── windows ────────────────────────────────────────────────────────
    def draw_file(self, box: Any) -> None:
        """The left window: Load example, Copy, Help, Guide, the Input section and the summary."""
        draw_sections(self.panels["file"]["sections"][:1], self.model, self.form, titles=False)
        if action_button("guide"):
            self.tour.start()
        self.item_rects["guide"] = im.get_item_rect()
        im.same_line()
        if action_button("help"):
            self.help_window.show()
        self.item_rects["help"] = im.get_item_rect()
        im.separator()
        draw_sections(self.input_sections, self.model, self.form, titles=False)
        if "workspace_input_rows" in self.form.rects:
            self.item_rects["workspace_input_rows"] = self.form.rects["workspace_input_rows"]
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
            im.text_disabled(tr("Loading the records..."))

    def draw_photons(self, box: Any) -> None:
        """The right window: navigation, page fields, channel and kind filters and the table."""
        draw_sections(self.panels["photons"]["sections"], self.model, self.form, titles=False)
        if TABLE_NAME in self.form.rects:
            self.item_rects["photon_table"] = self.form.rects[TABLE_NAME]

    # ── Copy ───────────────────────────────────────────────────────────
    def _requests(self) -> None:
        """Act on the model's ``request``: copy the rows."""
        request, self.model.request = self.model.request, ""
        if request == "copy" and self.model.loaded:
            im.set_clipboard_text(self.model.copy_text())
            self.model.notice = f"Copied {len(self.model.rows)} rows to the clipboard."

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


def receive_photons(app: PhotonTableApp, payload: dict) -> None:
    """Hand-off receiver (manifest ``accepts`` ``photons``): show the records of ``payload["file"]``,
    an address as the workspace hands it (a TTTR file or a container's photon stream)."""
    from chisurf.core.fio.address import container_of
    from chisurf.core.plugin.workspace_input import read_address

    address = read_address(str(payload["file"]))
    if not container_of(address).is_file():
        raise FileNotFoundError(f"{address} does not exist")
    if not app.load_file(address):
        raise RuntimeError(tr("the tool is busy; try again when it has finished"))
