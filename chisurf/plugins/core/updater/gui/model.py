"""Qt-free state and behaviour of the updater window (version check, changelog, update).

Everything the Qt ``UpdaterWidget`` did that was not drawing lives here, cut over unchanged where it could be:
the startup settings (``plugins.updater`` in the user's settings file), the changelog formatting, the version
list and the changelog of the selected version, and the update itself. The network and the machine are reached
only through :class:`~chisurf.plugins.core.updater.updater.ChiSurfUpdater`, so a test replaces its
``_list_remote_versions``, ``_run_update_in_separate_process`` and friends and sees the command line the real
code would have run.

Slow work (``auto_check``, ``do_check``, ``update_changelog_for_selected``, ``do_update``) are methods the app
runs on a snapshot of the model in a worker thread (``chisurf.emtk.jobs.SnapshotJob``); with no ``runner`` set
they run inline, which is what the tests of the model do.
"""

from __future__ import annotations

import html
import logging
import os
from typing import Any, Callable

from chisurf.core import info

from ..updater import ChiSurfUpdater
from .dialog_model import DialogMixin

#: The updater's own download location; ``ChiSurfUpdater`` ignores any other.
HARDCODED_URL = "https://www.peulen.xyz/downloads/chisurf/"

#: Shown in the changelog area until a changelog exists.
CHANGELOG_PLACEHOLDER = "Changelog will appear here after checking for updates..."

#: The question Update Now asks (the Qt dialog's text).
UPDATE_WARNING = (
    "The update process will close all ChiSurf windows and continue in a separate window.\n\n"
    "All unsaved work will be lost. After the update completes, you will need to restart ChiSurf manually.\n\n"
    "Do you want to continue?"
)


def parse_changelog(text: str) -> dict:
    """Split the raw changelog string into what both renderings (Qt rich text, emtk blocks) draw.

    Returns ``header`` (the leading ``Changes ...`` line or ``None``), ``items`` (the ``- `` lines), ``others``
    (any other lines) and ``footer`` (``More details:`` / ``See commit history:`` lines), all unescaped; ``empty``
    is true when there is nothing to show.
    """
    if not isinstance(text, str) or not text.strip():
        return {"empty": True, "header": None, "items": [], "others": [], "footer": []}
    header = None
    items: list[str] = []
    others: list[str] = []
    footer: list[str] = []
    # Simple state machine: collect leading header, bullet items, other lines, and detect footer hint
    for i, ln in enumerate(text.splitlines()):
        s = ln.strip("\r\n")
        if i == 0 and s.lower().startswith("changes "):
            header = s
            continue
        if s.startswith("- "):
            items.append(s[2:].strip())
        elif s.lower().startswith("more details:") or s.lower().startswith("see commit history:"):
            footer.append(s)
        elif s:
            others.append(s)
    return {"empty": False, "header": header, "items": items, "others": others, "footer": footer}


def split_footer(line: str) -> tuple[str, str | None]:
    """``(label, url)`` of a footer line: the first ``http(s)`` word is the link, the rest its caption."""
    url = None
    for word in line.split():  # naive
        if word.startswith("http://") or word.startswith("https://"):
            url = word
            break
    if url:
        return line.replace(url, "").strip(" :") or "More details", url
    return line, None


def format_changelog_html(text: str) -> str:
    """Return pretty HTML for the raw changelog string.

    - Converts lines starting with "- " into <li> items
    - Preserves non-list paragraphs and footer links
    """
    try:
        parsed = parse_changelog(text)
        if parsed["empty"]:
            return "<i>No changelog available.</i>"
        html_parts = []
        if parsed["header"]:
            html_parts.append(f"<b>{html.escape(parsed['header'])}</b>")
        if parsed["items"]:
            html_parts.append("<ul>")
            for it in parsed["items"]:
                html_parts.append(f"  <li>{html.escape(it)}</li>")
            html_parts.append("</ul>")
        # Any remaining paragraphs
        for para in parsed["others"]:
            html_parts.append(f"<p>{html.escape(para)}</p>")
        # Footer with links if any
        for ft in parsed["footer"]:
            label, url = split_footer(ft)
            if url:
                html_parts.append(
                    f'<p>{html.escape(label)}: <a href="{html.escape(url)}">{html.escape(url)}</a></p>'
                )
            else:
                html_parts.append(f"<p>{html.escape(ft)}</p>")
        return "\n".join(html_parts)
    except Exception:
        # Fallback: escaped preformatted
        return f"<pre>{html.escape(str(text))}</pre>"


def changelog_blocks(text: str) -> list[tuple[str, str, str | None]]:
    """The changelog as drawable blocks ``(kind, text, url)``: ``header``, ``item``, ``paragraph``, ``link``, ``empty``.

    Plain text, not Markdown: a commit message with ``_`` or ``*`` in it must show as written (a Markdown
    renderer would take them for emphasis and drop them, and emtk's has no escape).
    """
    parsed = parse_changelog(text)
    if parsed["empty"]:
        return [("empty", "No changelog available.", None)]
    blocks: list[tuple[str, str, str | None]] = []
    if parsed["header"]:
        blocks.append(("header", parsed["header"], None))
    blocks += [("item", it, None) for it in parsed["items"]]
    blocks += [("paragraph", para, None) for para in parsed["others"]]
    for ft in parsed["footer"]:
        label, url = split_footer(ft)
        blocks.append(("link", label, url) if url else ("paragraph", ft, None))
    return blocks


def load_startup_settings(cs_settings: Any) -> tuple[bool, bool]:
    """``(ignore_updates, check_on_startup)`` from ``cs_settings['plugins']['updater']`` (defaults False, True)."""
    try:
        plugins = cs_settings.get("plugins") or {}
        updater_settings = plugins.get("updater") or {}
        return (
            bool(updater_settings.get("ignore_updates_on_startup", False)),
            bool(updater_settings.get("check_on_startup", True)),
        )
    except Exception:
        return False, True


def save_startup_settings(ignore_updates: bool, check_on_startup: bool) -> bool:
    """Persist the two startup switches into the user's ``settings_chisurf.yaml`` (True on success)."""
    try:
        import chisurf.core.settings as _cs_settings_mod

        values = {
            "ignore_updates_on_startup": bool(ignore_updates),
            "check_on_startup": bool(check_on_startup),
        }
        all_settings = _cs_settings_mod.cs_settings
        plugins = all_settings.setdefault("plugins", {})
        plugins.setdefault("updater", {}).update(values)
        # Only this section, merged into the user's file: dumping the live
        # settings wrote every merged default into it, pinning them all.
        updater = dict(plugins["updater"])
        from chisurf.core.settings.settings_utils import update_settings_section

        return update_settings_section("plugins", {"updater": updater})
    except Exception:
        return False


class UpdaterModel(DialogMixin):
    """The updater window: installed version, update check, version list, changelog, Update Now."""

    def __init__(
        self,
        suppress_initial_notification: bool = False,
        updater: ChiSurfUpdater | None = None,
        cs_settings: Any = None,
    ) -> None:
        if cs_settings is None:
            from chisurf.core.settings import cs_settings as default_settings

            cs_settings = default_settings
        self.cs_settings = cs_settings
        #: Whether the check on start stays quiet (the Settings dialog / startup embed the window this way).
        self.suppress_initial_notification = bool(suppress_initial_notification)
        self._observers: list[Callable[[str], None]] = []
        #: ``runner(method)`` starts a slow method in the background (the app's job); ``None`` runs it inline.
        self.runner: Callable[[str], bool] | None = None
        self.current_version = info.__version__
        self.available_versions: list[dict] = []
        self.version_index = -1
        self.status = "Click 'Check for Updates' to check for available updates."
        self.update_enabled = False
        self.changelog_html = ""
        self.changelog_blocks: list[tuple[str, str, str | None]] = []
        self.busy = False
        #: Whether the check that runs when the window opens has still to be started (the app starts it).
        self.auto_check_pending = True
        #: The last progress line of a running update, and whether one is running.
        self.update_message = ""
        self.updating = False
        #: Set when the update script took the process over (the real runner ends with ``sys.exit``).
        self.exit_requested = False
        #: What the app has to do now: ``"package_manager"`` opens the package manager window.
        self.request = ""
        self.package_manager_available = True
        self.dev_checked = True
        self.ignore_updates, self._check_on_startup = load_startup_settings(cs_settings)
        update_url = cs_settings.get("update_url", HARDCODED_URL)
        self.updater = updater or ChiSurfUpdater(update_url=update_url)
        self._apply_channel()

    # -- observer plumbing ----------------------------------------------------------------------------------------- #
    def add_observer(self, callback: Callable[[str], None]) -> None:
        """Register a callback invoked with an event name after every change."""
        self._observers.append(callback)

    def notify(self, event: str = "changed") -> None:
        """Tell observers something changed."""
        for callback in list(self._observers):
            try:
                callback(event)
            except Exception:  # pragma: no cover - an observer must not break the model
                pass

    @property
    def status_text(self) -> str:
        """The line a job reports while it runs: the update's progress, else the status."""
        return self.update_message or self.status

    # -- what the form shows ----------------------------------------------------------------------------------------- #
    @property
    def current_version_text(self) -> str:
        """The installed version (the Qt tool showed it next to its caption)."""
        return self.current_version

    @property
    def solver_text(self) -> str:
        """Which solver would run the update and where it lives (the Qt status label's tooltip)."""
        try:
            solver_path = self.updater.pkg_manager.pkg_exe()
            solver_name = os.path.basename(solver_path).lower()
            if "micro" in solver_name:
                solver_type = "micromamba"
            elif "mamba" in solver_name:
                solver_type = "mamba"
            else:
                solver_type = "conda"
            return f"Solver: {solver_type}  ({solver_path})"
        except Exception:
            return "Solver information unavailable"

    @property
    def branch_text(self) -> str:
        """The branch the changelog is read from (the Qt label beside the Development box was empty)."""
        return f"branch: {self.updater.channel}"

    @property
    def development(self) -> bool:
        """The Development switch (always on in the tool: no stable release exists yet)."""
        return self.dev_checked

    @development.setter
    def development(self, value: bool) -> None:
        self.dev_checked = bool(value)
        self._apply_channel()

    def _apply_channel(self) -> None:
        # If ever allowed to uncheck, fall back to main/master (as the Qt box did)
        self.updater.channel = "development" if self.dev_checked else "master"

    @property
    def check_on_startup(self) -> bool:
        """Check for updates when ChiSurf starts (saved the moment it is changed, as in the Qt tool)."""
        return self._check_on_startup

    @check_on_startup.setter
    def check_on_startup(self, value: bool) -> None:
        self._check_on_startup = bool(value)
        save_startup_settings(self.ignore_updates, self._check_on_startup)

    @property
    def ignore_updates_on_startup(self) -> bool:
        """Do not prompt about updates when ChiSurf starts (saved the moment it is changed)."""
        return self.ignore_updates

    @ignore_updates_on_startup.setter
    def ignore_updates_on_startup(self, value: bool) -> None:
        self.ignore_updates = bool(value)
        save_startup_settings(self.ignore_updates, self._check_on_startup)

    @property
    def version_labels(self) -> list[str]:
        """One entry per available version, as the Qt drop-down listed them."""
        return [f"Version {v.get('version')}" for v in self.available_versions if v.get("version")]

    @property
    def selected_version(self) -> str:
        """The drop-down's current entry (``""`` while there is none)."""
        labels = self.version_labels
        return labels[self.version_index] if 0 <= self.version_index < len(labels) else ""

    @selected_version.setter
    def selected_version(self, label: str) -> None:
        labels = self.version_labels
        if label in labels:
            self.version_index = labels.index(label)

    @property
    def update_progress(self) -> None:
        """The progress bar of a running update: indeterminate (the length of an install is not known)."""
        return None

    @property
    def changelog_text(self) -> str:
        """What the changelog area shows until a check has run."""
        return CHANGELOG_PLACEHOLDER

    def set_status(self, text: str) -> None:
        """Replace the status line."""
        self.status = text
        self.notify("status")

    # -- what the controls may do ------------------------------------------------------------------------------------ #
    def enabled(self, name: str) -> bool:
        """Whether the control *name* is usable now."""
        if name in ("dialog_ok", "dialog_cancel"):
            return not self.updating
        if self.dialog or self.busy or self.updating:
            return False
        if name == "development":
            return False  # always on: no stable release exists yet (the Qt box was disabled)
        if name == "selected_version":
            return bool(self.available_versions)
        if name == "ask_update":
            return self.update_enabled
        if name == "open_package_manager":
            return self.package_manager_available
        return True

    # -- slow work -------------------------------------------------------------------------------------------------- #
    def _run(self, method: str, *args: Any) -> None:
        """Run *method* in the background when the app set a runner, else now."""
        if self.runner is not None and self.runner(method, *args):
            self.busy = True
        elif self.runner is None:
            getattr(self, method)(*args)

    def check_for_updates(self) -> None:
        """Check for Updates: list the available versions and say whether a newer one exists (in the background)."""
        self.status = "Checking for updates..."
        self._run("do_check")

    def do_check(self) -> None:
        """The check itself (network): the Qt ``check_for_updates`` slot."""
        logging.info("Checking for updates via UI")
        self.status = "Checking for updates..."
        self.update_enabled = False
        self.version_index = -1
        update_info = self.updater._get_update_info()
        if not update_info:
            self.available_versions = []
            self.status = "Error checking for updates: No update information available"
            logging.error(self.status)
            return
        self.available_versions = list(update_info.get("available_versions", []))
        if not self.available_versions and self.updater._is_local_folder():
            # a local update folder without versions in the update info: list it directly
            self.available_versions = self.updater._list_available_versions()
        if self.available_versions:
            self.version_index = 0
            self.update_enabled = True
            changelog = update_info.get("changelog") if isinstance(update_info, dict) else None
            if changelog:
                self._show_changelog(changelog)
            else:
                self.update_changelog_for_selected()
        update_available, latest_version, error = self._availability()
        if error:
            self.status = f"Error checking for updates: {error}"
        elif update_available and latest_version:
            self.status = f"Update available: version {latest_version}"
            self.update_enabled = True
        else:
            self.status = f"ChiSurf is already up to date (version {info.__version__})."
        logging.info(self.status)
        # Update the changelog after finishing
        self.update_changelog_for_selected()

    def auto_check(self) -> None:
        """The check that runs when the window opens (network): the Qt ``_auto_check_on_start``.

        Respects the startup switches only when the window was opened by ChiSurf's startup, not by the user.
        """
        if self.suppress_initial_notification and (
            self.ignore_updates or not self._check_on_startup
        ):
            self.status = "Startup update check is disabled by user settings."
            return
        self.update_enabled = False
        self.available_versions = []
        self.version_index = -1
        populated_versions = False
        try:
            update_info = self.updater._get_update_info()
            if update_info:
                self.available_versions = list(update_info.get("available_versions", []))
                if not self.available_versions and self.updater._is_local_folder():
                    self.available_versions = self.updater._list_available_versions()
                if self.available_versions:
                    self.version_index = 0
                    self.update_enabled = True
                    self.status = f"Found {len(self.available_versions)} available versions."
                    populated_versions = True
                    changelog = update_info.get("changelog")
                    if changelog:
                        self._show_changelog(changelog)
                    else:
                        self.update_changelog_for_selected()
        except Exception:
            populated_versions = False
        update_available, latest_version, error = self._availability()
        if error:
            # Keep any versions we may have populated, but show the error
            self.status = f"Update check failed or skipped: {error}"
            if not populated_versions:
                self.update_enabled = False
            return
        if update_available and latest_version:
            self.status = f"Update available: version {latest_version}"
            self.update_enabled = True
            if not self.suppress_initial_notification:
                self.notice(
                    "Update Available", f"A new version of ChiSurf ({latest_version}) is available."
                )
        elif not populated_versions:
            self.status = f"ChiSurf is up to date (version {info.__version__})."

    def _availability(self) -> tuple[bool, str | None, str | None]:
        """``(update available, latest version, error)`` as the updater's own check reports it."""
        try:
            return self.updater.check_for_updates()
        except Exception as exc:
            return False, None, str(exc)

    def on_version_changed(self, *_: Any) -> None:
        """A version was picked: show the changes up to it (network, in the background)."""
        self._run("update_changelog_for_selected")

    def update_changelog_for_selected(self) -> None:
        """The changelog of the selected version (network): the Qt ``_update_changelog_for_selected``."""
        try:
            idx = self.version_index
            if idx < 0 and self.available_versions:
                idx = 0
            if idx < 0 or idx >= len(self.available_versions):
                return
            data = self.available_versions[idx]
            if not isinstance(data, dict):
                return
            target_version = data.get("version")
            if not target_version:
                return
            # Default: show changes from currently installed to selected
            from_version = info.__version__
            # If a non-latest version is selected and a previous version exists in the list,
            # show the changes between the previous version and the selected version.
            try:
                if idx >= 0 and (idx + 1) < len(self.available_versions):
                    prev_info = self.available_versions[idx + 1]
                    if isinstance(prev_info, dict):
                        prev_ver = prev_info.get("version")
                        if isinstance(prev_ver, str) and prev_ver:
                            from_version = prev_ver
            except Exception:
                pass
            self._show_changelog(self.updater._build_changelog(from_version, target_version))
        except Exception as exc:
            self._show_changelog(f"Could not load changelog: {exc}")

    def _show_changelog(self, text: str) -> None:
        self.changelog_html = format_changelog_html(text)
        self.changelog_blocks = changelog_blocks(text)

    # -- Update Now ------------------------------------------------------------------------------------------------- #
    def ask_update(self) -> None:
        """Update Now: ask first (the update closes every ChiSurf window)."""
        self.ask("confirm_update", "Update Warning", UPDATE_WARNING)

    def on_dialog(self, kind: str, accepted: bool, value: str, context: Any) -> None:
        """What a closed dialog means."""
        if kind == "confirm_update":
            if accepted:
                self.update_message = "Preparing the update..."
                self.updating = True
                self._run("do_update")
            else:
                logging.info("Update cancelled by user")
                self.status = "Update cancelled by user."

    def do_update(self) -> None:
        """Run the update (it may end the process): the Qt ``update_chisurf`` slot after the confirmation."""
        logging.info("Starting ChiSurf update via UI")
        self.exit_requested = False

        def callback(message: str) -> None:
            self.update_message = message
            self.notify("message")

        try:
            if self.available_versions and 0 <= self.version_index < len(self.available_versions):
                selected = self.available_versions[self.version_index]
                version, file_path = selected["version"], selected["file_path"]
                self.status = f"Updating to version {version}..."
                callback(self.status)
                logging.info(f"Update file path: {file_path}")
                # auto_restart is ignored as the application will be closed
                result = self.updater.update_to_version(
                    file_path, callback=callback, auto_restart=False
                )
            else:
                logging.info("No specific version selected, using standard update")
                result = self.updater.update(callback, auto_restart=False)
        except SystemExit:
            # the update script took over: the real runner ends the process after starting it
            self.exit_requested = True
            result = (True, None)
        ok, message = (
            result if isinstance(result, tuple) and len(result) == 2 else (bool(result), None)
        )
        if self.exit_requested:
            self.status = (
                "The update continues in a separate window; restart ChiSurf when it has finished."
            )
        elif not ok:
            self.status = f"Update failed: {message}"
        elif message:
            self.status = str(message)
        else:
            self.status = (
                "The update was started in a separate window; restart ChiSurf when it has finished."
            )
        self.updating = False
        self.update_message = ""

    # -- the package manager ------------------------------------------------------------------------------------------ #
    def open_package_manager(self) -> None:
        """Package Manager: ask the app to open its window."""
        self.request = "package_manager"

    # -- persistence -------------------------------------------------------------------------------------------------- #
    def export_settings(self) -> dict:
        """The two startup switches (the Qt tool saved them to the settings file at once; the host copy follows)."""
        return {"check_on_startup": self._check_on_startup, "ignore_updates": self.ignore_updates}

    def restore_settings(self, settings: dict) -> None:
        """Restore :meth:`export_settings` without writing the settings file again."""
        self._check_on_startup = bool(settings.get("check_on_startup", self._check_on_startup))
        self.ignore_updates = bool(settings.get("ignore_updates", self.ignore_updates))
