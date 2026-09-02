"""Guardrail: the external graph library stays out of the tree.

Graphs in ChiSurf -- the fit factor graph, the node editor's DAG, the global-view
parameter network -- are handled by :mod:`chisurf.core.graph`, the in-tree graph layer
that ships with the application. ``networkx`` was the previous provider and was
removed; this test fails if an import or a packaging declaration brings it back,
which would re-add an external dependency for containers and algorithms the tree
already owns.

Notes
-----
``networkx`` may still be *installed* in a development environment, pulled in
transitively by other scientific packages. That is fine and precisely why the
guardrail is needed: an accidental import would work on a developer machine and
fail in a packaged install.
"""

from __future__ import annotations

import pathlib
import re

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Files whose only mention of the name is this test or an explanatory comment.
_ALLOWED = {
    "test/test_no_networkx_import.py",
}

_IMPORT_PATTERN = re.compile(
    r"^\s*(?:import\s+networkx|from\s+networkx[\s.])", re.MULTILINE
)


def _python_sources():
    """Yield every Python source file under ``chisurf/`` and ``test/``.

    Yields
    ------
    pathlib.Path
    """
    for folder in ("chisurf", "test"):
        yield from (REPO_ROOT / folder).rglob("*.py")


def test_no_module_imports_networkx():
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in _python_sources()
        if str(path.relative_to(REPO_ROOT)) not in _ALLOWED
        and _IMPORT_PATTERN.search(path.read_text(encoding="utf-8", errors="ignore"))
    ]
    assert not offenders, (
        "networkx is no longer a dependency; use `from chisurf.core import graph as cg` "
        f"instead. Importing modules: {offenders}"
    )


def test_packaging_does_not_declare_networkx():
    offenders = []
    for rel in (
        "pixi.toml",
        "pyproject.toml",
        "setup.py",
        "rattler-recipe/recipe.yaml",
    ):
        path = REPO_ROOT / rel
        if not path.exists() or rel in _ALLOWED:
            continue
        if "networkx" in path.read_text(encoding="utf-8", errors="ignore"):
            offenders.append(rel)
    assert not offenders, f"networkx reintroduced as a dependency in: {offenders}"
