"""A plugin's example data ships with the plugin, not with its tests.

An installer may leave out ``test/`` and ``tests/`` folders, and a *Load example*
that imports a test module or reads a test-data path then breaks on exactly the
installs a user has. batch_analysis once built its example session from
``test/fakes.py`` and burstwise_import read its folder from ``tests/data``. This
reads every shipped ``demo.py`` / ``demo_*.py`` (outside test folders) with ``ast``
and fails on an import from a test package or a path built from a ``test``/``tests``
component.
"""

from __future__ import annotations

import ast
import pathlib

PLUGINS = pathlib.Path(__file__).resolve().parents[1] / "chisurf" / "plugins"
TEST_PARTS = {"test", "tests"}


def _demo_modules():
    for path in sorted(PLUGINS.rglob("*.py")):
        if not (path.name == "demo.py" or path.name.startswith("demo_")):
            continue
        rel = path.relative_to(PLUGINS).parts
        if TEST_PARTS & set(rel[:-1]) or "cookiecutter" in str(path):
            continue
        yield path


def _test_dependencies(path: pathlib.Path) -> list[str]:
    found = []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            parts = (node.module or "").split(".")
            if TEST_PARTS & set(parts):
                found.append(f"{node.lineno}: from {'.' * node.level}{node.module} import ...")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if TEST_PARTS & set(alias.name.split(".")):
                    found.append(f"{node.lineno}: import {alias.name}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            parts = node.value.replace("\\", "/").split("/")
            if node.value in TEST_PARTS or (len(parts) > 1 and TEST_PARTS & set(parts)):
                found.append(f"{node.lineno}: path component {node.value!r}")
    return found


def test_shipped_demos_do_not_depend_on_test_code_or_test_data():
    """No demo module imports from a test package or reads a test-data path."""
    offenders = {}
    for path in _demo_modules():
        hits = _test_dependencies(path)
        if hits:
            offenders[str(path.relative_to(PLUGINS))] = hits
    assert not offenders, offenders


def test_the_guard_finds_both_shapes(tmp_path):
    """An import from a test package and a ``/ "tests" /`` path are both reported."""
    probe = tmp_path / "demo.py"
    probe.write_text(
        "from .test.fakes import FakeSession\n"
        "from pathlib import Path\n"
        "FIXTURE = Path(__file__).parent / 'tests' / 'data'\n",
        encoding="utf-8",
    )
    hits = _test_dependencies(probe)
    assert len(hits) == 2, hits
