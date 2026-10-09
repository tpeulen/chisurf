"""Qt-free model of the switch-user (MMFDB login) window.

It carries what the Qt ``LoginDialog`` carried: the server (or MMFDB URL) and port, the
account, the password, the two remember-options, the server history and the offered accounts,
and the login itself -- authenticate through the MMFDB client, then persist the choice in the
``mmfdb`` settings and the session-token stores exactly as the dialog did.

Messages the dialog showed in modal message boxes (Login Failed, Settings Not Saved, Autologin
Not Saved, Error) are queued in :attr:`notices` and shown one at a time by the app; the window
closes once the last one is acknowledged, as the dialog closed after its boxes.
"""

from __future__ import annotations

import json
from typing import Any, Callable

#: Servers remembered in the history, as in the Qt dialog.
HISTORY_LENGTH = 5


def format_login_error(error: object) -> str:
    """GUI-safe text for a raw MMFDB login error (the Qt dialog's rule)."""
    fallback = "Incorrect credentials"
    if error is None:
        return fallback
    if isinstance(error, str):
        return error or fallback
    if isinstance(error, dict):
        message = error.get("message") or error.get("error") or error.get("reason")
        if message is not None and message is not error:
            return format_login_error(message)
        try:
            return json.dumps(error, sort_keys=True)
        except TypeError:
            return str(error)
    return str(error)


def default_client_factory(mode: str, server: str, port: int):
    """The MMFDB client the dialog configured for *server* (host or URL) and *port*."""
    from chisurf.plugins.core.mmfdb_admin.gui.client import MMFDBClient

    if mode == "remote":
        return MMFDBClient(mode="remote", base_url=server)
    return MMFDBClient(mode="embedded", host=server, cmd_port=port, pub_port=port + 1)


class SwitchUserModel:
    """State and actions behind the emtk switch-user window."""

    def __init__(self, client_factory: Callable[[str, str, int], Any] | None = None) -> None:
        self._observers: list[Callable[[str], None]] = []
        self.client_factory = client_factory or default_client_factory
        #: ``runner(method_name)`` runs a model method off the draw loop; ``None`` runs it here.
        self.runner: Callable[..., bool] | None = None
        self.client_config: dict = {}
        self.mode = "embedded"
        self.server = "127.0.0.1"
        self.port = 8765
        self.user = "admin"
        #: The account chosen from the list: what an empty user field falls back to.
        self.picked_user = "admin"
        self.password = ""
        self.save_login = True
        self.autologin = False
        self.server_history: list[str] = []
        self.known_users: list[str] = []
        #: Pickers over the editable combos of the Qt dialog.
        self.recent_server = ""
        self.known_user = ""
        self.message = ""
        self.busy = False
        #: True once a login succeeded (the Qt dialog's ``accept``).
        self.accepted = False
        #: True once the window should close (accepted and notices read, or cancelled).
        self.closed = False
        #: Pending message boxes: ``(kind, title, text)``.
        self.notices: list[tuple[str, str, str]] = []
        self.load_settings()

    # -- observers (SnapshotJob contract) -------------------------------

    def add_observer(self, callback: Callable[[str], None]) -> None:
        """Register *callback(event)*."""
        self._observers.append(callback)

    def notify(self, event: str = "updated") -> None:
        """Tell every observer that *event* happened."""
        for callback in list(self._observers):
            callback(event)

    # -- reading the configuration (the dialog's constructor) -----------

    def load_settings(self) -> None:
        """Fill the form from the ``mmfdb`` settings, as the dialog's constructor did."""
        import chisurf.core.settings as cs_settings
        from chisurf.plugins.core.mmfdb_admin.gui.client import client_config

        mmfdb_settings = cs_settings.cs_settings.get("mmfdb", {})
        try:
            config = client_config(mmfdb_settings)
        except Exception as exc:  # a malformed settings block must not stop the window
            self.client_config = client_config({})
            self.message = f"The MMFDB client settings are invalid ({exc}); defaults are shown."
            mmfdb_settings = {}
        else:
            self.client_config = config
        config = self.client_config
        self.mode = config["mode"]
        if self.mode == "remote":
            last_server = config["base_url"]
            history = [last_server]
            last_port = 0
        else:
            history = list(mmfdb_settings.get("server_history", [config["host"]]))
            last_server = mmfdb_settings.get("last_server", config["host"])
            last_port = mmfdb_settings.get("last_port", config["cmd_port"])
        seen: list[str] = []
        for server in history:
            if server not in seen:
                seen.append(server)
        self.server_history = seen
        self.server = str(last_server)
        self.port = int(last_port) if self.mode != "remote" else 8765
        offered = [config["username"]]
        if self.mode == "embedded":
            from chisurf.core.mmfdb_services import DESKTOP_CREDENTIALS

            offered += [u for u in DESKTOP_CREDENTIALS if u != config["username"]]
        self.known_users = offered
        self.user = offered[0]
        self.picked_user = offered[0]
        self.save_login = bool(mmfdb_settings.get("save_login", True))
        self.autologin = bool(mmfdb_settings.get("autologin", False))
        self.password = ""
        self._sync_pickers()

    def _sync_pickers(self) -> None:
        self.recent_server = self.server if self.server in self.server_history else ""
        self.known_user = self.user if self.user in self.known_users else ""

    # -- spec hooks ------------------------------------------------------

    @property
    def server_label(self) -> str:
        """``MMFDB URL`` for a remote server, ``Server`` otherwise."""
        return "MMFDB URL" if self.mode == "remote" else "Server"

    def recent_servers(self) -> list[str]:
        """Options of the server-history picker."""
        return list(self.server_history)

    def offered_users(self) -> list[str]:
        """Options of the account picker."""
        return list(self.known_users)

    def bounds(self, name: str):
        """The port range of the Qt spin box."""
        if name == "port":
            return (1, 65535)
        return None

    def enabled(self, name: str) -> bool:
        """Whether the button *name* can be pressed."""
        if name in ("login", "cancel"):
            return not self.busy and not self.closed and not self.notices
        return True

    @property
    def remote(self) -> bool:
        """True when the port is hidden (a remote MMFDB is addressed by URL)."""
        return self.mode == "remote"

    @property
    def status_text(self) -> str:
        """The line under the buttons."""
        if self.busy:
            return "Signing in..."
        return self.message or "Enter your password and press Login."

    @property
    def notice_title(self) -> str:
        """Title of the message box being shown."""
        return self.notices[0][1] if self.notices else ""

    @property
    def notice_text(self) -> str:
        """Text of the message box being shown."""
        return self.notices[0][2] if self.notices else ""

    # -- picking from the lists -----------------------------------------

    def use_recent_server(self, value: Any = None) -> None:
        """Take the server picked from the history."""
        if self.recent_server:
            self.server = self.recent_server

    def use_known_user(self, value: Any = None) -> None:
        """Take the account picked from the list; the password is kept."""
        if self.known_user:
            self.user = self.known_user
            self.picked_user = self.known_user

    def edited_server(self, value: Any = None) -> None:
        """The server field was typed in: keep the picker in step."""
        self._sync_pickers()

    def edited_user(self, value: Any = None) -> None:
        """The account field was typed in: keep the picker in step."""
        self._sync_pickers()

    # -- actions ---------------------------------------------------------

    def cancel(self) -> None:
        """Close without changing the active user (the Qt Cancel button)."""
        self.password = ""
        self.closed = True

    def dismiss_notice(self) -> None:
        """Acknowledge the message box being shown."""
        if self.notices:
            self.notices.pop(0)
        if self.accepted and not self.notices:
            self.closed = True

    def _client(self):
        server = self.server.strip() or (
            self.client_config["base_url"] if self.remote else self.client_config["host"]
        )
        return self.client_factory(self.mode, server, int(self.port))

    def login(self) -> None:
        """The Login button: run :meth:`run_login` (on the app's job when there is one)."""
        if self.busy or self.closed or self.notices:
            return
        if self.runner is not None:
            self.busy = True
            self.runner("run_login")
        else:
            self.run_login()

    def run_login(self) -> None:
        """Authenticate and, on success, persist and apply the chosen account."""
        user_id = self.user.strip() or self.picked_user
        self.message = ""
        try:
            client = self._client()
            result = client.login(user_id=user_id, password=self.password)
            if result.get("ok") or result.get("authenticated"):
                self._apply(result, user_id)
            else:
                self.notices.append(
                    ("warning", "Login Failed", format_login_error(result.get("error")))
                )
                self.message = "Login failed."
        except Exception as exc:
            self.notices.append(("error", "Error", f"Login failed: {exc}"))
            self.message = "Login failed."
        finally:
            self.password = "" if self.accepted else self.password
        self.busy = False
        self.notify("login")

    def _apply(self, result: dict, user_id: str) -> None:
        """Remember the account and the server and keep the session token (as the dialog did)."""
        from mmfdb.security import credentials

        import chisurf.core.settings as cs_settings
        from chisurf.core.settings import settings_utils
        from chisurf.plugins.core.mmfdb_admin.gui.client import client_config, credential_endpoint

        mmfdb_settings = cs_settings.cs_settings.setdefault("mmfdb", {})
        configured = mmfdb_settings.setdefault("client", {})
        save_login, autologin = bool(self.save_login), bool(self.autologin)
        if save_login or autologin:
            mmfdb_settings["default_user_id"] = user_id
            configured["username"] = user_id
        mmfdb_settings["save_login"] = save_login
        mmfdb_settings["autologin"] = autologin
        configured["mode"] = self.client_config["mode"]
        server_host = self.server
        if configured["mode"] == "remote":
            configured["base_url"] = (server_host or self.client_config["base_url"]).rstrip("/")
        else:
            configured["host"] = server_host or self.client_config["host"]
            configured["cmd_port"] = int(self.port)
            configured["pub_port"] = int(self.port) + 1
        history = list(mmfdb_settings.get("server_history", []))
        if server_host not in history:
            history.insert(0, server_host)
            history = history[:HISTORY_LENGTH]
        else:
            history.remove(server_host)
            history.insert(0, server_host)
        mmfdb_settings["server_history"] = history
        mmfdb_settings["last_server"] = server_host
        mmfdb_settings["last_port"] = int(self.port)
        credential_host, credential_port = credential_endpoint(client_config(mmfdb_settings))
        token = result.get("token", "")
        if not settings_utils.set_mmfdb_login_settings(mmfdb_settings):
            self.notices.append(
                (
                    "warning",
                    "Settings Not Saved",
                    "Login succeeded, but ChiSurf could not store the MMFDB login settings.",
                )
            )
        token_saved = True
        if autologin:
            token_saved = credentials.store_session_token(
                credential_host, credential_port, user_id, token
            )
        else:
            credentials.delete_session_token(credential_host, credential_port, user_id)
        credentials.store_runtime_session_token(credential_host, credential_port, user_id, token)
        if autologin and not token_saved:
            cs_settings.cs_settings["mmfdb"]["autologin"] = False
            if hasattr(cs_settings, "mmfdb"):
                cs_settings.mmfdb["autologin"] = False
            settings_utils.set_mmfdb_login_settings(mmfdb_settings)
            self.autologin = False
            self.notices.append(
                (
                    "warning",
                    "Autologin Not Saved",
                    "Login succeeded, but ChiSurf could not store the session token in the OS "
                    "credential store.",
                )
            )
        self.server_history = history
        self._sync_pickers()
        self.accepted = True
        self.message = f"Signed in as {user_id}."
        if not self.notices:
            self.closed = True
