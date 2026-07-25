"""Guardrail: the third-party table editor stays out of the tree.

ChiSurf's tables are :mod:`chisurf.gui.widgets.chitable`. The ``guidata``
dependency existed solely for its ``DataFrameEditor`` and was removed once the
last two call sites (the Data-table plot and the legacy burst selector) moved
over. This test fails if an import or a packaging declaration reintroduces it,
which would quietly bring back a conda dependency and a second table style.
"""

from __future__ import annotations

import pathlib
import re

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Files whose only mention of the name is this test or an explanatory comment.
_ALLOWED = {
    "test/test_no_guidata_import.py",
    "rattler-recipe/recipe.yaml",
}

_IMPORT_PATTERN = re.compile(r"^\s*(?:import\s+guidata|from\s+guidata[\s.])", re.MULTILINE)


def _python_sources():
    """Yield every tracked Python source file under ``chisurf/``.

    Yields
    ------
    pathlib.Path
    """
    yield from (REPO_ROOT / "chisurf").rglob("*.py")


def test_no_module_imports_guidata():
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in _python_sources()
        if _IMPORT_PATTERN.search(path.read_text(encoding="utf-8", errors="ignore"))
    ]
    assert not offenders, (
        "guidata is no longer a dependency; use chisurf.gui.widgets.chitable "
        f"instead. Importing modules: {offenders}"
    )


def test_packaging_does_not_declare_guidata():
    offenders = []
    for rel in ("pixi.toml", "pyproject.toml", "setup.py", "build_tools/setup_runtime.sh"):
        path = REPO_ROOT / rel
        if not path.exists() or rel in _ALLOWED:
            continue
        if "guidata" in path.read_text(encoding="utf-8", errors="ignore"):
            offenders.append(rel)
    assert not offenders, f"guidata reintroduced as a dependency in: {offenders}"
