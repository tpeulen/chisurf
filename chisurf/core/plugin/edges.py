"""Derive the cross-plugin coupling graph from the tree itself.

Plugins reach each other through more channels than an import scan sees. A hub
tool holds ``"chisurf.plugins.x.y:Widget"`` as a *string* and resolves it when the
user clicks; a ``panels.json`` names another plugin's panel; a ``view.json``
embeds another plugin's widget; a manifest entrypoint points into a sibling
package. Each of those is a real dependency, and each fails at click time rather
than at boot, which is the worst moment to discover it.

So one rule covers every channel:

    Any dotted name ``chisurf.plugins.<...>`` -- as an AST import, an AST string
    constant, or a JSON string value -- that resolves to a plugin other than the
    one owning the file is an edge.

Edges are classified by *when* they fire, because only one class constrains boot
order:

``hard``
    A module-level ``import`` outside any ``try``. The target must be importable
    before the source is imported, so the resolver emits the target first.
``optional``
    Everything else -- a function-local import, a ``try``-guarded import, a
    string resolved later. Real coupling, but it happens after boot and imposes
    no ordering. Keeping these out of the ordering graph is what makes the graph
    acyclic: several plugin pairs point at each other, but never twice in the
    hard direction.

Tests are excluded. A test importing the plugin it exercises is not a runtime
dependency, and treating it as one would invent cycles that do not exist.
"""

from __future__ import annotations

import ast
import json
import pathlib
from dataclasses import dataclass

#: Dotted prefix every plugin module lives under.
PLUGIN_PACKAGE = "chisurf.plugins"

#: Directory names whose contents describe how a plugin is *tested*, not how it
#: runs. Excluded from the graph entirely.
TEST_DIR_NAMES = frozenset({"test", "tests"})

#: Path fragments that are not real plugins: the cookiecutter template (which is
#: not valid Python) and caches.
SKIP_PARTS = ("__pycache__",)

#: JSON files that can name another plugin's entrypoint.
JSON_GLOBS = ("*.json",)


@dataclass(frozen=True, order=True)
class PluginEdge:
    """One directed coupling from one plugin to another.

    Attributes
    ----------
    source, target : str
        Canonical manifest ids.
    kind : str
        ``"hard"`` (module-level import, constrains boot order) or
        ``"optional"``.
    where : str
        ``"<repo-relative path>:<line>"``, so a failure names the line to fix.

    """

    source: str
    target: str
    kind: str
    where: str


def plugin_root() -> pathlib.Path:
    """The shipped plugin tree (``chisurf/plugins``)."""
    return pathlib.Path(__file__).resolve().parents[2] / "plugins"


def _is_skipped(path: pathlib.Path) -> bool:
    """Whether *path* is a template, cache or test artefact."""
    parts = path.parts
    if any(part in SKIP_PARTS for part in parts):
        return True
    if any("{{" in part for part in parts):
        return True
    return any(part in TEST_DIR_NAMES for part in parts)


def module_owners(root: pathlib.Path | None = None) -> dict[str, str]:
    """Map each plugin's dotted module path to its canonical manifest id.

    The map is keyed by module path rather than directory because that is what
    both imports and entrypoint strings carry. Nine plugins have a directory
    name that differs from their id (``calculator/hub`` is ``calculators``,
    ``modelling/fret`` is ``fret_docking``, ``fcs/flc_2d`` is ``flc-2d``), so
    inferring the id from the path would mislabel them.

    Parameters
    ----------
    root : pathlib.Path, optional
        Plugin tree to scan. Defaults to :func:`plugin_root`.

    Returns
    -------
    dict
        ``{"chisurf.plugins.fcs.flc_2d": "flc-2d", ...}``

    """
    root = root or plugin_root()
    base = root.parent.parent
    owners: dict[str, str] = {}
    for manifest_path in sorted(root.rglob("manifest.json")):
        if _is_skipped(manifest_path):
            continue
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or "id" not in data or "version" not in data:
            continue
        rel = manifest_path.parent.relative_to(base)
        owners[".".join(rel.parts)] = str(data["id"])
    return owners


def owner_of_module(dotted: str, owners: dict[str, str]) -> str | None:
    """The id of the plugin owning *dotted*, by longest-prefix match.

    Longest-prefix rather than first match, because plugins nest: a module under
    ``chisurf.plugins.misc.games.breakout`` belongs to ``breakout``, not to the
    ``games`` hub that contains it.
    """
    best: str | None = None
    best_len = -1
    for module_path, plugin_id in owners.items():
        if dotted == module_path or dotted.startswith(module_path + "."):
            if len(module_path) > best_len:
                best, best_len = plugin_id, len(module_path)
    return best


def owner_of_path(path: pathlib.Path, owners: dict[str, str], base: pathlib.Path) -> str | None:
    """The id of the plugin owning the file at *path*."""
    rel = path.resolve().relative_to(base)
    return owner_of_module(".".join(rel.with_suffix("").parts), owners)


def _dotted_candidates(text: str) -> list[str]:
    """Plugin module paths mentioned in a single string value.

    Entrypoints are ``module:attr`` or ``cmd=module:attr``; a bare module path is
    also accepted. Anything not starting with the plugin package is ignored.
    """
    value = text.strip()
    if PLUGIN_PACKAGE not in value:
        return []
    out = []
    for chunk in value.replace("=", " ").split():
        candidate = chunk.split(":", 1)[0].strip().rstrip(",;")
        if candidate.startswith(PLUGIN_PACKAGE):
            out.append(candidate)
    return out


class _ImportVisitor(ast.NodeVisitor):
    """Collect plugin module references, tagged by when they fire.

    ``ast.walk`` cannot answer "is this import at module level, outside a
    ``try``", which is the whole classification, so the tree is walked
    explicitly with those two flags carried down.
    """

    def __init__(self, module_dotted: str) -> None:
        self.module_dotted = module_dotted
        #: ``(dotted, is_hard, lineno)``
        self.found: list[tuple[str, bool, int]] = []
        self._top_level = True
        self._in_try = False

    # -- scope tracking -------------------------------------------------
    def _visit_nested(self, node: ast.AST) -> None:
        previous = self._top_level
        self._top_level = False
        self.generic_visit(node)
        self._top_level = previous

    visit_FunctionDef = _visit_nested
    visit_AsyncFunctionDef = _visit_nested
    visit_Lambda = _visit_nested

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        # A class body runs at import time, so an import in it is still hard.
        self.generic_visit(node)

    def visit_Try(self, node: ast.Try) -> None:
        previous = self._in_try
        self._in_try = True
        for child in node.body:
            self.visit(child)
        self._in_try = previous
        for child in node.handlers + node.orelse + node.finalbody:
            self.visit(child)

    # -- references -----------------------------------------------------
    def _record(self, dotted: str, hard: bool, lineno: int) -> None:
        if dotted.startswith(PLUGIN_PACKAGE):
            self.found.append((dotted, hard, lineno))

    def visit_Import(self, node: ast.Import) -> None:
        hard = self._top_level and not self._in_try
        for alias in node.names:
            self._record(alias.name, hard, node.lineno)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        hard = self._top_level and not self._in_try
        if node.level:
            # Resolve `from ..sibling import x` against this module's package.
            parts = self.module_dotted.split(".")[: -node.level]
            dotted = ".".join(parts + ([node.module] if node.module else []))
        else:
            dotted = node.module or ""
        self._record(dotted, hard, node.lineno)

    def visit_Constant(self, node: ast.Constant) -> None:
        # A string naming a plugin module is resolved at click time, never at
        # import time -- so it is optional however it is nested.
        if isinstance(node.value, str):
            for dotted in _dotted_candidates(node.value):
                self._record(dotted, False, node.lineno)


def _iter_json_strings(node) -> list[str]:
    """Every string value in a parsed JSON document."""
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [s for value in node.values() for s in _iter_json_strings(value)]
    if isinstance(node, list):
        return [s for value in node for s in _iter_json_strings(value)]
    return []


def collect_edges(root: pathlib.Path | None = None) -> list[PluginEdge]:
    """Every cross-plugin edge in the tree.

    Parameters
    ----------
    root : pathlib.Path, optional
        Plugin tree to scan. Defaults to :func:`plugin_root`.

    Returns
    -------
    list of PluginEdge
        Sorted and de-duplicated on ``(source, target, kind, where)``. A pair
        coupled both hard and optionally keeps only the ``hard`` edge, since the
        stronger claim subsumes the weaker one.

    """
    root = root or plugin_root()
    base = root.parent.parent
    owners = module_owners(root)
    edges: set[PluginEdge] = set()

    for path in sorted(root.rglob("*.py")):
        if _is_skipped(path):
            continue
        source = owner_of_path(path, owners, base)
        if source is None:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        module_dotted = ".".join(path.resolve().relative_to(base).with_suffix("").parts)
        visitor = _ImportVisitor(module_dotted)
        visitor.visit(tree)
        for dotted, hard, lineno in visitor.found:
            target = owner_of_module(dotted, owners)
            if target is None or target == source:
                continue
            where = f"{path.relative_to(base)}:{lineno}"
            edges.add(PluginEdge(source, target, "hard" if hard else "optional", where))

    for glob in JSON_GLOBS:
        for path in sorted(root.rglob(glob)):
            if _is_skipped(path):
                continue
            source = owner_of_path(path.parent / "x.py", owners, base)
            if source is None:
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                continue
            for value in _iter_json_strings(data):
                for dotted in _dotted_candidates(value):
                    target = owner_of_module(dotted, owners)
                    if target is None or target == source:
                        continue
                    edges.add(PluginEdge(source, target, "optional", str(path.relative_to(base))))

    hard_pairs = {(e.source, e.target) for e in edges if e.kind == "hard"}
    return sorted(e for e in edges if e.kind == "hard" or (e.source, e.target) not in hard_pairs)


def declared_form(edges: list[PluginEdge]) -> dict[str, dict[str, dict[str, str]]]:
    """Fold edges into the manifest shape.

    Returns
    -------
    dict
        ``{source_id: {"requires": {target: "*"}, "optional_requires": {...}}}``,
        with every bound :data:`~chisurf.core.plugin.manifest.ANY_VERSION`.

    """
    from chisurf.core.plugin.manifest import ANY_VERSION  # noqa: PLC0415

    out: dict[str, dict[str, dict[str, str]]] = {}
    for edge in edges:
        key = "requires" if edge.kind == "hard" else "optional_requires"
        bucket = out.setdefault(edge.source, {"requires": {}, "optional_requires": {}})
        bucket[key][edge.target] = ANY_VERSION
    return out
