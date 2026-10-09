"""Qt-free model of the native plugin manager.

:class:`PluginManagerModel` is the shared :class:`~.view_model.PluginManagerViewModel`
(discovery rows, the settings working copy, selection, save and revert) plus what
only the painted window needs: record lists for the two tables that keep their
identity between frames, the in-app dialogs the Qt tool asked through message
boxes and file choosers (confirm, notice, rename), the icon panel, and the
background rescan / install / uninstall.

Nothing here imports Qt, and every file operation goes through the Qt-free
``api`` package, so the whole manager is testable against a throwaway plugin
directory.
"""

from __future__ import annotations

import csv
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
from typing import Any, Callable

from chisurf.plugins.core.plugin_manager.gui.view_model import PluginManagerViewModel

#: The columns of the plugin table, in the order the Qt table shows them:
#: ``(record key, header)``. The rest (Id, Optional, Source, Toolbar, Window
#: state) start hidden and are offered by the column picker.
TABLE_COLUMNS = (
    ("name", "Plugin"),
    ("version", "Version"),
    ("category", "Category"),
    ("status", "Status"),
    ("requires", "Requires"),
    ("required_by", "Required by"),
)

#: Side length of the icon written to disk (the Qt icon panel's size).
ICON_SIZE = 256


def open_path(path: str) -> None:
    """Show *path* in the system file browser (the Qt tool's ``Open folder``)."""
    if sys.platform.startswith("win"):  # pragma: no cover - platform specific
        os.startfile(path)  # type: ignore[attr-defined]  # noqa: S606
    else:
        command = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.Popen([command, path])  # noqa: S603


class _Records(list):
    """A list of table records that says when its content changed.

    The painted table re-reads its source when the list object, its length or
    its ``revision`` changes; a status that flips from enabled to disabled
    changes none of the first two, so the revision carries it.
    """

    revision = 0


class PluginManagerModel(PluginManagerViewModel):
    """State and actions behind the emtk plugin manager."""

    def __init__(self, settings_block: dict[str, Any] | None = None) -> None:
        #: ``runner(method_name)`` runs a model method off the draw loop (the
        #: app's :class:`~chisurf.emtk.jobs.SnapshotJob`); ``None`` runs it here.
        self.runner: Callable[[str], bool] | None = None
        self.busy = False
        #: Opens a folder or file in the system browser; tests replace it.
        self.opener: Callable[[str], None] = open_path
        #: ``"notice"``, ``"confirm_revert"``, ``"confirm_install"``,
        #: ``"confirm_uninstall"``, ``"confirm_icon_clear"`` or ``"rename"``
        #: while the app shows the dialog, else ``""``.
        self.dialog = ""
        self.dialog_title = ""
        self.dialog_text = ""
        #: The name typed into the rename dialog.
        self.dialog_input = ""
        #: ``"install"``, ``"icon_file"``, ``"copy"`` or ``"export"`` while the
        #: app should open a chooser or act on the table.
        self.request = ""
        #: The plan the install confirmation is about.
        self.install_plan: Any = None
        #: Returns the records the table shows (filtered, sorted) and its columns.
        self.displayed_provider: Callable[[], tuple[list[dict], list[tuple[str, str]]]] | None = (
            None
        )
        # icon panel
        self.icon_open = False
        self.icon_path_text = ""
        self.icon_provider = ""
        self.icon_endpoint = ""
        self.icon_model = ""
        self.icon_status = ""
        self.icon_changed = False
        self._records = _Records()
        self._signature: tuple = ()
        self._dep_records = _Records()
        self._dep_signature: tuple = ()
        super().__init__(settings_block)

    # -- table sources ---------------------------------------------------

    def plugin_rows(self) -> list[dict[str, Any]]:
        """The plugin table's source: one record per visible plugin, stable between edits."""
        records = [row.as_record() for row in self.visible_rows()]
        signature = tuple(tuple(r.items()) for r in records)
        if signature != self._signature:
            self._signature = signature
            fresh = _Records(records)
            fresh.revision = self._records.revision + 1
            self._records = fresh
        return self._records

    def dependency_rows(self) -> list[dict[str, Any]]:
        """The dependency table's source for the selected plugin, stable between edits."""
        records = []
        for record in super().dependency_rows():
            records.append({"key": f"{record['relation']}:{record['plugin']}", **record})
        signature = tuple(tuple(r.items()) for r in records)
        if signature != self._dep_signature:
            self._dep_signature = signature
            fresh = _Records(records)
            fresh.revision = self._dep_records.revision + 1
            self._dep_records = fresh
        return self._dep_records

    @property
    def selected_key(self) -> str:
        """Id of the selected plugin, ``""`` for none."""
        return self._selected_id

    def select_key(self, key: str) -> None:
        """Select the plugin with id *key* (a no-op when there is none)."""
        if any(r.plugin_id == key for r in self._rows):
            self._selected_id = key
            self.notify("selected")

    # -- what the details pane shows -------------------------------------

    def details_blocks(self) -> list[tuple[str, str]]:
        """The selected plugin as ``(kind, text)`` blocks for the painted pane.

        The Qt tool shows :meth:`details_text` as Markdown. The painted Markdown
        drops the underscores of every second plugin id, and the lists of
        requirements it adds are the rows of the Dependencies table beside it,
        so the painted pane draws these blocks as plain text instead: ``title``,
        ``text``, ``fact``, ``note`` and ``muted``.
        """
        row = self.selected
        if row is None:
            return [
                ("title", "No plugin selected"),
                (
                    "text",
                    "Pick a row to see what it is, what it depends on, and what depends on it.",
                ),
            ]
        blocks: list[tuple[str, str]] = [("title", row.name)]
        if row.description:
            blocks.append(("text", row.description.strip()))
        facts = [
            ("Id", row.plugin_id),
            ("Version", row.version or "—"),
            ("Category", row.category or "—"),
            ("Source", row.source or "—"),
            ("Status", row.status_text()),
            ("Window state", row.statefulness),
            ("Module", row.module_path),
            ("Folder", row.package_dir),
        ]
        blocks += [("fact", f"{label}: {value}") for label, value in facts]
        if row.health_note:
            blocks.append(("note", f"{row.health.title()} — {row.health_note}"))
        if not (row.requires or row.optional_requires or row.required_by or row.optional_for):
            blocks.append(
                ("muted", "Stands alone: nothing depends on it and it depends on nothing.")
            )
        return blocks

    # -- the global GUI runtime choice (emtk only) -----------------------

    @property
    def gui_runtime(self) -> str:
        """The GUI runtime preference as its label."""
        return {"auto": "Automatic", "emtk": "EMTK", "qt": "Qt"}[self.gui_mode]

    @gui_runtime.setter
    def gui_runtime(self, label: str) -> None:
        self.gui_mode = {"Automatic": "auto", "EMTK": "emtk", "Qt": "qt"}.get(label, "auto")

    # -- what the controls may do ----------------------------------------

    def enabled(self, name: str) -> bool:
        """Whether the control *name* is usable now."""
        if name in ("dialog_ok", "dialog_cancel"):
            return not self.busy
        if name.startswith("icon_") or name == "icon_close":
            return not self.busy and not self.dialog
        if self.busy or self.dialog or self.icon_open:
            return False
        if name in ("selected_disabled", "selected_in_toolbar", "selected_statefulness"):
            return self.selected is not None
        if name in ("move_up", "move_down"):
            return self.selected is not None
        return True

    # -- dialogs ---------------------------------------------------------

    def _ask(self, kind: str, title: str, text: str) -> None:
        self.dialog, self.dialog_title, self.dialog_text = kind, title, text

    def _notice(self, title: str, text: str) -> None:
        self._ask("notice", title, text)

    def _selected_or_notice(self):
        """The selected row, or ``None`` after telling the user to pick one."""
        row = self.selected
        if row is None:
            self._notice("No plugin selected", "Select a plugin first.")
        return row

    @property
    def dialog_has_input(self) -> bool:
        """Whether the dialog asks for text (the rename dialog)."""
        return self.dialog == "rename"

    @property
    def dialog_has_cancel(self) -> bool:
        """Whether the dialog has a second button."""
        return self.dialog not in ("notice", "")

    @property
    def dialog_input_hidden(self) -> str:
        """``"no"`` while the rename text field is shown (the spec hides it otherwise)."""
        return "no" if self.dialog == "rename" else "yes"

    @property
    def dialog_cancel_hidden(self) -> str:
        """``"no"`` while the dialog has a Cancel / No button."""
        return "no" if self.dialog_has_cancel else "yes"

    def dialog_ok_label(self) -> str:
        """Caption of the dialog's first button."""
        return "Yes" if self.dialog.startswith("confirm") else "OK"

    def dialog_cancel_label(self) -> str:
        """Caption of the dialog's second button."""
        return "No" if self.dialog.startswith("confirm") else "Cancel"

    def dialog_ok(self) -> None:
        """The first button: do what the dialog asked."""
        kind, self.dialog = self.dialog, ""
        if kind == "confirm_revert":
            self.revert()
        elif kind == "confirm_install":
            self._run("do_install")
        elif kind == "confirm_uninstall":
            self._run("do_uninstall")
        elif kind == "confirm_icon_clear":
            self._clear_icon_file()
        elif kind == "rename":
            problem = self.rename_selected(self.dialog_input)
            if problem:
                self._notice("Cannot rename", problem)

    def dialog_cancel(self) -> None:
        """The second button: leave everything as it is."""
        kind, self.dialog = self.dialog, ""
        if kind == "confirm_install":
            self.install_plan = None

    # -- background work -------------------------------------------------

    def _run(self, method: str) -> None:
        """Run the model method *method* in the background when a runner is set."""
        if self.runner is not None and self.runner(method):
            self.busy = True
            return
        getattr(self, method)()

    # -- toolbar actions -------------------------------------------------

    def ask_revert(self) -> None:
        """Revert, after the user confirms; nothing to ask when nothing changed."""
        if not self.dirty:
            self.set_status("Nothing to revert.")
            return
        self._ask(
            "confirm_revert",
            "Discard changes",
            "Discard every plugin setting changed since the last save?",
        )

    def rescan(self) -> None:
        """Walk the plugin folders again, in the background when a runner is set."""
        self._run("do_rescan")

    def do_rescan(self) -> None:
        """The work of :meth:`rescan`."""
        self.reload(rescan=True)
        self.set_status("Plugin folders rescanned.")

    def ask_install(self) -> None:
        """Ask the app for a plugin archive or folder."""
        self.request = "install"

    def choose_install_source(self, source: str) -> None:
        """Inspect *source* and ask before installing it (nothing is copied yet)."""
        from chisurf.plugins.core.plugin_manager.api import install as installer

        plan = installer.inspect_source(source)
        if not plan.ok:
            self._notice("Cannot install", "\n".join(plan.problems))
            return
        message = f"Install {plan.plugin_name!r} into {plan.destination.parent}?"
        if plan.overwrites:
            message += "\n\nThis replaces the plugin already installed there."
        if plan.warnings:
            message += "\n\n" + "\n".join(plan.warnings)
        self.install_plan = plan
        self._ask("confirm_install", "Install plugin", message)

    def do_install(self) -> None:
        """The work of the install confirmation: copy the plugin, then rescan."""
        from chisurf.plugins.core.plugin_manager.api import install as installer

        plan, self.install_plan = self.install_plan, None
        if plan is None:
            return
        try:
            destination = installer.install(plan)
        except Exception as exc:
            self._notice("Install failed", str(exc))
            return
        self.reload(rescan=True)
        self.set_status(f"Installed {plan.plugin_name!r} into {destination}.")

    def ask_uninstall(self) -> None:
        """Delete a user-installed plugin, after the user confirms."""
        row = self._selected_or_notice()
        if row is None:
            return
        dependants = row.blocking_dependants(self.settings.disabled)
        message = f"Permanently delete {row.name!r} from\n{row.package_dir}?"
        if dependants:
            message += "\n\nThese plugins require it and will stop working:\n  " + "\n  ".join(
                dependants
            )
        self._ask("confirm_uninstall", "Uninstall plugin", message)

    def do_uninstall(self) -> None:
        """The work of the uninstall confirmation; built-in plugins are refused."""
        from chisurf.plugins.core.plugin_manager.api import install as installer

        row = self.selected
        if row is None:
            return
        try:
            installer.uninstall(row.package_dir)
        except ValueError as exc:
            self._notice("Cannot uninstall", str(exc))
            return
        except Exception as exc:
            self._notice("Uninstall failed", str(exc))
            return
        self.reload(rescan=True)
        self.set_status(f"Removed {row.name!r}.")

    def move_up(self) -> None:
        """Move the selected plugin earlier in the menus."""
        self.move_selected(-1)

    def move_down(self) -> None:
        """Move the selected plugin later in the menus."""
        self.move_selected(+1)

    def ask_rename(self) -> None:
        """Ask for the new menu name of the selected plugin."""
        row = self._selected_or_notice()
        if row is None:
            return
        self.dialog_input = row.name
        self._ask("rename", "Rename plugin", "Enter the new name this plugin shows in the menus.")

    def open_folder(self) -> None:
        """Open the selected plugin's directory in the file browser."""
        row = self._selected_or_notice()
        if row is None:
            return
        self.opener(str(row.package_dir))

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
        return list(self.plugin_rows()), list(TABLE_COLUMNS)

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
            self.set_status(f"Could not write {path}: {exc}")
            return False
        self.set_status(f"Exported {len(self.displayed()[0])} rows to {target}.")
        return True

    # -- the icon panel --------------------------------------------------

    @property
    def icon_file(self) -> pathlib.Path | None:
        """Where the selected plugin's icon file lives."""
        row = self.selected
        return None if row is None else pathlib.Path(row.package_dir) / "icon.png"

    def ask_icon(self) -> None:
        """Open the icon panel for the selected plugin."""
        row = self._selected_or_notice()
        if row is None:
            return
        from chisurf.core.settings import ai_settings

        providers = [key for key, *_rest in ai_settings.PROVIDERS.values()]
        self.icon_provider = providers[0] if providers else ""
        self._provider_defaults()
        self.icon_status = ""
        self.icon_changed = False
        self.icon_path_text = str(self.icon_file) if self.icon_file.is_file() else ""
        self.icon_open = True

    def icon_provider_labels(self) -> list[str]:
        """Display names of the image providers (AI Settings' list)."""
        from chisurf.core.settings import ai_settings

        return list(ai_settings.PROVIDERS)

    @property
    def icon_provider_label(self) -> str:
        """The chosen provider as its display name."""
        from chisurf.core.settings import ai_settings

        for display, (key, *_rest) in ai_settings.PROVIDERS.items():
            if key == self.icon_provider:
                return display
        return ""

    @icon_provider_label.setter
    def icon_provider_label(self, label: str) -> None:
        from chisurf.core.settings import ai_settings

        if label in ai_settings.PROVIDERS:
            self.icon_provider = ai_settings.PROVIDERS[label][0]
            self._provider_defaults()

    def _provider_defaults(self) -> None:
        from chisurf.plugins.core.plugin_manager.api import icons as icon_api

        self.icon_endpoint, self.icon_model = icon_api.default_icon_generation_values(
            self.icon_provider
        )

    def icon_choose(self) -> None:
        """Ask the app for an image file."""
        self.request = "icon_file"

    def _set_manifest_icon(self, value: str | None) -> None:
        """Point the manifest's ``icon`` at *value*, or drop the key."""
        row = self.selected
        if row is None:
            return
        manifest_path = pathlib.Path(row.package_dir) / "manifest.json"
        if not manifest_path.is_file():
            return
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if value is None:
            data.pop("icon", None)
        else:
            data["icon"] = value
        manifest_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    def _write_image(self, image: Any) -> None:
        """Save a PIL *image* as the plugin's icon (square canvas) and record it."""
        from PIL import Image

        scaled = image.convert("RGBA")
        scale = min(ICON_SIZE / scaled.width, ICON_SIZE / scaled.height)
        scaled = scaled.resize(
            (max(1, round(scaled.width * scale)), max(1, round(scaled.height * scale))),
            Image.Resampling.LANCZOS,
        )
        canvas = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
        canvas.alpha_composite(
            scaled, ((ICON_SIZE - scaled.width) // 2, (ICON_SIZE - scaled.height) // 2)
        )
        canvas.save(self.icon_file, format="PNG")
        self._set_manifest_icon("icon.png")
        self.icon_changed = True
        self.icon_path_text = str(self.icon_file)

    def icon_use(self) -> None:
        """Write the chosen image as the plugin's icon (a PNG is copied as is)."""
        source = pathlib.Path(self.icon_path_text.strip())
        if not source.is_file():
            self._notice("No image", "Choose an image file first.")
            return
        if self.icon_file.exists() and source.resolve() == self.icon_file.resolve():
            return
        if source.suffix.lower() == ".png":
            shutil.copyfile(source, self.icon_file)
            self._set_manifest_icon("icon.png")
            self.icon_changed = True
            return
        from PIL import Image

        try:
            with Image.open(source) as image:
                image.load()
                self._write_image(image)
        except Exception:
            self._notice("Unreadable image", f"Could not read {source.name}.")

    def icon_generate(self) -> None:
        """Ask the configured provider for an icon, in the background."""
        from chisurf.plugins.core.plugin_manager.api import icons as icon_api

        config = icon_api.IconConfig(
            self.icon_provider, self.icon_endpoint.strip(), self.icon_model.strip()
        )
        if not config.base_url or not config.model:
            self._notice("Not configured", "Set an endpoint and an image model before generating.")
            return
        self.icon_status = "Generating…"
        self._run("do_generate_icon")

    def do_generate_icon(self) -> None:
        """The work of :meth:`icon_generate`: request, decode and write the icon."""
        import io as _io

        from PIL import Image

        from chisurf.plugins.core.plugin_manager.api import icons as icon_api

        row = self.selected
        if row is None:
            return
        config = icon_api.IconConfig(
            self.icon_provider, self.icon_endpoint.strip(), self.icon_model.strip()
        )
        try:
            payload = icon_api.request_icon_bytes(
                config, {"name": row.name, "doc": row.description}
            )
        except Exception as exc:
            self.icon_status = f"Generation failed: {exc}"
            return
        try:
            with Image.open(_io.BytesIO(payload)) as image:
                image.load()
                self._write_image(image)
        except Exception:
            self.icon_status = "The provider returned something that is not an image."
            return
        self.icon_status = "Icon generated."

    def icon_edit(self) -> None:
        """Open the icon in the system image editor."""
        if self.icon_file is None or not self.icon_file.is_file():
            self._notice("No icon", "This plugin has no icon file to edit.")
            return
        self.opener(str(self.icon_file))

    def icon_clear(self) -> None:
        """Remove the icon file, after the user confirms."""
        if self.icon_file is None:
            return
        if not self.icon_file.is_file():
            self._set_manifest_icon(None)
            return
        self._ask("confirm_icon_clear", "Clear icon", f"Delete {self.icon_file}?")

    def _clear_icon_file(self) -> None:
        self.icon_file.unlink()
        self._set_manifest_icon(None)
        self.icon_changed = True
        self.icon_path_text = ""

    def icon_close(self) -> None:
        """Close the panel; a changed icon rescans the plugins and says so."""
        row = self.selected
        self.icon_open = False
        if self.icon_changed and row is not None:
            self.reload(rescan=True)
            self.set_status(f"Icon updated for {row.name!r}.")
        self.icon_changed = False

    @property
    def icon_title(self) -> str:
        """Title of the icon panel."""
        row = self.selected
        return f"Icon — {row.name}" if row is not None else "Icon"
