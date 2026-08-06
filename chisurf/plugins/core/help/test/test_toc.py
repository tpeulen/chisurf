"""Tests for the help table of contents.

The tree is read from the documentation's own ``toctree`` blocks, so these
tests are the contract between the published manual and the in-app browser: if
a section is added to one, it appears in the other, in the author's order.
"""

import pathlib

from chisurf.plugins.core.help.api import toc as toc_api


def _write(tmp_path: pathlib.Path, relative: str, text: str) -> pathlib.Path:
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_rst_toctree_keeps_the_authors_order(tmp_path):
    _write(tmp_path, "b.rst", "Beta\n====\n")
    _write(tmp_path, "a.rst", "Alpha\n=====\n")
    index = _write(
        tmp_path,
        "index.rst",
        "Section\n=======\n\n.. toctree::\n   :maxdepth: 1\n\n   b\n   a\n",
    )
    nodes = toc_api.read_index(index)
    assert [node.title for node in nodes] == ["Beta", "Alpha"]


def test_rubrics_become_groups(tmp_path):
    _write(tmp_path, "one.rst", "One\n===\n")
    _write(tmp_path, "two.rst", "Two\n===\n")
    index = _write(
        tmp_path,
        "index.rst",
        "Section\n=======\n\n.. rubric:: First\n\n.. toctree::\n\n   one\n\n"
        ".. rubric:: Second\n\n.. toctree::\n\n   two\n",
    )
    nodes = toc_api.read_index(index)
    assert [node.title for node in nodes] == ["First", "Second"]
    assert [child.title for child in nodes[0].children] == ["One"]
    assert [child.title for child in nodes[1].children] == ["Two"]


def test_myst_headings_become_groups(tmp_path):
    _write(tmp_path, "one.md", "# One\n")
    index = _write(
        tmp_path,
        "index.md",
        "# Section\n\n## A group\n\n```{toctree}\n:maxdepth: 1\n\none\n```\n",
    )
    nodes = toc_api.read_index(index)
    assert [node.title for node in nodes] == ["A group"]
    assert [child.title for child in nodes[0].children] == ["One"]


def test_the_pages_own_title_is_not_a_group_inside_itself(tmp_path):
    _write(tmp_path, "one.rst", "One\n===\n")
    index = _write(
        tmp_path, "index.rst", "Reference\n=========\n\n.. toctree::\n\n   one\n"
    )
    nodes = toc_api.read_index(index)
    assert [node.title for node in nodes] == ["One"]


def test_a_toctree_caption_names_the_group(tmp_path):
    _write(tmp_path, "one.rst", "One\n===\n")
    index = _write(
        tmp_path,
        "index.rst",
        "Section\n=======\n\n.. toctree::\n   :caption: Chapter one\n\n   one\n",
    )
    nodes = toc_api.read_index(index)
    assert nodes[0].title == "Chapter one"
    assert nodes[0].children[0].title == "One"


def test_an_explicit_entry_title_wins(tmp_path):
    _write(tmp_path, "one.rst", "Original\n========\n")
    index = _write(
        tmp_path, "index.rst", "S\n=\n\n.. toctree::\n\n   Better name <one>\n"
    )
    assert toc_api.read_index(index)[0].title == "Better name"


def test_a_nested_index_becomes_a_group(tmp_path):
    _write(tmp_path, "sub/leaf.rst", "Leaf\n====\n")
    _write(tmp_path, "sub/index.rst", "Sub\n===\n\n.. toctree::\n\n   leaf\n")
    index = _write(tmp_path, "index.rst", "S\n=\n\n.. toctree::\n\n   sub/index\n")
    nodes = toc_api.read_index(index)
    assert nodes[0].kind == "group"
    assert [child.title for child in nodes[0].children] == ["Leaf"]


def test_summaries_come_from_the_page(tmp_path):
    page = _write(
        tmp_path,
        "one.md",
        "# One\n\nThis page explains what the thing is. And more after that.\n",
    )
    assert toc_api.page_summary(page).startswith("This page explains")


# ── the shipped documentation ───────────────────────────────────────


def test_the_real_documentation_builds_a_tree():
    toc = toc_api.build_toc()
    titles = [section.title for section in toc.children]
    for expected in ("Getting started", "Concepts", "Guides", "Reference", "Plugins"):
        assert any(expected in title for title in titles), titles


def test_developer_documentation_is_opt_in():
    assert not any(
        "Developing" in section.title for section in toc_api.build_toc().children
    )
    assert any(
        "Developing" in section.title
        for section in toc_api.build_toc(include_development=True).children
    )


def test_the_guides_are_grouped_not_one_flat_run():
    toc = toc_api.build_toc()
    guides = next(section for section in toc.children if "Guides" in section.title)
    groups = [child for child in guides.children if child.kind == "group"]
    assert len(groups) >= 5
    assert all(group.children for group in groups)


def test_the_manual_is_split_into_chapters():
    toc = toc_api.build_toc()
    manual = next(
        section for section in toc.children if "Fitting interface" in section.title
    )
    groups = [child.title for child in manual.children if child.kind == "group"]
    assert "The fitting interface" in groups
    assert any("Worked example" in title for title in groups)


def test_no_two_pages_in_a_section_share_a_title():
    """Duplicate rows ("Overview", "Overview") are unusable as navigation."""
    for section in toc_api.build_toc().children:
        titles = [node.title for node in toc_api.iter_pages(section)]
        duplicates = {title for title in titles if titles.count(title) > 1}
        assert not duplicates, (section.title, duplicates)


def test_every_page_in_the_tree_exists():
    for node in toc_api.iter_pages(toc_api.build_toc()):
        assert node.path.is_file(), node.path


def test_maintainer_pages_are_not_offered_as_plugin_documentation():
    toc = toc_api.build_toc()
    plugins = next(section for section in toc.children if section.title == "Plugins")
    names = {node.path.name.lower() for node in toc_api.iter_pages(plugins)}
    assert "status.md" not in names
    assert "contract.md" not in names
