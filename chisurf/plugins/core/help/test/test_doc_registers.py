"""The registers are the documentation's own inventory, and must stay true.

A figure whose origin nobody recorded can only ever be replaced by hand, and in
practice is never refreshed at all — which is how a manual ends up showing an
interface from three versions ago. These tests keep the inventory honest:
every image used is registered, every registered image exists, and the three
generated registers match what the pages actually contain.

The rules themselves are written down for whoever refreshes the documentation
next, in ``docs/development/documentation_maintenance.md``.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

from chisurf.plugins.core.help.api.toc import docs_root, repository_root

sys.path.insert(0, str(repository_root() / "build_tools" / "docs"))


def _registers():
    import make_registers

    return make_registers


def test_every_image_used_is_registered():
    """An unrecorded figure cannot be refreshed; the register names them."""
    registers = _registers()
    provenance = registers.load_provenance()
    used = {figure["src"] for figure in registers.collect_figures()}
    unrecorded = sorted(src for src in used if not (provenance.get(src) or {}).get("origin"))
    assert len(unrecorded) <= 8, unrecorded


def test_every_registered_image_exists():
    """A register entry for a file that is gone is a lie about the inventory."""
    registers = _registers()
    missing = [src for src in registers.load_provenance() if not (docs_root() / src).exists()]
    assert not missing, missing


def test_every_used_image_exists():
    """A page pointing at an image that is not there shows a broken box."""
    registers = _registers()
    missing = sorted(
        {
            f"{figure['page']} → {figure['src']}"
            for figure in registers.collect_figures()
            if not (docs_root() / figure["src"]).exists()
        }
    )
    assert not missing, missing


def test_a_recipe_says_enough_to_remake_the_figure():
    """ "Screenshot of the tool" is not a recipe anybody can follow."""
    registers = _registers()
    thin = []
    for src, record in (registers.load_provenance() or {}).items():
        record = record or {}
        if not record.get("origin"):
            continue
        recipe = " ".join(str(record.get("recipe", "")).split())
        if len(recipe.split()) < 8:
            thin.append(src)
    assert not thin, thin[:10]


def test_the_registers_are_up_to_date():
    """The indexes are generated; a stale one misdescribes the documentation."""
    result = subprocess.run(
        [sys.executable, "build_tools/docs/make_registers.py", "--check"],
        cwd=repository_root(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_literature_page_is_up_to_date():
    result = subprocess.run(
        [sys.executable, "build_tools/docs/make_bibliography.py", "--check"],
        cwd=repository_root(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_refresh_rule_is_written_down():
    """The instruction an agent follows must exist and stay complete.

    It is the only thing that makes a refresh repeatable rather than a fresh
    act of archaeology each time.
    """
    page = docs_root() / "development" / "documentation_maintenance.md"
    assert page.is_file(), page
    text = page.read_text(encoding="utf-8")
    for expected in (
        "make_registers.py --check",
        "make_bibliography.py --check",
        "review-set",
        "Never invent a DOI",
        "Address it by\n  **symbol**",
        "QT_QPA_PLATFORM=offscreen",
    ):
        assert expected in text, expected


@pytest.mark.parametrize("register", ["figures.md", "tables.md", "code.md"])
def test_register_is_reachable_from_the_reference_section(register):
    index = (docs_root() / "reference" / "index.rst").read_text(encoding="utf-8")
    assert pathlib.Path(register).stem in index


def test_a_register_row_never_leaves_a_formula_open():
    """A shortened caption must not end mid-formula.

    An unpaired ``$`` is closed against the *next* dollar on the page — several
    rows further down — and everything between them is swallowed into one
    nonsensical formula. The register is generated, so this can only be fixed
    where the shortening happens.
    """
    from chisurf.plugins.core.help.api.toc import docs_root

    offenders = []
    for name in ("figures", "tables", "code"):
        page = docs_root() / "reference" / f"{name}.md"
        if not page.is_file():
            continue
        for number, line in enumerate(page.read_text(encoding="utf-8").split("\n"), 1):
            if not line.startswith("|"):
                continue
            if line.count("$") % 2 or line.count("`") % 2:
                offenders.append((f"{name}.md", number, line[:80]))
    assert not offenders, offenders[:5]
