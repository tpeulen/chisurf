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
    "pyarrow-core": "pyarrow",
    "boost-histogram": "boost_histogram",
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
    "jupyter_client", "ipykernel", "traitlets", "notebook",
}

#: Packages of the surrounding scientific stack: separate repositories or
#: frameworks installed alongside chisurf rather than declared by it.
_SIBLING_PROJECTS = {
    "chisurf", "chinet", "ndxplorer", "quest", "mmfdb", "tttrlib", "IMP", "imp",
    "chimol", "RMF", "ihm", "pymol", "pymol2", "LabelLib",
}


def _declared_distributions() -> set[str]:
    """Return every distribution name declared by the packaging manifests.

    Returns
    -------
    set of str
        Lower-cased distribution names from ``pixi.toml`` (dependencies and
        PyPI dependencies) and every ``pyproject.toml`` dependency list,
        required and optional alike.
    """
    names: set[str] = set()

    pixi = (REPO_ROOT / "pixi.toml").read_text(encoding="utf-8")
    in_deps = False
    for line in pixi.splitlines():
        stripped = line.split("#", 1)[0].strip()
        if stripped.startswith("["):
            in_deps = stripped in ("[dependencies]", "[pypi-dependencies]")
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
