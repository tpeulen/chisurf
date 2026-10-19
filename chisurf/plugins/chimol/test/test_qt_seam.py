"""chimol imports no Qt, anywhere.

The rule
--------
chimol runs in hosts that have no Qt: a toolkit-free desktop window on GLFW,
ChiSurf's emtk surface, a notebook and a browser canvas. The Qt plugin window
(``hosts/qt/``) that once housed it was retired on 2026-10-13, and with it the
last module allowed to import a toolkit. A module that imports Qt is a module
no host can use -- and the failure is rarely a clean ``ImportError``, because
Qt is installed in this environment. It is a viewer that constructs a
``QWidget`` with no ``QApplication`` and takes a **SIGABRT**, or a reader that
opens a file dialog on a machine with no display.

:data:`ALLOWLIST_PATH` was the record of the leaks not yet closed. It is empty
and **shrinks** -- adding a line to it is the wrong move; the right one is to
pass the toolkit object in from the host, or to hand the data over as a NumPy
array and let the host convert.

Why this is parsed rather than grepped
--------------------------------------
An earlier version of this check matched the text ``from qtpy``, and its first
run flagged a module whose only mention of Qt was **a docstring explaining that
it no longer imports Qt**. A comment about a dependency is not a dependency;
the import graph is what matters, so the import graph is what is read.
"""

from __future__ import annotations

import ast
import inspect
import pathlib

import pytest

#: The package root: the relocated engine (top-level ``chimol``, installed
#: from ``modules/chimol`` / ``~/dev/chimol``). Resolved through the import
#: system so the test follows the installation the host actually uses.
PACKAGE = pathlib.Path(inspect.getfile(__import__("chimol"))).resolve().parent

#: Modules still importing Qt. **Shrinking**: never add to this. Empty since
#: the Qt host was retired (2026-10-13).
ALLOWLIST_PATH = pathlib.Path(__file__).resolve().parent / "qt_import_allowlist.txt"


def _allowlist() -> set[str]:
    if not ALLOWLIST_PATH.is_file():
        return set()
    return {
        line.strip()
        for line in ALLOWLIST_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }


def _imports_qt(path: pathlib.Path) -> bool:
    """Whether *path* really imports Qt, by reading its import statements.

    Docstrings and comments do not count -- see the module docstring for the
    version of this check that thought they did. Neither do ``TYPE_CHECKING``
    imports: they never execute, so they cannot pull a toolkit into a host
    that has none -- the same rule ``test_chisurf_seam.py`` applies to the
    chisurf dependency.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:  # pragma: no cover - a broken file is a different test
        return False
    for node in _runtime_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in ("qtpy", "PyQt5", "PyQt6", "PySide2", "PySide6"):
                    return True
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in ("qtpy", "PyQt5", "PyQt6", "PySide2", "PySide6"):
                return True
    return False


def _runtime_nodes(tree: ast.AST) -> list[ast.AST]:
    """Every node except the contents of ``if TYPE_CHECKING:`` blocks.

    ``ast.walk`` cannot prune, so the excluded nodes are collected from each
    ``TYPE_CHECKING`` guard's body and filtered out by identity.
    """
    excluded: set[int] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.If)
            and isinstance(node.test, ast.Name)
            and node.test.id == "TYPE_CHECKING"
        ):
            for child in node.body + node.orelse:
                for sub in ast.walk(child):
                    excluded.add(id(sub))
    return [n for n in ast.walk(tree) if id(n) not in excluded]


def _modules() -> list[pathlib.Path]:
    return sorted(p for p in PACKAGE.rglob("*.py") if "__pycache__" not in p.parts)


def test_no_new_module_imports_qt():
    """Every Qt importer is on the list, and the list only shrinks."""
    offenders = {str(p.relative_to(PACKAGE)) for p in _modules() if _imports_qt(p)}
    allowed = _allowlist()
    new = sorted(offenders - allowed)
    assert not new, (
        "these modules import Qt and are not on the allow-list:\n  "
        + "\n  ".join(new)
        + "\n\nchimol has no Qt host. Pass the toolkit "
        "object in from the host, or hand the data over as an array and let the "
        "host convert. Do not add a line to the allow-list."
    )


def test_the_allowlist_has_no_stale_entries():
    """A module that stopped importing Qt comes off the list.

    Without this the list never shrinks in practice: the work gets done and the
    record still claims the leak is there.
    """
    offenders = {str(p.relative_to(PACKAGE)) for p in _modules() if _imports_qt(p)}
    stale = sorted(_allowlist() - offenders)
    assert not stale, (
        "these are on the Qt allow-list but no longer import Qt -- delete the "
        "lines:\n  " + "\n  ".join(stale)
    )


@pytest.mark.parametrize(
    "module",
    [
        "viewport/canvas.py",
        "hosts/native/canvas.py",
        "render/backend.py",
        "render/scene.py",
        "render/pack.py",
        "io/structure.py",
        "io/mesh_export.py",
        "core/colors.py",
        "core/settings/config.py",
    ],
)
def test_the_toolkit_free_core_stays_toolkit_free(module):
    """Named individually, because these are the ones that regress.

    Each of these has had Qt in it at some point: the draw path, the renderer
    interface, the structure reader. A general rule is easy to weaken by adding
    a line to a list; naming the files that matter is not.
    """
    path = PACKAGE / module
    # An assertion, not a skip: after a rename a stale entry would otherwise
    # pass silently for ever, and the file it names would be unguarded.
    assert path.is_file(), f"{module} does not exist -- update this list to the file's new path"
    assert not _imports_qt(path), f"{module} must not import Qt"


def test_the_qt_host_stays_retired():
    """``hosts/qt/`` was deleted at control parity with the toolkit-free host.

    The before/after inventories are ChiSurf's
    ``okf/plugins/emtk-ports/chimol/retire_*``. A Qt window coming back would be
    a second implementation of the application, and the reason it was retired
    is that two drift.
    """
    assert not (PACKAGE / "hosts" / "qt").exists(), "a Qt host is back in chimol"
