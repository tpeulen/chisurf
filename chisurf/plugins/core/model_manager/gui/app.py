"""Native emtk model manager: which fitting models the model drop-down offers.

The whole form -- actions, the searchable model table, the Show disabled switch,
the status line, the Disabled switch and the confirmation dialog -- is the view
spec ``models_emtk.view.json`` drawn by :func:`emtk.view_form.draw_form`. Only
what a spec cannot express is drawn here: the Markdown details of the selected
model, the Help / Guide buttons and the file dialog for the CSV export. All state
and work is in :class:`~.model.ModelManagerModel`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from emtk import im
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog
from emtk.view_form import FormState, draw_sections

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.emtk.jobs import SnapshotJob

from .model import ModelManagerModel

HERE = Path(__file__).parent

#: ``name`` of the three panels of the spec.
_REGISTERED, _SELECTED, _CONFIRM = "registered", "selected", "confirm"
#: The table section's name in the form (its ``source``).
TABLE_NAME = "model_rows"


class ModelManagerApp(ImApp):
    """Browse the registered fitting models and choose which are offered."""

    def __init__(self, model: ModelManagerModel | None = None) -> None:
        self.model = model or ModelManagerModel()
        self.job = SnapshotJob(self.model)
        self.model.runner = self.start_job
        self.model.displayed_provider = self.displayed
        spec = json.loads((HERE / "models_emtk.view.json").read_text(encoding="utf-8"))
        self.panels = {p["name"]: p for p in spec["sections"]}
        self.form = FormState()
        self.form.custom["model_details"] = self._draw_details
        self.confirm_form = FormState()
        self.dialog: FileDialog | None = None
        self.confirm_window = DialogWindow("Confirm", size=(460.0, 150.0), key="model_manager")
        self.item_rects: dict[str, tuple] = {}
        self._reported_error = ""
        self._last_selected = self.model.selected_key
        self.help_window = EmTkHelpWindow(
            title="Models — Help", resource=HERE / "help.md", owner=self
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            owner=self,
            wait_for_controls=True,
            get_target_rect=lambda key: self.item_rects.get(key) or self.form.rects.get(key),
        )
        self.form.on_used = self.tour.notify_used
        self.docks = DockManager(Split("h", 0.67, Region("models"), Region("selected")))
        self.docks.add_window(
            "models", "Registered models", self.draw_models, dock="models", closable=False
        )
        self.docks.add_window(
            "selected", "Selected model", self.draw_selected, dock="selected", closable=False
        )
        super().__init__(self.render, continuous=True)

    # ── jobs ───────────────────────────────────────────────────────────
    def start_job(self, method: str) -> bool:
        """Run the model method *method* on a snapshot in a worker thread."""
        self._reported_error = ""
        return self.job.start(method)

    # ── one frame ──────────────────────────────────────────────────────
    def render(self) -> None:
        self.job.poll()
        self.model.busy = self.job.busy
        if self.job.error and self.job.error != self._reported_error:
            self._reported_error = self.job.error
            self.model.set_status(f"Rescan failed: {self.job.error}")
        vp = im.get_main_viewport()
        box = (*vp.pos, *vp.size)
        self.form.rects.clear()
        self.docks.draw(box)
        self._sync_table_selection()
        self._requests()
        self._draw_confirm(box)
        self._draw_file_dialog()
        self._tour_outcomes()
        self.help_window.draw(box)
        self.tour.draw(*vp.size)

    def _tour_outcomes(self) -> None:
        """Tell the tour when a row was picked (the table reports no field use)."""
        if TABLE_NAME in self.form.rects:
            self.item_rects["row_selected"] = self.form.rects[TABLE_NAME]
        key = self.model.selected_key
        if key and key != self._last_selected:
            self.tour.notify_used("row_selected")
        self._last_selected = key

    # ── windows ────────────────────────────────────────────────────────
    def draw_models(self, box: Any) -> None:
        """The left window: actions, filterable table, switch and status."""
        draw_sections(self.panels[_REGISTERED]["sections"], self.model, self.form, titles=False)

    def draw_selected(self, box: Any) -> None:
        """The right window: Help / Guide, the selected model's details, Disabled."""
        if im.button("Help"):
            self.help_window.show()
        im.set_item_tooltip("Explain the table, the Disabled switch and stale entries.")
        self.item_rects["help"] = im.get_item_rect()
        im.same_line()
        if im.button("Guide"):
            self.tour.start()
        im.set_item_tooltip("Walk through picking a model, disabling it and saving.")
        self.item_rects["guide"] = im.get_item_rect()
        im.separator()
        draw_sections(self.panels[_SELECTED]["sections"], self.model, self.form, titles=False)

    def _draw_details(self, section: dict, model: Any, state: FormState, width: float) -> None:
        """The ``model_details`` custom section: the selected model as Markdown."""
        im.markdown(model.details_text(callout=True))
        im.set_item_tooltip(str(section.get("description", "")))
        state.rects["model_details"] = im.get_item_rect()

    def _sync_table_selection(self) -> None:
        """Show the model's selection in the table (a restored or programmatic one)."""
        binding = self.form.tables.get(TABLE_NAME)
        if binding is None:
            return
        control = binding.control
        wanted = self.model.selected_key or None
        if control.selected_key != wanted:
            control.select_key(wanted)

    # ── the table as the user sees it ──────────────────────────────────
    def displayed(self) -> tuple[list[dict], list[tuple[str, str]]]:
        """Rows (filtered, sorted) and columns (visible) of the table, for Copy / Export."""
        binding = self.form.tables.get(TABLE_NAME)
        if binding is None:
            return list(self.model.model_rows()), []
        control = binding.control
        records = [control.records[i] for i in control.order()]
        columns = [(c.key, c.title or c.key) for c in control.visible_columns()]
        return records, columns

    # ── Copy and Export CSV ────────────────────────────────────────────
    def _requests(self) -> None:
        """Act on the model's ``request``: copy now, or open the export dialog."""
        request, self.model.request = self.model.request, ""
        if request == "copy":
            im.set_clipboard_text(self.model.table_text("\t", True))
            records, _ = self.model.displayed()
            self.model.set_status(f"Copied {len(records)} rows to the clipboard.")
        elif request == "export" and self.dialog is None:
            self.dialog = FileDialog(
                "Export models as CSV", mode="save", filename="models.csv",
                filters="CSV (*.csv);;All Files (*)",
            )

    def _draw_file_dialog(self) -> None:
        if self.dialog is None:
            return
        if im.begin(self.dialog.title):
            result = self.dialog.draw()
            if result:
                self.dialog = None
                self.model.export_csv(result[0])
            elif result is False:
                self.dialog = None
        im.end()

    # ── confirmation ───────────────────────────────────────────────────
    def _draw_confirm(self, box: Any) -> None:
        """The dialog that asks before Revert or Drop stale changes anything."""
        model = self.model
        if model.confirm and not self.confirm_window.open:
            self.confirm_window.title = model.confirm_title
            self.confirm_window.show()
        if not model.confirm and self.confirm_window.open:
            self.confirm_window.hide()
        if not self.confirm_window.open:
            return
        pressed = self.confirm_window.begin(box)
        draw_sections(self.panels[_CONFIRM]["sections"], model, self.confirm_form, titles=False)
        self.confirm_window.end()
        if pressed == "close":
            model.confirm_no()

    # ── persistence ────────────────────────────────────────────────────
    def export_settings(self) -> dict:
        """What is remembered: the switch and the selected model."""
        return {
            "show_disabled": bool(self.model.show_disabled),
            "selected_key": self.model.selected_key,
        }

    def restore_settings(self, settings: dict) -> None:
        """Restore :meth:`export_settings`."""
        self.model.show_disabled = bool(settings.get("show_disabled", True))
        key = str(settings.get("selected_key", "") or "")
        if key:
            self.model.select_key(key)
        self._last_selected = self.model.selected_key

    def close(self) -> None:
        """Detach the model's observers."""
        self.model._observers.clear()


def make_app() -> ModelManagerApp:
    """Build the model manager app (the manifest's ``entrypoints.emtk``)."""
    return ModelManagerApp()
