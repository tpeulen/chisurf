from __future__ import annotations

import dataclasses
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
    """Plugin entrypoint strings.

    ``gui``, ``cli`` and ``services`` are ``module:attr`` (or ``cmd=module:attr``)
    strings resolved by :mod:`importlib`. ``script`` is different in kind: it
    names a file inside the plugin directory that the menu *executes* rather
    than imports, which is how the older tools are entered. Declaring it is what
    distinguishes "has no GUI" from "has a GUI the manifest cannot name" -- the
    two used to be indistinguishable, so a script-launched tool that gained a
    manifest silently became ``cli_only`` and vanished from every menu.
    """

    gui: str | None = None
    cli: str | None = None
    services: str | None = None
    script: str | None = None


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

    #: ``_mmfdb_operation.operation_type`` terms this tool is the analysis step for.
    #: A result in a ``.pto`` records the operation that produced it but not the
    #: program that ran it -- deliberately, because the container is tool-agnostic.
    #: This is the reverse index: it lets a reader of a container get back to the
    #: tool that would recompute the step, which is the difference between reading
    #: a result and continuing the analysis.
    operation_types: list[str] = field(default_factory=list)

    #: External distributions this plugin needs (``{"ruff": ">=0.4"}``) -- PyPI /
    #: conda names, **not** plugin ids. Plugin-to-plugin edges live in
    #: :attr:`requires` and :attr:`optional_requires`.
    dependencies: dict[str, str] = field(default_factory=dict)

    #: Sibling plugins this one imports at **module import time**, as
    #: ``{plugin_id: specifier}``. These are the edges that constrain boot order:
    #: a hard top-level import means the target's package must already be
    #: importable, so the resolver emits the target first.
    requires: dict[str, str] = field(default_factory=dict)

    #: Sibling plugins this one reaches only *after* boot -- a function-local
    #: import, a ``try``-guarded import, or a ``"chisurf.plugins.x:Class"`` string
    #: resolved when the user clicks something. Real dependencies, but they impose
    #: no ordering, so declaring them here keeps the ordering graph acyclic while
    #: still recording the coupling. Bounds are checked only if the target exists.
    optional_requires: dict[str, str] = field(default_factory=dict)

    #: This package is shared code other plugins import, not a tool a user runs
    #: (``imaging_common``, ``mle_common``). It carries an id so edges can name
    #: it, but it offers no entrypoint and never reaches a menu.
    library: bool = False

    #: Mark a tool as experimental / not yet validated. Hosts (e.g. the meta-tool shell)
    #: surface this with a warning banner and a flagged navigation entry.
    experimental: bool = False
    experimental_message: str = ""

    #: Keep the tool out of the generated menus (registry.py builds menu entries
    #: only for manifests that do not set this).
    menu_hidden: bool = False

    #: Declared maturity flag from the plugin spec's "honest metadata" rule. Surfaced
    #: like ``experimental``: the meta-tool shell marks the navigation entry and tops
    #: the panel with a banner carrying ``deprecation_message``.
    deprecated: bool = False
    deprecation_message: str = ""

    #: Mark a tool as a demonstration/toy rather than something the application is
    #: for. Unlike the maturity flags this carries no banner: plugin discovery keeps
    #: a demo out of the generated menus entirely unless the ``plugins.show_demo_plugins``
    #: setting is on, so demos can ship without competing with analysis tools for
    #: menu space.
    demo: bool = False

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
            script=entrypoints_data.get("script"),
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
            operation_types=data.get("operation_types", []),
            dependencies=data.get("dependencies", {}),
            requires=data.get("requires", {}),
            optional_requires=data.get("optional_requires", {}),
            library=data.get("library", False),
            experimental=data.get("experimental", False),
            experimental_message=tr(data.get("experimental_message", "")),
            menu_hidden=data.get("menu_hidden", False),
            deprecated=data.get("deprecated", False),
            deprecation_message=tr(data.get("deprecation_message", "")),
            demo=data.get("demo", False),
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
                "script": self.entrypoints.script,
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
            "operation_types": list(self.operation_types),
            "dependencies": dict(self.dependencies),
            "requires": dict(self.requires),
            "optional_requires": dict(self.optional_requires),
            "library": self.library,
            "experimental": self.experimental,
            "experimental_message": self.experimental_message,
            "menu_hidden": self.menu_hidden,
            "deprecated": self.deprecated,
            "deprecation_message": self.deprecation_message,
            "demo": self.demo,
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


#: Where the written manifest schema file lives.
MANIFEST_SCHEMA_DIR = pathlib.Path(__file__).resolve().parent / "schemas"
MANIFEST_SCHEMA_PATH = MANIFEST_SCHEMA_DIR / "manifest.schema.json"


def _type_fragment(annotation) -> dict:
    """A JSON Schema fragment for a manifest dataclass field's annotation."""
    text = str(annotation)
    if "list" in text or "List" in text:
        return {"type": "array"}
    if "dict" in text or "Dict" in text or "Mapping" in text:
        return {"type": "object"}
    optional = "None" in text or "Optional" in text
    for needle, kind in (("bool", "boolean"), ("int", "integer"),
                         ("float", "number"), ("str", "string")):
        if needle in text:
            return {"type": [kind, "null"]} if optional else {"type": kind}
    return {}


def build_manifest_schema() -> dict:
    """The manifest scheme, derived from the manifest dataclasses.

    Every field :class:`PluginManifest` declares contributes one property, so
    a field added to the dataclass is legal the moment it exists and a key the
    loader would ignore is not.  Nested dataclasses (:class:`PluginEntrypoints`,
    :class:`PluginStatefulness`, :class:`PluginWindowState`,
    :class:`RPCMethodSpec`) contribute ``$defs`` the top level references.

    ``statefulness`` accepts either a boolean or an object because
    :meth:`PluginManifest._parse_statefulness` handles both.
    """
    def _props(cls) -> dict:
        return {
            f.name: _type_fragment(f.type)
            for f in dataclasses.fields(cls)
        }

    entrypoints_def = {
        "type": "object",
        "properties": _props(PluginEntrypoints),
        "additionalProperties": False,
    }
    window_state_def = {
        "type": "object",
        "properties": _props(PluginWindowState),
        "additionalProperties": False,
    }
    rpc_method_def = {
        "type": "object",
        "properties": {
            **_props(RPCMethodSpec),
            # params_schema / result_schema can be inline objects *or* JSON
            # reference strings (``api.contract#/inputs/Foo``) resolved later.
            "params_schema": {"type": ["object", "string", "null"]},
            "result_schema": {"type": ["object", "string", "null"]},
        },
        "required": ["name"],
        "additionalProperties": False,
    }

    #: ``_type_fragment`` reduces ``dict[str, str]`` to a bare ``{"type": "object"}``,
    #: which would accept ``{"burst_bva": 3}`` or a key that is not an id shape. The
    #: dependency maps are the one place a wrong *value* silently means "no bound",
    #: so they get spelled out rather than inferred.
    requirement_map_def = {
        "type": "object",
        "additionalProperties": {"type": "string"},
        "propertyNames": {"pattern": r"^[a-z0-9][a-z0-9_-]*$"},
    }

    top_props = {
        **_props(PluginManifest),
        "_comment": {"type": "string"},
        "$schema": {"type": "string"},
    }
    top_props["requires"] = dict(requirement_map_def)
    top_props["optional_requires"] = dict(requirement_map_def)
    # entrypoints is a nested object, not a scalar
    top_props["entrypoints"] = {"$ref": "#/$defs/entrypoints"}
    # rpc_methods items are RPCMethodSpec objects
    top_props["rpc_methods"] = {
        "type": "array",
        "items": {"$ref": "#/$defs/rpc_method"},
    }
    # statefulness: bool or object
    top_props["statefulness"] = {
        "oneOf": [
            {"type": "boolean"},
            {
                "type": "object",
                "properties": {
                    "enabled": {"type": "boolean"},
                    "window": {
                        "oneOf": [
                            {"type": "boolean"},
                            {"$ref": "#/$defs/window_state"},
                        ],
                    },
                },
                "additionalProperties": False,
            },
        ],
    }

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://chisurf.org/schemas/manifest.schema.json",
        "title": "ChiSurf plugin manifest",
        "description": (
            "Plugin metadata and contract. Generated from the PluginManifest "
            "dataclass by chisurf.core.plugin.manifest -- edit that, not this."
        ),
        "type": "object",
        "required": ["id", "version"],
        "properties": top_props,
        "additionalProperties": False,
        "$defs": {
            "entrypoints": entrypoints_def,
            "window_state": window_state_def,
            "rpc_method": rpc_method_def,
        },
    }


def validate_manifest_schema(data) -> list[str]:
    """Check a parsed manifest against the generated scheme.

    Returns
    -------
    list of str
        Empty when valid.  One line per problem, naming the path into the
        document.

    """
    try:
        import jsonschema  # noqa: PLC0415
    except ImportError:  # pragma: no cover
        return []

    schema = build_manifest_schema()
    validator = jsonschema.Draft202012Validator(schema)
    messages = []
    for error in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        where = "/".join(str(p) for p in error.path) or "manifest"
        cause = min(error.context, key=lambda e: len(list(e.path)), default=None) \
            if error.context else None
        messages.append(f"{where}: {(cause or error).message}")
    return messages


def write_manifest_schema() -> pathlib.Path:
    """Write the generated manifest schema to :data:`MANIFEST_SCHEMA_PATH`."""
    MANIFEST_SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_SCHEMA_PATH.write_text(
        json.dumps(build_manifest_schema(), indent=2) + "\n", encoding="utf-8"
    )
    return MANIFEST_SCHEMA_PATH


# The manifest schema, generated from :class:`PluginManifest`.  ``properties``
# is the **closed** set of manifest keys: ``_validate_known_keys`` rejects
# anything else, and a guardrail test pins it against the dataclass fields, so
# a key cannot be declared without a parser or parsed without being declared.
_MANIFEST_SCHEMA = build_manifest_schema()


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


#: Value meaning "any version, the plugin merely has to be there". Every seeded
#: edge uses this: a bound invented without evidence is maintenance on every
#: version bump and asserts nothing.
ANY_VERSION = "*"


def is_satisfied_by(specifier: str, version: str) -> bool:
    """Whether *version* satisfies *specifier*.

    Parameters
    ----------
    specifier : str
        :data:`ANY_VERSION` or a PEP 440 specifier such as ``">=2.0,<3"``.
    version : str
        The candidate plugin's ``version`` string.

    Returns
    -------
    bool
        True when the bound holds. An unparseable *version* satisfies only
        :data:`ANY_VERSION` -- a plugin whose version is not PEP 440 cannot be
        compared, and silently passing the bound would be worse than failing it.

    """
    if specifier.strip() in ("", ANY_VERSION):
        return True
    try:
        from packaging.specifiers import SpecifierSet  # noqa: PLC0415
        from packaging.version import InvalidVersion, Version  # noqa: PLC0415
    except ImportError:  # pragma: no cover - packaging is a declared dependency
        return True
    from packaging.specifiers import InvalidSpecifier  # noqa: PLC0415

    try:
        return Version(version) in SpecifierSet(specifier)
    except (InvalidVersion, InvalidSpecifier):
        return False


def _validate_requirement_map(data: dict[str, Any], key: str) -> list[str]:
    """Validate one of the plugin-to-plugin requirement maps."""
    errors: list[str] = []
    raw = data.get(key)
    if raw is None:
        return errors
    if not isinstance(raw, dict):
        return [f"field {key!r} must be an object mapping plugin id to a version specifier"]

    own_id = data.get("id")
    for plugin_id, specifier in raw.items():
        if not isinstance(plugin_id, str) or not plugin_id:
            errors.append(f"each {key!r} key must be a non-empty plugin id")
            continue
        if plugin_id == own_id:
            errors.append(f"{key}[{plugin_id!r}] declares the plugin as its own dependency")
        if not isinstance(specifier, str) or not specifier:
            errors.append(
                f"{key}[{plugin_id!r}] must be a non-empty string "
                f"({ANY_VERSION!r} or a PEP 440 specifier)"
            )
            continue
        if specifier.strip() == ANY_VERSION:
            continue
        try:
            from packaging.specifiers import InvalidSpecifier, SpecifierSet  # noqa: PLC0415

            SpecifierSet(specifier)
        except ImportError:  # pragma: no cover - packaging is a declared dependency
            continue
        except InvalidSpecifier:
            errors.append(
                f"{key}[{plugin_id!r}] is not a PEP 440 specifier: {specifier!r} "
                f"(use {ANY_VERSION!r} for 'any version')"
            )
    return errors


def _validate_dependencies(data: dict[str, Any]) -> list[str]:
    """Validate ``requires`` / ``optional_requires``.

    Beyond each map's own shape, the two must be disjoint: an id in both would
    be simultaneously boot-ordering and not, and the resolver would have to pick
    one silently.

    Parameters
    ----------
    data : dict
        Parsed manifest JSON data.

    Returns
    -------
    list of str
        Validation errors. Empty list means valid.

    """
    errors = _validate_requirement_map(data, "requires")
    errors.extend(_validate_requirement_map(data, "optional_requires"))

    hard = data.get("requires")
    soft = data.get("optional_requires")
    if isinstance(hard, dict) and isinstance(soft, dict):
        for plugin_id in sorted(set(hard) & set(soft)):
            errors.append(
                f"{plugin_id!r} is in both 'requires' and 'optional_requires' -- "
                "a dependency either constrains boot order or it does not"
            )
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
    errors.extend(_validate_dependencies(data))
    return errors
