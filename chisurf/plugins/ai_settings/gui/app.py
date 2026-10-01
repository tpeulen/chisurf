"""Native emtk AI Settings tool (Qt-free), at parity with the Qt tool.

The form -- the three collapsible sections of the Qt tool (API Configuration,
Models, Generation Settings), the Test connection / Save / Reset row and the
result line -- is the view spec ``ai_settings_emtk.view.json`` drawn by
:func:`emtk.view_form.draw_sections`. Only the Help / Guide buttons are drawn
here. All state and work is in :class:`~.model.AISettingsModel`; Fetch models,
Test connection and a pasted key's check run on a
:class:`~chisurf.emtk.jobs.SnapshotJob` so a slow endpoint never freezes the
window.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from emtk import im
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.view_form import FormState, draw_sections

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.emtk.jobs import SnapshotJob

from .model import AISettingsModel, BackgroundCall, describe_error

HERE = Path(__file__).parent

_SETTINGS, _ACTIONS = "settings", "actions"


class AISettingsApp(ImApp):
    """Edit the AI provider settings."""

    def __init__(self, model: AISettingsModel | None = None) -> None:
        self.model = model or AISettingsModel()
        self.call = BackgroundCall()
        self.job = SnapshotJob(self.call)
        self.model.async_runner = self.start_request
        spec = json.loads((HERE / "ai_settings_emtk.view.json").read_text(encoding="utf-8"))
        self.panels = {p["name"]: p for p in spec["sections"]}
        self.form = FormState()
        self.item_rects: dict[str, tuple] = {}
        self._reported_error = ""
        self.help_window = EmTkHelpWindow(
            title="AI Settings — Help", resource=HERE / "help.md", owner=self
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            owner=self,
            wait_for_controls=True,
            get_target_rect=lambda key: self.item_rects.get(key) or self.form.rects.get(key),
        )
        self.form.on_used = self.tour.notify_used
        # The form scrolls in its own window and the action bar with the result stays under it,
        # so the buttons and the answer are never scrolled out of sight.
        self.docks = DockManager(Split("v", 0.78, Region("settings"), Region("actions")))
        self.docks.add_window(
            "settings", "AI Settings", self.draw_settings, dock="settings", closable=False
        )
        self.docks.add_window(
            "actions", "Test / Save / Reset", self.draw_actions, dock="actions", closable=False
        )
        super().__init__(self.render, continuous=True)

    # -- jobs -------------------------------------------------------------- #
    def start_request(self, work: Any, done: Any) -> bool:
        """Run *work* on a snapshot job and hand its answer to *done* when polled.

        Returns False when a request is already running (the model says so).
        """
        if self.job.busy:
            return False
        self._reported_error = ""
        self.call.prepare(work, done)
        return self.job.start("run")

    # -- one frame --------------------------------------------------------- #
    def render(self) -> None:
        self.job.poll()
        self.model.busy = self.job.busy
        if self.job.error and self.job.error != self._reported_error:
            self._reported_error = self.job.error
            self.model._set_status(f"Failed: {describe_error(RuntimeError(self.job.error))}", "red")
        vp = im.get_main_viewport()
        box = (*vp.pos, *vp.size)
        self.form.rects.clear()
        self.docks.draw(box)
        self.help_window.draw(box)
        self.tour.draw(*vp.size)

    # -- windows ----------------------------------------------------------- #
    def draw_settings(self, box: Any) -> None:
        """The settings window: Help / Guide and the folding sections."""
        if im.button("Help"):
            self.help_window.show()
        im.set_item_tooltip("Explain the providers, the key, the models and the buttons.")
        self.item_rects["help"] = im.get_item_rect()
        im.same_line()
        if im.button("Guide"):
            self.tour.start()
        im.set_item_tooltip("Walk through choosing a provider, fetching models and testing it.")
        self.item_rects["guide"] = im.get_item_rect()
        draw_sections(self.panels[_SETTINGS]["sections"], self.model, self.form, titles=False)

    def draw_actions(self, box: Any) -> None:
        """The Test connection / Save / Reset bar and the result line."""
        draw_sections(self.panels[_ACTIONS]["sections"], self.model, self.form, titles=False)

    # -- persistence ------------------------------------------------------- #
    def export_settings(self) -> dict:
        """What the window remembers: which sections are folded.

        The provider settings, and with them the API key, live in the settings
        file written by the model; the key is never part of what a window saves.
        """
        return {"folds": dict(self.form.folds)}

    def restore_settings(self, settings: dict) -> None:
        """Restore :meth:`export_settings`."""
        folds = settings.get("folds", {})
        if isinstance(folds, dict):
            self.form.folds.update({str(k): bool(v) for k, v in folds.items()})

    def close(self) -> None:
        """Hide the key and let go of the model's runner."""
        self.model.show_key = False
        self.model.async_runner = None


def make_ai_settings_app() -> AISettingsApp:
    """Build the AI settings app (the manifest's ``entrypoints.emtk``)."""
    return AISettingsApp()


make_app = make_ai_settings_app
