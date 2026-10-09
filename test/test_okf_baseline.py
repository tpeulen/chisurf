"""Require explicit, shrinking ownership of existing knowledge-bundle debt."""

from build_tools.okf import baseline


def test_baseline_detects_changed_context_duplicates_and_stale_entries():
    """An allowance covers one exact defect, never a whole file or rule."""
    record = {"rule": "WIKI", "path": "note.md", "message": "wikilink", "source": "[[old]]"}
    assert baseline.compare([record], [record]) == {"new": [], "stale": []}
    changed = {**record, "source": "[[new]]"}
    assert all(baseline.compare([changed], [record]).values())
    assert len(baseline.compare([record, record], [record])["new"]) == 1
    assert len(baseline.compare([], [record])["stale"]) == 1


def test_baseline_ignores_line_shifts_but_preserves_exact_content():
    """Adding clean text before a finding does not expand its allowance."""
    old = {
        "rule": "FM",
        "path": "note.md",
        "message": "missing title",
        "source": "# Note",
        "line": 1,
    }
    assert baseline.compare([{**old, "line": 5}], [old]) == {"new": [], "stale": []}
