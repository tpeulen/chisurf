"""Every shipped manifest.json follows the declared scheme.

The scheme is generated from :class:`~chisurf.core.plugin.manifest.PluginManifest`
by :func:`~chisurf.core.plugin.manifest.build_manifest_schema`, so it cannot
drift from the code the way a hand-written transcription would.  This suite
asserts the other half: that the *files* follow it, that the written
``schemas/manifest.schema.json`` still matches the generator, and that the
scheme actually **rejects** something.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from chisurf.core.plugin.manifest import (
    MANIFEST_SCHEMA_PATH,
    build_manifest_schema,
    validate_manifest_schema,
)

_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Trees that ship plugins.
_SEARCH = ("chisurf", "modules")


def _find(pattern: str) -> list[pathlib.Path]:
    found: list[pathlib.Path] = []
    for tree in _SEARCH:
        base = _ROOT / tree
        if base.exists():
            for path in base.rglob(pattern):
                if "build" in path.parts or ".pixi" in path.parts:
                    continue
                # Skip files that share the name but are not plugin manifests
                # (e.g. chimol render fixtures): a real manifest carries id+version.
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                if isinstance(data, dict) and "id" in data and "version" in data:
                    found.append(path)
    return sorted(found)


MANIFESTS = _find("manifest.json")


def _label(path: pathlib.Path) -> str:
    return str(path.relative_to(_ROOT))


# --------------------------------------------------------------------- files


def test_there_are_manifests():
    """The premise. An empty glob would make every test below vacuous."""
    assert len(MANIFESTS) > 10, f"only found {len(MANIFESTS)} manifests"


@pytest.mark.parametrize("path", MANIFESTS, ids=_label)
def test_a_manifest_follows_the_scheme(path):
    """Every key is one the loader reads.

    A key it does not read is silently ignored by ``from_dict``, so this is
    the only place the difference between "declared" and "honoured" is visible
    at CI time.
    """
    problems = validate_manifest_schema(json.loads(path.read_text(encoding="utf-8")))
    assert not problems, f"{_label(path)}:\n  " + "\n  ".join(problems)


# ------------------------------------------------------------------- scheme


def test_the_written_schema_matches_the_generator():
    """The shipped ``manifest.schema.json`` is what editors and CI read."""
    assert MANIFEST_SCHEMA_PATH.exists(), f"{MANIFEST_SCHEMA_PATH} is missing; run the generator"
    written = json.loads(MANIFEST_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert written == build_manifest_schema(), (
        f"{MANIFEST_SCHEMA_PATH.name} is stale -- regenerate with "
        '`python -c "from chisurf.core.plugin.manifest import write_manifest_schema; '
        'write_manifest_schema()"`'
    )


# ------------------------------------------------- the scheme must say no


@pytest.mark.parametrize(
    "manifest, why",
    [
        ({"id": "x", "version": "1", "nonsense": True}, "an unknown top-level key"),
        ({"version": "1"}, "missing required field 'id'"),
        ({"id": "x"}, "missing required field 'version'"),
        (
            {"id": "x", "version": "1", "entrypoints": {"nonsense": True}},
            "an unknown entrypoints key",
        ),
        (
            {"id": "x", "version": "1", "rpc_methods": [{"nme": "x"}]},
            "a rpc_methods entry missing 'name'",
        ),
    ],
)
def test_the_scheme_rejects_what_the_loader_would_drop(manifest, why):
    """The control. Without this the suite could be passing vacuously."""
    assert validate_manifest_schema(manifest), f"the scheme accepted {why}"


def test_a_valid_manifest_is_accepted():
    """And the other direction, so the scheme is not merely strict."""
    assert (
        validate_manifest_schema(
            {
                "id": "test",
                "version": "1.0.0",
                "display_name": "Test",
                "description": "A test plugin",
                "categories": ["Tools"],
                "experimental": False,
                "entrypoints": {"gui": "test.gui:Tool"},
                "rpc_methods": [{"name": "test.ping", "summary": "Ping"}],
                "statefulness": {"enabled": True, "window": {"enabled": False}},
                "dependencies": {"chisurf": ">=3.0"},
            }
        )
        == []
    )
