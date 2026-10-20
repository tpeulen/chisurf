"""Every package in ChiSurf's stack declares the licence docs/licensing.md says it has.

Owner decision 2026-10-20: chisurf and its family (emtk, chimol, mmfdb, ndxplorer,
quest, imp-tricks, labelizer) are MIT, tttrlib is BSD-3-Clause, and IMP.bff is
LGPL-2.1-or-later as an IMP module. The audit that recorded this found the
declarations had drifted apart: imp.bff's pyproject said MPL-2.0 beside a
COPYING.LGPL, imp-tricks' recipe said BSD-3-Clause beside an MIT LICENSE, the
splash art still carried the GPL notice. The table in docs/licensing.md is the
single statement; these tests hold each repository's metadata, the installer's
licence texts, the tracker and the About window to it.

Companion repositories are found as ``modules/<name>`` or as siblings of this
checkout (``~/dev/<repo>``); a test for a repository that is not checked out skips.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

try:
    import tomllib
except ImportError:  # pragma: no cover - Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parents[1]
LICENSING = ROOT / "docs" / "licensing.md"

#: Package name in the table -> repository directory name (sibling or modules/).
REPOSITORY = {
    "chisurf": None,
    "emtk": "emtk",
    "chimol": "chimol",
    "mmfdb": "mmfdb",
    "ndxplorer": "ndxplorer",
    "quest": "quest",
    "imp-tricks": "imp-tricks",
    "labelizer": "labelizer",
    "tttrlib": "tttrlib",
    "imp-bff": "imp.bff",
}

#: Recipes that package something other than the repository's own library.
#: imp.bff's ``conda-recipe/imp`` builds the whole of IMP, GPL modules included.
FOREIGN_RECIPES = {"imp.bff/conda-recipe/imp/recipe.yaml"}


def stack_table() -> dict[str, str]:
    """The package -> SPDX table between the stack-licences markers."""
    text = LICENSING.read_text(encoding="utf-8")
    block = text.split("<!-- stack-licences:start -->", 1)[1].split("<!-- stack-licences:end -->", 1)[0]
    rows = {}
    for line in block.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2 or cells[0] in ("Package", "") or set(cells[0]) <= {"-"}:
            continue
        rows[cells[0]] = cells[1]
    return rows


def repository(package: str) -> Path | None:
    """The checkout of *package*, or None when it is not on this machine."""
    name = REPOSITORY[package]
    if name is None:
        return ROOT
    for candidate in (ROOT / "modules" / name, ROOT.parent / name):
        if (candidate / "pyproject.toml").is_file():
            return candidate.resolve()
    return None


def declared_licence(pyproject: Path) -> str:
    """``project.license`` as a string, whether PEP 639 string or legacy table."""
    project = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]
    licence = project.get("license", "")
    if isinstance(licence, dict):
        return licence.get("text", "")
    return licence


def test_the_table_names_every_package():
    assert set(stack_table()) == set(REPOSITORY)


def test_the_owner_decision_is_what_the_table_says():
    table = stack_table()
    assert table["tttrlib"] == "BSD-3-Clause"
    assert table["imp-bff"] == "LGPL-2.1-or-later"
    assert {table[p] for p in REPOSITORY if p not in ("tttrlib", "imp-bff")} == {"MIT"}



@pytest.mark.parametrize("package", sorted(REPOSITORY))
def test_pyproject_declares_the_table_licence(package):
    repo = repository(package)
    if repo is None:
        pytest.skip(f"{package} is not checked out here")
    assert declared_licence(repo / "pyproject.toml") == stack_table()[package]


@pytest.mark.parametrize("package", sorted(REPOSITORY))
def test_recipes_declare_the_table_licence(package):
    repo = repository(package)
    if repo is None:
        pytest.skip(f"{package} is not checked out here")
    recipes = [p for pattern in ("rattler-recipe/*.yaml", "conda-recipe/*.yaml", "recipes/*/recipe.yaml")
               for p in repo.glob(pattern) if p.name in ("recipe.yaml", "recipe-core.yaml", "meta.yaml")]
    recipes = [p for p in recipes if f"{repo.name}/{p.relative_to(repo).as_posix()}" not in FOREIGN_RECIPES]
    for recipe in recipes:
        for value in re.findall(r"^\s*license:\s*(.+?)\s*$", recipe.read_text(encoding="utf-8"), re.M):
            if "{{" in value:  # read from pyproject at build time (ndxplorer)
                continue
            assert value == stack_table()[package], f"{recipe}: {value}"


def test_the_application_reports_its_licence():
    from chisurf.core.info import __license__

    assert __license__ == stack_table()["chisurf"]


def test_the_about_window_names_the_companion_licences():
    from chisurf.plugins.core.about.gui.app import COMPANIONS

    table = stack_table()
    assert f"tttrlib {table['tttrlib']}" in COMPANIONS
    assert f"IMP.bff {table['imp-bff']}" in COMPANIONS


def test_the_splash_art_states_mit_not_gpl():
    svg = (ROOT / "chisurf" / "gui" / "resources" / "icons" / "splashscreen.svg").read_text(encoding="utf-8")
    assert "MIT License" in svg
    assert "General Public License" not in svg


def test_the_tracker_agrees_with_the_table():
    from build_tools.license_tracker import BUNDLED, OVERRIDES

    table = stack_table()
    assert OVERRIDES["imp-bff"][0] == table["imp-bff"]
    assert OVERRIDES["mmfdb"][0] == table["mmfdb"]
    assert {e["name"]: e["license"] for e in BUNDLED}["tttrlib"] == table["tttrlib"]


def test_the_installer_texts_are_the_upstream_texts():
    licences = ROOT / "build_tools" / "licenses"
    lgpl = (licences / "LGPL-2.1.txt").read_text(encoding="utf-8")
    assert "GNU LESSER GENERAL PUBLIC LICENSE" in lgpl[:200] and "Version 2.1" in lgpl[:200]
    assert "BSD-3-Clause" in (licences / "tttrlib-BSD-3-Clause.txt").read_text(encoding="utf-8")
    bff, tttr = repository("imp-bff"), repository("tttrlib")
    if bff is not None:
        assert lgpl == (bff / "COPYING.LGPL").read_text(encoding="utf-8")
    if tttr is not None:
        assert (licences / "tttrlib-BSD-3-Clause.txt").read_text(encoding="utf-8") == (
            tttr / "LICENSE.txt"
        ).read_text(encoding="utf-8")


def test_the_installer_writes_the_licence_folder(tmp_path):
    from build_tools import build_installer

    sdist = "imp_bff-0.15.0a2.dev248+g127e1b104.tar.gz"
    out = build_installer.install_licence_texts(tmp_path, Path(sys.executable),
                                                imp_bff_sdist=sdist)
    names = {p.name for p in out.iterdir()}
    assert names == {"LICENSE-ChiSurf.txt", "LICENSE-docs.txt", "LGPL-2.1.txt",
                     "tttrlib-BSD-3-Clause.txt", "NOTICE.txt"}
    notice = (out / "NOTICE.txt").read_text(encoding="utf-8")
    assert "{" not in notice, "an unfilled placeholder"
    assert "LGPL-2.1-or-later" in notice
    assert "https://github.com/tpeulen/IMP.bff" in notice
    assert sdist in notice, "NOTICE must name the exact sdist file"
    assert "same release page" in notice
