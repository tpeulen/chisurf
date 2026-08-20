"""Qt-free view model behind the user editor."""

from __future__ import annotations

import pathlib
from typing import Any

from chisurf.plugins.core.user_editor.api.client import active_user_id, make_mmfdb_client
from chisurf.plugins.core.user_editor.api.records import (
    ROLE_OPTIONS,
    UserRow,
    to_payload,
    validate_user,
)

_VIEW_JSON = pathlib.Path(__file__).parent / "users.view.json"


class UserEditorViewModel:
    """State and behaviour of the user editor panel.

    Nothing here talks to Qt, and nothing here is fetched in ``__init__`` -- the
    panel is built when its row in the Settings dialog is clicked, and a blocking
    RPC in a constructor froze that whole dialog for the client timeout whenever
    no server was reachable.
    """

    def __init__(self, client_factory=None) -> None:
        self._view_json = _VIEW_JSON
        self._observers: list[Any] = []
        self._client_factory = client_factory or make_mmfdb_client

        self.users: list[UserRow] = []
        self.edited: UserRow = UserRow()
        self._selected_id = ""
        self._creating = False
        self._password: str | None = None
        self._status = "Press Reload to fetch the user list."
        self._error = ""
        self._loaded = False

    # -- plumbing --------------------------------------------------------

    def add_observer(self, callback) -> None:
        """Register a callback invoked after every change."""
        self._observers.append(callback)

    def notify(self, event: str = "changed") -> None:
        """Tell observers something changed."""
        for callback in list(self._observers):
            try:
                callback(event)
            except Exception:  # pragma: no cover
                pass

    def view_spec(self):
        """The parsed view specification for this panel."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(self._view_json)

    # -- loading ---------------------------------------------------------

    def ensure_loaded(self) -> None:
        """Fetch the user list once, on first show."""
        if not self._loaded:
            self._loaded = True
            self.reload()

    def reload(self) -> None:
        """Fetch the user list.

        A failure is recorded as state, not raised and not shown as a modal:
        listing users requires an administrator and every user can open this
        panel, so the common case was a dialog interrupting someone who had done
        nothing wrong.
        """
        self._error = ""
        active = active_user_id()
        try:
            client = self._client_factory()
            records = client.list_users()
        except Exception as exc:
            message = str(exc)
            if "auth" in message.lower() or "admin" in message.lower():
                self._error = (
                    "Listing users requires an administrator account. Sign in as "
                    "an administrator, then press Reload."
                )
            else:
                self._error = f"Could not reach the MMFDB server: {message}"
            self.users = []
            self.notify("reloaded")
            return

        self.users = [UserRow.from_record(r, active_id=active) for r in records or []]
        if self._selected_id and not any(u.user_id == self._selected_id for u in self.users):
            self._selected_id = ""
            self.edited = UserRow()
        elif self._selected_id:
            self._select(self._selected_id)
        self._status = f"{len(self.users)} user(s). Signed in as {active!r}."
        self.notify("reloaded")

    # -- table -----------------------------------------------------------

    def user_rows(self) -> list[dict[str, Any]]:
        """The table source."""
        return [u.as_record() for u in self.users]

    def select_row(self, record: Any) -> None:
        """Called by the table when the selection moves."""
        if isinstance(record, dict):
            self._select(str(record.get("username") or ""))
        elif isinstance(record, int) and 0 <= record < len(self.users):
            self._select(self.users[record].user_id)
        else:
            self._selected_id = ""
            self.edited = UserRow()
        self.notify("selected")

    def _select(self, user_id: str) -> None:
        row = next((u for u in self.users if u.user_id == user_id), None)
        self._selected_id = user_id if row else ""
        self._creating = False
        self._password = None
        # A copy, so edits are discardable and the table keeps showing the
        # server's version until a save succeeds.
        self.edited = UserRow(**vars(row)) if row else UserRow()

    @property
    def selected(self) -> UserRow | None:
        """The account the table has selected."""
        return next((u for u in self.users if u.user_id == self._selected_id), None)

    # -- what the panel shows --------------------------------------------

    def status_text(self) -> str:
        """The status line."""
        if self._error:
            return self._error
        parts = [self._status]
        if self._password is not None:
            parts.append("a new password is staged")
        if self.dirty:
            parts.append("unsaved changes")
        return " · ".join(p for p in parts if p)

    def details_text(self) -> str:
        """Markdown context for the edited account."""
        if self._creating:
            return (
                "### New account\n\nFill in a username and a display name, then "
                "press **Save**. The username is what the account is addressed "
                "by and can be changed later."
            )
        row = self.selected
        if row is None:
            return (
                "### No user selected\n\nPick a row to edit that account, or "
                "press **New** to create one."
            )
        lines = [f"### {row.display_name or row.user_id}", ""]
        if row.is_active:
            lines += ["> This is the account ChiSurf uses for its own database "
                      "connections.", ""]
        if row.protected:
            lines += ["> A built-in account: it cannot be renamed or deleted.", ""]
        problems = self.problems()
        if problems:
            lines += ["**Cannot save yet**", ""] + [f"- {p}" for p in problems]
        return "\n".join(lines)

    def role_options(self) -> list[str]:
        """Options for the role combo."""
        return list(ROLE_OPTIONS)

    def problems(self) -> list[str]:
        """Validation problems with the edited account."""
        return validate_user(self.edited, existing=self.users, creating=self._creating)

    @property
    def dirty(self) -> bool:
        """Whether the edited account differs from the server's version."""
        if self._creating:
            return True
        row = self.selected
        if row is None:
            return False
        return vars(row) != vars(self.edited)

    # -- edited fields, bound by the view spec ---------------------------

    def _field(name: str):  # noqa: N805 - descriptor factory
        """Property forwarding one edited-account field to the view."""
        def getter(self):
            return getattr(self.edited, name)

        def setter(self, value):
            setattr(self.edited, name, value)
            self.notify("edited")

        return property(getter, setter)

    user_id = _field("user_id")
    display_name = _field("display_name")
    email = _field("email")
    role = _field("role")
    affiliation = _field("affiliation")
    department = _field("department")
    phone = _field("phone")
    website = _field("website")
    address = _field("address")
    details = _field("details")
    is_admin = _field("is_admin")
    allow_autologin = _field("allow_autologin")
    del _field

    # -- actions ---------------------------------------------------------

    def new_user(self) -> None:
        """Start a new account."""
        import uuid

        self._creating = True
        self._selected_id = ""
        self._password = None
        self.edited = UserRow(user_uuid=str(uuid.uuid4()))
        self._status = "New account. Fill in the fields and press Save."
        self.notify("selected")

    def stage_password(self, password: str) -> None:
        """Hold a new password until the account is saved."""
        self._password = password
        self.notify("edited")

    @property
    def password_staged(self) -> bool:
        """Whether a password is waiting to be saved."""
        return self._password is not None

    def save(self) -> str:
        """Save the edited account.

        Returns
        -------
        str
            An error message, or ``""`` on success.

        """
        problems = self.problems()
        if problems:
            return "\n".join(problems)

        old_user_id = None if self._creating else self._selected_id
        payload = to_payload(
            self.edited,
            old_user_id=old_user_id,
            password=self._password,
            requester_id=active_user_id(),
        )
        try:
            client = self._client_factory()
            client.save_user(payload)
        except Exception as exc:
            return str(exc)

        renamed_from = old_user_id if old_user_id and old_user_id != self.edited.user_id else None
        self._password = None
        self._creating = False
        self._selected_id = self.edited.user_id
        self.reload()
        self._status = f"Saved {self.edited.display_name or self.edited.user_id!r}."
        return "" if renamed_from is None else f"renamed:{renamed_from}"

    def delete(self, user_id: str, *, force: bool = False) -> str:
        """Delete an account. Returns an error message, or ``""``."""
        try:
            client = self._client_factory()
            client.delete_user(user_id, force=force, requester_id=active_user_id())
        except Exception as exc:
            return str(exc)
        self._selected_id = ""
        self.edited = UserRow()
        self.reload()
        self._status = f"Deleted {user_id!r}."
        return ""

    def revert(self) -> None:
        """Discard edits to the selected account."""
        self._creating = False
        self._password = None
        self._select(self._selected_id)
        self._status = "Changes discarded."
        self.notify("selected")
