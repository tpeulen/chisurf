"""Guardrail: a module-level import must come from a declared dependency.

An import that nothing declares works on a developer machine -- the package is
almost always installed transitively by something else -- and fails only in a
packaged install, where it surfaces as a plugin that will not load or a tool
that raises on its first use. ``tqdm`` sat in `chisurf/core` like that; so did
``psutil`` and ``scikit_fluorescence``.

The rule is about *module-level* imports only: an import inside a function, a
``try`` block or an ``if`` is an optional feature that the code is expected to
cope without, and those are deliberately not policed here.
"""

from __future__ import annotations

import ast
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Distribution name -> the module name it installs, where the two differ.
_IMPORT_NAMES = {
    "pyyaml": "yaml",
    "pyqt": "PyQt5",
    "pyqt5": "PyQt5",
    "python-docx": "docx",
    "pytables": "tables",
    "tables": "tables",
    "scikit-image": "skimage",
    "scikit-learn": "sklearn",
    "pyopengl": "OpenGL",
    "msgpack-python": "msgpack",
    "typing-extensions": "typing_extensions",
    "pillow": "PIL",
    "latexify-py": "latexify",
    "pyzmq": "zmq",
    "ipython": "IPython",
    "labellib": "LabelLib",
    "beautifulsoup4": "bs4",
}

#: Packages that are in the environment for reasons other than a chisurf import
#: (build tools, test tools) or that ship inside another declared distribution.
_EXTRA_ALLOWED = {
    "pytest", "mypy", "setuptools", "pkg_resources", "pip", "numpy", "matplotlib",
    "mpl_toolkits", "contourpy", "sip", "shiboken6", "PyQt5", "PySide2", "PySide6",
    "jupyter_client", "ipykernel", "traitlets",
}

#: Packages of the surrounding scientific stack: separate repositories or
#: frameworks installed alongside chisurf rather than declared by it.
_SIBLING_PROJECTS = {
    "chisurf", "ndxplorer", "quest", "mmfdb", "tttrlib", "IMP", "imp",
    "chimol", "RMF", "ihm", "pymol", "pymol2", "LabelLib",
}


#: pixi.toml sections that count as "available when the test suite runs" --
#: the packaged runtime (``[dependencies]``/``[pypi-dependencies]``) plus the
#: ``test`` feature (``pixi run -e test ...``, which every test invocation
#: uses), since a test-only import genuinely does not need to be in the
#: packaged app.
_DECLARING_SECTIONS = ("[dependencies]", "[pypi-dependencies]", "[feature.test.dependencies]")


def _declared_distributions() -> set[str]:
    """Return every distribution name declared by the packaging manifests.

    Returns
    -------
    set of str
        Lower-cased distribution names from ``pixi.toml`` (dependencies, PyPI
        dependencies, and the ``test`` feature) and every ``pyproject.toml``
        dependency list, required and optional alike.
    """
    names: set[str] = set()

    pixi = (REPO_ROOT / "pixi.toml").read_text(encoding="utf-8")
    in_deps = False
    for line in pixi.splitlines():
        stripped = line.split("#", 1)[0].strip()
        if stripped.startswith("["):
            in_deps = stripped in _DECLARING_SECTIONS
            continue
        if in_deps and "=" in stripped:
            names.add(stripped.split("=", 1)[0].strip().strip('"'))

    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for match in re.finditer(r'"([A-Za-z0-9_.\-]+)\s*[<>=!\[]?', pyproject):
        names.add(match.group(1))

    return {name.lower() for name in names if name}


def _allowed_modules() -> set[str]:
    """Return the module names a shipped source file may import at module level."""
    modules = set(_EXTRA_ALLOWED) | set(_SIBLING_PROJECTS) | set(sys.stdlib_module_names)
    for dist in _declared_distributions():
        modules.add(_IMPORT_NAMES.get(dist, dist.replace("-", "_")))
    return modules


#: Packages the dev env needs only to build the compiled modules.
_BUILD_ONLY = {
    "pip", "cmake", "ninja", "swig", "scikit-build-core", "pybind11",
    "llvm-openmp", "cmake-build-extension", "python",
    # hdf5 is a build dependency of the photon library, whose CMake requires it
    # unconditionally. It is not part of the released runtime -- the shipped
    # package depends on that library, already linked -- so it belongs here
    # rather than in the recipe's run list.
    "hdf5",
}

#: In the dev env but deliberately not in the released package, with the reason.
_NOT_SHIPPED = {
    "latexify-py": "conda-forge has no Python 3.12 build; the parse-model LaTeX "
                   "view falls back to its in-tree converter",
}

#: In the released package but not the dev env, with the reason.
_SHIPPED_ONLY = {
    "micromamba": "the updater drives it as an executable in an installed app; "
                  "developers already have a solver",
    "emtk": "a sibling checkout installed editable in the dev environment, the "
            "way tttrlib is; the shipped app gets the built package",
}

#: Runtime packages a wheel cannot or need not declare, with the reason.
_NOT_ON_PYPI = {
    "micromamba": "a conda package manager, not a Python distribution",
}

#: Distribution spellings that differ between conda and PyPI.
_PYPI_NAMES = {
    "pyqt": "pyqt5",
    "pytables": "tables",
    "msgpack-python": "msgpack",
    "wgpu-py": "wgpu",
}


def _pixi_dependencies() -> set[str]:
    """Return the names in ``pixi.toml`` ``[dependencies]``/``[pypi-dependencies]``."""
    names = set()
    in_deps = False
    for line in (REPO_ROOT / "pixi.toml").read_text(encoding="utf-8").splitlines():
        stripped = line.split("#", 1)[0].strip()
        if stripped.startswith("["):
            in_deps = stripped in ("[dependencies]", "[pypi-dependencies]")
            continue
        if in_deps and "=" in stripped:
            names.add(stripped.split("=", 1)[0].strip().strip('"').lower())
    return names


def _recipe_run_dependencies() -> set[str]:
    """Return the names in the recipe's ``requirements.run`` list."""
    text = (REPO_ROOT / "rattler-recipe" / "recipe.yaml").read_text(encoding="utf-8")
    run = text.split("  run:", 1)[1].split("\ntests:", 1)[0]
    names = set()
    for line in run.splitlines():
        stripped = line.split("#", 1)[0].strip()
        if stripped.startswith("- ") and "${{" not in stripped:
            names.add(stripped[2:].split()[0].lower())
    return names


def test_dev_env_and_released_package_declare_the_same_runtime():
    """``pixi.toml`` and the recipe's ``run:`` describe one runtime.

    They are read by different consumers -- developers and the conda package --
    and drift between them is invisible until an install that only has one of
    them fails. Every difference must be a deliberate, explained one.
    """
    pixi = _pixi_dependencies() - _BUILD_ONLY
    recipe = _recipe_run_dependencies() - _BUILD_ONLY

    missing_from_package = sorted(pixi - recipe - set(_NOT_SHIPPED))
    missing_from_dev_env = sorted(recipe - pixi - set(_SHIPPED_ONLY))

    assert not missing_from_package, (
        "declared for development but not shipped in the conda package -- add "
        f"them to rattler-recipe/recipe.yaml run:, or to _NOT_SHIPPED with a "
        f"reason: {missing_from_package}"
    )
    assert not missing_from_dev_env, (
        "shipped in the conda package but not declared for development -- add "
        f"them to pixi.toml [dependencies], or to _SHIPPED_ONLY with a reason: "
        f"{missing_from_dev_env}"
    )


def _pyproject_dependencies() -> set[str]:
    """Return every distribution ``pyproject.toml`` declares, required or extra."""
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    names = set()
    for block in re.findall(r"(?:^|\n)\w[\w.-]*\s*=\s*\[(.*?)\]", text, re.DOTALL):
        for match in re.finditer(r'"([A-Za-z0-9_.\-]+)', block):
            names.add(match.group(1).lower())
    return names


def test_the_wheel_declares_the_same_runtime_as_the_conda_package():
    """``pyproject.toml`` covers everything the conda runtime has.

    A ``pip install chisurf`` gets only this list, so anything the application
    imports has to appear here -- as a requirement, or as an extra when the code
    detects it at runtime and works without it.
    """
    conda_runtime = (_pixi_dependencies() | _recipe_run_dependencies()) - _BUILD_ONLY
    declared = _pyproject_dependencies()

    missing = sorted(
        name
        for conda_name in conda_runtime - set(_NOT_ON_PYPI)
        if (name := _PYPI_NAMES.get(conda_name, conda_name)) not in declared
    )
    assert not missing, (
        "in the conda runtime but not in pyproject.toml -- add them to "
        "[project.dependencies], or to an extra if the code copes without them, "
        f"or to _NOT_ON_PYPI with a reason: {missing}"
    )


class _ModuleLevelImports(ast.NodeVisitor):
    """Collect the top-level packages a module imports unconditionally."""

    def __init__(self):
        self.names: list[tuple[str, int]] = []

    def generic_visit(self, node):
        """Walk into everything except bodies where an import may legally fail."""
        if isinstance(node, (ast.Try, ast.FunctionDef, ast.AsyncFunctionDef, ast.If)):
            return
        super().generic_visit(node)

    def visit_Import(self, node):
        """Record ``import x`` at module level."""
        for alias in node.names:
            self.names.append((alias.name.split(".")[0], node.lineno))

    def visit_ImportFrom(self, node):
        """Record ``from x import y`` at module level, ignoring relative imports."""
        if not node.level and node.module:
            self.names.append((node.module.split(".")[0], node.lineno))


def _shipped_sources():
    """Yield the Python files that ship inside the chisurf package.

    The cookiecutter plugin template is skipped: it is not importable Python but
    a set of files with substitution markers.

    Yields
    ------
    pathlib.Path
    """
    for path in (REPO_ROOT / "chisurf").rglob("*.py"):
        if "cookiecutter" in path.parts or "{{cookiecutter.plugin_name}}" in str(path):
            continue
        yield path


def test_module_level_imports_are_declared():
    """Every unconditional import in chisurf/ resolves to a declared dependency."""
    allowed = _allowed_modules()
    offenders = []
    for path in _shipped_sources():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:  # pragma: no cover - template or broken file
            continue
        visitor = _ModuleLevelImports()
        visitor.visit(tree)
        for name, lineno in visitor.names:
            if name in allowed:
                continue
            # A module sitting next to the importer (test fixtures do this) is
            # local code found through sys.path, not a dependency.
            if (path.parent / f"{name}.py").exists() or (path.parent / name).is_dir():
                continue
            offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno} imports {name!r}")

    assert not offenders, (
        "module-level imports of packages no manifest declares -- declare the "
        "dependency, move the import inside a try/function so the feature is "
        "optional, or drop the code:\n  " + "\n  ".join(sorted(offenders))
    )
