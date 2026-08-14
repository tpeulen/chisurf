"""The dependency runs one way: ChiSurf may import chimol, not the reverse.

Why this exists
---------------
chimol is being made into its own repository (``~/dev/chimol``, symlinked into
``modules/`` the way tttrlib and imp-tricks already are). That move only stays
a *mechanical* one -- a directory move and an import rewrite -- if the code
does not reach back into ChiSurf, because after the move there is no ChiSurf
on the path to reach.

So the severing is done **here**, in place, against the real suite, and this is
the ledger. :data:`ALLOWLIST_PATH` lists every module that still imports
ChiSurf; it shrinks and never grows. When it is empty (or holds only the
deliberate soft dependencies described in the file itself) the move is
mechanical.

Why the import graph, not a grep
--------------------------------
The same reason ``test_qt_seam.py`` gives for the Qt seam, and it was a real
failure there: an earlier version of that check matched the text ``from
qtpy``, and its first run flagged a module whose only mention of Qt was **a
docstring explaining that it no longer imports Qt**. A comment about a
dependency is not a dependency. Several modules touched by this refactor now
carry exactly such a comment, so the graph is what is read.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

#: The package root: the relocated engine, installed from ``modules/chimol``
#: (``~/dev/chimol``) as the top-level ``chimol`` package. Resolved through
#: the import system rather than a relative path so the test follows whatever
#: installation the host actually uses.
PACKAGE = pathlib.Path(__import__("chimol").__file__).resolve().parent

#: Modules still importing ChiSurf. **Shrinking**: never add to this.
ALLOWLIST_PATH = pathlib.Path(__file__).resolve().parent / "chisurf_import_allowlist.txt"


def _allowlist() -> set[str]:
    if not ALLOWLIST_PATH.is_file():
        return set()
    return {
        line.strip()
        for line in ALLOWLIST_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def _modules() -> list[pathlib.Path]:
    return sorted(p for p in PACKAGE.rglob("*.py") if "__pycache__" not in p.parts)


def _runtime_body(tree: ast.AST) -> list[ast.AST]:
    """Every node except the contents of ``if TYPE_CHECKING:`` blocks.

    A ``TYPE_CHECKING`` block **never executes**, so an import inside one is
    not a runtime dependency -- it is a hint for a type checker, and on a
    machine where ChiSurf is installed it is a useful one. What this seam is
    about is whether chimol still *runs* without ChiSurf, so those blocks are
    excluded deliberately rather than by oversight.
    """
    skipped: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            test = node.test
            named = (
                (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING")
                or (isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING")
            )
            if named:
                for child in node.body:
                    for inner in ast.walk(child):
                        skipped.add(id(inner))
    return [n for n in ast.walk(tree) if id(n) not in skipped]


def _imports_chisurf(path: pathlib.Path) -> bool:
    """Whether *path* imports ``chisurf`` at runtime.

    Parsed, not grepped -- see the module docstring. Covers both spellings and
    an import anywhere in the file, including inside a function, which is how
    most of chimol's remaining ChiSurf imports are written (deferred so that
    importing the engine does not drag ChiSurf in). Annotation-only imports do
    not count; see :func:`_runtime_body`.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):  # pragma: no cover
        return False
    for node in _runtime_body(tree):
        if isinstance(node, ast.Import):
            if any(a.name == "chisurf" or a.name.startswith("chisurf.") for a in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            # `level > 0` is a relative import -- chimol's own package, never
            # ChiSurf. `module` is None for a bare `from . import x`.
            if node.level == 0 and node.module and (
                node.module == "chisurf" or node.module.startswith("chisurf.")
            ):
                return True
    return False


def _offenders() -> set[str]:
    return {
        str(p.relative_to(PACKAGE)) for p in _modules() if _imports_chisurf(p)
    }


def test_no_new_module_imports_chisurf():
    """Every ChiSurf importer is on the list, and the list only shrinks."""
    new = sorted(_offenders() - _allowlist())
    assert not new, (
        "these modules import ChiSurf and are not on the allow-list:\n  "
        + "\n  ".join(new)
        + "\n\nchimol is moving to its own repository, where ChiSurf is not on "
        "the path. Take what you need through a seam chimol owns (see "
        "`cmd/exporting.py` for the shape: ask inside a `try`, fall back to "
        "chimol's own answer -- or better, have the host *inject* the answer as "
        "`chisurf/plugins/chimol/__init__.py` does for the settings directory), "
        "or leave the code in the `app/` integration "
        "layer. Do not add a line to the allow-list."
    )


def test_the_allowlist_has_no_stale_entries():
    """A module that stopped importing ChiSurf comes off the list.

    Without this the list never shrinks in practice: the work gets done and the
    record still claims the dependency is there, so nobody can tell how close
    the move is.
    """
    stale = sorted(_allowlist() - _offenders())
    assert not stale, (
        "these are on the ChiSurf allow-list but no longer import ChiSurf -- "
        "delete the lines:\n  " + "\n  ".join(stale)
    )


#: Engine modules that ask for ChiSurf inside a ``try`` and carry their own
#: answer when it is not there. These **survive the move** -- they are the
#: target shape, not a violation -- so they are named rather than counted
#: among the dependencies still to be severed. Anything here must genuinely
#: degrade rather than fail; that is what :func:`test_soft_dependencies_are_guarded`
#: checks.
SOFT = {
    "cmd/exporting.py",
    # `io/atoms.py` used to be here -- it imported chisurf's `atom_dtype`
    # inside a try. The direction was inverted on 2026-08-14: chimol owns
    # `ATOM_DTYPE` and the host re-exports it, so the guarded import is gone
    # entirely and there is nothing left to sever.
    # Falls back to chimol's own secondary-structure path.
    "analysis/ss.py",
    # Attaches ChiSurf's console as the prompt's router when it is importable,
    # and uses chimol's own rule when it is not -- see `chimol/repl.py`. This
    # one was found by moving the CLI out of `app/`: it is toolkit-free, so the
    # Qt audit never saw it, and it imported ChiSurf at module scope.
    "cli.py",
}

#: Engine modules that import ChiSurf **unconditionally**. Every one of these
#: is a place the move would break.
#:
#: **Empty.** The engine no longer imports ChiSurf unconditionally anywhere:
#: the last entry was `analysis/elements.py`, which re-exported a periodic
#: table from `chisurf.core.fio.structure.elements` -- a table whose generator
#: already lived in chimol and which nothing in ChiSurf imported. chimol owns
#: it now. Keep this empty; a new name here means the move broke.
HARD: set[str] = set()


def test_the_engine_does_not_import_chisurf():
    """The half that actually moves must reach a state where it can.

    ``app/`` is the ChiSurf integration layer and may stay behind; everything
    else -- the renderer, the command language, the toolkit, the hosts -- is
    the engine, and it is what the new repository will contain. This is the
    check that says how close the *move* is, independently of how much of
    ``app/`` is left.
    """
    engine = {name for name in _offenders() if not name.startswith("app/")}
    assert engine == SOFT | HARD, (
        "the engine's ChiSurf dependencies changed: " + repr(sorted(engine))
        + "\n\nIf you severed one, take it out of HARD (and the allow-list). "
        "If you added one, take it through a seam instead -- the engine is the "
        "part that moves to a repository with no ChiSurf in it."
    )


@pytest.mark.parametrize("name", sorted(SOFT))
def test_soft_dependencies_are_guarded(name):
    """A "soft" dependency must actually be optional.

    The distinction only means something if the import is wrapped: an
    unguarded import in :data:`SOFT` would sail past
    :func:`test_the_engine_does_not_import_chisurf` while still breaking the
    move, which is the one thing this file exists to prevent.
    """
    tree = ast.parse((PACKAGE / name).read_text(encoding="utf-8"))
    guarded = {
        id(inner)
        for node in ast.walk(tree) if isinstance(node, ast.Try)
        for child in node.body for inner in ast.walk(child)
    }
    unguarded = [
        node for node in _runtime_body(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        and id(node) not in guarded
        and (
            (isinstance(node, ast.Import)
             and any(a.name.split(".")[0] == "chisurf" for a in node.names))
            or (isinstance(node, ast.ImportFrom) and node.level == 0
                and (node.module or "").split(".")[0] == "chisurf")
        )
    ]
    assert not unguarded, (
        f"{name} is listed as a soft dependency but imports ChiSurf outside a "
        f"`try` (line {unguarded[0].lineno}). Either guard it and fall back to "
        "chimol's own answer, or move it out of SOFT into HARD."
    )


@pytest.mark.parametrize("name", sorted(_allowlist()))
def test_every_allowlisted_module_exists(name):
    """A renamed or deleted module must not leave a line behind."""
    assert (PACKAGE / name).is_file(), f"{name} is on the allow-list but is gone"
