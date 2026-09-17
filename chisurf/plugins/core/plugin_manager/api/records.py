"""One row per plugin, assembled from discovery, settings and the dependency graph.

Discovery already hands over nineteen fields per plugin. The old manager read
five of them and re-derived two more by importing the module and re-parsing its
``__init__.py`` -- which is why opening the manager imported every plugin in the
tree. Everything here comes from the discovery record, so building the table
costs a dict lookup per plugin and imports nothing.

The dependency columns are the point: a plugin's ``requires`` says what must
load before it, and the *reverse* index says who breaks if you disable it. The
manager could previously offer to disable a plugin that seven others import,
with nothing to warn you.
"""

from __future__ import annotations

import ast
import pathlib
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any


def read_module_docstring(package_path: str | pathlib.Path) -> str:
    """The docstring of a package's ``__init__.py``, without importing it.

    Kept as public API because the package has always exported it. The manager
    itself no longer calls it -- the description arrives on the discovery
    record, so building the table imports nothing.
    """
    init_py = pathlib.Path(package_path) / "__init__.py"
    try:
        tree = ast.parse(init_py.read_bytes(), filename=str(init_py))
    except (OSError, SyntaxError, ValueError):
        return ""
    return ast.get_docstring(tree) or ""


#: Health verdicts, worst first. ``order`` sorts by these.
HEALTH_ORDER = ("broken", "deprecated", "experimental", "disabled", "ok")


@dataclass
class PluginRow:
    """Everything the manager shows about one plugin.

    Kept flat and JSON-ish because it is fed straight to a table as a record.
    """

    plugin_id: str
    name: str
    version: str
    category: str
    source: str
    module_path: str
    package_dir: str
    description: str
    #: ``{plugin_id: specifier}`` -- must load first.
    requires: dict[str, str] = field(default_factory=dict)
    #: ``{plugin_id: specifier}`` -- reached after boot.
    optional_requires: dict[str, str] = field(default_factory=dict)
    #: Plugin ids that declare this one in ``requires``.
    required_by: list[str] = field(default_factory=list)
    #: Plugin ids that declare this one in ``optional_requires``.
    optional_for: list[str] = field(default_factory=list)
    disabled: bool = False
    in_toolbar: bool = False
    menu_hidden: bool = False
    cli_only: bool = False
    library: bool = False
    demo: bool = False
    experimental: bool = False
    deprecated: bool = False
    statefulness: str = "plugin default"
    #: One of :data:`HEALTH_ORDER`.
    health: str = "ok"
    #: Why the health is not ``ok`` -- shown in the details pane.
    health_note: str = ""

    def as_record(self) -> dict[str, Any]:
        """The row as a flat table record.

        Dependency maps become comma-joined id lists, because a table cell shows
        text and the specifier is almost always ``*``; the details pane shows the
        bounds.
        """
        return {
            "name": self.name,
            "id": self.plugin_id,
            "version": self.version,
            "category": self.category,
            "status": self.status_text(),
            "requires": ", ".join(sorted(self.requires)),
            "required_by": ", ".join(sorted(self.required_by)),
            "optional": ", ".join(sorted(self.optional_requires)),
            "source": self.source,
            "toolbar": "yes" if self.in_toolbar else "",
            "state": self.statefulness,
        }

    def status_text(self) -> str:
        """A single word for the status column."""
        if self.disabled:
            return "disabled"
        if self.health != "ok":
            return self.health
        if self.library:
            return "library"
        if self.cli_only:
            return "cli only"
        return "enabled"

    def blocking_dependants(self, disabled: Iterable[str]) -> list[str]:
        """Enabled plugins that hard-require this one.

        Disabling this plugin breaks exactly these. Returned so the manager can
        say so *before* the checkbox is ticked rather than after a restart.
        """
        off = set(disabled)
        return sorted(p for p in self.required_by if p not in off)


def _category_of(display_name: str) -> str:
    """The top-level menu segment of a ``A:B:C`` display name."""
    parts = [p.strip() for p in str(display_name or "").split(":") if p.strip()]
    return parts[0] if len(parts) > 1 else ""


def _clean_name(display_name: str) -> str:
    """The leaf of a ``A:B:C`` display name."""
    text = str(display_name or "")
    return text.split(":")[-1].strip() or text


def health_of(record: dict[str, Any], disabled: bool) -> tuple[str, str]:
    """Classify one plugin's health.

    Parameters
    ----------
    record : dict
        A discovery record from :func:`chisurf.plugins.iter_plugins`.
    disabled : bool
        Whether the user has switched this plugin off.

    Returns
    -------
    tuple of (str, str)
        The verdict (one of :data:`HEALTH_ORDER`) and a sentence explaining it,
        empty when healthy.

    """
    if record.get("deprecated"):
        return "deprecated", str(record.get("deprecation_message") or "This tool is deprecated.")
    if record.get("experimental"):
        return "experimental", str(
            record.get("experimental_message") or "This tool is experimental and not yet validated."
        )
    if disabled:
        return "disabled", "Switched off in the plugin manager."
    return "ok", ""


def collect_rows(
    records: Iterable[dict[str, Any]],
    *,
    disabled: Iterable[str] = (),
    toolbar: Iterable[str] = (),
    statefulness: dict[str, Any] | None = None,
) -> list[PluginRow]:
    """Build one :class:`PluginRow` per discovery record.

    Parameters
    ----------
    records : iterable of dict
        Discovery records from :func:`chisurf.plugins.iter_plugins`.
    disabled, toolbar : iterable of str
        The ``plugins.disabled_plugins`` / ``plugins.toolbar_plugins`` lists.
        Matched against the plugin id **and** the display name, because those
        settings have historically been keyed by display name and renaming a
        plugin used to orphan the entry.
    statefulness : dict, optional
        The ``plugins.statefulness`` settings block.

    Returns
    -------
    list of PluginRow
        In discovery order (which is dependency order).

    """
    disabled_set = {str(x) for x in disabled}
    toolbar_set = {str(x) for x in toolbar}
    rows: list[PluginRow] = []

    for record in records:
        plugin_id = str(record.get("manifest_id") or "")
        display = str(record.get("plugin_name") or plugin_id)
        name = _clean_name(display)
        # Historic settings are keyed by display name; new ones by id. Accept
        # either so a rename does not silently lose the setting.
        keys = {plugin_id, display, name} - {""}
        is_disabled = bool(keys & disabled_set)
        verdict, note = health_of(record, is_disabled)

        rows.append(
            PluginRow(
                plugin_id=plugin_id or name,
                name=name,
                version=str(record.get("manifest_version") or ""),
                category=_category_of(display),
                source=str(record.get("source") or ""),
                module_path=str(record.get("module_path") or ""),
                package_dir=str(record.get("package_dir") or ""),
                description=str(record.get("description") or ""),
                requires=dict(record.get("requires") or {}),
                optional_requires=dict(record.get("optional_requires") or {}),
                disabled=is_disabled,
                in_toolbar=bool(keys & toolbar_set),
                menu_hidden=bool(record.get("menu_hidden")),
                cli_only=bool(record.get("cli_only")),
                library=bool(record.get("library")),
                demo=bool(record.get("demo")),
                experimental=bool(record.get("experimental")),
                deprecated=bool(record.get("deprecated")),
                statefulness=_statefulness_summary(plugin_id, name, statefulness),
                health=verdict,
                health_note=note,
            )
        )

    _fill_reverse_dependencies(rows)
    return rows


def _fill_reverse_dependencies(rows: list[PluginRow]) -> None:
    """Populate ``required_by`` / ``optional_for`` from the forward maps."""
    by_id = {row.plugin_id: row for row in rows}
    for row in rows:
        for target in row.requires:
            other = by_id.get(target)
            if other is not None:
                other.required_by.append(row.plugin_id)
        for target in row.optional_requires:
            other = by_id.get(target)
            if other is not None:
                other.optional_for.append(row.plugin_id)
    for row in rows:
        row.required_by.sort()
        row.optional_for.sort()


def dependants_of(rows: Iterable[PluginRow], plugin_id: str) -> list[str]:
    """Ids that hard-require *plugin_id*."""
    for row in rows:
        if row.plugin_id == plugin_id:
            return list(row.required_by)
    return []


def _statefulness_summary(plugin_id: str, name: str, settings: dict[str, Any] | None) -> str:
    """How window state is handled for one plugin.

    The old summary reported ``"plugin default"`` whenever there was no
    per-plugin override, ignoring the global mode entirely -- so with "Disable
    all" selected every row still claimed "plugin default", contradicting what
    :func:`chisurf.core.plugin.registry.resolve_plugin_statefulness` actually
    does. This mirrors that function's precedence: override, then mode, then the
    manifest default.
    """
    settings = settings or {}
    overrides = settings.get("per_plugin") or {}
    for key in (plugin_id, name):
        if key and key in overrides:
            value = overrides[key]
            if isinstance(value, str) and value.lower() == "plugin_default":
                break
            return "stateful" if value else "stateless"

    mode = str(settings.get("mode", "plugin_default")).lower()
    if mode in {"enabled", "force_enabled", "true"}:
        return "stateful (all)"
    if mode in {"disabled", "force_disabled", "false"}:
        return "stateless (all)"
    return "plugin default"
