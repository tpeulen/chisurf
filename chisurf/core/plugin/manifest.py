from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field
from typing import Any

from chisurf.core.i18n import tr


@dataclass
class RPCMethodSpec:
    """Describes a single RPC method exposed by a plugin.

    ``summary`` is the one-line label; ``description`` is the longer help text
    UIs surface inline (AutoForm maps it to the form's tooltip). Per-parameter
    help uses standard JSON-Schema ``description`` keys inside
    ``params_schema["properties"]`` — those become the per-field tooltips.
    """

    name: str
    summary: str = ""
    description: str = ""
    params_schema: dict[str, Any] | None = None
    result_schema: dict[str, Any] | None = None
    long_running: bool = False
    cancelable: bool = False
    events: list[str] = field(default_factory=list)


@dataclass
class PluginEntrypoints:
    """Plugin entrypoint strings."""

    gui: str | None = None
    cli: str | None = None
    services: str | None = None


@dataclass
class PluginWindowState:
    """Window-state persistence settings for a plugin."""

    enabled: bool = True
    settings_key: str | None = None


@dataclass
class PluginStatefulness:
    """State persistence settings for a plugin."""

    enabled: bool = False
    window: PluginWindowState = field(default_factory=PluginWindowState)


@dataclass
class PluginManifest:
    """Plugin metadata and contract definition.

    All fields are JSON-serializable. The manifest is loaded from
    ``manifest.json`` in the plugin root directory.
    """

    id: str
    version: str
    display_name: str = ""
    description: str = ""
    authors: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    icon: str | None = None

    state_namespace: str | None = None
    state_schema: dict[str, Any] | None = None
    statefulness: PluginStatefulness = field(default_factory=PluginStatefulness)

    entrypoints: PluginEntrypoints = field(default_factory=PluginEntrypoints)
    rpc_methods: list[RPCMethodSpec] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)

    dependencies: dict[str, str] = field(default_factory=dict)

    #: Mark a tool as experimental / not yet validated. Hosts (e.g. the meta-tool shell)
    #: surface this with a warning banner and a flagged navigation entry.
    experimental: bool = False
    experimental_message: str = ""

    #: Keep the tool out of the generated menus (registry.py builds menu entries
    #: only for manifests that do not set this).
    menu_hidden: bool = False

    #: Declared maturity flag from the plugin spec's "honest metadata" rule. Parsed
    #: and round-tripped, but no host surfaces it yet (unlike ``experimental``).
    deprecated: bool = False
    deprecation_message: str = ""

    @staticmethod
    def _parse_statefulness(data: dict[str, Any]) -> PluginStatefulness:
        """Parse plugin statefulness settings from manifest data."""
        raw = data.get("statefulness", {})
        if isinstance(raw, bool):
            return PluginStatefulness(enabled=raw)
        if not isinstance(raw, dict):
            return PluginStatefulness()

        window = PluginWindowState()
        window_data = raw.get("window", {})
        if isinstance(window_data, bool):
            window.enabled = window_data
        elif isinstance(window_data, dict):
            window.enabled = window_data.get("enabled", True)
            window.settings_key = window_data.get("settings_key")

        return PluginStatefulness(
            enabled=raw.get("enabled", False),
            window=window,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PluginManifest:
        """Build a manifest from parsed ``manifest.json`` data.

        Undeclared keys are ignored here; :func:`validate_manifest` reports them.

        Parameters
        ----------
        data : dict
            Parsed manifest JSON data. ``id`` and ``version`` are required.

        Returns
        -------
        PluginManifest
            The parsed manifest, with translatable text passed through ``tr()``.

        """
        entrypoints_data = data.get("entrypoints", {})
        entrypoints = PluginEntrypoints(
            gui=entrypoints_data.get("gui"),
            cli=entrypoints_data.get("cli"),
            services=entrypoints_data.get("services"),
        )

        methods = [
            RPCMethodSpec(
                name=m["name"],
                summary=tr(m.get("summary", "")),
                description=tr(m.get("description", "")),
                params_schema=m.get("params_schema"),
                result_schema=m.get("result_schema"),
                long_running=m.get("long_running", False),
                cancelable=m.get("cancelable", False),
                events=m.get("events", []),
            )
            for m in data.get("rpc_methods", [])
        ]

        return cls(
            id=data["id"],
            version=data["version"],
            # display_name and categories double as menu-path / identity keys
            # (see registry.py), so they stay canonical and are localized at the
            # navigation-render seam, not here.
            display_name=data.get("display_name", ""),
            description=tr(data.get("description", "")),
            authors=data.get("authors", []),
            categories=data.get("categories", []),
            icon=data.get("icon"),
            state_namespace=data.get("state_namespace"),
            state_schema=data.get("state_schema"),
            statefulness=cls._parse_statefulness(data),
            entrypoints=entrypoints,
            rpc_methods=methods,
            events=data.get("events", []),
            dependencies=data.get("dependencies", {}),
            experimental=data.get("experimental", False),
            experimental_message=tr(data.get("experimental_message", "")),
            menu_hidden=data.get("menu_hidden", False),
            deprecated=data.get("deprecated", False),
            deprecation_message=tr(data.get("deprecation_message", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the manifest back to plain JSON-compatible data.

        Returns
        -------
        dict
            One key per declared manifest field, so the result round-trips
            through :meth:`from_dict`.

        """
        return {
            "id": self.id,
            "version": self.version,
            "display_name": self.display_name,
            "description": self.description,
            "authors": list(self.authors),
            "categories": list(self.categories),
            "icon": self.icon,
            "state_namespace": self.state_namespace,
            "state_schema": self.state_schema,
            "statefulness": {
                "enabled": self.statefulness.enabled,
                "window": {
                    "enabled": self.statefulness.window.enabled,
                    "settings_key": self.statefulness.window.settings_key,
                },
            },
            "entrypoints": {
                "gui": self.entrypoints.gui,
                "cli": self.entrypoints.cli,
                "services": self.entrypoints.services,
            },
            "rpc_methods": [
                {
                    "name": m.name,
                    "summary": m.summary,
                    "description": m.description,
                    "params_schema": m.params_schema,
                    "result_schema": m.result_schema,
                    "long_running": m.long_running,
                    "cancelable": m.cancelable,
                    "events": list(m.events),
                }
                for m in self.rpc_methods
            ],
            "events": list(self.events),
            "dependencies": dict(self.dependencies),
            "experimental": self.experimental,
            "experimental_message": self.experimental_message,
            "menu_hidden": self.menu_hidden,
            "deprecated": self.deprecated,
            "deprecation_message": self.deprecation_message,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize the manifest to a ``manifest.json`` string.

        Parameters
        ----------
        indent : int, optional
            JSON indentation width, by default 2.

        Returns
        -------
        str
            The serialized manifest.

        """
        return json.dumps(self.to_dict(), indent=indent)


def load_manifest(path: pathlib.Path | str) -> PluginManifest | None:
    """Load and parse a ``manifest.json`` from *path*.

    Parameters
    ----------
    path : pathlib.Path or str
        Path to ``manifest.json``.

    Returns
    -------
    PluginManifest or None
        The parsed manifest, or ``None`` if the file does not exist or
        cannot be parsed.

    """
    path = pathlib.Path(path)
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        return PluginManifest.from_dict(data)
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


# Minimal JSON Schema draft-07 for validation. ``properties`` is the **closed**
# set of manifest keys: ``_validate_known_keys`` rejects anything else, and a
# guardrail test pins it against the ``PluginManifest`` fields, so a key cannot
# be declared without a parser or parsed without being declared.
_MANIFEST_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["id", "version"],
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "version": {"type": "string", "minLength": 1},
        "display_name": {"type": "string"},
        "description": {"type": "string"},
        "authors": {"type": "array", "items": {"type": "string"}},
        "categories": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "uniqueItems": True,
        },
        "icon": {"type": "string"},
        "state_namespace": {"type": "string"},
        "state_schema": {"type": "object"},
        "statefulness": {
            "oneOf": [
                {"type": "boolean"},
                {
                    "type": "object",
                    "properties": {
                        "enabled": {"type": "boolean"},
                        "window": {
                            "oneOf": [
                                {"type": "boolean"},
                                {
                                    "type": "object",
                                    "properties": {
                                        "enabled": {"type": "boolean"},
                                        "settings_key": {
                                            "type": ["string", "null"],
                                        },
                                    },
                                },
                            ]
                        },
                    },
                },
            ]
        },
        "entrypoints": {
            "type": "object",
            "properties": {
                "gui": {"type": "string"},
                "cli": {"type": "string"},
                "services": {"type": "string"},
            },
        },
        "rpc_methods": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "summary": {"type": "string"},
                    "description": {"type": "string"},
                    "params_schema": {"type": "object"},
                    "result_schema": {"type": "object"},
                    "long_running": {"type": "boolean"},
                    "cancelable": {"type": "boolean"},
                    "events": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "description": {"type": "string"},
                },
            },
        },
        "dependencies": {
            "type": "object",
            "additionalProperties": {"type": "string"},
        },
        "experimental": {"type": "boolean"},
        "experimental_message": {"type": "string"},
        "menu_hidden": {"type": "boolean"},
        "deprecated": {"type": "boolean"},
        "deprecation_message": {"type": "string"},
    },
}


def _validate_statefulness(data: dict[str, Any]) -> list[str]:
    """Validate the manifest statefulness field."""
    errors: list[str] = []
    statefulness = data.get("statefulness")

    if statefulness is None:
        return errors
    if isinstance(statefulness, bool):
        return errors
    if not isinstance(statefulness, dict):
        return ["field 'statefulness' must be a boolean or object"]

    if "enabled" in statefulness and not isinstance(statefulness["enabled"], bool):
        errors.append("field 'statefulness.enabled' must be a boolean")

    window = statefulness.get("window", {})
    if isinstance(window, bool):
        return errors
    if not isinstance(window, dict):
        errors.append("field 'statefulness.window' must be a boolean or object")
        return errors
    if "enabled" in window and not isinstance(window["enabled"], bool):
        errors.append("field 'statefulness.window.enabled' must be a boolean")
    if "settings_key" in window:
        settings_key = window["settings_key"]
        if settings_key is not None and (not isinstance(settings_key, str) or not settings_key):
            errors.append(
                "field 'statefulness.window.settings_key' must be a non-empty string or null"
            )
    return errors


def _validate_categories(data: dict[str, Any]) -> list[str]:
    """Validate the manifest categories field.

    ``categories`` is a set of menu/catalogue labels, not a path: it is rendered
    verbatim into the generated plugin documentation, so a repeated label shows
    up twice in the catalogue table. Comparison is case-insensitive so that
    ``["Structure", "structure"]`` is rejected too.

    Parameters
    ----------
    data : dict
        Parsed manifest JSON data.

    Returns
    -------
    list of str
        Validation errors. Empty list means valid.

    """
    errors: list[str] = []
    categories = data.get("categories")

    if categories is None:
        return errors
    if not isinstance(categories, list):
        return ["field 'categories' must be an array of strings"]

    seen: dict[str, str] = {}
    for category in categories:
        if not isinstance(category, str) or not category:
            errors.append("each 'categories' entry must be a non-empty string")
            continue
        key = category.casefold()
        if key in seen:
            errors.append(f"duplicate category {category!r} (already listed as {seen[key]!r})")
        else:
            seen[key] = category
    return errors


def _validate_known_keys(data: dict[str, Any]) -> list[str]:
    """Report top-level manifest keys that the schema does not declare.

    ``from_dict`` reads a fixed set of keys and ignores everything else, so a
    misspelled flag (``"experimantal"``) is silently dropped and the plugin
    ships unflagged. Declaring the key set closed turns that into a validation
    error the tree-wide manifest test catches.

    Parameters
    ----------
    data : dict
        Parsed manifest JSON data.

    Returns
    -------
    list of str
        Validation errors. Empty list means valid.

    """
    known = _MANIFEST_SCHEMA["properties"]
    return [f"unknown manifest field: {key!r}" for key in data if key not in known]


def validate_manifest(data: dict[str, Any]) -> list[str]:
    """Validate manifest data against the standard schema.

    Parameters
    ----------
    data : dict
        Parsed manifest JSON data.

    Returns
    -------
    list of str
        Validation errors. Empty list means valid.

    """
    errors: list[str] = []

    if not isinstance(data, dict):
        return ["manifest must be a JSON object"]

    for required in ("id", "version"):
        if required not in data:
            errors.append(f"missing required field: {required!r}")
        elif not isinstance(data[required], str) or not data[required]:
            errors.append(f"field {required!r} must be a non-empty string")

    for method in data.get("rpc_methods", []):
        if not isinstance(method, dict):
            errors.append("each rpc_methods entry must be an object")
            continue
        if "name" not in method or not isinstance(method["name"], str) or not method["name"]:
            errors.append("each rpc_methods entry must have a non-empty 'name'")
        for text_field in ("summary", "description"):
            if text_field in method and not isinstance(method[text_field], str):
                errors.append(f"rpc_methods field {text_field!r} must be a string")

    errors.extend(_validate_known_keys(data))
    errors.extend(_validate_categories(data))
    errors.extend(_validate_statefulness(data))
    return errors
