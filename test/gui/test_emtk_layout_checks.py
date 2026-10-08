"""Layout tripwires distinguish visible glyph bounds from clipping/alignment boxes."""

import pytest
from emtk.testing import RecordingPainter

from test.gui.emtk_layout_checks import assert_texts_apart, boxes

WHITE = (255, 255, 255, 255)


def test_editor_fragments_do_not_occupy_the_remaining_viewport():
    """Adjacent syntax runs are spaced by glyph advances, not their broad clip boxes."""
    painter = RecordingPainter()
    painter.text(10, 0, 200, 16, 0, "name", WHITE)
    painter.text(45, 0, 165, 16, 0, "CA", WHITE)
    assert boxes(painter) == [(10, 0, 28, 16, "name"), (45, 0, 14, 16, "CA")]
    assert_texts_apart(painter)


def test_clipped_tab_label_does_not_cover_overflow_arrow():
    """The reserved tab-strip clip protects its adjacent navigation button."""
    painter = RecordingPainter()
    painter.push_clip(0, 0, 20, 20)
    painter.text(0, 0, 200, 16, 0, "Long tab label", WHITE)
    painter.pop_clip()
    painter.text(25, 0, 14, 16, 0, "◀", WHITE)
    assert boxes(painter)[0][2] == 20
    assert_texts_apart(painter)


def test_actual_visible_overlap_remains_an_error():
    """Using glyph bounds cannot excuse two labels drawn over each other."""
    painter = RecordingPainter()
    painter.text(10, 0, 200, 16, 0, "name", WHITE)
    painter.text(18, 0, 165, 16, 0, "CA", WHITE)
    with pytest.raises(AssertionError, match="overlaps"):
        assert_texts_apart(painter)


def test_fully_clipped_labels_are_not_visible_boxes():
    """A hidden tab title contributes no occupied rectangle."""
    painter = RecordingPainter()
    painter.push_clip(0, 0, 20, 20)
    painter.text(30, 0, 200, 16, 0, "Hidden", WHITE)
    assert boxes(painter) == []
