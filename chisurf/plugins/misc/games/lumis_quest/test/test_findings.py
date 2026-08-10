"""Findings: what expert mode produces when a page is *not* fine."""

from __future__ import annotations

import json

import pytest

from chisurf.plugins.misc.games.lumis_quest.api import findings


def _finding(address="docs/a.md", span="A sentence at fault.",
             category="wrong-units", content_hash="h1"):
    """Build one finding."""
    return findings.Finding(
        address=address, content_hash=content_hash, span=span, category=category
    )


def test_a_finding_is_a_span_and_a_category():
    """No typing, and the record is machine-checkable rather than prose."""
    one = _finding()
    assert one.category in dict(findings.CATEGORIES)
    assert one.describes == "the units are wrong or missing"
    assert one.found_at, "a finding is dated when it is made"


def test_the_categories_are_a_fixed_comparable_list():
    """Two people flagging the same problem must produce the same record."""
    keys = [key for key, _ in findings.CATEGORIES]
    assert len(keys) == len(set(keys))
    assert all(" " not in key for key in keys), "keys are machine-readable"
    assert all(description for _, description in findings.CATEGORIES)


def test_findings_pool_and_round_trip(tmp_path):
    """They accumulate in the per-user directory."""
    path = tmp_path / "findings.json"
    findings.add(_finding(), path)
    findings.add(_finding(span="Another sentence.", category="dead-link"), path)

    pool = findings.load(path)
    assert len(pool) == 2
    assert {f.category for f in pool} == {"wrong-units", "dead-link"}


def test_the_same_finding_is_not_pooled_twice(tmp_path):
    """Flagging the same fault again is not new information."""
    path = tmp_path / "findings.json"
    findings.add(_finding(), path)
    findings.add(_finding(), path)
    assert len(findings.load(path)) == 1


def test_a_missing_or_corrupt_pool_is_empty_not_fatal(tmp_path):
    """Losing findings is annoying; refusing to run is worse."""
    assert findings.load(tmp_path / "nothing.json") == []
    bad = tmp_path / "bad.json"
    bad.write_text("{ not json", encoding="utf-8")
    assert findings.load(bad) == []
    bad.write_text(json.dumps([{"unexpected": "shape"}]), encoding="utf-8")
    assert findings.load(bad) == []


def test_nothing_is_ever_written_into_the_docs(tmp_path):
    """This repository is a shared working tree.

    Several agents and the user hold uncommitted edits at once, so a game that
    wrote into the documentation during play would silently destroy work.
    """
    docs = tmp_path / "docs"
    docs.mkdir()
    page = docs / "a.md"
    page.write_text("Original text.\n", encoding="utf-8")
    before = page.read_text(encoding="utf-8")

    pool = tmp_path / "pool.json"
    findings.add(_finding(content_hash=findings.current_hash(page)), pool)

    assert page.read_text(encoding="utf-8") == before
    assert pool.is_file() and not (docs / "findings.json").exists()


def test_export_writes_a_report_grouped_by_page(tmp_path):
    """Something a person can actually work from."""
    docs = tmp_path / "docs"
    docs.mkdir()
    page = docs / "a.md"
    page.write_text("Original text.\n", encoding="utf-8")
    page_hash = findings.current_hash(page)

    report = tmp_path / "report.md"
    exported, stale = findings.export(
        [
            _finding(address="docs/a.md", content_hash=page_hash),
            _finding(address="docs/a.md", span="Second one.",
                     category="dead-link", content_hash=page_hash),
        ],
        tmp_path,
        report,
    )
    assert (exported, stale) == (2, 0)
    text = report.read_text(encoding="utf-8")
    assert "## docs/a.md" in text
    assert "wrong-units" in text and "dead-link" in text
    assert "> A sentence at fault." in text


def test_a_finding_whose_page_moved_is_reported_stale_not_exported(tmp_path):
    """It points at a sentence that has moved or gone.

    A report full of stale references is worse than a short accurate one.
    """
    docs = tmp_path / "docs"
    docs.mkdir()
    page = docs / "a.md"
    page.write_text("Original text.\n", encoding="utf-8")
    stale_finding = _finding(address="docs/a.md", content_hash=findings.current_hash(page))

    page.write_text("Rewritten entirely.\n", encoding="utf-8")
    report = tmp_path / "report.md"
    exported, stale = findings.export([stale_finding], tmp_path, report)

    assert (exported, stale) == (0, 1)
    assert "1 stale finding(s) omitted" in report.read_text(encoding="utf-8")
