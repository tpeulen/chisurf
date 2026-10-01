"""Qt-free model of the native user editor.

:class:`UserEditorModel` is the shared :class:`~.view_model.UserEditorViewModel`
(the accounts, the edited copy, validation, save and delete through the MMFDB
client) plus what only the painted window needs: a table source that keeps its
identity between frames, the confirmations the Qt tool asked through message
boxes (revert, delete, forced delete), the password prompt, the messages the Qt
tool showed in warning dialogs (here: the status line), calls to the server on
the app's :class:`~chisurf.emtk.jobs.SnapshotJob`, and the table's CSV text.
"""

from __future__ import annotations

import csv
import io
import pathlib
from typing import Any, Callable

from chisurf import logging
from chisurf.plugins.core.user_editor.api.client import active_user_id
from chisurf.plugins.core.user_editor.api.records import (
    PROTECTED_USER_IDS,
    ROLE_OPTIONS,
)
from chisurf.plugins.core.user_editor.gui.view_model import UserEditorViewModel

#: The columns of the account table, in order: ``(record key, header)``.
TABLE_COLUMNS = (
    ("user", "User"),
    ("username", "Username"),
    ("role", "Role"),
    ("admin", "Admin"),
    ("autologin", "Autologin"),
    ("active", "Active"),
)

#: Characters that count as "special" in the password strength rule.
SPECIAL_CHARACTERS = "!@#$%^&*()_+-=[]{}|;':\",./<>?"


def password_strength(text: str) -> tuple[int, list[str]]:
    """The password-strength rule of the Qt password dialog.

    Parameters
    ----------
    text : str
        The password typed.

    Returns
    -------
    tuple
        ``(score, missing)``: the score 0 to 5 (length, lower case, upper case,
        digit, special character) and the requirements not yet met.
    """
    score = 0
    missing: list[str] = []
    checks = (
        (len(text) >= 8, "At least 8 characters"),
        (any(c.islower() for c in text), "At least one lowercase letter"),
        (any(c.isupper() for c in text), "At least one uppercase letter"),
        (any(c.isdigit() for c in text), "At least one number"),
        (any(c in SPECIAL_CHARACTERS for c in text), "At least one special character"),
    )
    for ok, message in checks:
        if ok:
            score += 1
        else:
            missing.append(message)
    return score, missing


def strength_label(text: str) -> str:
    """The word the Qt dialog shows for *text*: none, Weak, Medium or Strong."""
    score, _ = password_strength(text)
    if not text:
        return "Enter a password"
    if score <= 2:
        return "Strength: Weak"
    if score <= 4:
        return "Strength: Medium"
    return "Strength: Strong"


class _Records(list):
    """A list of table records that says when its content changed.

    The painted table re-reads its source when the list object, its length or
    its ``revision`` changes; an edit that leaves the row count alone (a saved
    role, a flipped Administrator flag) changes none of the first two.
    """

    revision = 0


class UserEditorModel(UserEditorViewModel):
    """State and actions behind the emtk user editor."""

    def __init__(self, client_factory=None) -> None:
        #: ``runner(method_name, *args)`` runs a model method off the draw loop
        #: (the app's SnapshotJob); ``None`` runs it here.
        self.runner: Callable[..., bool] | None = None
        self.busy = False
        #: ``"revert"`` / ``"delete"`` / ``"force_delete"`` while the app asks to confirm.
        self.confirm = ""
        #: ``"export"`` / ``"copy"`` while the app should act on the table.
        self.request = ""
        #: Returns the records the table shows (filtered, sorted) and its columns.
        self.displayed_provider: Callable[[], tuple[list[dict], list[tuple[str, str]]]] | None = None
        #: A one-off message (a refused save or delete) shown on the status line.
        self.notice = ""
        #: The account a pending delete confirmation is about, and why it was refused.
        self.delete_target = ""
        self.delete_problem = ""
        #: The password prompt: open flag, the account, the two typed passwords.
        self.password_open = False
        self.password_user = ""
        self.password_new = ""
        self.password_confirm = ""
        self.password_error = ""
        self._records = _Records()
        self._signature: tuple = ()
        super().__init__(client_factory=client_factory)

    # -- table source ----------------------------------------------------

    def user_records(self) -> list[dict[str, Any]]:
        """The table source: one record per account, stable between edits."""
        records = []
        for user in self.users:
            record = user.as_record()
            record["key"] = user.user_id
            records.append(record)
        signature = tuple(tuple(r.items()) for r in records)
        if signature != self._signature:
            self._signature = signature
            fresh = _Records(records)
            fresh.revision = self._records.revision + 1
            self._records = fresh
        return self._records

    @property
    def selected_key(self) -> str:
        """The username of the selected account, ``""`` for none."""
        return self._selected_id

    def select_key(self, key: str) -> None:
        """Select the account *key* (a no-op when there is none)."""
        if any(u.user_id == key for u in self.users):
            self._status = self._summary()
            self._select(key)
            self.notice = ""
            self.notify("selected")

    def select_row(self, record: Any) -> None:
        """The table moved its selection; a busy model keeps the one it has."""
        if self.busy:
            return
        self.notice = ""
        super().select_row(record)

    def role_options(self) -> list[str]:
        """The Role choices; a role stored by another tool is listed, not hidden."""
        options = list(ROLE_OPTIONS)
        current = self.edited.role
        if current and current not in options:
            options.append(current)
        return options

    # -- what the controls may do ----------------------------------------

    def enabled(self, name: str) -> bool:
        """Whether the control *name* is usable now."""
        if name in ("do_save", "ask_revert"):
            return self.dirty and not self.busy and not self.confirm
        if name == "ask_delete":
            return self.selected is not None and not self.busy and not self.confirm
        if name == "ask_password":
            return (
                bool(self.selected is not None or self._creating)
                and not self.busy
                and not self.confirm
            )
        if name in ("do_reload", "new_user"):
            return not self.busy and not self.confirm
        if name in FIELD_NAMES:
            return self.selected is not None or self._creating
        return True

    # -- the status line -------------------------------------------------

    def status_text(self) -> str:
        """The status line: a refused action first, then the Qt tool's text."""
        text = super().status_text()
        if self.busy:
            text = f"Working... {text}" if text else "Working..."
        if self.notice:
            return f"{self.notice} · {text}" if text else self.notice
        return text

    def details_text(self, callout: bool = True) -> str:
        """Markdown for the edited account; *callout* draws the quotes as boxes.

        The painted Markdown shows a plain ``>`` quote under an empty title, so
        the notes use ``> [!NOTE] Title`` blocks there.
        """
        if self._creating or self.selected is None:
            return super().details_text()
        row = self.selected
        lines = [f"### {row.display_name or row.user_id}", ""]
        if row.is_active:
            text = "This is the account ChiSurf uses for its own database connections."
            lines += [f"> [!NOTE] Active account\n> {text}" if callout else f"> {text}", ""]
        if row.protected:
            text = "A built-in account: it cannot be renamed or deleted."
            lines += [f"> [!NOTE] Built-in account\n> {text}" if callout else f"> {text}", ""]
        problems = self.problems()
        if problems:
            lines += ["**Cannot save yet**", ""] + [f"- {p}" for p in problems]
        return "\n".join(lines)

    # -- loading ---------------------------------------------------------

    def start_loading(self) -> None:
        """Fetch the list once, in the background; what the Qt tool did on first show."""
        if not self._loaded:
            self._loaded = True
            self._dispatch("reload")

    def do_reload(self) -> None:
        """Fetch the user list again, in the background."""
        self.notice = ""
        self._dispatch("reload")

    def _dispatch(self, method: str, *args: Any) -> None:
        """Run *method* on the job when there is one, else here."""
        if self.runner is not None and self.runner(method, *args):
            self.busy = True
            return
        getattr(self, method)(*args)

    # -- new -------------------------------------------------------------

    def new_user(self) -> None:
        """Start a new account."""
        self.notice = ""
        super().new_user()

    # -- save ------------------------------------------------------------

    def do_save(self) -> None:
        """Save the edited account: refuse early on a problem, else call the server."""
        self.notice = ""
        if not self.dirty:
            self.notice = "Nothing to save."
            return
        problems = self.problems()
        if problems:
            self.notice = "Cannot save: " + " ".join(problems)
            return
        self._dispatch("save_work")

    def save_work(self) -> None:
        """The work of :meth:`do_save`: the server call, then a rename's local state."""
        problem = self.save()
        if problem.startswith("renamed:"):
            old = problem.split(":", 1)[1]
            self.carry_local_state(old, self.edited.user_id)
            return
        if problem:
            self.notice = f"Cannot save: {problem}"

    @staticmethod
    def carry_local_state(old_user_id: str, new_user_id: str) -> None:
        """Move the stored session tokens after a rename, so the user stays signed in."""
        try:
            from mmfdb.security.credentials import (
                rename_runtime_session_token,
                rename_session_token,
            )

            from chisurf.core.settings.settings_utils import set_mmfdb_login_settings
            from chisurf.plugins.core.user_editor.api.client import server_address

            host, port = server_address()
            rename_runtime_session_token(host, port, old_user_id, new_user_id)
            rename_session_token(host, port, old_user_id, new_user_id)
            set_mmfdb_login_settings({"default_user_id": new_user_id})
        except Exception:
            logging.exception("User Editor: could not carry local state after a rename")

    # -- revert ----------------------------------------------------------

    def ask_revert(self) -> None:
        """Revert, after the user confirms; nothing to ask when nothing changed."""
        self.notice = ""
        if not self.dirty:
            self.notice = "Nothing to revert."
            return
        self.confirm = "revert"

    # -- delete ----------------------------------------------------------

    def signed_in_is_admin(self) -> bool:
        """Whether the signed-in account is an administrator."""
        me = active_user_id()
        return any(u.user_id == me and u.is_admin for u in self.users)

    def ask_delete(self) -> None:
        """Delete the selected account, after the user confirms.

        Refuses, with a message, when nothing is selected, for a built-in account
        and for the account ChiSurf is using: the cases the Qt tool refused in a
        warning dialog.
        """
        self.notice = ""
        row = self.selected
        if row is None:
            self.notice = "No user selected. Select an account first."
        elif row.user_id in PROTECTED_USER_IDS:
            self.notice = f"Cannot delete: {row.user_id!r} is a built-in account."
        elif row.is_active:
            self.notice = (
                "Cannot delete: this is the account ChiSurf is using. "
                "Switch to another account first."
            )
        else:
            self.delete_target = row.user_id
            self.confirm = "delete"

    def delete_work(self, user_id: str, force: bool = False) -> None:
        """The work of a confirmed delete: the server call, then what a refusal means.

        The backend refuses an account that owns committed data; an
        administrator is then offered a forced deletion, anyone else the reason.
        """
        problem = self.delete(user_id, force=force)
        if not problem:
            return
        if force:
            self.notice = f"Force delete failed: {problem}"
        elif self.signed_in_is_admin():
            self.delete_target = user_id
            self.delete_problem = problem
            self.confirm = "force_delete"
        else:
            self.notice = f"Cannot delete: {problem}"

    # -- confirmations ---------------------------------------------------

    @property
    def confirm_title(self) -> str:
        """Title of the confirmation dialog."""
        return {
            "revert": "Discard changes",
            "delete": "Delete user",
            "force_delete": "Force delete",
        }.get(self.confirm, "")

    @property
    def confirm_text(self) -> str:
        """The question the confirmation dialog asks."""
        if self.confirm == "revert":
            return "Discard the edits to this account?"
        row = next((u for u in self.users if u.user_id == self.delete_target), None)
        label = (row.display_name or row.user_id) if row else self.delete_target
        if self.confirm == "delete":
            return f"Permanently delete {label!r}?"
        if self.confirm == "force_delete":
            return (
                f"Could not delete the account:\n{self.delete_problem}\n\n"
                "Force the deletion? The account goes, its committed data stays."
            )
        return ""

    def confirm_yes(self) -> None:
        """The user agreed: do what was asked."""
        action, self.confirm = self.confirm, ""
        if action == "revert":
            self.revert()
        elif action == "delete":
            self._dispatch("delete_work", self.delete_target, False)
        elif action == "force_delete":
            self._dispatch("delete_work", self.delete_target, True)

    def confirm_no(self) -> None:
        """The user declined: nothing changes."""
        self.confirm = ""

    # -- password --------------------------------------------------------

    def ask_password(self) -> None:
        """Open the password prompt for the account being edited."""
        self.notice = ""
        row = self.selected
        user_id = self.edited.user_id or (row.user_id if row else "")
        if not user_id:
            self.notice = "No user selected. Select or create an account first."
            return
        self.password_user = user_id
        self.password_new = ""
        self.password_confirm = ""
        self.password_error = ""
        self.password_open = True

    @property
    def password_title(self) -> str:
        """Title of the password prompt."""
        return f"Change Password for {self.password_user}"

    @property
    def password_score(self) -> int:
        """Strength 0 to 5 of the password typed."""
        return password_strength(self.password_new)[0]

    @property
    def password_fraction(self) -> float:
        """The strength as a fraction for the progress bar."""
        return self.password_score / 5.0

    def password_strength_text(self) -> str:
        """Strength word for the bar, as the Qt dialog's label."""
        return strength_label(self.password_new)

    def password_feedback(self) -> str:
        """What the password still lacks, or the last refusal."""
        if self.password_error:
            return self.password_error
        if not self.password_new:
            return "Type a password; it is applied when you press Save."
        score, missing = password_strength(self.password_new)
        if score >= 5:
            return "All requirements are met."
        return "Requirements: " + ", ".join(missing)

    def password_set(self) -> None:
        """Check the two entries and stage the password for the next Save.

        The Qt dialog refused a mismatch and, for an administrator, a score
        under 4; an empty password is refused here too.
        """
        password, confirm = self.password_new, self.password_confirm
        if not password:
            self.password_error = "Enter a password."
        elif password != confirm:
            self.password_error = "Passwords do not match."
        elif self.edited.is_admin and self.password_score < 4:
            self.password_error = (
                "Administrator password is too weak. It must be at least Medium "
                "strength (score >= 4)."
            )
        else:
            self.stage_password(password)
            self.password_cancel()
            return
        self.notify("password")

    def password_cancel(self) -> None:
        """Close the password prompt and forget what was typed."""
        self.password_open = False
        self.password_new = ""
        self.password_confirm = ""
        self.password_error = ""

    # -- copy and export -------------------------------------------------

    def request_copy(self) -> None:
        """Ask the app to copy the shown rows to the clipboard."""
        self.request = "copy"

    def request_export(self) -> None:
        """Ask the app to choose a CSV file for the shown rows."""
        self.request = "export"

    def displayed(self) -> tuple[list[dict], list[tuple[str, str]]]:
        """The rows and columns the table shows: after its filter, sort and column choice."""
        if self.displayed_provider is not None:
            records, columns = self.displayed_provider()
            return list(records), list(columns)
        return list(self.user_records()), list(TABLE_COLUMNS)

    def table_text(self, delimiter: str = "\t", header: bool = True) -> str:
        """The shown rows as delimited text."""
        records, columns = self.displayed()
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=delimiter, lineterminator="\n")
        if header:
            writer.writerow([title for _key, title in columns])
        for record in records:
            writer.writerow([record.get(key, "") for key, _title in columns])
        return buffer.getvalue()

    def export_csv(self, path: str) -> bool:
        """Write the shown rows to *path* as CSV; returns whether it worked."""
        try:
            target = pathlib.Path(path)
            if target.suffix == "":
                target = target.with_suffix(".csv")
            target.write_text(self.table_text(",", True), encoding="utf-8", newline="")
        except OSError as exc:
            self.notice = f"Could not write {path}: {exc}"
            return False
        self.notice = f"Exported {len(self.displayed()[0])} rows to {target}."
        return True


#: The editable account fields (the spec's ``attr`` names), enabled with a selection.
FIELD_NAMES = frozenset(
    {
        "user_id",
        "display_name",
        "email",
        "role",
        "affiliation",
        "department",
        "phone",
        "website",
        "address",
        "details",
        "is_admin",
        "allow_autologin",
    }
)
