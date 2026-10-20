"""Every non-Python file shipped inside ``chisurf/`` is installed with it.

``[tool.setuptools.package-data]`` is an allow-list of glob patterns. A data file
whose extension is missing from it is simply *not copied* into an installed
distribution -- and nothing complains. The package keeps working from a source
checkout, so the failure only appears for someone who installed it, which is the
worst possible place to find out.

This caught a real one: a shader read from disk when the render pipeline is built
was missed because ``*.wgsl`` was not in the list.

This is a static check: no display, no install.
"""

from __future__ import annotations

import fnmatch
import pathlib
import re
import subprocess
import warnings
from contextlib import closing
from functools import cache

import tomllib
from setuptools import Distribution, find_namespace_packages, find_packages
from setuptools._distutils.filelist import FileList
from setuptools._distutils.text_file import TextFile
from setuptools.config.expand import canonic_package_data

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
    # .c/.cpp/.h and .pml are covered now: the AV kernel's bundled C sources
    # went with the move to IMP.bff, and the viewer scripts are packaged.
    ".dcd",
    ".pdb",  # bundled molecular examples
    ".gnumeric",
    ".xlsx",
    ".xlsm",  # potential-energy databases
    ".pdf",  # reference document beside those databases
    ".icns",
    ".ico",  # icons (the Qt resource manifest went with the Qt shell)
    ".ini",
    ".yml",  # device and plugin configuration
    ".bmp",  # one more icon the installed copy would lack
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


def _git_ignored(paths: list[pathlib.Path]) -> set[pathlib.Path]:
    """Which of these git ignores.

    An ignored file is not shipped, so it has no business failing a packaging
    check. This matters in practice: opening the bundled SQLite database
    read-write leaves ``.db-wal``/``.db-shm`` beside it, both gitignored, and
    the sweep failed on transient artifacts nobody would ever package.

    Parameters
    ----------
    paths : list of pathlib.Path
        Candidates, relative to the repository root.

    Returns
    -------
    set of pathlib.Path
        The ignored subset; empty when git is unavailable.
    """
    if not paths:
        return set()
    try:
        result = subprocess.run(
            ["git", "check-ignore", "--stdin"],
            input="\n".join(str(path) for path in paths),
            capture_output=True,
            text=True,
            cwd=ROOT,
            check=False,
        )
    except OSError:
        return set()
    return {pathlib.Path(line) for line in result.stdout.splitlines() if line}


def _candidate_data_files() -> list[pathlib.Path]:
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
    ignored = _git_ignored(found)
    return [path for path in found if path not in ignored]


@cache
def _packaging_config() -> dict:
    """Read the release selection policy used by setuptools itself."""
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)["tool"]["setuptools"]


@cache
def _selected_packages() -> tuple[str, ...]:
    """Apply the configured namespace finder, including its actual exclusions."""
    find = _packaging_config()["packages"]["find"]
    finder = find_namespace_packages if find.get("namespaces", True) else find_packages
    result = []
    for where in find.get("where", ["."]):
        result.extend(
            finder(
                str(ROOT / where),
                include=find.get("include", ["*"]),
                exclude=find.get("exclude", []),
            )
        )
    return tuple(result)


def _build_command():
    """Configure real build_py selection without running a native build or egg_info."""
    config = _packaging_config()
    distribution = Distribution(
        {
            "name": "release-data-probe",
            "version": "0",
            "packages": list(_selected_packages()),
            "include_package_data": config.get("include-package-data", False),
            "package_data": canonic_package_data(dict(config.get("package-data", {}))),
            "exclude_package_data": canonic_package_data(
                dict(config.get("exclude-package-data", {}))
            ),
        }
    )
    command = distribution.get_command_obj("build_py")
    command.ensure_finalized()
    return command


def _shipped_data_files() -> list[pathlib.Path]:
    """Runtime data candidates, before positive extension globs can silently drop them."""
    command = _build_command()
    packages = {pathlib.Path(command.get_package_dir(name)): name for name in _selected_packages()}
    found = []
    for path in _candidate_data_files():
        parent = path.parent
        while parent not in packages and parent != pathlib.Path("."):
            parent = parent.parent
        if parent in packages and command.exclude_data_files(
            packages[parent], str(parent), [str(path)]
        ):
            found.append(path)
    return found


def _manifest_files(source_files: list[pathlib.Path]) -> list[str]:
    """Apply setuptools' MANIFEST reader to all possible source-tree inclusions."""
    files = FileList()
    files.allfiles = [str(path) for path in source_files]
    # A VCS plugin or an old SOURCES.txt can contribute any of these files.
    files.files = list(files.allfiles)
    with closing(
        TextFile(
            str(ROOT / "MANIFEST.in"),
            strip_comments=True,
            skip_blanks=True,
            join_lines=True,
            lstrip_ws=True,
            rstrip_ws=True,
        )
    ) as template:
        for line in template.readlines():
            files.process_template_line(line)
    return files.files


def test_namespace_discovery_does_not_install_test_packages():
    """Development packages are absent from real setuptools namespace discovery."""
    assert any(path.name in {"test", "tests"} for path in PACKAGE.rglob("*") if path.is_dir())
    assert not [
        name for name in _selected_packages() if {"test", "tests"}.intersection(name.split("."))
    ]


def test_sdist_and_wheel_data_selection_exclude_test_trees(tmp_path, monkeypatch):
    """Manifest pruning and build_py both exclude fixtures without dropping runtime data."""
    monkeypatch.chdir(ROOT)
    source_files = [
        path.relative_to(ROOT)
        for base in (PACKAGE, ROOT / "test")
        for path in base.rglob("*")
        if path.is_file() and not IGNORED_PARTS.intersection(path.parts)
    ]
    test_files = [path for path in source_files if {"test", "tests"}.intersection(path.parts)]
    assert test_files, "the actual fixture census must not be vacuous"
    manifest = _manifest_files(source_files)
    assert not [
        path for path in manifest if {"test", "tests"}.intersection(pathlib.Path(path).parts)
    ]
    command = _build_command()
    egg_info = tmp_path / "probe.egg-info"
    egg_info.mkdir()
    # Exercise wheel selection even with a stale source manifest containing fixtures.
    (egg_info / "SOURCES.txt").write_text("\n".join(map(str, source_files)) + "\n")
    command.existing_egg_info_dir = str(egg_info)
    command.build_lib = str(tmp_path / "build")
    with warnings.catch_warnings(record=True) as messages:
        selected = {
            pathlib.Path(directory) / name
            for _, directory, _, names in command._get_data_files()
            for name in names
        }
    # The deliberately stale manifest can produce setuptools' excluded-package
    # diagnostic before exclude-package-data filters it. Capture only that case.
    for message in messages:
        match = re.search(r"Package '([^']+)'", str(message.message))
        assert match and {"test", "tests"}.intersection(match[1].split(".")), str(message.message)
    assert not [path for path in selected if {"test", "tests"}.intersection(path.parts)]
    runtime = {
        pathlib.Path("chisurf/core/experiments/tcspc/tcspc_simulator.view.json"),
        pathlib.Path("chisurf/core/settings/settings_chisurf.yaml"),
    }
    assert all((ROOT / path).is_file() for path in runtime)
    assert runtime <= selected
    assert {str(path) for path in runtime} <= set(manifest)


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
        + "\n  ".join(
            f"{suffix or '(no suffix)'}  e.g. {example}"
            for suffix, example in sorted(uncovered.items())
        )
    )


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
