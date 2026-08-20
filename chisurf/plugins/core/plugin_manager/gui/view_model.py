"""Qt-free view model behind the plugin manager.

Everything the panel shows and every edit it makes lives here; ``tool.py`` only
builds a toolbar and hands this object to :class:`~chisurf.gui.autoform.AutoForm`.
That split is what makes the manager testable headlessly -- the old widget put
the data model, the settings writer, the installer and an HTTP client inside Qt
callbacks, so none of it could be exercised without a display.
"""

from __future__ import annotations

import pathlib
from typing import Any

from chisurf.plugins.core.plugin_manager.api.records import PluginRow, collect_rows
from chisurf.plugins.core.plugin_manager.api.settings_io import PluginSettings

_VIEW_JSON = pathlib.Path(__file__).parent / "plugins.view.json"

#: Per-plugin window-state override, as (label, value). ``None`` clears the
#: override and lets the manifest and the global mode decide.
SELECTED_STATEFULNESS = (
    ("Plugin default", None),
    ("Remember", True),
    ("Do not remember", False),
)

#: Global window-state modes, as (label, settings value).
STATEFULNESS_MODES = (
    ("Plugin default", "plugin_default"),
    ("Remember for all", "enabled"),
    ("Remember for none", "disabled"),
)


class PluginManagerViewModel:
    """State and behaviour of the plugin manager panel."""

    def __init__(self, settings_block: dict[str, Any] | None = None) -> None:
        self._view_json = _VIEW_JSON
        self._observers: list[Any] = []

        if settings_block is None:
            try:
                import chisurf as cs

                settings_block = cs.core.settings.cs_settings.setdefault("plugins", {})
            except Exception:
                settings_block = {}
        self._settings_block = settings_block
        self.settings = PluginSettings(settings_block)

        self._rows: list[PluginRow] = []
        self._selected_id: str = ""
        self._status: str = ""
        self.show_disabled: bool = not self.settings.hide_disabled
        self.reload()

    # -- observer plumbing ----------------------------------------------

    def add_observer(self, callback) -> None:
        """Register a callback invoked with an event name after every change."""
        self._observers.append(callback)

    def notify(self, event: str = "changed") -> None:
        """Tell observers something changed."""
        for callback in list(self._observers):
            try:
                callback(event)
            except Exception:  # pragma: no cover - an observer must not break the model
                pass

    def view_spec(self):
        """The parsed view specification for this panel."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(self._view_json)

    # -- discovery -------------------------------------------------------

    def reload(self, *, rescan: bool = False) -> None:
        """Rebuild the plugin rows.

        Parameters
        ----------
        rescan : bool, optional
            Drop the discovery cache and walk the tree again. The default reuses
            the cache, because opening the manager should not cost a full
            re-scan -- the old one did, on every reorder click.

        """
        import chisurf.plugins as plugins

        if rescan:
            plugins.invalidate_plugin_cache()
        try:
            records = list(plugins.iter_plugins())
        except Exception as exc:  # pragma: no cover - discovery is defensive already
            records = []
            self._status = f"Plugin discovery failed: {exc}"
        self._rows = collect_rows(
            records,
            disabled=self.settings.disabled,
            toolbar=self.settings.toolbar,
            statefulness=self.settings.statefulness,
        )
        if self._selected_id and not any(r.plugin_id == self._selected_id for r in self._rows):
            self._selected_id = ""
        self.notify("reloaded")

    @property
    def rows(self) -> list[PluginRow]:
        """Every discovered plugin."""
        return list(self._rows)

    def visible_rows(self) -> list[PluginRow]:
        """Rows after the show/hide-disabled filter.

        Sorting and searching are the table's job -- it does both natively, which
        is why the old hand-rolled filter box is gone.
        """
        if self.show_disabled:
            return list(self._rows)
        return [row for row in self._rows if not row.disabled]

    def plugin_rows(self) -> list[dict[str, Any]]:
        """The table source: one flat record per visible plugin."""
        return [row.as_record() for row in self.visible_rows()]

    # -- selection -------------------------------------------------------

    def select_row(self, record: Any) -> None:
        """Called by the table when the selection moves."""
        if isinstance(record, dict):
            self._selected_id = str(record.get("id") or "")
        elif isinstance(record, int) and 0 <= record < len(self.visible_rows()):
            self._selected_id = self.visible_rows()[record].plugin_id
        else:
            self._selected_id = ""
        self.notify("selected")

    @property
    def selected(self) -> PluginRow | None:
        """The selected plugin, or ``None``."""
        for row in self._rows:
            if row.plugin_id == self._selected_id:
                return row
        return None

    def _row(self, plugin_id: str) -> PluginRow | None:
        for row in self._rows:
            if row.plugin_id == plugin_id:
                return row
        return None

    # -- what the details pane shows -------------------------------------

    def details_text(self) -> str:
        """A markdown summary of the selected plugin."""
        row = self.selected
        if row is None:
            return (
                "### No plugin selected\n\n"
                "Pick a row to see what it is, what it depends on, and what "
                "depends on it."
            )
        lines = [f"### {row.name}", ""]
        if row.description:
            lines += [row.description.strip(), ""]

        facts = [
            ("Id", f"`{row.plugin_id}`"),
            ("Version", row.version or "—"),
            ("Category", row.category or "—"),
            ("Source", row.source or "—"),
            ("Status", row.status_text()),
            ("Window state", row.statefulness),
            ("Module", f"`{row.module_path}`"),
            ("Folder", f"`{row.package_dir}`"),
        ]
        lines += [f"- **{label}:** {value}" for label, value in facts]

        if row.health_note:
            lines += ["", f"> **{row.health.title()}** — {row.health_note}"]

        if row.requires:
            lines += ["", "**Requires (loaded first)**"]
            lines += [
                f"- `{dep}` {spec}" if spec != "*" else f"- `{dep}`"
                for dep, spec in sorted(row.requires.items())
            ]
        if row.optional_requires:
            lines += ["", "**Optionally uses**"]
            lines += [
                f"- `{dep}` {spec}" if spec != "*" else f"- `{dep}`"
                for dep, spec in sorted(row.optional_requires.items())
            ]
        if row.required_by:
            lines += ["", "**Required by** (these break if it is switched off)"]
            lines += [f"- `{dep}`" for dep in row.required_by]
        if row.optional_for:
            lines += ["", "**Optionally used by**"]
            lines += [f"- `{dep}`" for dep in row.optional_for]
        if not (row.requires or row.optional_requires or row.required_by or row.optional_for):
            lines += ["", "_Stands alone: nothing depends on it and it depends on nothing._"]
        return "\n".join(lines)

    def dependency_rows(self) -> list[dict[str, Any]]:
        """The selected plugin's dependency edges, as table records."""
        row = self.selected
        if row is None:
            return []
        out: list[dict[str, Any]] = []
        for dep, spec in sorted(row.requires.items()):
            out.append(self._edge(dep, spec, "requires"))
        for dep, spec in sorted(row.optional_requires.items()):
            out.append(self._edge(dep, spec, "optional"))
        for dep in row.required_by:
            out.append(self._edge(dep, "", "required by"))
        for dep in row.optional_for:
            out.append(self._edge(dep, "", "optional for"))
        return out

    def _edge(self, plugin_id: str, specifier: str, relation: str) -> dict[str, Any]:
        """One dependency row, annotated with the target's real state."""
        other = self._row(plugin_id)
        return {
            "plugin": plugin_id,
            "relation": relation,
            "bound": specifier if specifier and specifier != "*" else "any",
            "installed": "—" if other is None else (other.version or "yes"),
            "status": "missing" if other is None else other.status_text(),
        }

    def status_text(self) -> str:
        """The status line under the table."""
        if self._status:
            return self._status
        total = len(self._rows)
        disabled = sum(1 for r in self._rows if r.disabled)
        problems = [r for r in self._rows if r.health in ("broken", "deprecated")]
        parts = [f"{total} plugins", f"{disabled} disabled"]
        if problems:
            parts.append(f"{len(problems)} needing attention")
        if self.settings.dirty:
            parts.append("unsaved changes")
        return " · ".join(parts)

    def set_status(self, text: str) -> None:
        """Show *text* in the status line until the next reload."""
        self._status = text
        self.notify("status")

    # -- edits -----------------------------------------------------------

    def _aliases(self, row: PluginRow) -> set[str]:
        """Every key an older settings file might have used for this plugin."""
        display = row.name
        return {row.plugin_id, display} - {""}

    @property
    def selected_disabled(self) -> bool:
        """Whether the selected plugin is switched off."""
        row = self.selected
        return bool(row and row.disabled)

    @selected_disabled.setter
    def selected_disabled(self, value: bool) -> None:
        self.set_disabled(bool(value))

    def set_disabled(self, disabled: bool) -> list[str]:
        """Switch the selected plugin off or on.

        Returns
        -------
        list of str
            Enabled plugins that hard-require this one and would break. The
            caller warns with these; the change is applied either way, because
            refusing outright would make a broken graph unfixable.

        """
        row = self.selected
        if row is None:
            return []
        self.settings.set_disabled(row.plugin_id, disabled, aliases=self._aliases(row))
        blocking = row.blocking_dependants(self.settings.disabled) if disabled else []
        self.reload()
        return blocking

    @property
    def selected_in_toolbar(self) -> bool:
        """Whether the selected plugin is pinned to the main toolbar."""
        row = self.selected
        return bool(row and row.in_toolbar)

    @selected_in_toolbar.setter
    def selected_in_toolbar(self, value: bool) -> None:
        row = self.selected
        if row is None:
            return
        self.settings.set_toolbar(row.plugin_id, bool(value), aliases=self._aliases(row))
        self.reload()

    def statefulness_mode_labels(self) -> list[str]:
        """Labels for the global window-state mode choice."""
        return [label for label, _ in STATEFULNESS_MODES]

    @property
    def statefulness_mode(self) -> str:
        """The global window-state mode, as its label."""
        current = str(self.settings.statefulness.get("mode", "plugin_default")).lower()
        for label, value in STATEFULNESS_MODES:
            if value == current:
                return label
        return STATEFULNESS_MODES[0][0]

    @statefulness_mode.setter
    def statefulness_mode(self, label: str) -> None:
        for text, value in STATEFULNESS_MODES:
            if text == label:
                self.settings.set_statefulness_mode(value)
                break
        self.reload()

    def set_statefulness_override(self, value: bool | None) -> None:
        """Force window-state persistence for the selected plugin."""
        row = self.selected
        if row is None:
            return
        self.settings.set_statefulness_override(row.plugin_id, value)
        self.reload()

    def selected_statefulness_labels(self) -> list[str]:
        """Options for the selected plugin's window-state override."""
        return [label for label, _ in SELECTED_STATEFULNESS]

    @property
    def selected_statefulness(self) -> str:
        """The selected plugin's window-state override, as a label."""
        row = self.selected
        if row is None:
            return SELECTED_STATEFULNESS[0][0]
        overrides = self.settings.statefulness.get("per_plugin") or {}
        for key in (row.plugin_id, row.name):
            if key and key in overrides:
                value = overrides[key]
                if isinstance(value, str) and value.lower() == "plugin_default":
                    break
                return SELECTED_STATEFULNESS[1][0] if value else SELECTED_STATEFULNESS[2][0]
        return SELECTED_STATEFULNESS[0][0]

    @selected_statefulness.setter
    def selected_statefulness(self, label: str) -> None:
        for text, value in SELECTED_STATEFULNESS:
            if text == label:
                self.set_statefulness_override(value)
                return

    def rename_selected(self, new_name: str) -> str:
        """Rename the selected plugin's menu entry.

        The old implementation ran an unanchored ``re.sub`` over the package's
        ``__init__.py``, which also matched ``display_name = "..."`` and
        ``plugin_name = "..."`` and rewrote every one of them -- turning
        ``display_name = "X"`` into ``display_`` + ``name = "New"``. It also
        never touched ``manifest.json``, which is the field discovery actually
        reads, so for any plugin with a manifest it was a no-op that still
        damaged the source.

        This edits the manifest's ``display_name`` -- the authoritative field --
        and leaves the source alone. The menu path is preserved: renaming
        ``Tools:Alpha`` to ``Beta`` yields ``Tools:Beta``.

        Returns
        -------
        str
            An error message, or ``""`` on success.

        """
        import json

        row = self.selected
        if row is None:
            return "No plugin selected."
        new_name = new_name.strip()
        if not new_name:
            return "The name cannot be empty."
        if ":" in new_name:
            return "Use the leaf name only; the menu path is kept."

        manifest_path = pathlib.Path(row.package_dir) / "manifest.json"
        if not manifest_path.is_file():
            return (
                "This plugin has no manifest.json, so there is no name to edit. "
                "Give it a manifest first."
            )
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return f"manifest.json is not readable: {exc}"

        segments = [p for p in str(data.get("display_name") or "").split(":") if p]
        segments = segments[:-1] + [new_name] if segments else [new_name]
        data["display_name"] = ":".join(segments)
        try:
            manifest_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
        except OSError as exc:
            return f"Could not write manifest.json: {exc}"

        self.reload(rescan=True)
        self.set_status(f"Renamed to {data['display_name']!r}.")
        return ""

    def move_selected(self, delta: int) -> None:
        """Move the selected plugin up (-1) or down (+1) in menu order."""
        row = self.selected
        if row is None:
            return
        keys = [r.plugin_id for r in self.visible_rows()]
        self.settings.move(row.plugin_id, keys, delta)
        self.reload()

    # -- persistence -----------------------------------------------------

    @property
    def dirty(self) -> bool:
        """Whether there are unsaved changes."""
        return self.settings.dirty

    def save(self) -> None:
        """Write the settings to the user's settings file.

        This used to call a ``cs.core.settings.write_settings()`` that does not
        exist anywhere in the tree, inside a bare ``except: pass`` -- so the
        panel reported "saved" and nothing ever reached disk.
        """
        self.settings.apply(self._settings_block)
        from chisurf.core.settings.settings_utils import update_settings_section

        written = update_settings_section("plugins", dict(self._settings_block))
        self._refresh_host_toolbar()
        if written:
            self.set_status("Settings saved. Menu changes appear after a restart.")
        else:
            self.set_status("Could not write the settings file -- see the log for why.")

    def revert(self) -> None:
        """Discard unsaved changes."""
        self.settings.revert()
        self.reload()
        self.set_status("Unsaved changes discarded.")

    @staticmethod
    def _refresh_host_toolbar() -> None:
        """Rebuild the main window's plugin toolbar, if one is up."""
        try:
            from qtpy import QtWidgets

            for widget in QtWidgets.QApplication.topLevelWidgets():
                loader = getattr(widget, "load_toolbar_plugins", None)
                if callable(loader):
                    toolbar = getattr(widget, "plugins_toolbar", None)
                    if toolbar is not None:
                        toolbar.clear()
                    loader()
        except Exception:
            pass
