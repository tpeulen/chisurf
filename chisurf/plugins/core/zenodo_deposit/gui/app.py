"""Native emtk Zenodo deposit tool: review a record, then upload it as a draft.

The window is the view spec ``zenodo_deposit_emtk.view.json`` drawn by
:func:`emtk.view_form.draw_sections`; the review state, the gate and the
worker are :class:`~.model.ZenodoDepositModel`. Only Help and Guide are drawn
here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from emtk import im
from emtk.app import ImApp
from emtk.docking import DockManager, Region
from emtk.view_form import FormState, draw_sections

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.plugins.emtk_layout import action_button, window_size

from .model import ZenodoDepositModel

HERE = Path(__file__).parent


class ZenodoDepositApp(ImApp):
    """Review a deposition record and upload it to Zenodo."""

    def __init__(self, model: ZenodoDepositModel | None = None) -> None:
        self.model = model or ZenodoDepositModel()
        spec = json.loads((HERE / "zenodo_deposit_emtk.view.json").read_text(encoding="utf-8"))
        self.window_size = window_size(spec, (1280, 900))
        self.sections = spec["sections"]
        self.form = FormState()
        self.item_rects: dict[str, tuple] = {}
        self.help_window = EmTkHelpWindow(
            title="Zenodo deposit — Help", resource=HERE / "help_emtk.md", owner=self
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide_emtk.json",
            owner=self,
            wait_for_controls=True,
            get_target_rect=lambda key: self.item_rects.get(key) or self.form.rects.get(key),
        )
        self.form.on_used = self.tour.notify_used
        self.docks = DockManager(Region("deposit"))
        self.docks.add_window("deposit", "Zenodo deposit", self.draw_deposit, dock="deposit")
        super().__init__(self.render, continuous=True)

    def render(self) -> None:
        self.model.poll()
        vp = im.get_main_viewport()
        box = (*vp.pos, *vp.size)
        self.form.rects.clear()
        self.docks.draw(box)
        self.help_window.draw(box)
        self.tour.draw(*vp.size)

    def draw_deposit(self, box: Any) -> None:
        """Help / Guide, then the records, the items, the selected item and the upload."""
        if action_button("guide"):
            self.tour.start()
        self.item_rects["guide"] = im.get_item_rect()
        im.same_line()
        if action_button("help"):
            self.help_window.show()
        self.item_rects["help"] = im.get_item_rect()
        im.separator()
        draw_sections(self.sections, self.model, self.form, titles=True)
        for name in ("records", "items"):
            if name in self.form.rects:
                self.item_rects[f"{name}_table"] = self.form.rects[name]

    def export_settings(self) -> dict:
        """The data root and the sandbox switch; reviews live in the records."""
        return self.model.export_settings()

    def restore_settings(self, settings: dict) -> None:
        self.model.restore_settings(settings)

    def close(self) -> None:
        """Stop a running step; an upload in flight is abandoned, never half-published."""
        self.model.close()


def create_app() -> ZenodoDepositApp:
    """Build the deposit app (the manifest's ``entrypoints.emtk``)."""
    return ZenodoDepositApp()


make_app = create_app
