"""Guardrail: retired third-party packages stay out of the tree.

Each package listed in :data:`RETIRED` was a runtime dependency that either had
an in-tree replacement written for it -- because the whole package was a few
lines of code -- or was declared without anything ever importing it. This test
fails if an import or a packaging declaration brings one back.

Notes
-----
These packages may still be *installed* in a development environment, pulled in
transitively by other scientific packages. That is exactly why the guardrail is
needed: an accidental import would work on a developer machine and fail in a
packaged install, usually inside a ``try``/``except`` that turns it into a
silently degraded path rather than a crash.
"""

from __future__ import annotations

import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: ``import name -> (packaging name, what to use instead)``.
RETIRED = {
    "deprecation": (
        "deprecation",
        "use chisurf.core.decorators.deprecated",
    ),
    "click_didyoumean": (
        "click-didyoumean",
        "use chisurf.core.cli_support.DidYouMeanGroup",
    ),
    "tqdm": (
        "tqdm",
        "use chisurf.core.progress.progress / trange",
    ),
    "msgpack_numpy": (
        "msgpack-numpy",
        "encode arrays through the MMFDB payload codec",
    ),
    "pytools": ("pytools", "it was never imported"),
    "jsonschema": ("jsonschema", "it was never imported"),
}

#: Files whose only mention of the names is this test itself.
_ALLOWED = {"test/test_no_retired_dependency_imports.py"}

#: Packaging manifests that describe the chisurf runtime.
_MANIFESTS = (
    "pixi.toml",
    "pyproject.toml",
    "setup.py",
    "rattler-recipe/recipe.yaml",
    "test/settings/test_py314.toml",
)


def _python_sources():
    """Yield every Python source file under the folders chisurf ships.

    Yields
    ------
    pathlib.Path
    """
    for folder in ("chisurf", "modules/chinet", "modules/ndxplorer", "test"):
        folder_path = REPO_ROOT / folder
        if folder_path.exists():
            yield from folder_path.rglob("*.py")


def _declared_dependencies(text: str) -> set[str]:
    """Return the requirement names declared in a manifest.

    Comments are stripped first, so an explanatory note naming a retired
    package does not read as a declaration. Both the TOML (``name = "*"``) and
    the recipe YAML (``- name >=1.0``) spellings are recognised.

    Parameters
    ----------
    text : str
        Full manifest text.

    Returns
    -------
    set of str
        Lower-cased requirement names.
    """
    names = set()
    for line in text.splitlines():
        line = line.split("#", 1)[0]
        match = re.match(r"^\s*(?:-\s*)?[\"']?([A-Za-z0-9_.\-]+)", line)
        if match:
            names.add(match.group(1).lower())
    return names


@pytest.mark.parametrize("module", sorted(RETIRED))
def test_no_module_imports_retired_package(module):
    """No shipped source imports the retired package."""
    packaging_name, hint = RETIRED[module]
    pattern = re.compile(rf"^\s*(?:import\s+{module}\b|from\s+{module}[\s.])", re.MULTILINE)
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in _python_sources()
        if str(path.relative_to(REPO_ROOT)) not in _ALLOWED
        and pattern.search(path.read_text(encoding="utf-8", errors="ignore"))
    ]
    assert not offenders, (
        f"{packaging_name} is no longer a dependency ({hint}). Importing modules: {offenders}"
    )


@pytest.mark.parametrize("module", sorted(RETIRED))
def test_packaging_does_not_declare_retired_package(module):
    """No packaging manifest declares the retired package."""
    packaging_name, hint = RETIRED[module]
    offenders = []
    for rel in _MANIFESTS:
        path = REPO_ROOT / rel
        if not path.exists():
            continue
        declared = _declared_dependencies(path.read_text(encoding="utf-8", errors="ignore"))
        if packaging_name.lower() in declared:
            offenders.append(rel)
    assert not offenders, f"{packaging_name} reintroduced as a dependency ({hint}) in: {offenders}"
