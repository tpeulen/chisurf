"""The native MMFDB Admin's shell model: connection, login, the rail, dialogs and jumps (Qt-free).

:class:`AdminModel` is what the toolbar, the menu bar, the rail and the status
bar of ``gui/app.py`` are drawn over, and the hub every panel talks through:

* the **connection** -- host, port, user and a masked password in the toolbar;
  Login builds a client for that endpoint, checks the transport, signs in (an
  existing token, the process's cached session, a passwordless login, the typed
  password, and else the login dialog) and refuses a user who is not an MMFDB
  administrator, as the Qt tool does. Nothing here persists a password;
* the **panels** -- the rail's destinations in the Qt tool's order, each a model
  (:mod:`.entity`, :mod:`.panels`, :mod:`.spectra`, :mod:`.provenance`), made on
  first use and loaded the first time they are opened;
* the **calls** -- every server call goes through :meth:`AdminModel.run` on a
  :class:`~.runner.Runner`, so the window never waits on the network;
* the **dialogs** -- a stack of :mod:`.dialogs` models the app draws on top;
* what only the host can do -- copy to the clipboard, open a file or URL, ask
  for a path -- is requested here and served by the app (or by a test).
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from typing import Any

from ..entity_registry import ENTITY_REGISTRY, build_registry_dict
from ..entity_schema import entity_field_specs
from .base import Panel
from .dialogs import ConfirmDialog, ConnectionDialog, Dialog, MessageDialog
from .entity import EntityPanel
from .panels import (
    AllItemsPanel,
    CalibrationsPanel,
    ElabPanel,
    ImportExportPanel,
    LifecyclePanel,
    MeasurementsPanel,
    MetadataPanel,
    OverviewPanel,
    PipelinesPanel,
    ProtocolsPanel,
    ReagentsPanel,
    StudiesPanel,
)
from .provenance import ProvenancePanel
from .runner import Call, Runner, ThreadRunner

#: The rail: ``("group", title)`` starts a group; anything else is a panel key.
RAIL: tuple = (
    "overview",
    "all_items",
    "measurements",
    ("group", "Samples & chemistry"),
    "sample",
    "condition",
    "entity",
    "probe",
    "position",
    "fret_pair",
    "metadata",
    "spectra",
    ("group", "Experiments & data"),
    "experiment",
    "experiment_type",
    "setup",
    "detector_channel",
    "pie_window",
    "fcs_pair",
    "device",
    "raw_data",
    "processing_run",
    "processed_product",
    "analysis",
    "object",
    ("group", "Provenance"),
    "project",
    "branch",
    "provenance",
    ("group", "Administration"),
    "user",
    "import_export",
    "elabftw",
    ("group", "Workflows & QC"),
    "studies",
    "protocols",
    "lifecycle",
    "calibrations",
    "reagents",
    "pipelines",
)

SPECIAL_PANELS: dict[str, type[Panel]] = {
    "overview": OverviewPanel,
    "all_items": AllItemsPanel,
    "measurements": MeasurementsPanel,
    "metadata": MetadataPanel,
    "provenance": ProvenancePanel,
    "import_export": ImportExportPanel,
    "elabftw": ElabPanel,
    "studies": StudiesPanel,
    "protocols": ProtocolsPanel,
    "lifecycle": LifecyclePanel,
    "calibrations": CalibrationsPanel,
    "reagents": ReagentsPanel,
    "pipelines": PipelinesPanel,
}

CLIENT_METADATA = {"name": "mmfdb-admin", "host": "local"}


def _special(key: str) -> type[Panel]:
    if key == "spectra":
        from .spectra import SpectraPanel

        return SpectraPanel
    return SPECIAL_PANELS[key]


#: How the transports report that nobody answered (``ZmqClient`` / the HTTP client).
_TRANSPORT_PREFIXES = ("timeout", "send failed", "poll failed", "recv failed", "this client is closed",
                       "connection refused", "failed to connect", "urlopen error")


def is_transport_error(exc: BaseException) -> bool:
    """Whether *exc* says the server did not answer (rather than that it refused)."""
    if isinstance(exc, (OSError, TimeoutError, ConnectionError)):
        return True
    return str(exc).strip().lower().startswith(_TRANSPORT_PREFIXES)


def open_location(location: str) -> None:
    """Open a file, folder or URL with the desktop's default handler."""
    if sys.platform == "darwin":
        subprocess.Popen(["open", location])  # noqa: S603,S607 - the user's own file
    elif os.name == "nt":  # pragma: no cover - platform specific
        os.startfile(location)  # noqa: S606
    else:  # pragma: no cover - platform specific
        subprocess.Popen(["xdg-open", location])  # noqa: S603,S607


class AdminModel:
    """The shell of the native MMFDB Admin and the hub its panels talk through."""

    def __init__(self, client: Any = None, runner: Runner | None = None) -> None:
        from ..session import active_user_id

        try:
            import chisurf.core.settings as cs_settings

            from ..client import client_config

            config = client_config(cs_settings.cs_settings.get("mmfdb", {}))
        except Exception:  # noqa: BLE001 - settings unreadable: the defaults
            config = {"mode": "embedded", "host": "127.0.0.1", "cmd_port": 8765,
                      "pub_port": 8766, "base_url": "", "username": "admin"}
        self.remote = config.get("mode") == "remote"
        self.host = str(config.get("base_url") if self.remote else config.get("host", "127.0.0.1"))
        self.port = int(config.get("cmd_port", 8765))
        self.pub_port = int(config.get("pub_port", self.port + 1))
        self.user = active_user_id()
        self.password = ""
        #: A client handed in (a test, a host that already holds one): Login reuses it.
        self.client = client
        self._given_client = client
        self.runner = runner or ThreadRunner()
        self.runner.on_error = self._call_failed
        #: ``disconnected`` / ``connecting`` / ``connected`` / ``denied``.
        self.connection = "disconnected"
        self.login_user = ""
        self.status = "Ready"
        self.summary = ""
        #: The database line of the last status call (the Qt status bar's permanent text).
        self.database_summary = ""
        self.registry = build_registry_dict()
        self._dictionary: Any = None
        self._schema_map: Any = None
        self._dictionary_loaded = False
        self.panel_models: dict[str, Panel] = {}
        self.selected = "overview"
        self.dialogs: list[Dialog] = []
        self.search = ""
        #: Host requests: text to copy, and a path request (title, mode, name, filters, callback).
        self.copies: list[str] = []
        self.file_request: tuple | None = None
        #: ``chooser(title, mode, filename, filters) -> path | None`` answers a path
        #: request without a dialog (tests); ``opener(location)`` opens a file / URL.
        self.chooser: Callable[..., str | None] | None = None
        self.opener: Callable[[str], Any] = open_location

    # ── calls ──────────────────────────────────────────────────────────
    def run(
        self,
        label: str,
        fn: Callable[[], Any],
        done: Callable[[Any], None] | None = None,
        failed: Callable[[str], None] | None = None,
        redact: tuple[str, ...] = (),
    ) -> None:
        self.runner.submit(Call(label, fn, done, failed, tuple(redact)))

    def _call_failed(self, call: Call, message: str) -> None:
        self.set_status(f"{call.label} failed: {message}")

    def poll(self) -> bool:
        return self.runner.poll()

    @property
    def busy(self) -> bool:
        return self.runner.busy

    def set_status(self, text: str) -> None:
        self.status = str(text)

    def set_summary(self, text: str) -> None:
        self.summary = str(text)

    # ── the rail ───────────────────────────────────────────────────────
    def _ensure_dictionary(self) -> None:
        if self._dictionary_loaded:
            return
        self._dictionary_loaded = True
        try:
            from mmfdb.schema.dictionary_schema_map import build_dictionary_schema_map
            from mmfdb.schema.pdbx_metadata import MmcifDictionary

            self._dictionary = MmcifDictionary.load_bundled()
            self._schema_map = build_dictionary_schema_map()
        except Exception as exc:  # noqa: BLE001 - legacy field lists still work
            self.set_status(f"The mmCIF dictionary could not be loaded: {exc}")

    def entity_spec(self, key: str):
        return next((s for s in ENTITY_REGISTRY if s.key == key), None)

    def panel(self, key: str) -> Panel:
        """The model of panel *key*, made on first use."""
        model = self.panel_models.get(key)
        if model is None:
            spec = self.entity_spec(key)
            if spec is not None:
                self._ensure_dictionary()
                fields = entity_field_specs(spec, self._dictionary, self._schema_map, self.registry)
                model = EntityPanel(self, spec, fields)
            else:
                model = _special(key)(self)
            self.panel_models[key] = model
        return model

    def panel_name(self, key: str) -> str:
        spec = self.entity_spec(key)
        if spec is not None:
            return spec.title
        return _special(key).name

    def panel_description(self, key: str) -> str:
        spec = self.entity_spec(key)
        if spec is not None:
            return f"Browse and edit {spec.title.lower()}."
        return _special(key).description

    def rail(self) -> list[tuple[str, str]]:
        """``(kind, key_or_title)`` rows of the rail (``group`` / ``panel``), filtered by the search."""
        query = self.search.strip().casefold()
        rows: list[tuple[str, str]] = []
        for item in RAIL:
            if isinstance(item, tuple):
                if not query:
                    rows.append(("group", item[1]))
                continue
            text = f"{self.panel_name(item)} {self.panel_description(item)} {item}".casefold()
            if not query or query in text:
                rows.append(("panel", item))
        return rows

    def panel_keys(self) -> list[str]:
        return [item for item in RAIL if not isinstance(item, tuple)]

    def select(self, key: str) -> Panel:
        """Open panel *key* (loading it the first time)."""
        self.selected = key
        model = self.panel(key)
        model.ensure_loaded()
        self.summary = model.status_line()
        return model

    @property
    def current(self) -> Panel:
        return self.panel(self.selected)

    def step(self, delta: int) -> None:
        """Back / Next: the neighbouring panel of the rail."""
        keys = self.panel_keys()
        index = keys.index(self.selected) + delta
        if 0 <= index < len(keys):
            self.select(keys[index])

    def can_step(self, delta: int) -> bool:
        keys = self.panel_keys()
        return 0 <= keys.index(self.selected) + delta < len(keys)

    def jump(self, entity_key: str, record_id: str) -> None:
        """Open *entity_key*'s panel and select *record_id* in it (an FK link, All items)."""
        if entity_key not in self.registry and entity_key != "metadata":
            return
        model = self.select(entity_key)
        jump_to = getattr(model, "jump_to", None)
        if callable(jump_to):
            jump_to(record_id)

    def provenance_seed(self, seed_type: str, seed_id: str) -> None:
        """Open the Provenance Graph on *seed_id* and load its full graph."""
        model = self.select("provenance")
        model.set_seed(seed_type, seed_id)

    def selected_sample_id(self) -> str:
        """The sample selected in the Samples panel ('' if none)."""
        model = self.panel_models.get("sample")
        return str(getattr(model, "selected_id", "") or "")

    # ── dialogs and host requests ──────────────────────────────────────
    def show(self, dialog: Dialog) -> Dialog:
        dialog.stack = self.dialogs
        self.dialogs.append(dialog)
        return dialog

    @property
    def dialog(self) -> Dialog | None:
        return self.dialogs[-1] if self.dialogs else None

    def copy(self, text: str) -> None:
        self.copies.append(str(text))

    def open_location(self, location: str) -> None:
        try:
            self.opener(str(location))
        except Exception as exc:  # noqa: BLE001 - shown, not raised
            self.show(MessageDialog("Reveal failed", str(exc)))

    def request_file(
        self, title: str, mode: str, filename: str, filters: str, then: Callable[[str], Any]
    ) -> None:
        """Ask for a path (a file dialog, or :attr:`chooser`); *then(path)* gets it."""
        if self.chooser is not None:
            path = self.chooser(title, mode, filename, filters)
            if path:
                then(str(path))
            return
        self.file_request = (title, mode, filename, filters, then)

    # ── connection ─────────────────────────────────────────────────────
    @property
    def connected(self) -> bool:
        return self.connection == "connected"

    @property
    def signed_in(self) -> bool:
        """Signed in (an administrator or not): Logout applies."""
        return self.connection in ("connected", "denied")

    def connection_tip(self) -> str:
        return {
            "connected": f"Connected as {self.login_user}" if self.login_user else "Connected",
            "connecting": "Connecting...",
            "denied": "Signed in, but not as an MMFDB administrator",
        }.get(self.connection, "Not connected")

    def connection_colour(self) -> tuple[int, int, int, int]:
        return {
            "connected": (46, 125, 50, 255),
            "connecting": (255, 193, 7, 255),
        }.get(self.connection, (244, 67, 54, 255))

    def _endpoint(self, client: Any) -> tuple[str, int, int]:
        from ..client import credential_endpoint

        if getattr(client, "mode", "embedded") == "remote":
            host, port = credential_endpoint({"mode": "remote", "base_url": client.base_url})
            return host, port, port
        return (
            getattr(client, "host", "127.0.0.1"),
            int(getattr(client, "cmd_port", 8765)),
            int(getattr(client, "pub_port", 8766)),
        )

    def _make_client(self, host: str, port: int, pub_port: int) -> Any:
        from ..client import MMFDBClient

        given = self._given_client
        if given is not None and (
            getattr(given, "inprocess", False)
            or (getattr(given, "host", None), getattr(given, "cmd_port", None)) == (host, port)
            or (self.remote and getattr(given, "base_url", None) == host)
        ):
            return given
        if self.remote:
            return MMFDBClient(mode="remote", base_url=host)
        return MMFDBClient(mode="embedded", host=host, cmd_port=port, pub_port=pub_port)

    def login(self) -> None:
        """Toolbar Login: connect to the endpoint above and sign in."""
        self._connect(self.host.strip() or "127.0.0.1", int(self.port), int(self.port) + 1,
                      self.user.strip(), self.password)
        self.password = ""

    def start(self) -> None:
        """The first frame: connect as the configured user without asking, if that is possible."""
        if self.connection == "disconnected":
            self._connect(self.host.strip() or "127.0.0.1", int(self.port), int(self.pub_port),
                          self.user.strip(), None)

    def _connect(
        self, host: str, port: int, pub_port: int, user: str, password: str | None,
        dialog: ConnectionDialog | None = None,
    ) -> None:
        self.connection = "connecting"
        self.set_status("Connecting...")

        def work():
            client = self._make_client(host, port, pub_port)
            outcome = self._authenticate(client, user, password)
            outcome["client"], outcome["status"] = client, {}
            if outcome.get("ok"):
                outcome["admin"] = self._is_admin(client, outcome["user"])
                if outcome["admin"]:
                    outcome["status"] = client.status() or {}
            return outcome

        def done(outcome: dict) -> None:
            self.client = outcome["client"]
            if not outcome.get("ok"):
                self.connection = "disconnected"
                self.login_user = ""
                reason = outcome.get("error", "")
                if dialog is not None:
                    dialog.refused(reason or "Invalid credentials. Please try again.")
                elif outcome.get("need_password"):
                    self.ask_login(user or self.user)
                else:
                    self.show(MessageDialog("MMFDB login failed", reason or "Invalid credentials. Please try again."))
                self.set_status("Not logged in.")
                return
            if dialog is not None:
                dialog.close()
            self.login_user = outcome["user"]
            self.user = outcome["user"]
            if not outcome.get("admin"):
                self.connection = "denied"
                self.show(
                    MessageDialog(
                        "Access denied",
                        f"User '{self.login_user}' is not an administrator. "
                        "mmfdb-admin is restricted to MMFDB administrators.",
                    )
                )
                self.set_status(f"'{self.login_user}' is not an MMFDB administrator.")
                return
            self.connection = "connected"
            self._apply_status(outcome["status"])
            for model in self.panel_models.values():
                model.loaded = False
            self.current.ensure_loaded()

        def failed(error: str) -> None:
            self.connection = "disconnected"
            if dialog is not None:
                dialog.refused(error)
            self.set_status(f"MMFDB transport unavailable: {error}")

        self.run("Connect", work, done, failed)

    def _authenticate(self, client: Any, user: str, password: str | None) -> dict:
        """Sign *client* in; ``{"ok", "user"}`` or ``{"ok": False, "need_password"|"error"}``."""
        from ..session import cache_session, cached_token, cached_user

        if getattr(client, "token", None):
            return {"ok": True, "user": getattr(client, "_auth_user_id", None) or user or cached_user() or ""}
        host, cmd, pub = self._endpoint(client)
        token = cached_token(host, cmd, pub)
        if token:
            client.token = token
            try:
                me = client.me(quiet=True) or {}
                who = str((me.get("user") or {}).get("user_id") or me.get("user_id") or cached_user() or "")
                return {"ok": True, "user": who or user}
            except Exception:  # noqa: BLE001 - a stale token: sign in again
                client.token = None
        if not user:
            return {"ok": False, "need_password": True}
        try:
            result = client.login(user_id=user, password=password or "",
                                  client_metadata=CLIENT_METADATA, quiet=True)
        except Exception as exc:
            # The server refusing the login raises too; only a transport failure (no
            # answer) is reported as one -- a refusal asks for the password.
            if is_transport_error(exc):
                raise
            result = {"ok": False, "error": str(exc)}
        if isinstance(result, dict) and result.get("ok"):
            cache_session(user, getattr(client, "token", None), host, cmd, pub)
            return {"ok": True, "user": user}
        if password:
            return {"ok": False, "error": "Invalid credentials. Please try again."}
        return {"ok": False, "need_password": True}

    @staticmethod
    def _is_admin(client: Any, user: str) -> bool:
        """Administrators only (and anyone while no administrator exists: bootstrap)."""
        try:
            users = client.list_users()
        except Exception:  # noqa: BLE001 - listing refused: not an administrator
            return False
        if not users or not any(u.get("is_admin") for u in users):
            return True
        return any(u.get("user_id") == user and u.get("is_admin") for u in users)

    def ask_login(self, user: str = "") -> None:
        """The login dialog (the toolbar's ... and a refused passwordless login)."""
        if any(isinstance(d, ConnectionDialog) for d in self.dialogs):
            return

        def go(values: dict) -> None:
            self.host = values["host"] or self.host
            self.port = int(values["cmd_port"])
            self.pub_port = int(values["pub_port"])
            self.user = values["user"] or self.user
            self._connect(self.host, self.port, self.pub_port, self.user, values["password"], dialog)

        dialog = ConnectionDialog(user or self.user, self.host, self.port, self.pub_port, go)
        self.show(dialog)

    def more_options(self) -> None:
        self.ask_login(self.user)

    def logout(self) -> None:
        """Drop the session (and the process's cached one)."""
        from ..session import clear_cached_session

        client = self.client

        def work():
            try:
                client.logout()
            finally:
                client.token = None

        def done(_r: Any = None) -> None:
            clear_cached_session()
            self.connection = "disconnected"
            self.login_user = ""
            self.set_status("Logged out.")

        if client is None:
            done()
            return
        self.run("Logout", work, done, lambda _e: done())

    def _apply_status(self, status: dict) -> None:
        client = self.client
        mode = "remote" if str(getattr(client, "mode", "embedded")) == "remote" else "embedded"
        self.summary = self.database_summary = (
            f"{mode} | User DB: {status.get('user_database', '—')} | schema "
            f"{status.get('schema_version', '?')} | samples {status.get('sample_count', '?')} | "
            f"experiments {status.get('experiment_count', '?')}"
        )
        self.set_status("Ready")

    def refresh(self) -> None:
        """Toolbar Refresh: the status line, then the open panel."""
        if not self.connected:
            self.login()
            return

        def done(status: dict) -> None:
            self._apply_status(status or {})
            for key, model in self.panel_models.items():
                model.loaded = key == self.selected
            self.current.refresh()

        self.run("Refresh", lambda: self.client.status() or {}, done,
                 lambda error: self.set_status(f"MMFDB transport unavailable: {error}"))

    def enabled(self, name: str) -> bool:
        if name in ("login", "more_options"):
            return self.connection in ("disconnected", "denied")
        if name == "logout":
            return self.connection in ("connected", "denied")
        if name in ("refresh",):
            return self.connection != "connecting"
        if name in ("import_file", "export_selected_sample", "backup_database", "reset_database"):
            return self.connected
        return True

    # ── file menu / toolbar actions ────────────────────────────────────
    def import_file(self) -> None:
        """Import a PDBx / PDB-IHM / FLR CIF file (the Import / Export panel shows the result)."""
        self.panel("import_export").import_file()

    def export_selected_sample(self) -> None:
        """Export the sample selected in Samples as FLR CIF (validated first)."""
        sample_id = self.selected_sample_id()
        if not sample_id:
            self.set_status("Select a sample to export")
            self.show(MessageDialog("Export selected sample", "Select a sample in the Samples panel first."))
            return

        def save(path: str) -> None:
            self.run(
                "Export sample",
                lambda: self.client.export_sample(sample_id, output_path=path),
                lambda result: self.set_status(f"Exported {(result or {}).get('output_path', path)}"),
            )

        def ask_path() -> None:
            self.request_file("Export FLR CIF", "save", f"{sample_id}.cif",
                              "CIF files (*.cif *.mmcif);;All files (*)", save)

        def validated(result: dict) -> None:
            result = result or {}
            if result.get("valid", True):
                ask_path()
                return
            warnings = "\n".join(f"- {w}" for w in result.get("warnings", []))
            self.show(ConfirmDialog(
                "Export validation warnings",
                f"The following issues were found:\n\n{warnings}\n\nExport anyway?",
                ask_path,
            ))

        self.run("Validate export", lambda: self.client.validate_sample_export(sample_id),
                 validated, lambda _e: ask_path())

    def backup_database(self) -> None:
        self.run("Backup", lambda: self.client.backup(),
                 lambda path: self.set_status(f"Backup: {path}"))

    def reset_database(self) -> None:
        """Replace the user database with the curated source (a backup is written first)."""
        def done(result: dict) -> None:
            admin_user = (result or {}).get("admin_user")
            hint = f" Log in as {admin_user}." if admin_user else ""
            self.set_status(f"Reset complete. Backup: {(result or {}).get('backup_path')}.{hint}")
            self.refresh()

        self.show(ConfirmDialog(
            "Reset database",
            "Replace the user database with the curated source database?\n\n"
            "Samples, projects and user accounts are replaced. A backup is written first, and the "
            "default administrator is restored so the workspace stays loginable.",
            lambda: self.run("Reset", lambda: self.client.reset_from_source(), done),
            yes_label="Reset",
        ))

    def about_text(self) -> str:
        return (
            "mmfdb-admin\n\nMultiparametric Fluorescence Database\n\nBrowse, edit, import, and "
            "export fluorescence measurements, samples, setups, and analysis runs."
        )

    def show_about(self) -> None:
        self.show(MessageDialog("About mmfdb-admin", self.about_text()))

    def close(self) -> None:
        for model in self.panel_models.values():
            closer = getattr(model, "close", None)
            if callable(closer):
                closer()
        self.password = ""
        self.runner.close()
