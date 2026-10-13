"""Guard: every module under ``chisurf/emtk/fit_pages/pages`` is reachable from the tree.

The plot package is a registry, not a scratchpad: a plot is used by being named
in a model widget's ``plot_classes`` (or imported by
``chisurf/emtk/fit_pages/pages/__init__.py``). Nothing discovers plot modules dynamically,
so a module nobody imports is dead — and dead plot modules are not harmless.
They keep obsolete dependencies alive: ``av_plot.py`` was the last
``pyqtgraph.opengl`` entry on the PRD-64 migration tracker, and
``surfaceplot/`` carried a runtime ``.ui`` form plus the guiqwt compatibility
shim, both of which the repo is removing.

This test fails when a module under ``chisurf/emtk/fit_pages/pages`` has no importer
anywhere in ``chisurf/`` outside its own subtree. Fix it by wiring the plot up
or by deleting it — never by special-casing it here.
"""

from __future__ import annotations

import ast
import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_PKG = _ROOT / "chisurf"
_PLOTS = _PKG / "emtk" / "fit_pages" / "pages"
_PLOTS_MODULE = "chisurf.emtk.fit_pages.pages"
_DECLARED_PATH = re.compile(r"^(chisurf(?:\.\w+)+):\w+$")


def _module_name(path: pathlib.Path) -> str:
    """Return the dotted module name of a source file inside ``chisurf/``.

    Parameters
    ----------
    path : pathlib.Path
        Absolute path to a ``.py`` file below :data:`_ROOT`.

    Returns
    -------
    str
        Dotted module name, e.g. ``chisurf.emtk.fit_pages.pages.lcurve``. A package
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
    are resolved against the file's own package. A string literal of the form
    ``"chisurf.x.y:Name"`` counts as an import of ``chisurf.x.y``: that is how a
    declarative registry names what it imports lazily.

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
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            # A declared ``"module:Class"`` path that a registry hands to
            # ``importlib`` (the fit-page table in ``chisurf.emtk.fit_pages.plots``)
            # imports that module as surely as an import statement does.
            match = _DECLARED_PATH.match(node.value)
            if match:
                found.add(match.group(1))
    return found


def _exported_names() -> dict[str, str]:
    """Map each public plot name to the submodule that ``plots/__init__.py`` serves it from.

    The package resolves its public names lazily from an ``_EXPORTS`` table, so
    ``from chisurf.emtk.fit_pages.pages import LinePlot`` is an import of ``plots.lineplot``
    even though no import statement names that module.

    Returns
    -------
    dict
        ``{"LinePlot": "chisurf.emtk.fit_pages.pages.lineplot", ...}``.
    """
    tree = ast.parse((_PLOTS / "__init__.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "_EXPORTS" for t in node.targets)
            and isinstance(node.value, ast.Dict)
        ):
            return {
                key.value: f"{_PLOTS_MODULE}.{value.value}"
                for key, value in zip(node.value.keys, node.value.values)
                if isinstance(key, ast.Constant) and isinstance(value, ast.Constant)
            }
    return {}


def _attribute_names(path: pathlib.Path) -> set[str]:
    """Every attribute name a source file reads (``x.LinePlot`` gives ``LinePlot``)."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:  # pragma: no cover - a broken file is another test's problem
        return set()
    return {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}


def test_no_orphan_plot_modules():
    """Every ``chisurf.emtk.fit_pages.pages`` submodule has an importer outside itself."""
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
    exported = _exported_names()
    for source in _PKG.rglob("*.py"):
        # A page names its siblings relatively (``from .emtk_text_view import ...``).
        if _PLOTS not in source.parents and "fit_pages" not in source.read_text(
            encoding="utf-8", errors="ignore"
        ):
            continue
        refs = {ref for ref in _imported_paths(source) if ref.startswith(_PLOTS_MODULE)}
        # `from chisurf.emtk.fit_pages.pages import LinePlot` reaches the module that serves that name.
        refs |= {
            exported[ref.rpartition(".")[2]]
            for ref in refs
            if ref.rpartition(".")[0] == _PLOTS_MODULE and ref.rpartition(".")[2] in exported
        }
        # So does `import chisurf.emtk.fit_pages.pages as p` followed by `p.LinePlot`: the plot registry
        # resolves every plot that way, inside a zero-argument factory.
        if _PLOTS_MODULE in refs:
            refs |= {exported[name] for name in _attribute_names(source) if name in exported}
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
