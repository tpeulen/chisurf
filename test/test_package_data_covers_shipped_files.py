"""Every non-Python file shipped inside ``chisurf/`` is installed with it.

``[tool.setuptools.package-data]`` is an allow-list of glob patterns. A data file
whose extension is missing from it is simply *not copied* into an installed
distribution -- and nothing complains. The package keeps working from a source
checkout, so the failure only appears for someone who installed it, which is the
worst possible place to find out.

This caught a real one: chigame's ``sprite.wgsl`` is read from disk when the
render pipeline is built, and ``*.wgsl`` was not in the list.

This is a static check: no Qt, no display, no install.
"""

from __future__ import annotations

import fnmatch
import pathlib
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "chisurf"

#: Extensions that are build artefacts, caches or editor droppings rather than
#: shipped data. These are expected to be absent from an installed copy.
IGNORED_SUFFIXES = {
    ".py",
    ".pyc",
    ".pyo",
    ".pyd_",
    ".log",
    ".bak",
    ".orig",
    ".rej",
    ".swp",
    ".DS_Store",
    "",
}

#: Directories whose contents are never installed.
IGNORED_PARTS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "_build"}

#: Extensions that are in the tree, are *not* covered by any package-data
#: pattern, and were already like that. Each one is a file type that will be
#: **missing from an installed distribution** -- icons the GUI loads, device
#: configuration, and the potential-energy databases among them.
#:
#: This is a **shrinking** list. It exists so this test can catch a *newly*
#: uncovered type today rather than waiting for the whole backlog to be paid
#: off; it is not somewhere to add a new extension. Adding a pattern to
#: pyproject.toml and striking the line here is the fix.
KNOWN_UNCOVERED = {
    ".c", ".cpp", ".h",          # bundled C sources for the AV kernel
    ".dcd", ".pdb", ".pml",      # structure fixtures and viewer scripts
    ".gnumeric", ".xlsx", ".xlsm",  # potential-energy databases
    ".pdf",                      # reference document beside those databases
    ".icns", ".ico", ".qrc",     # icons and the Qt resource manifest
    ".ini", ".yml",              # device and plugin configuration
    ".pdat",                     # the fortune database
    ".mti", ".spc", ".rmf3", ".bur",  # measurement fixtures
    ".bmp",                      # one more icon the installed copy would lack
}


def _patterns() -> list[str]:
    """Read every package-data glob from ``pyproject.toml``.

    Returns
    -------
    list of str
        Patterns from all package-data sections, flattened.
    """
    with (ROOT / "pyproject.toml").open("rb") as handle:
        config = tomllib.load(handle)
    data = config["tool"]["setuptools"]["package-data"]
    patterns: list[str] = []
    for globs in data.values():
        patterns.extend(globs)
    return patterns


def _shipped_data_files() -> list[pathlib.Path]:
    """Every candidate data file under the package.

    Returns
    -------
    list of pathlib.Path
        Paths relative to the repository root.
    """
    found = []
    for path in PACKAGE.rglob("*"):
        if not path.is_file():
            continue
        if IGNORED_PARTS.intersection(path.parts):
            continue
        if path.suffix in IGNORED_SUFFIXES or path.name.startswith("."):
            continue
        found.append(path.relative_to(ROOT))
    return found


def test_every_shipped_data_extension_has_a_package_data_pattern():
    """No data file type is silently dropped from an installed distribution."""
    patterns = _patterns()
    uncovered: dict[str, str] = {}
    for path in _shipped_data_files():
        if any(fnmatch.fnmatch(path.name, pattern) for pattern in patterns):
            continue
        if path.suffix in KNOWN_UNCOVERED:
            continue
        # Report one example per extension: the fix is per-pattern, not per-file.
        uncovered.setdefault(path.suffix, str(path))

    assert not uncovered, (
        "these file types live in chisurf/ but no [tool.setuptools.package-data] "
        "pattern matches them, so they will be missing from an installed copy:\n  "
        + "\n  ".join(f"{suffix or '(no suffix)'}  e.g. {example}" for suffix, example in sorted(uncovered.items()))
    )


def test_the_chigame_shader_is_covered():
    """The shader chigame reads at runtime is installed.

    Pinned by name rather than only by the sweep above, because this file has a
    hard runtime dependency: without it no render pipeline can be built at all.
    """
    shader = PACKAGE / "gui" / "chigame" / "shaders" / "sprite.wgsl"
    assert shader.is_file(), "the sprite shader moved; update this test and the packaging"
    assert any(fnmatch.fnmatch(shader.name, pattern) for pattern in _patterns())


def test_the_known_uncovered_list_does_not_rot():
    """Every entry in the shrinking list is still a real gap.

    An extension that has since been covered, or that no longer appears in the
    tree, must be struck -- otherwise the list quietly grows stale and stops
    describing anything.
    """
    patterns = _patterns()
    present = {path.suffix for path in _shipped_data_files()}
    stale = {
        suffix
        for suffix in KNOWN_UNCOVERED
        if suffix not in present
        or any(fnmatch.fnmatch("x" + suffix, pattern) for pattern in patterns)
    }
    assert not stale, f"strike these from KNOWN_UNCOVERED, they are no longer gaps: {sorted(stale)}"
