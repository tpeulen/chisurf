"""Guardrail: the conda recipe describes a build that can actually happen.

Packaging errors are invisible in a source checkout -- every entry point works,
because the module is right there on ``sys.path``, and every build tool is
present, because the developer environment has it. They surface only in a
released package, and only for the person who installed it.

Three real ones motivated this file:

* ``csc`` pointed at ``chisurf.cli`` for months after the module became
  ``chisurf.core.cli``, so the packaged command raised ``ModuleNotFoundError``;
  18 other entry points were missing entirely and ``burst-background`` had
  quietly dropped out.
* ``rattler-recipe/build.sh`` and ``build.bat`` were maintained for three months
  after an inline ``script:`` in the recipe made rattler-build ignore them.
* The recipe's own test invoked ``chisurf --version``, an entry point that takes
  no arguments and enters the Qt event loop -- it would have hung the build if
  the driver had not been skipping tests.
"""

from __future__ import annotations

import ast
import importlib.util
import pathlib
import re
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
RECIPE = REPO_ROOT / "rattler-recipe" / "recipe.yaml"

#: Import roots an entry-point module may resolve against: the repo itself plus
#: the sibling projects the installer adds to the runtime environment.
_IMPORT_ROOTS = (
    REPO_ROOT,
    REPO_ROOT / "modules" / "chinet",
    REPO_ROOT / "modules" / "ndxplorer",
    REPO_ROOT / "modules" / "quest",
    REPO_ROOT / "modules" / "mmfdb" / "src",
)

#: Toolchain packages that must not reappear in the recipe. ChiSurf compiles
#: nothing (see ``test_recipe_needs_no_toolchain``); what does compile --
#: tttrlib, labellib, the local modules -- is built by build_tools/, not here.
_TOOLCHAIN = frozenset({
    "cmake", "ninja", "make", "cython", "pythran", "swig", "pybind11", "eigen",
    "boost-cpp", "doxygen", "hdf5", "pkg-config", "vs2022_win-64",
})


def _recipe_text() -> str:
    """Return the recipe source."""
    return RECIPE.read_text(encoding="utf-8")


def _recipe_entry_points() -> dict[str, str]:
    """Return the recipe's generated entry-point block as ``{name: target}``."""
    text = _recipe_text()
    block = text.split("BEGIN_ENTRY_POINTS", 1)[1].split("END_ENTRY_POINTS", 1)[0]
    entry_points = {}
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        name, _, target = stripped[2:].partition("=")
        entry_points[name.strip()] = target.strip()
    return entry_points


def _section(name: str) -> list[str]:
    """Return the ``- `` items of a top-level ``requirements`` subsection."""
    text = _recipe_text()
    match = re.search(rf"^  {name}:\n((?:    .*\n|\n)*)", text, flags=re.MULTILINE)
    if not match:
        return []
    items = []
    for line in match.group(1).splitlines():
        stripped = line.split("#", 1)[0].strip()
        if stripped.startswith("- "):
            items.append(stripped[2:].strip())
    return items


def _module_path(module: str) -> pathlib.Path | None:
    """Return the file a dotted module name resolves to, without importing it.

    ``importlib`` is deliberately not used: resolving a plugin entry point would
    import its parent packages, and those pull in Qt.

    Parameters
    ----------
    module : str
        Dotted module name, e.g. ``chisurf.plugins.fcs.fcs_convert.cli``.

    Returns
    -------
    pathlib.Path or None
        The ``.py`` file (or package ``__init__.py``), or ``None`` when the
        module's top-level package is not present in this checkout.
    """
    parts = module.split(".")
    for root in _IMPORT_ROOTS:
        if not (root / parts[0]).is_dir():
            continue
        base = root.joinpath(*parts)
        for candidate in (base.with_suffix(".py"), base / "__init__.py"):
            if candidate.is_file():
                return candidate
        return None  # top level is here, so the rest must be too
    return None


def _bound_names(path: pathlib.Path) -> set[str]:
    """Return the names a module binds: definitions, assignments and imports.

    An entry point may name something the module only re-exports (a plugin's
    ``cli/__init__.py`` doing ``from .main import cli``), so an import alias
    counts as a binding.

    Parameters
    ----------
    path : pathlib.Path
        The module file to parse.

    Returns
    -------
    set of str
        Every name bound anywhere in the module.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def test_recipe_entry_points_are_current():
    """The generated block matches what ``collect_entry_points.py`` discovers.

    Regenerate with ``python rattler-recipe/collect_entry_points.py`` after
    adding, renaming or moving a CLI.
    """
    spec = importlib.util.spec_from_file_location(
        "_collect_entry_points", REPO_ROOT / "rattler-recipe" / "collect_entry_points.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    scripts, gui_scripts = module.read_pyproject_entry_points(REPO_ROOT / "pyproject.toml")
    scripts.update(module.discover_plugin_entry_points(REPO_ROOT / "chisurf" / "plugins"))

    expected = {**scripts, **gui_scripts}
    assert _recipe_entry_points() == expected, (
        "rattler-recipe/recipe.yaml is out of date -- run "
        "`python rattler-recipe/collect_entry_points.py`"
    )


@pytest.mark.parametrize("name,target", sorted(_recipe_entry_points().items()))
def test_entry_point_target_exists(name: str, target: str):
    """Every packaged command points at a module that exists and defines it."""
    module, _, attribute = target.partition(":")
    path = _module_path(module)
    if path is None and not any((root / module.split(".")[0]).is_dir() for root in _IMPORT_ROOTS):
        pytest.skip(f"{module.split('.')[0]} is a sibling project absent from this checkout")
    assert path is not None, f"entry point {name!r} points at missing module {module!r}"
    assert attribute in _bound_names(path), (
        f"{module}:{attribute} -- {path.relative_to(REPO_ROOT)} binds no {attribute!r}"
    )


def test_recipe_needs_no_toolchain():
    """No compiler or build tool is declared, because nothing is compiled.

    ``setup.py`` builds no extension; the burbulator C++ library and the Cython
    modules that justified the toolchain are retired. If that changes, this test
    is the place to say so -- and the declaration comes back with it.
    """
    sources = [
        p for p in (REPO_ROOT / "chisurf").rglob("*")
        if p.suffix in (".pyx", ".pxd", ".i")
    ]
    assert not sources, f"the tree compiles again: {sources} -- restore the recipe toolchain"

    text = _recipe_text()
    assert "\n  build:\n" not in text, "recipe declares a build: section for a build that compiles nothing"

    for section in ("host", "run"):
        declared = {
            item.split()[0].lower() for item in _section(section)
            if not item.startswith("${{")
        }
        assert not declared & _TOOLCHAIN, (
            f"toolchain packages in {section}: {sorted(declared & _TOOLCHAIN)} -- nothing in "
            "`pip install .` uses them"
        )


def test_recipe_has_no_ignored_build_script():
    """No ``build.sh``/``build.bat`` sits beside an inline ``script:``.

    rattler-build runs one or the other, and the inline script wins. A file that
    looks like the build but never runs is worse than no file: it gets
    maintained. Extend the ``script:`` in the recipe instead.
    """
    assert re.search(r"^  script:\n", _recipe_text(), flags=re.MULTILINE)
    for name in ("build.sh", "build.bat"):
        assert not (RECIPE.parent / name).exists(), (
            f"rattler-recipe/{name} would be ignored while recipe.yaml sets script:"
        )


def test_recipe_tests_terminate():
    """The recipe's tests are headless and finite.

    A ``script:`` test that runs a GUI entry point blocks the build in the Qt
    event loop. Every ``gui-scripts`` name is therefore banned from the test
    block; a script test may only run something that exits on its own.
    """
    text = _recipe_text()
    block = text.split("\ntests:", 1)[1].split("\nabout:", 1)[0]
    # Only the commands of `script:` tests can hang; a `python: imports:` list
    # names modules, and one of them is legitimately called `chisurf`.
    commands = "\n".join(
        re.findall(r"- script:\n((?:\s+-\s+.*\n)+)", block)
    )
    gui_names = [
        line.split("=", 1)[0].strip()
        for line in (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        .split("[project.gui-scripts]", 1)[-1]
        .split("[", 1)[0]
        .splitlines()
        if "=" in line
    ]
    for name in gui_names:
        assert not re.search(rf"^\s*-\s+{re.escape(name)}\b", commands, flags=re.MULTILINE), (
            f"recipe test runs the GUI entry point {name!r}, which never returns"
        )
