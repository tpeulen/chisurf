"""Every ``from test.<module> import ...`` names a module that exists.

Tests share builders by importing each other (``from test.gui.tcspc_fixtures
import _fit``). Deleting such a file breaks collection of every importer, and a
collection error stops the whole suite, not one file -- so the gate reports two
errors and runs nothing. This finds a dangling import without collecting.
"""

from __future__ import annotations

import ast
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]


def _sources():
    yield from (REPO / "test").rglob("*.py")
    for directory in ("test", "tests"):
        yield from (REPO / "chisurf").rglob(f"{directory}/*.py")


def test_imports_from_the_test_package_resolve():
    """Each ``test.a.b`` imported anywhere is ``test/a/b.py`` or a package."""
    dangling = []
    for path in sorted(set(_sources())):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module]
            elif isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            else:
                continue
            for name in names:
                if name != "test" and not name.startswith("test."):
                    continue
                target = REPO.joinpath(*name.split("."))
                if not (target.with_suffix(".py").exists() or (target / "__init__.py").exists()):
                    dangling.append(f"{path.relative_to(REPO)}:{node.lineno}: {name}")
    assert not dangling, "\n".join(dangling)
