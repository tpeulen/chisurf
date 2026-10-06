"""The dialogs of the native MMFDB Admin, as models a spec panel draws (Qt-free).

A dialog is an object with a ``title``, the ``spec`` name of the panel of
``admin.view.json`` that draws it, and the attributes and actions that panel
binds. :class:`~.model.AdminModel` keeps a stack of them (``dialogs``); the app
draws the top one in a :class:`emtk.dialog_window.DialogWindow`. Closing the
window (its ``x`` or Escape) is the dialog's :meth:`Dialog.cancel`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..password_strength import ADMIN_MIN_SCORE, score_password, strength_label


class Dialog:
    """Base: a title, the spec panel that draws it, and the stack that holds it."""

    spec = ""
    #: The first frame's size of the window (it fits its height to the content).
    size = (460.0, 160.0)

    def __init__(self, title: str) -> None:
        self.title = title
        self.stack: list[Dialog] | None = None
        #: An error or hint shown in the dialog (empty: nothing to say).
        self.error = ""

    def close(self) -> None:
        """Take the dialog off the stack."""
        if self.stack is not None and self in self.stack:
            self.stack.remove(self)

    def cancel(self) -> None:
        """Close without doing anything (the window's x, Escape, Cancel)."""
        self.close()

    def enabled(self, name: str) -> bool:  # noqa: ARG002 - view_form hook
        return True

    def error_text(self) -> str:
        return self.error


class ConfirmDialog(Dialog):
    """Asks before something changes the database: Yes runs *on_yes*."""

    spec = "confirm"

    def __init__(
        self, title: str, text: str, on_yes: Callable[[], Any], yes_label: str = "Yes"
    ) -> None:
        super().__init__(title)
        self.text = text
        self.on_yes = on_yes
        self.yes_label = yes_label

    def confirm_text(self) -> str:
        return self.text

    def yes_caption(self) -> str:
        return self.yes_label

    def yes(self) -> None:
        self.close()
        self.on_yes()

    def no(self) -> None:
        self.close()


class MessageDialog(Dialog):
    """Tells the user something (a result, a warning); OK closes it."""

    spec = "message"

    def __init__(self, title: str, text: str) -> None:
        super().__init__(title)
        self.text = text

    def message_text(self) -> str:
        return self.text

    def ok(self) -> None:
        self.close()


class ChoiceDialog(Dialog):
    """Pick one of a few values (a validation status): OK runs *on_ok(value)*."""

    spec = "choose"

    def __init__(
        self,
        title: str,
        prompt: str,
        options: list[str],
        value: str,
        on_ok: Callable[[str], Any],
    ) -> None:
        super().__init__(title)
        self.prompt = prompt
        self.options = list(options)
        self.value = value if value in self.options else (self.options[0] if options else "")
        self.on_ok = on_ok

    def prompt_text(self) -> str:
        return self.prompt

    def option_list(self) -> list[str]:
        return self.options

    def ok(self) -> None:
        self.close()
        self.on_ok(self.value)


class TextDialog(Dialog):
    """Type one value (a branch head operation): OK runs *on_ok(text)*."""

    spec = "ask_text"

    def __init__(
        self,
        title: str,
        prompt: str,
        on_ok: Callable[[str], Any],
        value: str = "",
        label: str = "Value",
    ) -> None:
        super().__init__(title)
        self.prompt = prompt
        self.value = value
        self.label = label
        self.on_ok = on_ok

    def prompt_text(self) -> str:
        return self.prompt

    def ok(self) -> None:
        self.close()
        self.on_ok(self.value.strip())


class ConnectionDialog(Dialog):
    """The MMFDB login: password, and the user and server under Advanced.

    Drawn from the same ``connection_auth.view.json`` the Qt login dialog renders.
    OK hands the values to *on_ok*; the dialog stays open showing the reason when
    the login is refused (:attr:`error`), until it succeeds or is cancelled.
    """

    spec = "connection"
    size = (440.0, 200.0)

    def __init__(
        self,
        user: str,
        host: str,
        cmd_port: int,
        pub_port: int,
        on_ok: Callable[[dict], Any],
        on_cancel: Callable[[], Any] | None = None,
    ) -> None:
        super().__init__(f"MMFDB login — {user}")
        self.password = ""
        self.user = user
        self.host = host
        self.cmd_port = int(cmd_port)
        self.pub_port = int(pub_port)
        self.on_ok = on_ok
        self.on_cancel = on_cancel
        self.busy = False

    def values(self) -> dict:
        return {
            "user": self.user.strip(),
            "password": self.password,
            "host": self.host.strip(),
            "cmd_port": int(self.cmd_port),
            "pub_port": int(self.pub_port),
        }

    def enabled(self, name: str) -> bool:
        return not (self.busy and name == "ok")

    def ok(self) -> None:
        values = self.values()
        self.password = ""  # never kept longer than the attempt
        self.error = ""
        self.busy = True
        self.on_ok(values)

    def refused(self, reason: str) -> None:
        """The login failed: stay open and say why."""
        self.busy = False
        self.error = reason

    def cancel(self) -> None:
        self.password = ""
        self.close()
        if self.on_cancel is not None:
            self.on_cancel()


class PasswordDialog(Dialog):
    """Set or clear a user's password, with the strength the Qt dialog shows.

    Save checks the two entries match and that an administrator's password is
    not empty and at least medium strength; Clear (refused for administrators)
    asks first. Both hand the outcome to *on_done(password, cleared)*.
    """

    spec = "password"
    size = (440.0, 220.0)

    def __init__(
        self,
        user_id: str,
        is_admin: bool,
        on_done: Callable[[str, bool], Any],
        ask: Callable[[Dialog], Any],
    ) -> None:
        super().__init__(f"Change Password for {user_id}")
        self.user_id = user_id
        self.is_admin = bool(is_admin)
        self.password_new = ""
        self.password_confirm = ""
        self.on_done = on_done
        self._ask = ask

    @property
    def score(self) -> int:
        return score_password(self.password_new)[0]

    @property
    def password_fraction(self) -> float:
        return self.score / 5.0

    def password_strength_text(self) -> str:
        return strength_label(self.password_new, self.score)

    def password_feedback(self) -> str:
        if self.error:
            return self.error
        score, missing = score_password(self.password_new)
        if not self.password_new or score >= 5:
            return ""
        return "Requirements: " + ", ".join(missing)

    def enabled(self, name: str) -> bool:
        return not (name == "clear" and self.is_admin)

    def save(self) -> None:
        if self.password_new != self.password_confirm:
            self.error = "Passwords do not match."
            return
        if self.is_admin and not self.password_new:
            self.error = "Administrator passwords cannot be empty."
            return
        if self.is_admin and self.score < ADMIN_MIN_SCORE:
            self.error = "Administrator passwords must be at least medium strength."
            return
        password = self.password_new
        self._forget()
        self.close()
        self.on_done(password, False)

    def clear(self) -> None:
        if self.is_admin:
            self.error = "Administrator passwords cannot be cleared."
            return

        def cleared() -> None:
            self._forget()
            self.close()
            self.on_done("", True)

        self._ask(
            ConfirmDialog(
                "Clear password",
                f"Remove the password for '{self.user_id}'?\n\n"
                "The user will be able to log in without a password. Enable 'Allow "
                "Passwordless Login' on the user record if you want passwordless login "
                "to actually work.",
                cleared,
            )
        )

    def _forget(self) -> None:
        self.password_new = self.password_confirm = ""

    def cancel(self) -> None:
        self._forget()
        self.close()


class JumpBranchDialog(Dialog):
    """Create a branch at a past operation and make it the user's active branch."""

    spec = "jump_branch"
    size = (460.0, 220.0)

    def __init__(self, user_id: str, on_ok: Callable[[dict], Any]) -> None:
        super().__init__(f"Jump to branch — {user_id}")
        self.user_id = user_id
        self.operation_id = ""
        self.branch_name = ""
        self.description = ""
        self.on_ok = on_ok

    def jump_text(self) -> str:
        return (
            f"Create a branch for '{self.user_id}' that starts at a recorded operation, "
            "and make it the user's active branch."
        )

    def ok(self) -> None:
        if not self.operation_id.strip():
            self.error = "The operation ID is required."
            return
        self.close()
        self.on_ok(
            {
                "user_id": self.user_id,
                "operation_id": self.operation_id.strip(),
                "branch_name": self.branch_name.strip() or None,
                "description": self.description.strip() or None,
            }
        )


class AnalysisDetailsDialog(Dialog):
    """Parameters and the linked input / output products of an analysis run."""

    spec = "analysis_details"
    size = (760.0, 440.0)

    PRODUCT_KEYS = ("processed_data_id", "product_type", "storage_mode", "validation_status", "file_path")

    def __init__(self, analysis_id: str, detail: dict) -> None:
        super().__init__(f"Analysis details: {analysis_id}")
        self.analysis_id = analysis_id
        self.detail = dict(detail or {})

    def summary_text(self) -> str:
        d = self.detail
        return (
            f"{self.analysis_id} · {d.get('analysis_type') or d.get('type') or ''} · "
            f"{d.get('convergence_status') or d.get('status') or ''}"
        )

    @staticmethod
    def _rows(items: list, keys: tuple[str, ...]) -> list[dict]:
        import json

        out = []
        for i, item in enumerate(items or []):
            row = {"_row": i}
            for key in keys:
                value = (item or {}).get(key, "")
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, sort_keys=True)
                row[key] = "" if value is None else value
            out.append(row)
        return out

    def parameter_rows(self) -> list[dict]:
        return self._rows(
            self.detail.get("parameters") or [],
            ("name", "value", "standard_error", "units", "parameter_type"),
        )

    def input_rows(self) -> list[dict]:
        return self._rows(self.detail.get("input_processed_data") or [], self.PRODUCT_KEYS)

    def output_rows(self) -> list[dict]:
        return self._rows(self.detail.get("processed_data") or [], self.PRODUCT_KEYS)

    def close_dialog(self) -> None:
        self.close()
