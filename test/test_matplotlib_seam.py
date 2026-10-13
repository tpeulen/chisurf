"""Guard: matplotlib is being retired from the shipped package, and only shrinks.

**The rule: no new matplotlib.** ``test/matplotlib_import_allowlist.txt`` is a
shrinking record of files not yet routed -- never somewhere to add yourself.
When it empties, matplotlib leaves ``pixi.toml``, the recipe's ``run:`` and
ndXplorer's ``pyproject.toml``.

What matplotlib was doing in the tree, and where each use goes instead:

* **Colour tables and colour parsing** -- ``emtk.colormaps``.
* **Static figures written to a file** -- ``chiplot.figure``, drawn by emtk on
  the CPU rasteriser, so no window, GPU or Qt is needed.
* **Interactive plots** -- ``chiplot.Panel``, which is the plotting API anyway.
* **LaTeX formulas as images** -- a math typesetter in emtk (``emtk.mathtext``
  still hands the layout to matplotlib).

Test files are exempt: matplotlib stays the oracle for colormap parity tests.
"""

from __future__ import annotations

import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_ALLOWLIST = _ROOT / "test" / "matplotlib_import_allowlist.txt"

#: ChiMOL is excluded, not exempted: its port is tracked separately.
_EXCLUDED_PREFIXES = ("chisurf/plugins/chimol/",)

#: Permanent, deliberate importers, with the reason. Not dependencies: each one
#: serves matplotlib code the *user* runs and degrades to nothing when
#: matplotlib is absent. The guard checks they still guard the import.
_OPTIONAL_INTEGRATIONS = {
    "chisurf/core/console/mpl_inline.py": "inline figures for the user's own "
    "matplotlib calls in the console",
    "chisurf/core/console/shell.py": "shows a matplotlib Figure/Axes the user's "
    "console expression returned",
    "chisurf/core/console/formatters.py": "draws a matplotlib Figure the user's "
    "console expression returned",
}

#: matplotlib backends: modules matplotlib itself imports, by name, once the
#: console selected them. They subclass matplotlib's canvas, so they import it
#: at module scope -- and therefore nothing in the tree may import *them*.
_BACKEND_MODULES = {
    "chisurf/core/console/mpl_backend.py": "the console's inline backend "
    "(module://chisurf.core.console.mpl_backend)",
}

_PACKAGES = (
    _ROOT / "chisurf",
    _ROOT / "modules" / "ndxplorer",
)

#: Any spelling of the import, module scope or function-local.
_IMPORT_RE = re.compile(
    r"^\s*(?:import\s+matplotlib\b|from\s+matplotlib(?:\.\w+)*\s+import\b)",
    re.MULTILINE,
)


def _load_allowlist() -> set[str]:
    """Return the allow-listed repository-relative paths.

    Returns
    -------
    set of str
        Paths with blank lines and ``#`` comments stripped.
    """
    lines = _ALLOWLIST.read_text(encoding="utf-8").splitlines()
    return {ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")}


def _current_importers() -> set[str]:
    """Return every shipped file that imports matplotlib.

    Returns
    -------
    set of str
        Repository-relative POSIX paths; tests and excluded trees left out.
    """
    found: set[str] = set()
    for package in _PACKAGES:
        if not package.exists():
            continue
        for path in package.rglob("*.py"):
            if any(part in ("test", "tests") for part in path.parts):
                continue
            relative = path.relative_to(_ROOT).as_posix()
            if relative.startswith(_EXCLUDED_PREFIXES):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if _IMPORT_RE.search(text):
                found.add(relative)
    return found


def test_no_new_matplotlib_imports():
    """No shipped file imports matplotlib unless it is allow-listed."""
    known = _load_allowlist() | set(_OPTIONAL_INTEGRATIONS) | set(_BACKEND_MODULES)
    new_offenders = sorted(_current_importers() - known)
    assert not new_offenders, (
        "New matplotlib import(s) detected -- matplotlib is being retired:\n  "
        + "\n  ".join(new_offenders)
        + "\n\nDo NOT add these to test/matplotlib_import_allowlist.txt: that "
        "list only shrinks. Colours: emtk.colormaps. A figure written to a "
        "file: chiplot.figure. A plot in a GUI: chiplot.Panel."
    )


def test_allowlist_has_no_stale_entries():
    """Every allow-listed file still imports matplotlib; routed ones are struck."""
    stale = sorted(_load_allowlist() - _current_importers())
    assert not stale, (
        "Allow-list entries no longer import matplotlib -- strike them from "
        "test/matplotlib_import_allowlist.txt:\n  " + "\n  ".join(stale)
    )


def test_optional_integrations_guard_their_import():
    """The console integrations import matplotlib only inside a function."""
    for relative in _OPTIONAL_INTEGRATIONS:
        text = (_ROOT / relative).read_text(encoding="utf-8")
        module_scope = re.search(
            r"^(?:import\s+matplotlib\b|from\s+matplotlib(?:\.\w+)*\s+import\b)",
            text,
            re.MULTILINE,
        )
        assert module_scope is None, (
            f"{relative} imports matplotlib at module scope; an optional "
            "integration must import it where it is used, behind a guard"
        )


def test_backend_modules_are_imported_only_by_matplotlib():
    """No shipped file imports a backend module, so matplotlib stays optional."""
    offenders = []
    for relative in _BACKEND_MODULES:
        dotted = relative[: -len(".py")].replace("/", ".")
        name = dotted.rsplit(".", 1)
        pattern = re.compile(
            rf"^\s*(?:import\s+{re.escape(dotted)}\b|from\s+{re.escape(name[0])}\s+import\s+"
            rf"[^\n]*\b{re.escape(name[1])}\b)",
            re.MULTILINE,
        )
        for package in _PACKAGES:
            for path in package.rglob("*.py"):
                if pattern.search(path.read_text(encoding="utf-8", errors="ignore")):
                    offenders.append(path.relative_to(_ROOT).as_posix())
    assert not offenders, f"backend modules are matplotlib's to import: {offenders}"
