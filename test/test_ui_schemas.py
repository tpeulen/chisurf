"""Every shipped view spec and guided tour follows the declared scheme.

Why this suite exists
---------------------
Two formats are written by hand, by everyone, in every plugin: the AutoForm
**view spec** (``*.view.json``) and the **guided tour** (``gui/guide.json``).
Both loaders are forgiving, and in the same expensive way:
:func:`chisurf.core.dataspec.load_view_spec` keeps only the keys its dataclasses
declare and **silently drops the rest**, and the tour loader returns an empty
tour rather than raising. A misspelled key is therefore not an error -- it is a
control that never appears, or a step pointing at nothing, found by a user.

Writing this suite found nine real defects that had shipped:

* ``rebuild_on_change`` on three ``value`` sections -- only ``choice``
  implements it, and :class:`~chisurf.core.dataspec.ChoiceSection` says in its
  own docstring why ``value``/``toggle`` deliberately do not (a rebuild
  mid-drag on a spin box). The three specs asked for a rebuild and got nothing;
* ``kind: "combo"`` on a ``choice`` -- the key is ``style``;
* ``kind: "path"`` twice, which is not one of the implemented kinds, so both
  rendered as a plain string field with **no browse button** and nothing to say
  so;
* ``n_col`` on an ``info``, ``key`` on an ``info``, ``hide_label`` on a
  ``value`` -- all dropped;
* and in the tours, **nine steps using ``target.widget``** where the loader
  reads ``target.name``. Nine steps that resolved to nothing and rendered as a
  centred bubble pointing at no control at all -- in a *guided tour*, whose
  entire purpose is pointing at controls.

None of those raised anything, anywhere.

The scheme is generated from the loader's own dataclasses
---------------------------------------------------------
:mod:`chisurf.core.dataspec.schema` derives the view scheme from
``_SECTION_TYPES``, so it cannot drift from the code the way a transcription
would. What this suite adds is the other half: that the *files* follow it, that
the written ``schemas/*.schema.json`` still match the generator, and -- the test
that keeps the rest honest -- that the scheme actually **rejects** something.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from chisurf.core.dataspec.schema import (
    GUIDE_SCHEMA_PATH,
    VIEW_SCHEMA_PATH,
    build_guide_schema,
    build_view_schema,
    validate_guide,
    validate_view_spec,
)

_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Trees that ship user interfaces. ``build/`` is excluded deliberately: it
#: holds copies, and a failure there names a path nobody edits.
_SEARCH = ("chisurf", "modules")


def _find(pattern: str) -> list[pathlib.Path]:
    found: list[pathlib.Path] = []
    for tree in _SEARCH:
        base = _ROOT / tree
        if base.exists():
            found.extend(
                path
                for path in base.rglob(pattern)
                if "build" not in path.parts and ".pixi" not in path.parts
            )
    return sorted(found)


VIEW_SPECS = _find("*.view.json")
GUIDES = _find("guide.json")


def _label(path: pathlib.Path) -> str:
    return str(path.relative_to(_ROOT))


# --------------------------------------------------------------------- files


def test_there_are_view_specs_and_guides():
    """The premise. An empty glob would make every test below vacuous."""
    assert len(VIEW_SPECS) > 50, f"only found {len(VIEW_SPECS)} view specs"
    assert len(GUIDES) > 10, f"only found {len(GUIDES)} guides"


@pytest.mark.parametrize("path", VIEW_SPECS, ids=_label)
def test_a_view_spec_follows_the_scheme(path):
    """Every key is one the loader reads.

    A key it does not read is dropped in silence, so this is the only place the
    difference between "declared" and "honoured" is ever visible.
    """
    problems = validate_view_spec(json.loads(path.read_text(encoding="utf-8")))
    assert not problems, f"{_label(path)}:\n  " + "\n  ".join(problems)


@pytest.mark.parametrize("path", GUIDES, ids=_label)
def test_a_guide_follows_the_scheme(path):
    """Same, for tours -- where an unread key means a step points at nothing."""
    problems = validate_guide(json.loads(path.read_text(encoding="utf-8")))
    assert not problems, f"{_label(path)}:\n  " + "\n  ".join(problems)


@pytest.mark.parametrize("path", VIEW_SPECS, ids=_label)
def test_a_view_spec_still_loads(path):
    """Validating is not enough: the loader has to accept it too.

    The scheme is derived from the loader, so these should never disagree --
    which is exactly why it is worth asserting. A scheme that passed files the
    loader rejects would be worse than none.
    """
    from chisurf.core.dataspec import load_view_spec

    load_view_spec(path)


# ------------------------------------------------------------------- scheme


def test_the_written_schemas_match_the_generator():
    """The shipped ``.schema.json`` files are what editors and CI read.

    They are generated, so this fails whenever a section field is added to the
    loader without regenerating -- which would otherwise leave a schema quietly
    disagreeing with the code it came from.

    Regenerate with ``python -m chisurf.core.dataspec.schema``.
    """
    for path, generated in (
        (VIEW_SCHEMA_PATH, build_view_schema()),
        (GUIDE_SCHEMA_PATH, build_guide_schema()),
    ):
        assert path.exists(), f"{path} is missing; run the generator"
        written = json.loads(path.read_text(encoding="utf-8"))
        assert written == generated, (
            f"{path.name} is stale -- regenerate with `python -m chisurf.core.dataspec.schema`"
        )


def test_every_section_type_is_in_the_scheme():
    """A new section type must reach the scheme, or its files cannot validate."""
    from chisurf.core.dataspec import _SECTION_TYPES

    schema = build_view_schema()
    described = set(schema["$defs"]["section"]["properties"]["type"]["enum"])
    assert described == set(_SECTION_TYPES), (
        f"scheme and loader disagree: {described ^ set(_SECTION_TYPES)}"
    )


def test_every_declared_field_is_in_the_scheme():
    """Property-for-field, per type. This is what makes the scheme derived."""
    import dataclasses

    from chisurf.core.dataspec import _SECTION_TYPES

    branches = {
        branch["then"]["properties"]["type"]["const"]: branch["then"]
        for branch in build_view_schema()["$defs"]["section"]["allOf"]
        if "properties" in branch["then"]
        and "type" in branch["then"]["properties"]
        and "const" in branch["then"]["properties"]["type"]
    }
    for name, cls in _SECTION_TYPES.items():
        fields = {f.name for f in dataclasses.fields(cls)}
        # `type` is the discriminator, present in both, and `_comment` is the
        # annotation carve-out the scheme allows everywhere.
        described = set(branches[name]["properties"]) - {"_comment"}
        fields = fields | {"type"}
        assert described == fields, f"{name}: scheme and dataclass disagree on {described ^ fields}"


# ------------------------------------------------- the scheme must say no


@pytest.mark.parametrize(
    "spec, why",
    [
        (
            {"sections": [{"type": "value", "attr": "x", "rebuild_on_change": True}]},
            "a value section cannot rebuild the form -- only a choice can",
        ),
        (
            {"sections": [{"type": "choice", "attr": "x", "kind": "combo"}]},
            "a choice uses `style`, not `kind`",
        ),
        (
            {"sections": [{"type": "value", "attr": "x", "kind": "path"}]},
            "`path` is not an implemented kind; a file field renders as plain text",
        ),
        ({"sections": [{"type": "info", "n_col": 1}]}, "`n_col` belongs to a panel"),
        (
            {"sections": [{"type": "value", "attr": "x", "hide_label": False}]},
            "`hide_label` is not read",
        ),
        ({"sections": [{"type": "not_a_type"}]}, "an unknown section type"),
        ({"nonsense": 1}, "an unknown top-level key"),
        (
            {"sections": [{"type": "custom", "key": "help", "options": {"tite": "hello"}}]},
            "a typo in a documented custom-section option name",
        ),
        (
            {
                "sections": [
                    {"type": "custom", "key": "background_run", "options": {"start_acton": "go"}}
                ]
            },
            "a typo in a background_run option name",
        ),
    ],
)
def test_the_scheme_rejects_what_the_loader_would_drop(spec, why):
    """The control. Without this the suite could be passing vacuously.

    Every case here is a defect that had actually shipped, except the last two.
    """
    assert validate_view_spec(spec), f"the scheme accepted {why}"


@pytest.mark.parametrize(
    "guide, why",
    [
        (
            {"steps": [{"title": "a", "target": {"widget": "someButton"}}]},
            "`widget` is not read -- the key is `name`, and nine steps shipped this way",
        ),
        ({"steps": [{"title": "a", "target": {"nope": "x"}}]}, "an unknown target key"),
        ({"steps": [{"title": "a", "await": {"nope": 1}}]}, "an unknown await key"),
        ({"no_steps": []}, "a tour object with no steps"),
    ],
)
def test_the_scheme_rejects_a_tour_that_points_at_nothing(guide, why):
    """The same control for tours, where the cost is a step pointing nowhere."""
    assert validate_guide(guide), f"the scheme accepted {why}"


def test_a_valid_document_is_accepted():
    """And the other direction, so the scheme is not merely strict."""
    assert (
        validate_view_spec(
            {
                "_comment": "a note about this file",
                "$schema": "https://chisurf.org/schemas/view.schema.json",
                "sections": [
                    {
                        "type": "panel",
                        "title": "Group",
                        "sections": [
                            {
                                "type": "value",
                                "attr": "x",
                                "kind": "float",
                                "minimum": 0.0,
                                "maximum": 1.0,
                                "description": "a number",
                            },
                            {"type": "toggle", "attr": "on", "label": "On"},
                            {
                                "type": "choice",
                                "attr": "mode",
                                "options": ["a", "b"],
                                "style": "combo",
                                "rebuild_on_change": True,
                            },
                        ],
                    }
                ],
                "plots": [{"key": "line", "options": {}}],
            }
        )
        == []
    )
    assert (
        validate_guide(
            {
                "_comment": "a note",
                "$schema": "https://chisurf.org/schemas/guide.schema.json",
                "steps": [
                    {"title": "Intro", "text": "why", "target": {}},
                    {"title": "Do it", "target": {"name": "run"}, "await": {"hint": "press it"}},
                ],
            }
        )
        == []
    )


# ------------------------------------------------- starter view spec generator


class _FakeGroup:
    """Minimal duck-typed stand-in for FittingParameterGroup."""

    def __init__(self, name=""):
        self.name = name

    @property
    def parameters_all(self):
        return []


class _FakeModel:
    """A model with two parameter-group attributes and some noise."""

    def __init__(self):
        self.generic = _FakeGroup("Generic")
        self.lifetimes = _FakeGroup("Lifetimes")
        self._private = _FakeGroup("should not appear")
        self.x = 42  # not a group


def test_starter_view_spec_is_valid():
    """The generated starter spec follows the scheme it was generated for."""
    from chisurf.core.dataspec.schema import generate_starter_view_spec

    spec = generate_starter_view_spec(_FakeModel())
    assert validate_view_spec(spec) == [], "generated spec does not validate: " + "; ".join(
        validate_view_spec(spec)
    )


def test_starter_view_spec_has_one_table_per_group():
    """Each parameter-group attribute becomes exactly one table section."""
    from chisurf.core.dataspec.schema import generate_starter_view_spec

    spec = generate_starter_view_spec(_FakeModel())
    targets = [s["target"] for s in spec["sections"]]
    assert targets == ["generic", "lifetimes"]
    assert all(s["type"] == "parameter_group_table" for s in spec["sections"])
