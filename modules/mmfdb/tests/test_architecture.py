"""Architecture guardrails for the standalone MMFDB package."""

from __future__ import annotations

import ast
import sqlite3
from pathlib import Path
from unittest.mock import patch

PACKAGE_ROOT = Path(__file__).parents[1] / "src" / "mmfdb"


def test_classes_do_not_shadow_methods_in_the_same_body() -> None:
    """A class body must not silently replace an earlier method definition."""
    duplicates: list[str] = []
    for path in PACKAGE_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            definitions: dict[str, int] = {}
            for item in node.body:
                if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if item.name in definitions:
                    relative = path.relative_to(PACKAGE_ROOT)
                    duplicates.append(
                        f"{relative}:{item.lineno} {node.name}.{item.name} "
                        f"(first defined at line {definitions[item.name]})"
                    )
                definitions[item.name] = item.lineno

    assert duplicates == []


def test_standalone_package_does_not_import_chisurf() -> None:
    """MMFDB must remain importable without the ChiSurf host application."""
    violations: list[str] = []
    for path in PACKAGE_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            imported: list[str] = []
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported = [node.module]
            if any(name == "chisurf" or name.startswith("chisurf.") for name in imported):
                violations.append(f"{path.relative_to(PACKAGE_ROOT)}:{node.lineno}")

    assert violations == []


def test_readonly_repository_cannot_mutate_database(tmp_path: Path) -> None:
    """The readonly constructor must enforce its contract at SQLite level."""
    from mmfdb.repository import MFDatabase

    path = tmp_path / "readonly.db"
    with MFDatabase(path) as writable:
        writable.conn.execute("CREATE TABLE readonly_probe (value TEXT)")
        writable.conn.commit()

    with MFDatabase(path, readonly=True) as readonly:
        assert readonly.conn.execute("PRAGMA query_only").fetchone()[0] == 1
        try:
            readonly.conn.execute("INSERT INTO readonly_probe VALUES ('no')")
        except sqlite3.OperationalError as error:
            assert "readonly" in str(error).lower()
        else:
            raise AssertionError("readonly MFDatabase accepted a write")


def test_current_database_open_does_not_reconcile_schema(tmp_path: Path) -> None:
    """Schema reconciliation is a migration step, not a normal open side effect."""
    from mmfdb.repository import MFDatabase

    path = tmp_path / "current.db"
    MFDatabase(path).close()

    with patch("mmfdb.schema.schema.reconcile_current_schema") as reconcile:
        MFDatabase(path).close()

    reconcile.assert_not_called()
