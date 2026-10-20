"""A project one test adds to the recent list does not reach the next test.

The two tests run in file order: the first records a project, the second must see the empty
list again (``test/conftest.py::_forget_recent_projects``).
"""

from __future__ import annotations

from chisurf.core.project import recent


def test_a_records_a_recent_project(tmp_path):
    recent.store(recent.added(recent.load(), str(tmp_path / "leak.cs.pto")))
    assert recent.load()


def test_b_starts_with_no_recent_projects():
    assert recent.load() == []
