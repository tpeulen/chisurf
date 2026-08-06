"""The marker that says which reference files have been mined.

ChiMOL is built by transcribing PyMOL's source, so *which parts have been read*
is a question the tree has to be able to answer -- otherwise the same file gets
re-read and "is the source exhausted?" has no answer at all. The answer is a
header in the reference file itself, and this covers the reader for it.

The reference checkouts live in gitignored ``junk/`` and are not present in CI,
so these tests build their own tiny tree. That is deliberate: a test that skips
without a 132 MB checkout would be a test that never runs.
"""
from __future__ import annotations

import pathlib

import pytest

from chisurf.plugins.chimol.chimol.analysis import reference_coverage as rc


@pytest.fixture
def checkout(tmp_path):
    """A three-file stand-in for a reference checkout."""
    layer2 = tmp_path / "layer2"
    layer2.mkdir()
    (layer2 / "RepMarked.cpp").write_text(
        "/*\n"
        " * CHIMOL-REVIEWED: 2026-08-06\n"
        " * CHIMOL-TAKEN: cSetting_thing -> renderer/view.py::_thing\n"
        " * CHIMOL-SKIPPED: RepOther -- no data for it\n"
        " * CHIMOL-RECORD: okf/plugins/pymol-parity.md\n"
        " */\n"
        "int main() { return 0; }\n",
        encoding="utf-8",
    )
    (layer2 / "RepUnmarked.cpp").write_text("int main() { return 1; }\n", encoding="utf-8")
    (layer2 / "notes.md").write_text("CHIMOL-REVIEWED: 2026-08-06\n", encoding="utf-8")
    return tmp_path


def test_a_marked_file_reports_what_was_taken_and_skipped(checkout):
    review = rc.read_marker(checkout / "layer2" / "RepMarked.cpp")
    assert review.reviewed
    assert review.date == "2026-08-06"
    assert review.taken == ["cSetting_thing -> renderer/view.py::_thing"]
    assert review.skipped == ["RepOther -- no data for it"]


def test_an_unmarked_file_is_not_reviewed(checkout):
    review = rc.read_marker(checkout / "layer2" / "RepUnmarked.cpp")
    assert not review.reviewed
    assert review.taken == [] and review.skipped == []


def test_only_source_files_are_counted(checkout):
    """A markdown file carrying the words is not a reviewed source file.

    The denominator decides what "exhausted" means, so what goes into it has to
    be deliberate rather than whatever happens to match.
    """
    reviews = rc.survey(checkout, ("layer2",))
    names = sorted(r.path.name for r in reviews)
    assert names == ["RepMarked.cpp", "RepUnmarked.cpp"], names


def test_the_report_states_coverage_and_what_was_taken(checkout):
    text = rc.report(rc.survey(checkout, ("layer2",)), checkout)
    assert "layer2" in text
    assert "50.0%" in text, text
    assert "cSetting_thing" in text
    assert "RepOther" in text, "a skipped finding is the expensive one; it must show"


def test_a_marker_below_the_header_does_not_count(tmp_path):
    """Only the head is read, and that is a promise as well as an optimisation.

    A marker has to be in the header where a reader meets it. Scanning whole
    files would also mean a stray mention deep in a 10,000-line source counted
    as a review.
    """
    path = tmp_path / "layer2"
    path.mkdir()
    buried = path / "Deep.cpp"
    buried.write_text("\n" * 60 + "// CHIMOL-REVIEWED: 2026-08-06\n", encoding="utf-8")
    assert not rc.read_marker(buried).reviewed


def test_an_absent_checkout_is_an_empty_survey_not_a_crash(tmp_path):
    """`junk/` is gitignored, so "not there" is the ordinary case."""
    assert rc.survey(tmp_path / "nothing", rc.PYMOL_SOURCE_DIRS) == []
