"""ChiMOL's own UI files follow ChiSurf's scheme, and its reader does not drift.

Why chimol needs its own copy of this
-------------------------------------
``test/test_ui_schemas.py`` validates every shipped view spec and tour, chimol's
included. What it cannot check is the thing chimol adds: a **second reader** of
the same format. Two readers of one format is exactly the arrangement that
grows two dialects -- one of them convenient, undocumented, and valid nowhere
else -- and the first draft of chimol's adapter did precisely that, inventing
``{"type": "float", "min": 0, "max": 1}`` where the real dialect is
``{"type": "value", "kind": "float", "minimum": 0, "maximum": 1}``. It read
perfectly well here and was rejected by AutoForm and by the scheme.

So this file pins the seam from chimol's side:

* chimol's own specs and tours validate against the **shared** scheme;
* every ``kind`` chimol claims to render is a kind the AutoForm loader
  implements, and every section type it edits is a real section type -- so the
  adapter cannot quietly accept a spelling nobody else does;
* the same spec that chimol paints also loads in the Qt loader, which is what
  "one dialect" means operationally.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from chisurf.core.dataspec.schema import validate_guide, validate_view_spec

#: The relocated engine, resolved through the import system (see
#: test_chisurf_seam.PACKAGE).
_CHIMOL = pathlib.Path(__import__("chimol").__file__).resolve().parent

VIEW_SPECS = sorted(p for p in _CHIMOL.rglob("*.view.json") if "build" not in p.parts)
TOURS = sorted(p for p in (_CHIMOL / "data" / "tours").glob("*.json"))


def _label(path: pathlib.Path) -> str:
    return path.name


def test_chimol_ships_specs_and_tours():
    """The premise; an empty glob would make the rest vacuous."""
    assert VIEW_SPECS, "chimol ships no view specs"
    assert TOURS, "chimol ships no tours"


@pytest.mark.parametrize("path", VIEW_SPECS, ids=_label)
def test_a_chimol_spec_follows_the_shared_scheme(path):
    """Validated by the same scheme as every other tool's, deliberately."""
    problems = validate_view_spec(json.loads(path.read_text(encoding="utf-8")))
    assert not problems, f"{path.name}:\n  " + "\n  ".join(problems)


@pytest.mark.parametrize("path", TOURS, ids=_label)
def test_a_chimol_tour_follows_the_shared_scheme(path):
    """Chimol's tours are painted rather than Qt, and are the same format."""
    problems = validate_guide(json.loads(path.read_text(encoding="utf-8")))
    assert not problems, f"{path.name}:\n  " + "\n  ".join(problems)


@pytest.mark.parametrize("path", VIEW_SPECS, ids=_label)
def test_a_chimol_spec_also_loads_in_the_qt_loader(path):
    """The operational meaning of "one dialect".

    A spec chimol can paint but AutoForm cannot parse would be a second format
    wearing the same file extension.
    """
    from chisurf.core.dataspec import load_view_spec

    load_view_spec(path)


def test_the_adapter_only_claims_kinds_the_loader_implements():
    """Chimol must not invent a ``kind``.

    If it accepted one AutoForm does not, a spec written against chimol would
    render there and vanish everywhere else -- and the scheme, which is derived
    from the loader, would reject the file while chimol drew it happily.
    """
    from emtk.widgets.view_spec import FIELD_KINDS

    from chisurf.core.dataspec.schema import VALUE_KINDS

    unknown = set(FIELD_KINDS) - set(VALUE_KINDS)
    assert not unknown, f"chimol renders kinds that do not exist: {sorted(unknown)}"


def test_the_adapter_only_binds_real_section_types():
    """Same, one level up: the types it edits have to be types."""
    from emtk.widgets.view_spec import CONTAINER_TYPES, SECTION_KINDS

    from chisurf.core.dataspec import _SECTION_TYPES

    unknown = set(SECTION_KINDS) - set(_SECTION_TYPES)
    assert not unknown, f"chimol edits section types that do not exist: {sorted(unknown)}"

    # Containers are looser on purpose -- the adapter treats anything holding
    # `sections` as a group -- but the ones it names must still be real.
    named = {name for name in CONTAINER_TYPES if name in _SECTION_TYPES}
    assert named, "none of the container types chimol knows are real section types"


def test_every_kind_the_loader_implements_is_handled_or_deliberately_not():
    """The other direction, so the adapter's coverage is visible rather than assumed.

    Not a demand that chimol render everything -- a painted panel has no date
    picker. What it must not do is *silently* fall through: an unhandled kind
    lands on a text row, which is a control that looks like it works.
    """
    from emtk.widgets.view_spec import FIELD_KINDS

    from chisurf.core.dataspec.schema import VALUE_KINDS

    missing = set(VALUE_KINDS) - set(FIELD_KINDS)
    assert not missing, (
        f"chimol has no row for {sorted(missing)}; add one, or map it to TEXT "
        "explicitly so the fall-through is a decision rather than an accident"
    )
