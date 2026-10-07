"""Designer retirement leaves only the explicitly deferred shell surface."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST = ROOT / "test/ui_file_allowlist.txt"
LOADER_ALLOWLIST = {"chisurf/gui/main.py", "chisurf/gui/retranslate.py"}
LOADER_NAMES = {"loadUi", "loadUiType", "init_with_ui", "qtpy_loadUi"}


def _allowed_files() -> set[str]:
    """Read the shrinking allow-list without comments or empty rows."""
    return {
        row.strip()
        for row in ALLOWLIST.read_text().splitlines()
        if row.strip() and not row.lstrip().startswith("#")
    }


def test_no_ui_files_outside_allowlist():
    """Every remaining Designer file has an explicit deferred owner."""
    actual = {str(path.relative_to(ROOT)) for path in (ROOT / "chisurf").rglob("*.ui")}
    assert not actual - _allowed_files(), sorted(actual - _allowed_files())


def test_no_ui_loader_tokens():
    """Retired loader calls and decorators are rejected outside the shell."""
    violations = []
    for path in sorted((ROOT / "chisurf").rglob("*.py")):
        relative = str(path.relative_to(ROOT))
        if relative in LOADER_ALLOWLIST or "cookiecutter-chisurf-plugin" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        for node in ast.walk(tree):
            name = (
                node.id
                if isinstance(node, ast.Name)
                else node.attr
                if isinstance(node, ast.Attribute)
                else None
            )
            if name in LOADER_NAMES:
                violations.append(f"{relative}:{node.lineno}: {name}")
    assert not violations, "\n".join(violations)


def test_allowlist_entries_exist():
    """Removing the final shell file also requires removing its allow-list row."""
    missing = [path for path in sorted(_allowed_files()) if not (ROOT / path).is_file()]
    assert not missing, missing
