"""Guards for real defects found by mypy triage (wrong arity / missing required kwarg).

Each was a latent ``TypeError`` on an error path that no functional test reached.
"""

from __future__ import annotations

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_service_error_always_gets_error_code():
    """``service_error`` requires ``error_code``; omitting it crashed the error path."""
    offenders = []
    for path in (ROOT / "chisurf" / "server" / "services").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "service_error"
                and not any(k.arg == "error_code" or k.arg is None for k in node.keywords)
            ):
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not offenders, offenders


def test_mmfdb_admin_fill_experiment_type_table_takes_no_arguments():
    """The method refetches itself; passing the saved list raised TypeError."""
    tree = ast.parse((ROOT / "chisurf/plugins/core/mmfdb_admin/gui/tool.py").read_text())
    bad = [
        n.lineno
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "fill_experiment_type_table"
        and (n.args or n.keywords)
    ]
    assert not bad, bad
