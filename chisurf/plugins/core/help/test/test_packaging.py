"""The documentation a distribution carries, and how it is found again.

``docs/`` sits beside the package rather than inside it, so nothing put it in a
wheel or a conda package: installed from a distribution, the Help window opened
onto an empty tree. The build now copies a selection into ``chisurf/docs`` and
:func:`~chisurf.plugins.core.help.api.toc.docs_root` prefers it.

Two things can quietly break that. The selection can stop covering what the
browser opens — a page in a format nobody thought to list ships as a broken
link, not as an error — and the lookup can start finding the checkout again,
which passes every test on a developer's machine and nowhere else.
"""

import pathlib
import sys

import pytest

from chisurf.plugins.core.help.api import toc as toc_api


def _shipped_docs():
    """Import the build's selection module from the repository root."""
    root = toc_api.repository_root()
    if not (root / "_shipped_docs.py").is_file():
        pytest.skip("no source checkout: the build's selection is not present")
    sys.path.insert(0, str(root))
    try:
        import _shipped_docs

        return _shipped_docs
    finally:
        sys.path.remove(str(root))


def test_every_page_in_the_tree_is_shipped():
    """A page the browser lists must be a page the distribution carries."""
    module = _shipped_docs()
    docs = toc_api.docs_root()
    shipped = set(module.iter_shipped_docs(docs))

    pages = [node.path for node in toc_api.build_toc().walk() if node.path is not None]
    assert pages, "the table of contents is empty"
    missing = sorted(
        {
            page.relative_to(docs).as_posix()
            for page in pages
            if page.is_relative_to(docs) and page.relative_to(docs) not in shipped
        }
    )
    assert not missing, f"pages the browser lists but no distribution carries: {missing}"


def test_the_bibliography_and_figures_are_shipped():
    """Citations and screenshots are as much the page as its prose."""
    module = _shipped_docs()
    docs = toc_api.docs_root()
    shipped = {path.as_posix() for path in module.iter_shipped_docs(docs)}

    assert any(name.endswith(".bib") or "references" in name for name in shipped)
    assert any(name.endswith(".png") for name in shipped)
    assert "index.md" in shipped


def test_build_output_and_dead_formats_are_not_shipped():
    """Sphinx output and the manual's EMF figures dwarf everything else."""
    module = _shipped_docs()
    docs = toc_api.docs_root()
    shipped = list(module.iter_shipped_docs(docs))

    assert not [path for path in shipped if path.parts[0] in module.SHIPPED_EXCLUDED_DIRS]
    assert not [path for path in shipped if path.suffix.lower() in {".emf", ".wmf", ".docx"}]


def test_a_packaged_copy_wins_over_the_checkout(tmp_path, monkeypatch):
    """An installed ChiSurf reads its own documentation, not a stray tree."""
    packaged = tmp_path / "chisurf"
    (packaged / "docs").mkdir(parents=True)
    (packaged / "docs" / "index.md").write_text("stub\n", encoding="utf-8")

    monkeypatch.setattr(toc_api, "package_root", lambda: packaged)
    toc_api.docs_root.cache_clear()
    try:
        assert toc_api.docs_root() == packaged / "docs"
        assert toc_api.repository_root() == packaged
    finally:
        toc_api.docs_root.cache_clear()


def test_the_checkout_is_used_when_nothing_is_packaged(tmp_path, monkeypatch):
    """A developer edits ``docs/`` and sees the edit, with no copy in the way."""
    monkeypatch.setattr(toc_api, "package_root", lambda: tmp_path / "chisurf")
    toc_api.docs_root.cache_clear()
    try:
        root = toc_api.docs_root()
        assert root.name == "docs"
        assert (root / "index.md").is_file()
    finally:
        toc_api.docs_root.cache_clear()


def test_one_resolver_answers_for_the_whole_plugin():
    """Cross-references and review tracking must read the same tree."""
    from chisurf.plugins.core.help.api import review, xref

    assert xref.repository_root() == toc_api.repository_root()
    assert review.docs_root() in (None, toc_api.docs_root())


def test_the_selection_is_a_sane_size():
    """A wheel carries the reader's documentation, not the whole tree."""
    module = _shipped_docs()
    docs = toc_api.docs_root()
    total = sum((docs / path).stat().st_size for path in module.iter_shipped_docs(docs))
    assert total < 64 * 1024 * 1024, f"{total / 1e6:.0f} MB of documentation is too much"


def test_pathlib_relative_addresses_stay_docs_relative():
    """The address bar reads ``docs/...`` in a checkout and in an install."""
    docs = toc_api.docs_root()
    page = docs / "index.md"
    assert pathlib.Path(page).relative_to(toc_api.repository_root()).as_posix() == "docs/index.md"
