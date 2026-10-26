"""Every shipped Python source compiles.

A module nothing imports at test time can carry a syntax error for days: a
mechanical edit once moved an import inside a call's argument list in an rpc
client, and no test noticed because no test imported that client. Compiling
every file catches the whole class without importing anything.
"""

from __future__ import annotations

import pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]

#: Templated skeletons, not Python until rendered.
SKIP = ("cookiecutter-chisurf-plugin",)


def test_every_source_under_chisurf_compiles():
    """``compile()`` each ``chisurf/**/*.py``; report every file that fails."""
    failures = []
    for path in sorted((REPO / "chisurf").rglob("*.py")):
        if any(part in SKIP for part in path.parts):
            continue
        try:
            compile(path.read_bytes(), str(path), "exec", dont_inherit=True)
        except SyntaxError as error:
            failures.append(f"{path.relative_to(REPO)}:{error.lineno}: {error.msg}")
    assert not failures, "\n".join(failures)
