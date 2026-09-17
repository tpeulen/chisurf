"""Guard: a plugin declares every sibling plugin it actually couples to.

**The rule: what a plugin reaches for, its manifest says.** Every cross-plugin
coupling in the tree -- a module-level import, a lazy import, a ``try``-guarded
import, a ``"chisurf.plugins.x:Class"`` string a hub resolves on click, a
``panels.json`` entry, a ``view.json`` widget -- appears in that plugin's
``requires`` (if it fires at import time) or ``optional_requires`` (if it fires
later).

Why this suite exists: plugin registration ran in filesystem order, and every
failure path was a ``try``/``except`` that logged and moved on. A plugin whose
sibling was not importable yet did not crash -- it silently vanished from a
menu, or its services never registered, and nothing named the cause. Declaring
the edges is what lets the resolver order boot correctly; this suite is what
keeps the declarations true as the code moves under them.

The checks below ship with **nothing exempted** -- the edges were seeded from
the tree itself, so the extractor and the manifests agree today. Only the
RPC-namespace check has an allow-list, and
``test/plugin_dependency_allowlist.txt`` is a **shrinking** record of what is
still wrong, never somewhere to add yourself to make this test pass. The end
state is an empty allow-list.
"""

from __future__ import annotations

import json
import pathlib
import random

import pytest

from chisurf.core.plugin.dependencies import ordered_manifests, resolve
from chisurf.core.plugin.edges import (
    _is_skipped,
    collect_edges,
    module_owners,
    plugin_root,
)
from chisurf.core.plugin.manifest import ANY_VERSION, validate_manifest

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_ALLOWLIST = _ROOT / "test" / "plugin_dependency_allowlist.txt"

_PLUGIN_ROOT = plugin_root()
_OWNERS = module_owners(_PLUGIN_ROOT)
_EDGES = collect_edges(_PLUGIN_ROOT)


def _load_allowlist() -> set[str]:
    """The allow-listed RPC namespace squats, one ``plugin:method`` per line."""
    if not _ALLOWLIST.exists():
        return set()
    lines = _ALLOWLIST.read_text(encoding="utf-8").splitlines()
    return {ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")}


def _manifests() -> dict[str, dict]:
    """Every shipped manifest, keyed by plugin id."""
    out: dict[str, dict] = {}
    for path in sorted(_PLUGIN_ROOT.rglob("manifest.json")):
        if _is_skipped(path):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "id" in data and "version" in data:
            out[data["id"]] = data
    return out


MANIFESTS = _manifests()


def _declared(plugin_id: str, key: str) -> dict[str, str]:
    """One requirement map of one plugin."""
    return MANIFESTS.get(plugin_id, {}).get(key) or {}


# ── the premise ────────────────────────────────────────────────────────


def test_there_are_plugins_and_edges():
    """The premise. An empty extraction would make every test below vacuous."""
    assert len(MANIFESTS) > 100, f"only found {len(MANIFESTS)} manifests"
    assert len(_EDGES) > 50, f"only extracted {len(_EDGES)} cross-plugin edges"
    assert any(e.kind == "hard" for e in _EDGES), "no hard edges -- extractor is broken"


# ── the coupling is declared ───────────────────────────────────────────


def test_every_hard_edge_is_declared_in_requires():
    """A module-level import of a sibling is declared, and constrains boot order."""
    undeclared = sorted(
        f"{e.source} -> {e.target}  ({e.where})"
        for e in _EDGES
        if e.kind == "hard" and e.target not in _declared(e.source, "requires")
    )
    assert not undeclared, (
        "These plugins import a sibling at module import time without declaring "
        "it. Add the target to 'requires' in the source plugin's manifest.json "
        f"(value {ANY_VERSION!r} unless a real bound is needed):\n  " + "\n  ".join(undeclared)
    )


def test_every_optional_edge_is_declared_in_optional_requires():
    """A lazy, guarded or string-resolved reference is declared too.

    These are the ones that used to fail at click time: a hub holding a stale
    ``"chisurf.plugins.x:Widget"`` string looks fine until someone presses the
    button.
    """
    undeclared = sorted(
        f"{e.source} -> {e.target}  ({e.where})"
        for e in _EDGES
        if e.kind == "optional" and e.target not in _declared(e.source, "optional_requires")
    )
    assert not undeclared, (
        "These plugins reference a sibling lazily, inside try/except, or by "
        "string without declaring it. Add the target to 'optional_requires':\n  "
        + "\n  ".join(undeclared)
    )


def test_no_declaration_points_at_a_plugin_that_does_not_exist():
    """Every declared id resolves to a real plugin."""
    known = set(MANIFESTS)
    dangling = sorted(
        f"{plugin_id}.{key}[{target!r}]"
        for plugin_id in MANIFESTS
        for key in ("requires", "optional_requires")
        for target in _declared(plugin_id, key)
        if target not in known
    )
    assert not dangling, (
        "These declarations name a plugin id that is not in the tree -- a typo, "
        "or a plugin that was renamed or removed:\n  " + "\n  ".join(dangling)
    )


def test_no_stale_declarations():
    """Every declared edge still corresponds to real coupling.

    A declaration left behind after the code stopped using it makes the manifest
    a work of fiction, and the next reader cannot tell which half is true.
    """
    real = {(e.source, e.target) for e in _EDGES}
    real_hard = {(e.source, e.target) for e in _EDGES if e.kind == "hard"}
    stale = []
    for plugin_id in MANIFESTS:
        for target in _declared(plugin_id, "requires"):
            if (plugin_id, target) not in real_hard:
                stale.append(f"{plugin_id}.requires[{target!r}]")
        for target in _declared(plugin_id, "optional_requires"):
            if (plugin_id, target) not in real:
                stale.append(f"{plugin_id}.optional_requires[{target!r}]")
    assert not stale, (
        "These declared dependencies are no longer used by the code. Strike them "
        "from the manifest -- a declaration that is not true is worse than none:\n  "
        + "\n  ".join(sorted(stale))
    )


# ── the graph resolves ─────────────────────────────────────────────────


def test_the_requires_graph_is_acyclic():
    """Boot order exists.

    Several plugin pairs point at each other, but never twice in the hard
    direction -- that is precisely why ``optional_requires`` is a separate
    bucket. A cycle here means a pair now hard-imports each other, and no load
    order can satisfy both.
    """
    report = resolve(MANIFESTS.values())
    assert not report.cycles, (
        "The hard-dependency graph has a cycle, so no boot order satisfies it. "
        "Make one direction lazy (import inside the function that uses it) and "
        "move it to 'optional_requires':\n  "
        + "\n  ".join(" -> ".join(c + [c[0]]) for c in report.cycles)
    )


def test_the_tree_resolves_with_no_problems():
    """Nothing is missing, out of bounds or unknown in the shipped tree."""
    report = resolve(MANIFESTS.values())
    assert report.ok, "plugin dependency problems:\n  " + "\n  ".join(report.problems())
    assert len(report.order) == len(MANIFESTS)


def test_dependencies_precede_dependants():
    """The order actually does the thing it exists to do."""
    report = resolve(MANIFESTS.values())
    rank = {plugin_id: index for index, plugin_id in enumerate(report.order)}
    for plugin_id, data in MANIFESTS.items():
        for target in data.get("requires") or {}:
            assert rank[target] < rank[plugin_id], (
                f"{target!r} must be loaded before {plugin_id!r}, "
                f"but got ranks {rank[target]} and {rank[plugin_id]}"
            )


def test_the_order_is_deterministic():
    """Shuffled input gives the same order.

    Filesystem order is what this replaces; inheriting any of it would defeat
    the point, and a non-reproducible boot order is a bug that only shows up on
    someone else's machine.
    """
    items = list(MANIFESTS.values())
    first = resolve(items).order
    for seed in (1, 2, 3):
        shuffled = list(items)
        random.Random(seed).shuffle(shuffled)
        assert resolve(shuffled).order == first, f"order changed under shuffle {seed}"


def test_ordered_manifests_never_drops_anything():
    """Sorting is a permutation, not a filter."""
    items = list(MANIFESTS.values())
    ordered, _ = ordered_manifests(items)
    assert len(ordered) == len(items)
    assert {id(m) for m in ordered} == {id(m) for m in items}


# ── versions and bounds ────────────────────────────────────────────────


@pytest.mark.parametrize("plugin_id", sorted(MANIFESTS))
def test_a_plugin_version_is_pep440(plugin_id):
    """A version that cannot be parsed cannot be compared to a bound."""
    from packaging.version import InvalidVersion, Version

    version = MANIFESTS[plugin_id]["version"]
    try:
        Version(version)
    except InvalidVersion:  # pragma: no cover - guarded by the assert
        pytest.fail(f"{plugin_id}: version {version!r} is not a PEP 440 version")


@pytest.mark.parametrize("plugin_id", sorted(MANIFESTS))
def test_a_manifest_validates(plugin_id):
    """The hand-rolled validator accepts every shipped manifest.

    Deliberately the hand-rolled path, not ``validate_manifest_schema``: that
    one returns ``[]`` when ``jsonschema`` is not importable, and ``jsonschema``
    is not a declared dependency -- so on a clean environment it proves nothing.
    """
    problems = validate_manifest(MANIFESTS[plugin_id])
    assert not problems, f"{plugin_id}:\n  " + "\n  ".join(problems)


# ── namespace ownership ────────────────────────────────────────────────


def test_no_plugin_declares_rpc_methods_in_another_plugins_namespace():
    """An RPC namespace that is another plugin's id belongs to that plugin.

    Domain namespaces are fine and common (``mmfdb.*``, ``phasor.*``,
    ``editor.*``) -- only a namespace that *is* a sibling's id is squatting, and
    it collides the moment that sibling registers its own methods.
    """
    known = set(MANIFESTS)
    allowed = _load_allowlist()
    offenders = sorted(
        f"{plugin_id}:{method['name']}"
        for plugin_id, data in MANIFESTS.items()
        for method in data.get("rpc_methods", [])
        if (ns := method["name"].split(".")[0]) != plugin_id and ns in known
    )
    unexpected = [o for o in offenders if o not in allowed]
    assert not unexpected, (
        "These plugins declare RPC methods under another plugin's id. Move the "
        "method to the owning plugin, or rename it into a domain namespace.\n"
        "Do NOT add these to test/plugin_dependency_allowlist.txt: that list "
        "only shrinks.\n  " + "\n  ".join(unexpected)
    )


def test_the_allowlist_has_no_stale_entries():
    """Every allow-listed squat still exists.

    An entry that has been fixed must be struck, otherwise the list stops being
    a worklist and starts being decoration.
    """
    known = set(MANIFESTS)
    current = {
        f"{plugin_id}:{method['name']}"
        for plugin_id, data in MANIFESTS.items()
        for method in data.get("rpc_methods", [])
        if (ns := method["name"].split(".")[0]) != plugin_id and ns in known
    }
    stale = sorted(_load_allowlist() - current)
    assert not stale, (
        "These no longer squat another plugin's namespace -- strike them from "
        "test/plugin_dependency_allowlist.txt:\n  " + "\n  ".join(stale)
    )


# ── the controls ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "manifest, why",
    [
        (
            {"id": "a", "version": "1.0.0", "requires": {"b": "nonsense"}},
            "a specifier that is not PEP 440",
        ),
        (
            {"id": "a", "version": "1.0.0", "requires": {"a": ANY_VERSION}},
            "a plugin depending on itself",
        ),
        (
            {
                "id": "a",
                "version": "1.0.0",
                "requires": {"b": ANY_VERSION},
                "optional_requires": {"b": ANY_VERSION},
            },
            "an id in both requirement maps",
        ),
        ({"id": "a", "version": "1.0.0", "requires": {"b": 3}}, "a non-string specifier"),
        ({"id": "a", "version": "1.0.0", "requires": ["b"]}, "a list instead of a map"),
    ],
)
def test_the_validator_rejects_what_the_resolver_could_not_use(manifest, why):
    """The control. Without this the suite could be passing vacuously."""
    assert validate_manifest(manifest), f"the validator accepted {why}"


def test_the_resolver_reports_rather_than_raises():
    """Boot must survive a broken third-party plugin in ~/.chisurf/plugins."""
    broken = [
        {"id": "a", "version": "1.0.0", "requires": {"ghost": ANY_VERSION}},
        {"id": "b", "version": "1.0.0", "requires": {"c": ">=9"}},
        {"id": "c", "version": "1.0.0"},
    ]
    report = resolve(broken)
    assert report.missing == {"a": ["ghost"]}
    assert "b" in report.out_of_bounds
    assert sorted(report.order) == ["a", "b", "c"], "every plugin still gets an order"


def test_a_cycle_degrades_instead_of_hanging():
    """A cycle is reported, and every plugin still reaches the order."""
    cyclic = [
        {"id": "a", "version": "1.0.0", "requires": {"b": ANY_VERSION}},
        {"id": "b", "version": "1.0.0", "requires": {"a": ANY_VERSION}},
        {"id": "c", "version": "1.0.0"},
    ]
    report = resolve(cyclic)
    assert report.cycles == [["a", "b"]]
    assert sorted(report.order) == ["a", "b", "c"]


def test_the_extractor_does_not_read_prose_as_an_edge():
    """A docstring naming a plugin module is not a dependency.

    The scan reads AST string *constants* and imports, never raw source text, so
    a comment cannot manufacture an edge. A docstring can -- it is a string
    constant -- which is why the classification is ``optional``, never ``hard``.
    """
    import ast

    from chisurf.core.plugin.edges import _ImportVisitor

    source = (
        "# see chisurf.plugins.core.help for the rules\nx = 1  # chisurf.plugins.burst.burst_bva\n"
    )
    visitor = _ImportVisitor("chisurf.plugins.demo.thing")
    visitor.visit(ast.parse(source))
    assert visitor.found == [], f"comments became edges: {visitor.found}"
