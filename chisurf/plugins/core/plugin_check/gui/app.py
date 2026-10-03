"""Native plugin checker: every plugin's startup check, its details and a guided tour, without Qt.

The sweep actions, the two sweep options, the progress bar, the status line and the plugin table are the view spec
``plugin_check_emtk.view.json`` drawn by :func:`emtk.view_form.draw_sections` over
:class:`~.model.PluginCheckModel`. Only what a spec cannot draw is drawn here: the selected plugin's details, the
selectable error text, and the Help / Guide buttons.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from emtk import im
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.view_form import FormState, draw_sections
from emtk.widgets.text_editor import TextEditor

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.plugins.emtk_layout import cap_widths

from .model import PluginCheckModel

HERE = Path(__file__).parent
TABLE = "check_rows"
#: Width the details window needs for a caption and a wrapped line, and the share of the window it may take.
DETAILS_MIN = 280.0


def _load_spec() -> dict:
    spec = json.loads((HERE / "plugin_check_emtk.view.json").read_text(encoding="utf-8"))
    cap_widths(spec["sections"])
    return spec


class PluginCheckApp(ImApp):
    """Start startup sweeps, read the results per plugin, without a Qt host."""

    window_title = "ChiSurf Plugin Check"

    def __init__(self, model: PluginCheckModel | None = None) -> None:
        self.model = model or PluginCheckModel()
        self.panels = {p["name"]: p for p in _load_spec()["sections"]}
        self.form = FormState()
        self.form.custom["plugin_details"] = self._draw_details
        self.form.custom["error_text"] = self._draw_error
        self.item_rects: dict[str, tuple] = {}
        self._error_editor = TextEditor("")
        self._error_editor.config.show_line_numbers = False
        self._error_editor.config.read_only = True
        self._error_key: tuple = ()
        self._last_selected = self.model.selected_key
        self._pending_query: str | None = None
        self._sized: tuple | None = None
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            owner=self,
            wait_for_controls=True,
            get_target_rect=lambda key: self.item_rects.get(key) or self.form.rects.get(key),
        )
        self.help_window = EmTkHelpWindow(title="Plugin Check - Help", resource=HERE / "help.md", owner=self,
                                          on_start_guide=self.tour.start)
        self.form.on_used = self.tour.notify_used
        self.docks = DockManager(Split("h", 0.64, Region("plugins"), Region("details")))
        self.docks.add_window("plugins", "Plugin startup checks", self.draw_plugins, dock="plugins", closable=False)
        self.docks.add_window("details", "Plugin details", self.draw_selected, dock="details", closable=False)
        super().__init__(self.render)

    # -- persistence ---------------------------------------------------------------- #
    def export_settings(self) -> dict:
        """What is remembered: the selected plugin, the two sweep options and the filter text."""
        binding = self.form.tables.get(TABLE)
        query = binding.control.filter.text if binding is not None else ""
        return {"selected": self.model.selected_key, "delay": self.model.delay,
                "skip_blacklisted": bool(self.model.skip_blacklisted), "query": str(query or "")}

    def restore_settings(self, settings: dict) -> None:
        """Restore :meth:`export_settings`; unknown or invalid values are ignored."""
        selected = settings.get("selected")
        if selected in self.model.catalog:
            self.model.selected_key = selected
            self._last_selected = selected
        try:
            delay = float(settings.get("delay"))
            if 0.0 <= delay <= 5.0:
                self.model.delay = delay
        except (TypeError, ValueError):
            pass
        if isinstance(settings.get("skip_blacklisted"), bool):
            self.model.skip_blacklisted = settings["skip_blacklisted"]
        if settings.get("query"):
            self._pending_query = str(settings["query"])

    # -- one frame ---------------------------------------------------------------------- #
    def render(self) -> None:
        self.model.poll()
        viewport = im.get_main_viewport()
        box = (*viewport.pos, *viewport.size)
        if self._sized != tuple(viewport.size):
            # The details window needs about DETAILS_MIN px; a resize re-proposes the split (a drag in between stays).
            self._sized = tuple(viewport.size)
            self.docks.set_ratio("root", min(0.72, max(0.5, 1.0 - DETAILS_MIN / float(viewport.size[0]))))
        self.form.rects.clear()
        self.docks.draw(box)
        self._sync_table_selection()
        self._tour_outcomes()
        self.help_window.draw(box)
        self.tour.draw(*viewport.size)

    def _sync_table_selection(self) -> None:
        binding = self.form.tables.get(TABLE)
        if binding is None:
            return
        control = binding.control
        if self._pending_query is not None:
            control.filter.set_text(self._pending_query)
            self._pending_query = None
        wanted = self.model.selected_key or None
        if control.selected_key != wanted:
            control.select_key(wanted)

    def _tour_outcomes(self) -> None:
        """Tell the tour when a row was picked or a sweep has begun (a table reports no field use)."""
        if TABLE in self.form.rects:
            self.item_rects["row_selected"] = self.form.rects[TABLE]
        key = self.model.selected_key
        if key != self._last_selected:
            self.tour.notify_used("row_selected")
        self._last_selected = key

    # -- windows ---------------------------------------------------------------------- #
    def draw_plugins(self, box: Any) -> None:
        """The left window: Help / Guide, then the spec's actions, options, progress, status and table."""
        if im.button("Help"):
            self.help_window.show()
        im.set_item_tooltip("Explain the table, the sweep and what a check proves.")
        self.item_rects["help"] = im.get_item_rect()
        im.same_line()
        if im.button("Guide"):
            self.tour.start()
        im.set_item_tooltip("Walk through a safe sweep and the details of a plugin.")
        self.item_rects["guide"] = im.get_item_rect()
        draw_sections(self.panels["checks"]["sections"], self.model, self.form, titles=False)

    def draw_selected(self, box: Any) -> None:
        """The right window: details and error text of the selected plugin."""
        draw_sections(self.panels["details"]["sections"], self.model, self.form, titles=False)

    def _draw_details(self, section: dict, model: Any, state: FormState, width: float) -> None:
        top = im.get_cursor_screen_pos()
        blocks = model.details()
        if not blocks:
            im.text_wrapped("Select a plugin to inspect its details.")
        for caption, text in blocks:
            im.text_disabled(caption)
            im.text_wrapped(text)
        bottom = im.get_cursor_screen_pos()
        state.rects["plugin_details"] = (top[0], top[1], width, max(1.0, bottom[1] - top[1]))
        im.set_item_tooltip(str(section.get("description", "")))

    def _draw_error(self, section: dict, model: Any, state: FormState, width: float) -> None:
        text = model.error_text
        if not text:
            return
        im.separator_text("Startup error")
        token = (model.selected_key, text)
        if token != self._error_key:
            self._error_key = token
            self._error_editor.set_text(text)
        top = im.get_cursor_screen_pos()
        height = max(80.0, min(260.0, im.get_content_region_avail()[1] - 8))
        im.text_editor("##plugin_error", self._error_editor, (0, height))
        state.rects["error_text"] = (top[0], top[1], width, height)
        im.set_item_tooltip(str(section.get("description", "")))

    # -- frames only while something moves --------------------------------------------- #
    def animating(self) -> bool:
        return self.model.running or not self.model._events.empty() or super().animating()

    def close(self) -> None:
        self.model.close()


def make_app() -> PluginCheckApp:
    """Build the plugin check app (the manifest's ``entrypoints.emtk``)."""
    from chisurf.emtk.i18n import install

    install()
    return PluginCheckApp()
