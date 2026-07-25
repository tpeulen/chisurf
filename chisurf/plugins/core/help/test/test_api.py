"""Tests for the Help plugin API layer."""

import pathlib

from chisurf.plugins.core.help.api.io import core_doc_paths, discover_docs
from chisurf.plugins.core.help.api.markdown import render_markdown
from chisurf.plugins.core.help.gui.client import HelpClient


def test_discover_docs_returns_entries():
    info = discover_docs()
    assert info.entries
    assert info.tree


def test_core_doc_paths_allow_lists_project_documentation(tmp_path):
    """Scratch space, the knowledge bundle and dot-directories stay out."""
    (tmp_path / "README.md").write_text("# Readme", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("# Agent notes", encoding="utf-8")
    for scratch in ("junk", "okf", "AGENT", ".claude"):
        (tmp_path / scratch).mkdir()
        (tmp_path / scratch / "note.md").write_text("# Note", encoding="utf-8")
    (tmp_path / "examples" / "projects").mkdir(parents=True)
    (tmp_path / "examples" / "projects" / "README.md").write_text("# Ex", encoding="utf-8")
    (tmp_path / "modules" / "tool" / "plugins").mkdir(parents=True)
    (tmp_path / "modules" / "tool" / "plugins" / "own.md").write_text("# Own", encoding="utf-8")

    found = {p.relative_to(tmp_path).as_posix() for p in core_doc_paths(tmp_path)}
    assert found == {"README.md", "examples/projects/README.md"}


def test_core_category_excludes_scratch_and_knowledge_bundle():
    info = discover_docs()
    core = [e for e in info.entries if e.category == "Core"]
    assert core
    excluded = {"junk", "okf", "AGENT", "scratch", "build_tools", "test", "docs"}
    for entry in core:
        parts = pathlib.Path(entry.file_name).parts
        assert parts[0] not in excluded, entry.file_name
        assert not any(part.startswith(".") for part in parts), entry.file_name


def test_render_markdown_adds_heading_id():
    html = render_markdown("# Hello {#world}\n\nContent")
    assert 'id="world"' in html
    assert "Content" in html


def test_help_client_can_list_docs():
    client = HelpClient()
    result = client.list_docs()
    assert result.get("ok") is True
    payload = result.get("result", {})
    assert "entries" in payload
    assert "tree" in payload
    assert payload["entries"]


def test_help_client_can_search_docs():
    client = HelpClient()
    results = client.search_docs("fcs")
    assert results
    assert {"path", "title", "match_type"} <= set(results[0])


def test_help_client_can_read_doc():
    info = discover_docs()
    path = info.entries[0].path
    client = HelpClient()
    result = client.read_doc(path)
    assert result is not None
    assert "content" in result
    assert "html" in result
