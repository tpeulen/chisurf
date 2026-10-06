"""Native emtk plugin manager: what is installed, how it is wired, what to switch off.

The whole form -- the action bar, the searchable plugin table, the Show disabled
switch, the status line, the switches and window-state choices of the selected
plugin, its dependency table, and the confirm / rename dialogs -- is the view
spec ``plugins_emtk.view.json`` drawn by :func:`emtk.view_form.draw_sections`.
Only what a spec cannot express is drawn here: the Markdown details of the
selected plugin, the icon preview, the Help / Guide buttons and the file
choosers for Install, Icon and Export CSV. All state and work is in
:class:`~.model.PluginManagerModel`.
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

from .model import PluginManagerModel

HERE = Path(__file__).parent
_HOME = str(Path.home())

#: ``name`` of the four panels of the spec.
_REGISTERED, _SELECTED, _DIALOG, _ICON = "registered", "selected", "dialog", "icon"
#: The two tables' names in the form (their ``source``).
TABLE_NAME = "plugin_rows"
DEPENDENCY_TABLE = "dependency_rows"


class PluginManagerApp(ImApp):
    """Browse, configure, install and remove plugins without a Qt host."""

    window_title = "ChiSurf Plugin Manager"

    def __init__(self, model: PluginManagerModel | None = None) -> None:
        self.model = model or PluginManagerModel()
        self.job = SnapshotJob(self.model)
        self.model.runner = self.start_job
        self.model.displayed_provider = self.displayed
        spec = json.loads((HERE / "plugins_emtk.view.json").read_text(encoding="utf-8"))
        self.panels = {p["name"]: p for p in spec["sections"]}
        self.form = FormState()
        self.form.custom["plugin_details"] = self._draw_details
        self.form.custom["icon_preview"] = self._draw_icon_preview
        self.dialog_form = FormState()
        self.icon_form = FormState()
        self.icon_form.custom["icon_preview"] = self._draw_icon_preview
        #: The file chooser that is open, and what it is for.
        self.dialog: FileDialog | None = None
        self.dialog_purpose = ""
        self.message_window = DialogWindow(
            "Plugin Manager", size=(520.0, 190.0), key="plugin_manager_dialog", fit_height=True
        )
        self.icon_window = DialogWindow(
            "Icon", size=(580.0, 400.0), key="plugin_manager_icon", fit_height=True
        )
        self.item_rects: dict[str, tuple] = {}
        self._reported_error = ""
        self._last_selected = self.model.selected_key
        self._textures: dict = {}
        self._pending_query: str | None = None
        self._sized: tuple | None = None
        self.help_window = EmTkHelpWindow(
            title="Plugins — Help", resource=HERE / "help.md", owner=self
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            owner=self,
            wait_for_controls=True,
            get_target_rect=lambda key: self.item_rects.get(key) or self.form.rects.get(key),
        )
        self.form.on_used = self.tour.notify_used
        self.docks = DockManager(Split("h", 0.6, Region("plugins"), Region("details")))
        self.docks.add_window(
            "plugins", "Installed plugins", self.draw_plugins, dock="plugins", closable=False
        )
        self.docks.add_window(
            "details", "Selected plugin", self.draw_selected, dock="details", closable=False
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
            self.model.set_status(f"Failed: {self.job.error}")
        vp = im.get_main_viewport()
        box = (*vp.pos, *vp.size)
        if self._sized != tuple(vp.size):
            # The right window needs about 460 px for its labels and combos; a
            # resize of the window re-proposes the split (a drag in between stays).
            self._sized = tuple(vp.size)
            self.docks.set_ratio("root", min(0.66, max(0.45, 1.0 - 460.0 / float(vp.size[0]))))
        self.form.rects.clear()
        self.docks.draw(box)
        self._sync_table_selection()
        self._requests()
        self._draw_icon(box)
        self._draw_message(box)
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
    def draw_plugins(self, box: Any) -> None:
        """The left window: actions, filterable table, switch and status."""
        draw_sections(self.panels[_REGISTERED]["sections"], self.model, self.form, titles=False)

    def draw_selected(self, box: Any) -> None:
        """The right window: Help / Guide, the details, the switches, the dependencies."""
        if im.button("Help"):
            self.help_window.show()
        im.set_item_tooltip("Explain the table, the dependency columns and the switches.")
        self.item_rects["help"] = im.get_item_rect()
        im.same_line()
        if im.button("Guide"):
            self.tour.start()
        im.set_item_tooltip("Walk through picking a plugin, switching it off and saving.")
        self.item_rects["guide"] = im.get_item_rect()
        im.separator()
        draw_sections(self.panels[_SELECTED]["sections"], self.model, self.form, titles=False)

    def _draw_details(self, section: dict, model: Any, state: FormState, width: float) -> None:
        """The ``plugin_details`` custom section: the selected plugin as plain text blocks."""
        top = im.get_cursor_screen_pos()
        for kind, text in model.details_blocks():
            if kind == "title":
                im.heading(text, 3)
            else:
                im.text_wrapped(text)
        bottom = im.get_cursor_screen_pos()
        state.rects["plugin_details"] = (top[0], top[1], width, max(1.0, bottom[1] - top[1]))
        im.set_item_tooltip(str(section.get("description", "")))

    def _draw_icon_preview(self, section: dict, model: Any, state: FormState, width: float) -> None:
        """The ``icon_preview`` custom section: the plugin's icon, or ``no icon``."""
        path = model.icon_file
        texture = None
        if path is not None and path.is_file():
            stamp = (str(path), path.stat().st_mtime_ns)
            if stamp not in self._textures:
                self._textures = {stamp: self._load_texture(path)}
            texture = self._textures[stamp]
        if texture is not None:
            im.image(texture, (96.0, 96.0))
        else:
            im.text_disabled("no icon")
        im.set_item_tooltip(str(section.get("description", "")))
        state.rects["icon_preview"] = im.get_item_rect()

    @staticmethod
    def _load_texture(path: Path) -> Any:
        try:
            from PIL import Image

            with Image.open(path) as image:
                return image.convert("RGBA").resize((96, 96))
        except Exception:
            return None

    def _sync_table_selection(self) -> None:
        """Show the model's selection in the table (a restored or programmatic one)."""
        binding = self.form.tables.get(TABLE_NAME)
        if binding is None:
            return
        control = binding.control
        if self._pending_query is not None:
            control.filter.set_text(self._pending_query)
            self._pending_query = None
        wanted = self.model.selected_key or None
        if control.selected_key != wanted:
            control.select_key(wanted)

    # ── the table as the user sees it ──────────────────────────────────
    def displayed(self) -> tuple[list[dict], list[tuple[str, str]]]:
        """Rows (filtered, sorted) and columns (visible) of the table, for Copy / Export."""
        binding = self.form.tables.get(TABLE_NAME)
        if binding is None:
            return list(self.model.plugin_rows()), []
        control = binding.control
        records = [control.records[i] for i in control.order()]
        columns = [(c.key, c.title or c.key) for c in control.visible_columns()]
        return records, columns

    # ── choosers, Copy and Export CSV ──────────────────────────────────
    def _requests(self) -> None:
        """Act on the model's ``request``: copy now, or open a chooser."""
        request, self.model.request = self.model.request, ""
        if request == "copy":
            im.set_clipboard_text(self.model.table_text("\t", True))
            records, _ = self.model.displayed()
            self.model.set_status(f"Copied {len(records)} rows to the clipboard.")
        elif request and self.dialog is None:
            if request == "install":
                self._open_dialog(
                    "install_archive",
                    FileDialog(
                        "Choose a plugin archive",
                        filters="Plugin archive (*.zip);;All files (*)",
                        directory=_HOME,
                    ),
                )
            elif request == "icon_file":
                self._open_dialog(
                    "icon",
                    FileDialog(
                        "Choose an icon image",
                        filters="Images (*.png *.jpg *.jpeg *.ico);;All files (*)",
                        directory=_HOME,
                    ),
                )
            elif request == "export":
                self._open_dialog(
                    "export",
                    FileDialog(
                        "Export plugins as CSV",
                        mode="save",
                        filename="plugins.csv",
                        directory=_HOME,
                        filters="CSV (*.csv);;All Files (*)",
                    ),
                )

    def _open_dialog(self, purpose: str, dialog: FileDialog) -> None:
        self.dialog, self.dialog_purpose = dialog, purpose

    def _draw_file_dialog(self) -> None:
        if self.dialog is None:
            return
        result = None
        if im.begin(self.dialog.title):
            result = self.dialog.draw()
        im.end()
        purpose = self.dialog_purpose
        if result:
            self.dialog = None
            path = result[0]
            if purpose in ("install_archive", "install_folder"):
                self.model.choose_install_source(path)
            elif purpose == "icon":
                self.model.icon_path_text = path
            elif purpose == "export":
                self.model.export_csv(path)
        elif result is False:
            self.dialog = None
            if purpose == "install_archive":
                # As in the Qt tool: no archive chosen, so offer a folder instead.
                self._open_dialog(
                    "install_folder",
                    FileDialog(
                        "Choose a plugin folder",
                        mode="folder",
                        action="Choose folder",
                        directory=_HOME,
                    ),
                )

    # ── confirm / notice / rename dialog ───────────────────────────────
    def _draw_message(self, box: Any) -> None:
        """The dialog that asks before Revert, Install or Uninstall changes anything."""
        model = self.model
        window = self.message_window
        if model.dialog and not window.open:
            window.show()
        if not model.dialog and window.open:
            window.hide()
        if not window.open:
            return
        window.title = model.dialog_title
        pressed = window.begin(box)
        draw_sections(self.panels[_DIALOG]["sections"], model, self.dialog_form, titles=False)
        window.end()
        if pressed == "close":
            model.dialog_cancel() if model.dialog_has_cancel else model.dialog_ok()

    # ── the icon panel ─────────────────────────────────────────────────
    def _draw_icon(self, box: Any) -> None:
        model = self.model
        window = self.icon_window
        if model.icon_open and not window.open:
            window.show()
        if not model.icon_open and window.open:
            window.hide()
        if not window.open:
            return
        window.title = model.icon_title
        pressed = window.begin(box)
        draw_sections(self.panels[_ICON]["sections"], model, self.icon_form, titles=False)
        window.end()
        if pressed == "close" and not model.dialog:
            model.icon_close()

    # ── persistence ────────────────────────────────────────────────────
    def export_settings(self) -> dict:
        """What is remembered: the filter text and the selected plugin."""
        binding = self.form.tables.get(TABLE_NAME)
        query = binding.control.filter.text if binding is not None else ""
        return {"query": str(query or ""), "selected_key": self.model.selected_key}

    def restore_settings(self, settings: dict) -> None:
        """Restore :meth:`export_settings`."""
        self._pending_query = str(settings.get("query", "") or "")
        key = str(settings.get("selected_key", settings.get("selected", "")) or "")
        if key:
            self.model.select_key(key)
        self._last_selected = self.model.selected_key

    def close(self) -> None:
        """Detach the model's observers."""
        self.model._observers.clear()


def make_app() -> PluginManagerApp:
    """Build the plugin manager app (the manifest's ``entrypoints.emtk``)."""
    from chisurf.emtk.i18n import install

    install()
    return PluginManagerApp()
