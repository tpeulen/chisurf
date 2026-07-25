"""Tests for documentation review-status tracking and manual rendering."""

from __future__ import annotations

import pathlib

import pytest

from chisurf.plugins.core.help.api import render, review, rst


@pytest.fixture
def manual(tmp_path, monkeypatch):
    """Provide an isolated tracked ``manual`` directory."""
    docs = tmp_path / "docs"
    (docs / "manual").mkdir(parents=True)
    (docs / "guides").mkdir()
    monkeypatch.setattr(review, "docs_root", lambda: docs)
    return docs / "manual"


def _page(manual: pathlib.Path, name: str = "page.rst", text: str = "Title\n=====\n") -> pathlib.Path:
    path = manual / name
    path.write_text(text, encoding="utf-8")
    return path


# ── hashing ─────────────────────────────────────────────────────────


def test_content_hash_ignores_line_endings():
    assert review.content_hash("a\nb\n") == review.content_hash("a\r\nb\r\n")


def test_content_hash_ignores_trailing_newlines():
    assert review.content_hash("a\nb") == review.content_hash("a\nb\n\n")


def test_content_hash_detects_real_change():
    assert review.content_hash("a\nb\n") != review.content_hash("a\nc\n")


# ── status lifecycle ────────────────────────────────────────────────


def test_page_is_unreviewed_by_default(manual):
    path = _page(manual)
    assert review.status_of(path).status == review.STATUS_UNREVIEWED


def test_marking_reviewed_sets_status_and_metadata(manual):
    path = _page(manual)
    assert review.set_status(path, review.STATUS_REVIEWED, reviewer="tpeulen")
    status = review.status_of(path)
    assert status.status == review.STATUS_REVIEWED
    assert status.reviewer == "tpeulen"
    assert status.date


def test_editing_a_reviewed_page_makes_it_stale(manual):
    """The whole point of storing a hash: sign-off must not survive an edit."""
    path = _page(manual)
    review.set_status(path, review.STATUS_REVIEWED, reviewer="tpeulen")
    assert review.status_of(path).status == review.STATUS_REVIEWED

    path.write_text("Title\n=====\n\nSomething new.\n", encoding="utf-8")
    assert review.status_of(path).status == review.STATUS_STALE


def test_reformatting_line_endings_does_not_make_a_page_stale(manual):
    path = _page(manual, text="Title\n=====\n\nBody.\n")
    review.set_status(path, review.STATUS_REVIEWED)
    path.write_text("Title\r\n=====\r\n\r\nBody.\r\n", encoding="utf-8")
    assert review.status_of(path).status == review.STATUS_REVIEWED


def test_re_reviewing_a_stale_page_restores_reviewed(manual):
    path = _page(manual)
    review.set_status(path, review.STATUS_REVIEWED)
    path.write_text("Title\n=====\n\nEdited.\n", encoding="utf-8")
    assert review.status_of(path).status == review.STATUS_STALE

    review.set_status(path, review.STATUS_REVIEWED, reviewer="tpeulen")
    assert review.status_of(path).status == review.STATUS_REVIEWED


def test_unreviewing_clears_the_record(manual):
    path = _page(manual)
    review.set_status(path, review.STATUS_REVIEWED)
    review.set_status(path, review.STATUS_UNREVIEWED)
    assert review.status_of(path).status == review.STATUS_UNREVIEWED
    assert "page.rst" not in review.load_registry(manual)


# ── tracking scope ──────────────────────────────────────────────────


def test_untracked_pages_never_block(manual):
    """Pages outside tracked directories must not gate the build."""
    outside = manual.parent / "guides" / "guide.md"
    outside.write_text("# Guide\n", encoding="utf-8")
    assert not review.is_tracked(outside)
    assert not review.status_of(outside).is_blocking


def test_non_page_files_are_not_tracked(manual):
    image = manual / "figure.png"
    image.write_bytes(b"\x89PNG")
    assert not review.is_tracked(image)


def test_set_status_refuses_untracked_pages(manual):
    outside = manual.parent / "guides" / "guide.md"
    outside.write_text("# Guide\n", encoding="utf-8")
    assert not review.set_status(outside, review.STATUS_REVIEWED)


# ── reporting ───────────────────────────────────────────────────────


def test_scan_reports_each_status(manual):
    ok = _page(manual, "ok.rst")
    stale = _page(manual, "stale.rst")
    _page(manual, "new.rst")
    review.set_status(ok, review.STATUS_REVIEWED)
    review.set_status(stale, review.STATUS_REVIEWED)
    stale.write_text("Changed\n=======\n", encoding="utf-8")

    report = review.scan()
    assert {p.rel_path for p in report.reviewed} == {"ok.rst"}
    assert {p.rel_path for p in report.stale} == {"stale.rst"}
    assert {p.rel_path for p in report.unreviewed} == {"new.rst"}
    assert not report.ok
    assert len(report.blocking) == 2


def test_report_ok_once_everything_is_reviewed(manual):
    for name in ("a.rst", "b.rst"):
        review.set_status(_page(manual, name), review.STATUS_REVIEWED)
    report = review.scan()
    assert report.ok
    assert report.blocking == []


def test_registry_survives_a_reload(manual):
    path = _page(manual)
    review.set_status(path, review.STATUS_REVIEWED, reviewer="tpeulen")
    records = review.load_registry(manual)
    assert records["page.rst"].reviewer == "tpeulen"
    assert records["page.rst"].sha256


def test_corrupt_registry_degrades_to_unreviewed(manual):
    path = _page(manual)
    review.registry_path(manual).write_text("{not json", encoding="utf-8")
    assert review.status_of(path).status == review.STATUS_UNREVIEWED


# ── reStructuredText rendering ──────────────────────────────────────


def test_rst_title_extraction():
    assert rst.extract_rst_title("Analysis dock\n-------------\n\nBody\n") == "Analysis dock"


def test_rst_title_handles_overline():
    assert rst.extract_rst_title("=====\nTitle\n=====\n\nBody\n") == "Title"


def test_rst_renders_to_html():
    html = rst.render_rst("Title\n=====\n\nSome **bold** text.\n")
    assert html and "<strong>bold</strong>" in html


def test_sphinx_only_roles_do_not_break_rendering():
    """Bare docutils does not know :doc:/:ref:; they must degrade, not error."""
    html = rst.render_rst("Title\n=====\n\nSee :doc:`/guides/index` and :ref:`concept-fret`.\n")
    assert html
    assert "problematic" not in html.lower()
    assert "system-message" not in html.lower()


def test_role_with_explicit_label_shows_the_label():
    html = rst.render_rst("Title\n=====\n\nSee :doc:`the guides </guides/index>`.\n")
    assert html and "the guides" in html


def test_render_dispatches_on_suffix():
    assert render.is_rst("a.rst")
    assert not render.is_rst("a.md")
    md = render.render_document("# Heading\n", "a.md")
    rs = render.render_document("Heading\n=======\n", "a.rst")
    assert md and "Heading" in md
    assert rs and "Heading" in rs


def test_document_title_dispatches_on_suffix():
    assert render.document_title("# Md title\n", "a.md") == "Md title"
    assert render.document_title("Rst title\n=========\n", "a.rst") == "Rst title"
