"""The data scheme for view specs and guided tours, derived from the loader.

Why this exists
---------------
Two of ChiSurf's file formats are written by hand, by everyone, in every
plugin: the AutoForm **view spec** (``*.view.json``) and the **guided tour**
(``gui/guide.json``). Both loaders are forgiving in the same way, and it is the
expensive way -- :func:`~chisurf.core.dataspec.load_view_spec` keeps only the
keys its dataclasses declare and **silently drops the rest**, and
:func:`~chisurf.gui.widgets.tools.guided_tour.load_tour` returns an empty tour
rather than raising. So a misspelled key is not an error; it is a control that
never appears, or a tour step that points at nothing, discovered by a user.

The survey that prompted this found real instances across the shipped tree:
``rebuild_on_change`` on a ``value`` section (only ``choice`` implements it),
``hide_label`` on a ``value``, ``kind: "path"`` where no such kind exists, and
nine tour steps using ``target.widget`` where the loader reads ``target.name``
-- nine steps that resolve to nothing and render as a centred bubble.

So the scheme is **generated from the loader's own dataclasses** rather than
transcribed. A transcription is a second source of truth that drifts; this one
cannot, and :func:`build_view_schema` is re-derived on every call. The written
``schemas/*.schema.json`` files are the artifact editors and CI consume, and a
test asserts they still match what this produces.

Strictness
----------
``additionalProperties`` is **false** everywhere, which is the entire point:
permitting unknown keys would validate exactly the files that are broken. Two
deliberate exceptions are carved out and named:

``_comment``
    Allowed at any level. It is the established convention for saying what a
    file is and what reads it -- 99 of the 129 view specs carry one.
``options`` on a ``custom`` section
    Free-form by design: it is forwarded verbatim to a registered factory,
    whose signature is Python, not JSON.
"""

from __future__ import annotations

import dataclasses
import json
import pathlib

__all__ = [
    "GUIDE_SCHEMA_PATH",
    "SCHEMA_DIR",
    "VIEW_SCHEMA_PATH",
    "build_guide_schema",
    "build_view_schema",
    "generate_starter_view_spec",
    "validate_guide",
    "validate_view_spec",
]

#: Where the written schema files live.
SCHEMA_DIR = pathlib.Path(__file__).resolve().parent / "schemas"
VIEW_SCHEMA_PATH = SCHEMA_DIR / "view.schema.json"
GUIDE_SCHEMA_PATH = SCHEMA_DIR / "guide.schema.json"

#: Top-level keys a view spec may carry that are not sections.
#:
#: ``title`` and ``model`` are read by chimol, which builds painted forms from
#: the same files (`emtk.view_spec`); the Qt loader ignores both.
#: They are in the scheme because a key that one reader honours and another
#: ignores is still part of the format -- leaving it out would make chimol's
#: own specs invalid.
_VIEW_TOP_LEVEL = {
    "_comment": {"type": "string", "description": "What this file is and what reads it."},
    "$schema": {
        "type": "string",
        "description": (
            "JSON Schema URI for editor validation. Map the pattern in "
            ".vscode/settings.json or set this to the schema's $id."
        ),
    },
    "sections": {"type": "array", "items": {"$ref": "#/$defs/section"}},
    "plots": {"type": "array", "items": {"$ref": "#/$defs/plot"}},
    "title": {"type": "string", "description": "Window title; read by chimol's painted forms."},
    "model": {
        "type": "string",
        "description": (
            "Which object the spec edits, for readers that must choose one. "
            "chimol understands 'settings' and 'viewer'."
        ),
    },
}

#: ``kind`` values :mod:`chisurf.gui.autoform.sections.builtin` actually
#: implements for a ``value`` section. Anything else falls through to a plain
#: string field -- which is how ``kind: "path"`` shipped twice, rendering with
#: no browse button and nothing to say so.
VALUE_KINDS = (
    "int",
    "float",
    "str",
    "text",
    "expression",
    "date",
    "password",
    "secret",
    "file",
    "directory",
)

#: Free-form section keys whose contents are forwarded to Python.
_OPAQUE = {
    ("custom", "options"),
    ("plot", "options"),
}

#: Documented option shapes for the eight core custom-section keys whose
#: factories accept a bounded set of named options (rather than forwarding
#: ``**options`` to an arbitrary widget).  An option key not in this mapping
#: stays opaque — the right default for a plugin-specific factory.
_CUSTOM_OPTION_KEYS: dict[str, set[str]] = {
    "help": {"text", "resource", "title", "label", "align"},
    "embed": {"widget", "attr", "kwargs", "pass_model", "expanding"},
    "scalar_table": {"rows", "call", "title"},
    "background_run": {
        "start_action",
        "stop_action",
        "running_attr",
        "progress_attr",
        "status_attr",
        "start_label",
        "start_description",
        "stop_label",
        "stop_description",
        "interval_ms",
    },
    "rate_matrix": {
        "attr",
        "size_attr",
        "labels_attr",
        "minimum",
        "maximum",
        "decimals",
        "diagonal",
        "unit_attr",
        "unit",
        "title",
        "popup",
        "disable_row0",
    },
    "path_list": {
        "extensions",
        "path_filter",
        "add_folders",
        "dialog_filter",
        "mmfdb",
        "mmfdb_kinds",
        "mmfdb_scope",
        "select_first",
        "checkable",
        "allow_duplicates",
        "replace_on_drop",
        "folder_expander",
        "guards",
        "max_height",
        "title",
    },
    "lcurve": {
        "compute_action",
        "select_action",
        "log10_min",
        "log10_max",
        "n_points",
        "x_label",
        "y_label",
    },
    "fitting_parameter": {"prior", "label"},
}


def _json_type(annotation) -> dict:
    """A JSON Schema fragment for a dataclass field's annotation.

    Deliberately loose where the annotation is: ``Any`` and unparameterised
    containers become "anything", because the loader does not check either and
    a schema stricter than the code rejects files that work.
    """
    text = str(annotation)
    if "Sequence" in text or "List" in text or "list" in text or "Tuple" in text:
        return {"type": "array"}
    if "Mapping" in text or "Dict" in text or "dict" in text:
        return {"type": "object"}
    optional = "Optional" in text or "None" in text
    for needle, kind in (
        ("bool", "boolean"),
        ("int", "integer"),
        ("float", "number"),
        ("str", "string"),
    ):
        if needle in text:
            return {"type": [kind, "null"]} if optional else {"type": kind}
    return {}


def build_view_schema() -> dict:
    """The view-spec scheme, derived from the loader's section dataclasses.

    Every registered section type contributes one branch, whose properties are
    exactly the fields its dataclass declares -- so a field added to the loader
    is legal here the moment it exists, and a key the loader would drop is not.
    """
    from . import _SECTION_TYPES  # noqa: PLC0415 - avoids an import cycle

    branches = {}
    for name, cls in sorted(_SECTION_TYPES.items()):
        properties: dict = {
            "type": {"const": name},
            "_comment": {"type": "string"},
        }
        for field in dataclasses.fields(cls):
            if field.name == "type":
                continue
            fragment = _json_type(field.type)
            if (name, field.name) in _OPAQUE:
                fragment = {}
            properties[field.name] = fragment

        # A nested section list is the same shape as the top-level one.
        for key in ("sections", "steps"):
            if key in properties:
                properties[key] = {"type": "array", "items": {"$ref": "#/$defs/section"}}
        if name == "value" and "kind" in properties:
            properties["kind"] = {"enum": list(VALUE_KINDS)}

        branches[name] = {
            "type": "object",
            "properties": properties,
            "additionalProperties": False,
        }

    # Per-key option validation for documented custom-section factories.
    # The eight core keys above have bounded option sets; a typo in one of
    # their option names is caught here. Unknown keys stay opaque.
    if "custom" in branches:
        conditions = []
        for key, allowed in sorted(_CUSTOM_OPTION_KEYS.items()):
            conditions.append(
                {
                    "if": {
                        "properties": {"key": {"const": key}},
                        "required": ["key"],
                    },
                    "then": {
                        "properties": {
                            "options": {
                                "type": "object",
                                "properties": {k: {} for k in sorted(allowed)},
                                "additionalProperties": False,
                            },
                        },
                    },
                }
            )
        if conditions:
            existing = branches["custom"].get("allOf", [])
            branches["custom"]["allOf"] = existing + conditions

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://chisurf.org/schemas/view.schema.json",
        "title": "ChiSurf view spec",
        "description": (
            "Declarative layout for an AutoForm panel. Generated from "
            "chisurf.core.dataspec's section dataclasses by "
            "chisurf.core.dataspec.schema -- edit those, not this."
        ),
        "type": "object",
        "properties": _VIEW_TOP_LEVEL,
        "additionalProperties": False,
        "$defs": {
            # Dispatched on `type` rather than expressed as a `oneOf` over the
            # branches. Both accept the same documents; only this one produces
            # a readable error. A `oneOf` failure reports that the object
            # matched none of seventeen alternatives and lists every key each
            # one rejected, which names the wrong section type in the message
            # a plugin author reads.
            "section": {
                "type": "object",
                "properties": {"type": {"enum": sorted(branches)}},
                "allOf": [
                    {
                        "if": {
                            "properties": {"type": {"const": name}},
                            "required": ["type"],
                        },
                        "then": branch,
                    }
                    for name, branch in sorted(branches.items())
                ]
                + [
                    # No `type` at all: the loader defaults to
                    # `parameter_group`, and a `steps` entry omits it
                    # entirely -- as all nineteen shipped wizard steps do, so
                    # a wizard step's own keys have to be legal here too.
                    {
                        "if": {"not": {"required": ["type"]}},
                        "then": {
                            "type": "object",
                            "properties": {
                                key: value
                                for branch in branches.values()
                                for key, value in branch["properties"].items()
                                if key != "type"
                            },
                            "additionalProperties": False,
                        },
                    },
                ],
            },
            "plot": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "options": {"type": "object"},
                    "_comment": {"type": "string"},
                },
                "required": ["key"],
                "additionalProperties": False,
            },
        },
    }


def build_guide_schema() -> dict:
    """The guided-tour scheme.

    Written out rather than derived: the tour loader reads a plain dict by hand
    instead of declaring dataclasses, so there is nothing to derive *from*. The
    keys are taken from :mod:`chisurf.gui.widgets.tools.guided_tour`, and the
    test that walks every shipped tour is what keeps this honest.
    """
    target = {
        "type": "object",
        "description": "Which control the step points at. An empty object centres the bubble.",
        "properties": {
            "panel": {"type": "string", "description": "A navigation-panel row, by substring."},
            "tab": {"type": "string", "description": "A dock or tab label, by substring."},
            "name": {"type": "string", "description": "A widget objectName, exact or by suffix."},
            "action": {
                "type": "string",
                "description": "A toolbar action's text, or a button's text or tooltip.",
            },
            "attr": {
                "type": "string",
                "description": "The model attribute a view-spec field is bound to.",
            },
            "key": {"type": "string", "description": "A custom section's key."},
            "title": {"type": "string", "description": "A section title, exactly."},
            "command": {
                "type": "boolean",
                "description": "The command prompt (chimol's painted tours).",
            },
            "menu": {"type": "string", "description": "A menu-bar title (chimol's painted tours)."},
            "toolbar": {"type": "string", "description": "A toolbar button's label (chimol)."},
            "object": {"type": "string", "description": "An object-list row, by name (chimol)."},
            "window": {
                "type": "string",
                "description": (
                    "A window drawn in the viewport, by key -- density, "
                    "objects, mouse, history (chimol). Resolves only while it "
                    "is open, so the step should open it first."
                ),
            },
            "movie": {"type": "boolean", "description": "The playback transport (chimol)."},
            "sequence": {"type": "boolean", "description": "The sequence strip (chimol)."},
            "wizard": {
                "type": "boolean",
                "description": (
                    "The running wizard's panel (chimol). Resolves only "
                    "while a wizard is running, so the step should start it "
                    "first."
                ),
            },
        },
        "additionalProperties": False,
    }
    step = {
        "type": "object",
        "properties": {
            "_comment": {"type": "string"},
            "title": {"type": "string"},
            "text": {
                "type": "string",
                "description": "Rich text; <b> and <i> are honoured by the Qt tour.",
            },
            "target": target,
            "await": {
                "description": (
                    "Wait for the user to use the highlighted control. true "
                    "auto-detects the signal; an object names it and the hint."
                ),
                "oneOf": [
                    {"type": "boolean"},
                    {"type": "null"},
                    {
                        "type": "object",
                        "properties": {
                            "signal": {"type": "string"},
                            "hint": {"type": "string"},
                        },
                        "additionalProperties": False,
                    },
                ],
            },
            "expect": {
                "type": "string",
                "description": (
                    "The command a step waits for, in chimol's painted tours, "
                    "where there are no widget signals to wait on."
                ),
            },
            "hint": {"type": "string", "description": "What to do, shown while waiting (chimol)."},
            "setup": {
                "type": "string",
                "description": (
                    "A command run when the step is shown, to put on screen "
                    "the panel or window it describes (chimol). Distinct from "
                    "`run`: setup reveals the subject, run performs the action."
                ),
            },
            "run": {
                "type": "string",
                "description": (
                    "What the step's Run button issues, when `expect` is a "
                    "prefix rather than a whole command (chimol). A step "
                    "matching any `translate` cannot run the word on its own."
                ),
            },
            "links": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "url": {"type": "string"},
                        "cite": {"type": "string"},
                        "doc": {"type": "string"},
                        "src": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
            },
        },
        "additionalProperties": False,
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://chisurf.org/schemas/guide.schema.json",
        "title": "ChiSurf guided tour",
        "description": (
            "A tour points at one real control at a time and waits for the "
            "user to use it. Read by chisurf.gui.widgets.tools.guided_tour "
            "and, for painted chrome, by chimol.tour."
        ),
        # Dispatched on the file's shape rather than expressed as a `oneOf`,
        # for the same reason the sections are: a `oneOf` failure reprints the
        # entire document as "is not of type 'array'" and never names the step
        # that is actually wrong.
        "type": ["array", "object"],
        "allOf": [
            {"if": {"type": "array"}, "then": {"type": "array", "items": step}},
            {
                "if": {"type": "object"},
                "then": {
                    "type": "object",
                    "properties": {
                        "_comment": {"type": "string"},
                        "$schema": {
                            "type": "string",
                            "description": ("JSON Schema URI for editor validation."),
                        },
                        "title": {"type": "string"},
                        "steps": {"type": "array", "items": step},
                    },
                    "required": ["steps"],
                    "additionalProperties": False,
                },
            },
        ],
        "$defs": {"step": step},
    }


def _validate(data, schema, label: str) -> list[str]:
    """Validate *data*, returning readable messages rather than raising.

    Returns
    -------
    list of str
        Empty when valid. One line per problem, each naming the path into the
        document, because "additionalProperties: false" on its own tells a
        plugin author nothing about *where*.
    """
    import jsonschema  # noqa: PLC0415

    validator = jsonschema.Draft202012Validator(schema)
    messages = []
    for error in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        where = "/".join(str(part) for part in error.path) or label
        # A oneOf failure reports the union, which is unreadable. The useful
        # half is the deepest cause, which is what the reader needs.
        cause = (
            min(error.context, key=lambda e: len(list(e.path)), default=None)
            if error.context
            else None
        )
        messages.append(f"{where}: {(cause or error).message}")
    return messages


def validate_view_spec(data) -> list[str]:
    """Check a parsed view spec against the scheme."""
    return _validate(data, build_view_schema(), "view spec")


def validate_guide(data) -> list[str]:
    """Check a parsed guided tour against the scheme."""
    return _validate(data, build_guide_schema(), "guide")


def write_schemas() -> list[pathlib.Path]:
    """Write the generated schemas to :data:`SCHEMA_DIR`.

    The written files are what editors and other tools consume; a test asserts
    they still equal what the generator produces, so a section field added to
    the loader without regenerating is a failing test rather than a schema that
    quietly disagrees with the code.
    """
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    for path, schema in (
        (VIEW_SCHEMA_PATH, build_view_schema()),
        (GUIDE_SCHEMA_PATH, build_guide_schema()),
    ):
        path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
        written.append(path)
    return written


def generate_starter_view_spec(model) -> dict:
    """Generate a starter ``view.json`` from a model's parameter groups.

    Walks *model*'s attributes for :class:`~chisurf.core.fitting.parameter.FittingParameterGroup`
    instances and emits one ``parameter_group_table`` section per group, plus
    the standard plots.  The result is a plain dict that serialises to valid
    JSON — a developer edits it into the final spec rather than spelling every
    section from memory.

    Parameters
    ----------
    model : Model
        A model instance (already constructed with its parameter groups).

    Returns
    -------
    dict
        A view-spec dict.  Pass through :func:`json.dumps` to write a file.

    Examples
    --------
    >>> from chisurf.core.dataspec.schema import generate_starter_view_spec
    >>> spec = generate_starter_view_spec(my_model)
    >>> print(json.dumps(spec, indent=2))

    """
    sections = []
    seen: set[int] = set()
    for attr_name, value in vars(model).items():
        if attr_name.startswith("_") or value is model:
            continue
        # Duck-typed: anything that looks like a parameter group (has
        # ``parameters_all``) is treated as one, avoiding a heavy import.
        if hasattr(value, "parameters_all"):
            if id(value) in seen:
                continue
            seen.add(id(value))
            title = getattr(value, "name", None) or attr_name.replace("_", " ").title()
            sections.append(
                {
                    "type": "parameter_group_table",
                    "target": attr_name,
                    "title": title,
                    "collapsible": True,
                }
            )

    return {
        "_comment": (
            "Auto-generated starter view spec — edit as needed. Validate with the view spec schema."
        ),
        "sections": sections,
        "plots": [
            {"key": "line", "options": {"x_label": "x", "y_label": "y"}},
            {"key": "fit_info"},
            {"key": "residual"},
        ],
    }


if __name__ == "__main__":  # pragma: no cover - a maintenance entry point
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--generate":
        # ``python -m chisurf.core.dataspec.schema --generate <dotted.path>``
        # imports a model class, instantiates it with dummy arguments, and
        # writes a starter view spec to stdout.
        import importlib

        parts = sys.argv[2].rsplit(".", 1)
        module = importlib.import_module(parts[0])
        cls = getattr(module, parts[1])
        spec = generate_starter_view_spec(cls.__new__(cls))
        print(json.dumps(spec, indent=2))
    else:
        for written in write_schemas():
            print(f"wrote {written}")
