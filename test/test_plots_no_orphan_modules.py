"""Guard: every module under ``chisurf/gui/plots`` is reachable from the tree.

The plot package is a registry, not a scratchpad: a plot is used by being named
in a model widget's ``plot_classes`` (or imported by
``chisurf/gui/plots/__init__.py``). Nothing discovers plot modules dynamically,
so a module nobody imports is dead — and dead plot modules are not harmless.
They keep obsolete dependencies alive: ``av_plot.py`` was the last
``pyqtgraph.opengl`` entry on the PRD-64 migration tracker, and
``surfaceplot/`` carried a runtime ``.ui`` form plus the guiqwt compatibility
shim, both of which the repo is removing.

This test fails when a module under ``chisurf/gui/plots`` has no importer
anywhere in ``chisurf/`` outside its own subtree. Fix it by wiring the plot up
or by deleting it — never by special-casing it here.
"""

from __future__ import annotations

import ast
import pathlib

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_PKG = _ROOT / "chisurf"
_PLOTS = _PKG / "gui" / "plots"
_PLOTS_MODULE = "chisurf.gui.plots"


def _module_name(path: pathlib.Path) -> str:
    """Return the dotted module name of a source file inside ``chisurf/``.

    Parameters
    ----------
    path : pathlib.Path
        Absolute path to a ``.py`` file below :data:`_ROOT`.

    Returns
    -------
    str
        Dotted module name, e.g. ``chisurf.gui.plots.lcurve``. A package
        ``__init__.py`` resolves to the package itself.
    """
    rel = path.relative_to(_ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _imported_paths(path: pathlib.Path) -> set[str]:
    """Collect the dotted paths a source file imports.

    Both the imported module and each ``from ... import <name>`` target are
    recorded, because a submodule may be pulled in either way. Relative imports
    are resolved against the file's own package.

    Parameters
    ----------
    path : pathlib.Path
        Absolute path to a ``.py`` file below :data:`_ROOT`.

    Returns
    -------
    set of str
        Absolute dotted paths referenced by the file's import statements.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:  # pragma: no cover - a broken file is another test's problem
        return set()

    package = _module_name(path)
    if path.name != "__init__.py":
        package = package.rpartition(".")[0]

    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package
                for _ in range(node.level - 1):
                    base = base.rpartition(".")[0]
                module = f"{base}.{node.module}" if node.module else base
            else:
                module = node.module or ""
            if not module:
                continue
            found.add(module)
            found.update(f"{module}.{alias.name}" for alias in node.names)
    return found


def test_no_orphan_plot_modules():
    """Every ``chisurf.gui.plots`` submodule has an importer outside itself."""
    candidates = {}
    for entry in sorted(_PLOTS.iterdir()):
        if entry.name.startswith(("_", ".")) or entry.name == "__pycache__":
            continue
        if entry.is_dir() and (entry / "__init__.py").exists():
            candidates[f"{_PLOTS_MODULE}.{entry.name}"] = entry
        elif entry.suffix == ".py":
            candidates[f"{_PLOTS_MODULE}.{entry.stem}"] = entry

    # Parse each source at most once, and only those whose text could name a
    # plot module at all; a per-candidate rescan would re-parse the whole tree.
    imports_by_file = {}
    for source in _PKG.rglob("*.py"):
        if "plots" not in source.read_text(encoding="utf-8", errors="ignore"):
            continue
        refs = {ref for ref in _imported_paths(source) if ref.startswith(_PLOTS_MODULE)}
        if refs:
            imports_by_file[source] = refs

    orphans = []
    for dotted, entry in candidates.items():
        subtree = entry if entry.is_dir() else None
        importers = (
            source
            for source, refs in imports_by_file.items()
            if source != entry
            and (subtree is None or subtree not in source.parents)
            and any(ref == dotted or ref.startswith(f"{dotted}.") for ref in refs)
        )
        if next(importers, None) is None:
            orphans.append(dotted)

    assert not orphans, (
        "Plot module(s) with no importer anywhere in chisurf/ — wire them up or "
        "delete them; nothing discovers plots dynamically:\n  " + "\n  ".join(orphans)
    )
