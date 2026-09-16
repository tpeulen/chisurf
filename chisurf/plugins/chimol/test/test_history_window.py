"""The history panel scrolls, and draws only the rows that fit.

It used to draw the *tail* of the undo ring -- as many of the newest entries as
the window happened to be tall enough for -- with no scrollbar and no wheel. For
a panel whose entire job is answering "how far back can I go", losing the far
end of the list was losing the answer. It is a
:class:`~emtk.widgets.list_view.ListView` now, so the whole ring is
reachable and only the visible rows are ever built.
"""
from __future__ import annotations

import pytest

from emtk.testing import RecordingPainter
from emtk.widgets.list_view import ListView
from chimol.plugins.history.window import HistoryWindow
from chimol.ui.gui import Rect


class _Change:
    def __init__(self, revision, label):
        self.revision = revision
        self.label = label
        self.kind = "touch"


class _Objects:
    def __init__(self, changes):
        self._redo = []
        self._undo = list(changes)

    def can_undo(self):
        return bool(self._undo)


class _Viewer:
    """Just the two doors the panel reads."""

    def __init__(self, count):
        self.changes = [_Change(i + 1, f"change {i}") for i in range(count)]
        self.objects = _Objects(self.changes)

    def object_history(self):
        return tuple(self.changes)


@pytest.fixture
def panel():
    return HistoryWindow(_Viewer(200))


def _draw(panel, painter, h=120.0):
    panel.draw(painter, Rect(0.0, 0.0, 260.0, h))


def test_only_the_visible_rows_are_drawn(panel):
    p = RecordingPainter()
    _draw(panel, p)
    # A hundred and twenty pixels holds a handful of fifteen-pixel rows plus
    # the `ctrl+z:` footer -- not two hundred rows.
    assert 4 <= len(p.strings) <= 16
    assert any(s.startswith("ctrl+z:") for s in p.strings)


def test_it_opens_at_the_newest_entry(panel):
    p = RecordingPainter()
    _draw(panel, p)
    assert "change 199" in p.strings


def test_the_wheel_reaches_the_oldest_entry(panel):
    p = RecordingPainter()
    _draw(panel, p)
    for _ in range(100):
        panel.on_wheel(10.0, 10.0, 1, Rect(0.0, 0.0, 260.0, 120.0))
    p = RecordingPainter()
    _draw(panel, p)
    assert "change 0" in p.strings
    assert "change 199" not in p.strings


def test_an_empty_history_says_so():
    panel = HistoryWindow(_Viewer(0))
    p = RecordingPainter()
    _draw(panel, p)
    assert p.strings == ["Nothing has changed yet."]


def test_a_new_change_brings_the_view_back_to_the_bottom(panel):
    p = RecordingPainter()
    _draw(panel, p)
    for _ in range(100):
        panel.on_wheel(10.0, 10.0, 1, Rect(0.0, 0.0, 260.0, 120.0))
    panel.viewer.changes.append(_Change(201, "change 200"))
    p = RecordingPainter()
    _draw(panel, p)
    assert "change 200" in p.strings


def test_the_window_forwards_its_input_to_the_list(panel):
    win = panel.window()
    assert win.on_press is not None and win.on_wheel is not None
    assert win.on_drag is not None and win.on_release is not None
    # And the forwarding actually moves the list rather than being wired to
    # something that swallows it.
    _draw(panel, RecordingPainter())
    top = panel.list.scrollbar.top
    assert top > 0, "the panel opens at the newest entry, so there is room above"
    win.on_wheel(10.0, 10.0, 1, Rect(0.0, 0.0, 260.0, 120.0))
    assert panel.list.scrollbar.top == top - ListView.WHEEL_ROWS
