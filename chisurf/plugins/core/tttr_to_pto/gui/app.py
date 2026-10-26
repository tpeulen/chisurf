"""Native emtk TTTR <-> .pto converter: pack a vendor photon stream, unpack a container.

The window is the view spec ``tttr_to_pto_emtk.view.json`` drawn by
:func:`emtk.view_form.draw_sections`, with the generated Input section first (the
workspace's photon streams, as the manifest's ``accepts[].from_workspace`` declares).
Only the Help / Guide buttons are handled here; the queue, the worker and the
conversions are :class:`~.model.TttrToPtoModel`, and :func:`receive_photons` is how
the workspace hands it data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from emtk import im
from emtk.app import ImApp
from emtk.docking import DockManager, Region
from emtk.view_form import FormState, draw_sections

from chisurf.core.plugin.workspace_input import spec_for, with_workspace_input
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.plugins.emtk_layout import action_button, window_size

from .model import TttrToPtoModel

HERE = Path(__file__).parent
TABLE_NAME = "records"


class TttrToPtoApp(ImApp):
    """Pack vendor photon streams into a .pto, or unpack a .pto, as picked from the workspace."""

    def __init__(self, converter=None, extractor=None) -> None:
        self.model = TttrToPtoModel(converter, extractor)
        spec = json.loads((HERE / "tttr_to_pto_emtk.view.json").read_text(encoding="utf-8"))
        self.window_size = window_size(spec, (1200, 800))
        manifest = json.loads((HERE.parent / "manifest.json").read_text(encoding="utf-8"))
        found = spec_for(manifest)
        if found is not None:  # the input: the workspace's photon streams
            spec = with_workspace_input(spec, found[1])
        self.sections = spec["sections"]
        self.form = FormState()
        self.model.workspace_input_app = self
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
        self.model.workspace_input_on_used = self.tour.notify_used
        self.docks = DockManager(Region("conversion"))
        self.docks.add_window("conversion", "TTTR ⇄ .pto", self.draw_conversion, dock="conversion")
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

    def add_paths(self, paths: Any, *, source: str = "") -> bool:
        """Queue paths (see :meth:`TttrToPtoModel.add_paths`): the API's and scripts' route."""
        return self.model.add_paths(paths, source=source)

    # ── one frame ──────────────────────────────────────────────────────
    def render(self) -> None:
        self.model.poll()
        vp = im.get_main_viewport()
        box = (*vp.pos, *vp.size)
        self.form.rects.clear()
        self.docks.draw(box)
        self.help_window.draw(box)
        self.tour.draw(*vp.size)

    def draw_conversion(self, box: Any) -> None:
        """The window: Help / Guide, the hint, the buttons, the status and the history."""
        if action_button("guide"):
            self.tour.start()
        self.item_rects["guide"] = im.get_item_rect()
        im.same_line()
        if action_button("help"):
            self.help_window.show()
        self.item_rects["help"] = im.get_item_rect()
        im.separator()
        draw_sections(self.sections, self.model, self.form, titles=False)
        if TABLE_NAME in self.form.rects:
            self.item_rects["conversion_table"] = self.form.rects[TABLE_NAME]
        if "workspace_input_rows" in self.form.rects:
            self.item_rects["workspace_input_rows"] = self.form.rects["workspace_input_rows"]

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


def receive_photons(app: TttrToPtoApp, payload: dict) -> None:
    """Hand-off receiver (manifest ``accepts`` ``convert``): convert ``payload["files"]``.

    The values are addresses as the workspace hands them: a vendor photon file is packed (those
    handed over together into one container), a photon stream of a ``.pto`` unpacks its container.
    ``datasets`` (their uids) names the source: what is written becomes its child in the workspace.
    """
    from chisurf.core.plugin.workspace_input import read_address
    from chisurf.plugins.tttr.workspace_io import container_files

    files = payload.get("files")
    addresses = [files] if isinstance(files, str) else list(files or [])
    paths = container_files(read_address(a) for a in addresses)
    if not paths:
        raise ValueError("no photon stream was handed over")
    source = str((payload.get("datasets") or [""])[0])
    app.model.add_paths(paths, source=source)


def create_app() -> TttrToPtoApp:
    """Build the converter app (the manifest's ``entrypoints.emtk``)."""
    return TttrToPtoApp()


make_app = create_app
