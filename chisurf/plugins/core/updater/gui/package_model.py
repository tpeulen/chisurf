"""Qt-free state and behaviour of the package manager window (installed packages, search, environments, channels).

Everything the Qt ``PackageManagerWidget`` did that was not drawing: each button's call reaches the solver only through
:class:`~chisurf.plugins.core.updater.updater.PackageManager` (``_popen``), so a test replaces that one method and sees the
command line the real code would have run. Slow calls (``do_*``) run on a snapshot in a worker thread (the app's job);
with no ``runner`` set they run inline, which is what the model tests do. Destructive actions (remove, remove environment,
install, update all) ask first through the shared dialog; the answer runs the ``do_*`` method.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Callable

from ..updater import PackageManager
from .dialog_model import DialogMixin

TABS = ("Installed Packages", "Search & Install", "Environments", "Channels")


class PackageManagerModel(DialogMixin):
    """The package manager: four pages and one operation log."""

    def __init__(self, manager: PackageManager | None = None) -> None:
        self.manager = manager or PackageManager()
        self._observers: list[Callable[[str], None]] = []
        self.runner: Callable[..., bool] | None = None
        self.busy = False
        self.tab = 0
        self.current_env = ""
        self.installed_all: list[dict] = []
        self.installed_filter = ""
        self.installed_rows: list[dict] = []
        self.search_query = ""
        self.search_rows: list[dict] = []
        self.env_rows: list[dict] = []
        self.channel_rows: list[dict] = []
        #: The selected record of each table (``None`` for none).
        self.sel_installed: dict | None = None
        self.sel_search: dict | None = None
        self.sel_env: dict | None = None
        self.sel_channel: dict | None = None
        self.log: list[str] = []
        #: What the app has to do: ``"export"`` / ``"import"`` open a file dialog; ``"export_path:<p>"`` etc. are not used.
        self.request = ""
        self._import_path = ""

    # -- observer plumbing ----------------------------------------------------------------------------------------------- #
    def add_observer(self, callback: Callable[[str], None]) -> None:
        """Register a callback invoked with an event name after every change."""
        self._observers.append(callback)

    def notify(self, event: str = "changed") -> None:
        """Tell observers something changed."""
        for callback in list(self._observers):
            try:
                callback(event)
            except Exception:  # pragma: no cover
                pass

    @property
    def status_text(self) -> str:
        """The last log line (what a running job reports)."""
        return self.log[-1] if self.log else ""

    # -- what the form shows ----------------------------------------------------------------------------------------------- #
    @property
    def current_env_text(self) -> str:
        """The environment the manager works on."""
        return self.current_env or "Loading..."

    @property
    def log_text(self) -> str:
        """The operation log, one timestamped line per entry."""
        return "\n".join(self.log)

    def append_log(self, message: str) -> None:
        """Append a timestamped message to the operation log (as the Qt log did)."""
        self.log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

    def enabled(self, name: str) -> bool:
        """Whether the control *name* is usable now."""
        if name in ("dialog_ok", "dialog_cancel"):
            return True
        if self.dialog or self.busy:
            return False
        needs = {"ask_update_selected": self.sel_installed, "ask_remove_selected": self.sel_installed,
                 "ask_install_selected": self.sel_search, "ask_clone_env": self.sel_env, "ask_remove_env": self.sel_env,
                 "remove_channel": self.sel_channel}
        if name in needs:
            return needs[name] is not None
        if name == "search_packages":
            return bool(self.search_query.strip())
        return True

    # -- background plumbing ------------------------------------------------------------------------------------------------ #
    def _run(self, method: str, *args: Any) -> None:
        if self.runner is not None and self.runner(method, *args):
            self.busy = True
        elif self.runner is None:
            getattr(self, method)(*args)

    @staticmethod
    def _normalise(result: Any) -> tuple[bool, Any, str]:
        """A solver call's answer as ``(success, data, error)`` (the Qt worker's rule)."""
        if isinstance(result, tuple):
            if len(result) == 3:
                return result[0], result[1], result[2]
            if len(result) == 2:      # (success, output): on failure the output is the error text
                return result[0], result[1], "" if result[0] else str(result[1])
        return True, result, ""

    def _call(self, func: Callable, *args: Any, **kwargs: Any) -> tuple[bool, Any, str]:
        try:
            return self._normalise(func(*args, **kwargs))
        except Exception as exc:
            return False, None, str(exc)

    # -- loading ------------------------------------------------------------------------------------------------------------ #
    def refresh_all(self) -> None:
        """Refresh All: installed packages, environments, channels and the environment label."""
        self._run("do_refresh_all")

    def do_refresh_all(self) -> None:
        """Reload the three lists (solver calls)."""
        self.do_refresh_installed()
        self.do_refresh_envs()
        self.do_refresh_channels()
        self.current_env = self.manager.current_prefix()

    def refresh_installed(self) -> None:
        """Refresh List: reload the installed packages."""
        self._run("do_refresh_installed")

    def do_refresh_installed(self) -> None:
        self.append_log("Refreshing installed packages...")
        ok, data, err = self._call(self.manager.list_installed)
        if not ok:
            self.append_log(f"Error loading installed packages: {err}")
            return
        self.installed_all = list(data or [])
        self.apply_filter()
        self.append_log(f"Loaded {len(self.installed_all)} packages.")

    def do_refresh_envs(self) -> None:
        ok, data, err = self._call(self.manager.list_envs)
        if ok:
            self.env_rows = [{"env": e} for e in data]
            self.sel_env = None
        else:
            self.append_log(f"Error loading environments: {err}")

    def do_refresh_channels(self) -> None:
        ok, data, err = self._call(self.manager.get_channels)
        if ok:
            self.channel_rows = [{"channel": c} for c in data]
            self.sel_channel = None
        else:
            self.append_log(f"Error loading channels: {err}")

    def apply_filter(self, *_: Any) -> None:
        """Show only the installed packages whose name contains the filter text (case-insensitive)."""
        text = self.installed_filter.lower()
        self.installed_rows = [
            {"name": p.get("name", ""), "version": p.get("version", ""), "channel": p.get("channel", "")}
            for p in self.installed_all if text in p.get("name", "").lower()
        ]
        self.sel_installed = None

    # -- selection (the tables' ``selected_call``) ------------------------------------------------------------------------------- #
    def select_installed(self, record: dict | None) -> None:
        self.sel_installed = record or None

    def select_search(self, record: dict | None) -> None:
        self.sel_search = record or None

    def select_env(self, record: dict | None) -> None:
        self.sel_env = record or None

    def select_channel(self, record: dict | None) -> None:
        self.sel_channel = record or None

    # -- search & install ---------------------------------------------------------------------------------------------------- #
    def search_packages(self) -> None:
        """Search: look for the query in the configured channels."""
        if self.search_query.strip():
            self._run("do_search")

    def do_search(self) -> None:
        query = self.search_query.strip()
        self.append_log(f"Searching for '{query}'...")
        ok, data, err = self._call(self.manager.search, query)
        if not ok:
            self.append_log(f"Search failed: {err}")
            return
        self.search_rows = [dict(p, id=f"{p['name']}=={p['version']}@{p['channel']}") for p in data] if isinstance(data, list) else []
        self.sel_search = None
        self.append_log(f"Found {len(self.search_rows)} results.")

    def ask_install_selected(self) -> None:
        """Install Selected: ask first."""
        if self.sel_search:
            name = self.sel_search["name"]
            self.ask("install", "Confirm Installation", f"Are you sure you want to install:\n{name}?", context=[name])

    def ask_update_selected(self) -> None:
        """Update Selected: no question (as in the Qt tool)."""
        if self.sel_installed:
            self._operate("update", [self.sel_installed["name"]], label=f"Updating {self.sel_installed['name']}...")

    def ask_update_all(self) -> None:
        """Update All: ask first."""
        self.ask("update_all", "Update All", "Update all packages in the current environment?")

    def ask_remove_selected(self) -> None:
        """Remove Selected: ask first."""
        if self.sel_installed:
            name = self.sel_installed["name"]
            self.ask("remove", "Confirm Removal", f"Are you sure you want to remove:\n{name}?", context=[name])

    # -- environments ------------------------------------------------------------------------------------------------------- #
    def ask_create_env(self) -> None:
        """Create New: ask for the name."""
        self.ask("create_env", "New Environment", "Enter environment name:", yes_no=False, entry=True)

    def ask_clone_env(self) -> None:
        """Clone Selected: ask for the new name."""
        if self.sel_env:
            src = self.sel_env["env"]
            self.ask("clone_env", "Clone Environment", f"Enter new name for clone of '{src}':", yes_no=False, entry=True, context=src)

    def ask_remove_env(self) -> None:
        """Remove Selected (environment): ask first."""
        if self.sel_env:
            env = self.sel_env["env"]
            self.ask("remove_env", "Confirm removal", f"Remove environment '{env}'?", context=env)

    def request_export(self) -> None:
        """Export to File: the app asks for the file."""
        self.request = "export"

    def request_import(self) -> None:
        """Import from File: the app asks for the file."""
        self.request = "import"

    def export_to(self, path: str) -> None:
        """Write the selected (or the current) environment as YAML to *path* (background)."""
        prefix = self.manager.current_prefix() if not self.sel_env else self.sel_env["env"]
        if self.sel_env and os.sep not in prefix:
            prefix = None
        self.append_log(f"Exporting environment to {path}...")
        self._run("do_export", path, prefix)

    def do_export(self, path: str, prefix: str | None) -> None:
        ok, data, err = self._call(self.manager.export_env, prefix=prefix)
        if not ok:
            self.append_log(f"Export failed: {err}")
            return
        try:
            with open(path, "w") as handle:
                handle.write(data)
            self.append_log(f"Exported successfully to {path}")
        except Exception as exc:
            self.append_log(f"Failed to write file: {exc}")

    def import_from(self, path: str) -> None:
        """A file was chosen for import: ask for the new name (optional)."""
        self._import_path = path
        self.ask("import_env", "Import Environment", "Enter name for new environment (optional):", yes_no=False, entry=True)

    # -- channels ----------------------------------------------------------------------------------------------------------- #
    def ask_add_channel(self) -> None:
        """Add Channel: ask for the name or URL."""
        self.ask("add_channel", "Add Channel", "Enter channel name or URL:", yes_no=False, entry=True)

    def remove_channel(self) -> None:
        """Remove Selected (channel): no question (as in the Qt tool)."""
        if self.sel_channel:
            ch = self.sel_channel["channel"]
            self._operate("remove_channel", ch, label=f"Removing channel '{ch}'...")

    # -- dialogs -> operations ------------------------------------------------------------------------------------------------ #
    def on_dialog(self, kind: str, accepted: bool, value: str, context: Any) -> None:
        """What a closed dialog means: a confirmed question runs its operation; a refused one changes nothing."""
        value = value.strip()
        if kind == "notice" or not accepted:
            return
        if kind == "install":
            self._operate("install", context, label=f"Installing {', '.join(context)}...")
        elif kind == "update_all":
            self._operate("update", label="Updating all packages...")
        elif kind == "remove":
            self._operate("remove", context, label=f"Removing {', '.join(context)}...")
        elif kind == "create_env" and value:
            self._operate("create_env", name=value, label=f"Creating environment '{value}'...")
        elif kind == "clone_env" and value:
            src = context
            kw = {"prefix_src": src} if os.sep in src else {"name_src": src}
            self._operate("clone_env", name_dst=value, label=f"Cloning environment '{src}' to '{value}'...", **kw)
        elif kind == "remove_env":
            kw = {"prefix": context} if os.sep in context else {"name": context}
            self._operate("remove_env", label=f"Removing environment '{context}'...", **kw)
        elif kind == "import_env":
            self.append_log(f"Importing environment from {self._import_path}...")
            self._run("do_operation", "import_env", [self._import_path, value or None], {})
        elif kind == "add_channel" and value:
            self._operate("add_channel", value, label=f"Adding channel '{value}'...")

    def _operate(self, op: str, *args: Any, label: str = "", **kwargs: Any) -> None:
        if label:
            self.append_log(label)
        self._run("do_operation", op, list(args), kwargs)

    def do_operation(self, op: str, args: list, kwargs: dict) -> None:
        """Run the solver call *op* and report: success refreshes everything, failure shows an error box."""
        ok, data, err = self._call(getattr(self.manager, op), *args, **kwargs)
        if ok:
            self.append_log("Operation completed successfully.")
            self.do_refresh_all()
        else:
            self.append_log(f"Operation failed: {err}")
            self.notice("Error", f"The operation failed:\n{err}")

    # -- persistence ---------------------------------------------------------------------------------------------------------- #
    def export_settings(self) -> dict:
        """What is remembered: the page and the filter."""
        return {"tab": self.tab, "installed_filter": self.installed_filter}

    def restore_settings(self, settings: dict) -> None:
        """Restore :meth:`export_settings`."""
        self.tab = int(settings.get("tab", 0)) % len(TABS)
        self.installed_filter = str(settings.get("installed_filter", ""))
        self.apply_filter()
