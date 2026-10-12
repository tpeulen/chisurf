"""Every ChiSurf module a guide screenshot grabber imports exists.

When a GUI was retired its grabber kept importing the deleted ``gui/tool.py``: the grab
raised ImportError inside ``make_screenshots``' catch-all, printed ``SKIP`` and left the
guide showing a screenshot of a window that no longer ships (guides 01, 08, 19, 30, 41,
66 among them). The list of grabbers not yet ported is
``test/guide_screenshot_dead_import_allowlist.txt`` -- a shrinking list.
"""

from __future__ import annotations

import ast
import importlib
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = [
    REPO / "docs/guides/make_screenshots.py",
    *sorted((REPO / "docs/guides/screenshots").glob("*.py")),
]
ALLOW = REPO / "test/guide_screenshot_dead_import_allowlist.txt"


def _allowed() -> set[str]:
    lines = ALLOW.read_text(encoding="utf-8").splitlines()
    return {line.strip() for line in lines if line.strip() and not line.startswith("#")}


def _imports():
    for script in SCRIPTS:
        rel = script.relative_to(REPO).as_posix()
        for node in ast.walk(ast.parse(script.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.startswith("chisurf")
            ):
                for alias in node.names:
                    yield rel, node.module, alias.name


def _dead() -> set[str]:
    dead = set()
    for rel, module, name in _imports():
        try:
            mod = importlib.import_module(module)
        except ModuleNotFoundError:
            dead.add(f"{rel}::{module}")
            continue
        if not hasattr(mod, name):
            try:
                importlib.import_module(f"{module}.{name}")
            except ModuleNotFoundError:
                dead.add(f"{rel}::{module}:{name}")
    return dead


@pytest.fixture(scope="module")
def dead():
    return _dead()


def test_no_new_grabber_imports_a_missing_module(dead):
    new = sorted(dead - _allowed())
    assert not new, (
        f"guide grabbers import modules that do not exist (port them to the native app): {new}"
    )


def test_the_allowlist_only_shrinks(dead):
    stale = sorted(_allowed() - dead)
    assert not stale, f"these grabbers were ported: strike them from {ALLOW.name}: {stale}"
