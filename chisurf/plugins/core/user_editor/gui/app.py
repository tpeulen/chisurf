"""Native emtk user editor: the accounts registered in the MMFDB.

The whole form -- actions, the searchable account table, the account fields, the
status line, the password prompt and the confirmation dialog -- is the view spec
``users_emtk.view.json`` drawn by :func:`emtk.view_form.draw_sections`. Only what
a spec cannot express is drawn here: the Markdown details of the selected
account, the two masked password entries (the spec's ``password`` kind is not
masked), the Help / Guide buttons and the file dialog of the CSV export. All
state and work is in :class:`~.model.UserEditorModel`; the calls to the server
run on a :class:`~chisurf.emtk.jobs.SnapshotJob`.
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

from .model import UserEditorModel

HERE = Path(__file__).parent

#: ``name`` of the four panels of the spec.
_ACCOUNTS, _ACCOUNT, _PASSWORD, _CONFIRM = "accounts", "account", "password", "confirm"
#: The table section's name in the form (its ``source``).
TABLE_NAME = "user_records"


class UserEditorApp(ImApp):
    """Browse and edit the MMFDB user accounts."""

    def __init__(self, model: UserEditorModel | None = None, autoload: bool = True) -> None:
        self.model = model or UserEditorModel()
        self.job = SnapshotJob(self.model)
        self.model.runner = self.start_job
        self.model.displayed_provider = self.displayed
        #: Fetch the accounts on the first frame, as the Qt tool does when first shown.
        self.autoload = autoload
        spec = json.loads((HERE / "users_emtk.view.json").read_text(encoding="utf-8"))
        self.panels = {p["name"]: p for p in spec["sections"]}
        self.form = FormState()
        self.form.custom["account_details"] = self._draw_details
        self.form.custom["password_fields"] = self._draw_password_fields
        self.password_form = FormState()
        self.password_form.custom["password_fields"] = self._draw_password_fields
        self.confirm_form = FormState()
        self.dialog: FileDialog | None = None
        self.confirm_window = DialogWindow(
            "Confirm", size=(480.0, 120.0), key="user_editor", fit_height=True
        )
        self.password_window = DialogWindow(
            "Password", size=(440.0, 190.0), key="user_editor_password", fit_height=True
        )
        self.item_rects: dict[str, tuple] = {}
        self._reported_error = ""
        self._last_selected = self.model.selected_key
        #: A remembered selection, applied once the accounts have been fetched.
        self._restore_key = ""
        self.help_window = EmTkHelpWindow(
            title="Users — Help", resource=HERE / "help.md", owner=self
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            owner=self,
            wait_for_controls=True,
            get_target_rect=lambda key: self.item_rects.get(key) or self.form.rects.get(key),
        )
        self.form.on_used = self.tour.notify_used
        self.docks = DockManager(Split("h", 0.52, Region("accounts"), Region("account")))
        self.docks.add_window(
            "accounts", "Accounts", self.draw_accounts, dock="accounts", closable=False
        )
        self.docks.add_window(
            "account", "Account", self.draw_account, dock="account", closable=False
        )
        super().__init__(self.render, continuous=True)

    # ── jobs ───────────────────────────────────────────────────────────
    def start_job(self, method: str, *args: Any) -> bool:
        """Run the model method *method* on a snapshot in a worker thread."""
        self._reported_error = ""
        return self.job.start(method, *args)

    # ── one frame ──────────────────────────────────────────────────────
    def render(self) -> None:
        if self.autoload:
            self.autoload = False
            self.model.start_loading()
        self.job.poll()
        self.model.busy = self.job.busy
        if self._restore_key and self.model.users and not self.job.busy:
            self.model.select_key(self._restore_key)
            self._restore_key = ""
            self._last_selected = self.model.selected_key
        if self.job.error and self.job.error != self._reported_error:
            self._reported_error = self.job.error
            self.model.notice = f"The server call failed: {self.job.error}"
        vp = im.get_main_viewport()
        box = (*vp.pos, *vp.size)
        self.form.rects.clear()
        self.docks.draw(box)
        self._sync_table_selection()
        self._requests()
        self._draw_confirm(box)
        self._draw_password(box)
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
    def draw_accounts(self, box: Any) -> None:
        """The left window: actions, the filterable table and the status line."""
        draw_sections(self.panels[_ACCOUNTS]["sections"], self.model, self.form, titles=False)

    def draw_account(self, box: Any) -> None:
        """The right window: Help / Guide, the details and the account form."""
        if im.button("Help"):
            self.help_window.show()
        im.set_item_tooltip("Explain the table, the account form, passwords and deleting.")
        self.item_rects["help"] = im.get_item_rect()
        im.same_line()
        if im.button("Guide"):
            self.tour.start()
        im.set_item_tooltip("Walk through picking an account, editing it and saving.")
        self.item_rects["guide"] = im.get_item_rect()
        im.separator()
        draw_sections(self.panels[_ACCOUNT]["sections"], self.model, self.form, titles=False)

    def _draw_details(self, section: dict, model: Any, state: FormState, width: float) -> None:
        """The ``account_details`` custom section: the edited account as Markdown."""
        im.markdown(model.details_text(callout=True))
        im.set_item_tooltip(str(section.get("description", "")))
        state.rects["account_details"] = im.get_item_rect()

    def _sync_table_selection(self) -> None:
        """Show the model's selection in the table (a restored, new or programmatic one)."""
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
            return list(self.model.user_records()), []
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
            self.model.notice = f"Copied {len(records)} rows to the clipboard."
        elif request == "export" and self.dialog is None:
            self.dialog = FileDialog(
                "Export users as CSV", mode="save", filename="users.csv",
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
        """The dialog that asks before Revert or Delete changes anything."""
        model = self.model
        if model.confirm and not self.confirm_window.open:
            self.confirm_window.show()
        if not model.confirm and self.confirm_window.open:
            self.confirm_window.hide()
        if not self.confirm_window.open:
            return
        self.confirm_window.title = model.confirm_title or self.confirm_window.title
        pressed = self.confirm_window.begin(box)
        draw_sections(self.panels[_CONFIRM]["sections"], model, self.confirm_form, titles=False)
        self.confirm_window.end()
        if pressed == "close":
            model.confirm_no()

    # ── password ───────────────────────────────────────────────────────
    def _draw_password(self, box: Any) -> None:
        """The password prompt: two masked entries, the strength bar, Set / Cancel."""
        model = self.model
        if model.password_open and not self.password_window.open:
            self.password_window.show()
        if not model.password_open and self.password_window.open:
            self.password_window.hide()
        if not self.password_window.open:
            return
        self.password_window.title = model.password_title
        pressed = self.password_window.begin(box)
        draw_sections(
            self.panels[_PASSWORD]["sections"], model, self.password_form, titles=False
        )
        self.password_window.end()
        if pressed == "close":
            model.password_cancel()

    def _draw_password_fields(
        self, section: dict, model: Any, state: FormState, width: float
    ) -> None:
        """The ``password_fields`` custom section: two masked text entries."""
        flags = im.InputTextFlags.PASSWORD
        label_w = max(im.calc_text_size("Confirm password")[0], im.calc_text_size("New password")[0])
        for label, attr, name, tip in (
            ("New password", "password_new", "password_new",
             "The new password; shown as stars. It is applied when you press Save."),
            ("Confirm password", "password_confirm", "password_confirm",
             "Type the new password again; it must match."),
        ):
            im.text(label)
            im.same_line(label_w + 14.0)
            im.set_next_item_width(max(width - label_w - 22.0, 80.0))
            changed, value = im.input_text(f"##{name}", getattr(model, attr), "", flags)
            im.set_item_tooltip(tip)
            self.item_rects[name] = im.get_item_rect()
            if changed:
                setattr(model, attr, value)
                model.password_error = ""

    # ── persistence ────────────────────────────────────────────────────
    def export_settings(self) -> dict:
        """What is remembered: the selected account."""
        return {"selected_key": self.model.selected_key}

    def restore_settings(self, settings: dict) -> None:
        """Restore :meth:`export_settings` (applied once the accounts are loaded)."""
        self._restore_key = str(settings.get("selected_key", "") or "")
        if self._restore_key and self.model.users:
            self.model.select_key(self._restore_key)
            self._restore_key = ""
        self._last_selected = self.model.selected_key

    def close(self) -> None:
        """Detach the model's observers and forget a typed password."""
        self.model.password_cancel()
        self.model._observers.clear()


def make_app() -> UserEditorApp:
    """Build the user editor app (the manifest's ``entrypoints.emtk``)."""
    return UserEditorApp()
