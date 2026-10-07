"""Layout checks measure painted text rather than widget allocation boxes."""

import pytest
from emtk.painter import ALIGN_HCENTER, ALIGN_LEFT, ALIGN_RIGHT

from chisurf.plugins.core.project_browser.test.driving import (
    ClipPainter,
    clipped_texts,
    layout_problems,
)


@pytest.mark.parametrize("alignment", [ALIGN_LEFT, ALIGN_HCENTER, ALIGN_RIGHT])
def test_adjacent_tokens_with_remaining_line_boxes_do_not_overlap(alignment):
    """Syntax-highlighted text remains separate within overlapping allocation boxes."""
    painter = ClipPainter()
    start = 10.0
    for token in ("name", "CA", "and", "resSeq"):
        width = painter.text_width(token)
        allocation = 150.0
        offset = (
            allocation - width
            if alignment == ALIGN_RIGHT
            else ((allocation - width) / 2 if alignment == ALIGN_HCENTER else 0)
        )
        painter.text(start - offset, 10, allocation, 15, alignment, token, (255, 255, 255))
        start += width + 7
    assert layout_problems(painter, (400, 100)) == []


def test_real_glyph_overlap_is_reported():
    """Measuring ink retains detection of genuinely colliding text."""
    painter = ClipPainter()
    painter.text(10, 10, 100, 15, ALIGN_LEFT, "collision", (255, 255, 255))
    painter.text(15, 10, 100, 15, ALIGN_LEFT, "collision", (255, 255, 255))
    assert any(problem.startswith("overlap:") for problem in layout_problems(painter, (300, 100)))


def test_unused_allocation_outside_window_is_not_painted_overflow():
    """A short label can fit even when its allocation extends past the window."""
    painter = ClipPainter()
    painter.text(10, 10, 500, 15, ALIGN_LEFT, "label", (255, 255, 255))
    assert layout_problems(painter, (200, 100)) == []


def test_painted_overflow_is_reported():
    """An unclipped string beyond the viewport remains a real layout failure."""
    painter = ClipPainter()
    painter.text(190, 10, 100, 15, ALIGN_LEFT, "overflow", (255, 255, 255))
    assert any(
        problem.startswith("outside the window:")
        for problem in layout_problems(painter, (200, 100))
    )


def test_right_edge_clipping_check_is_preserved():
    """Clip diagnostics still measure the full text needed beyond a clip edge."""
    painter = ClipPainter()
    painter.push_clip(0, 0, 40, 100)
    painter.text(10, 10, 200, 15, ALIGN_LEFT, "a long label", (255, 255, 255))
    painter.pop_clip()
    assert any(problem.startswith("cut at the right edge:") for problem in clipped_texts(painter))


def test_text_clipped_away_does_not_count_as_collision():
    """Scrolled-away text never contributes an apparent visible overlap."""
    painter = ClipPainter()
    painter.push_clip(0, 30, 200, 50)
    painter.text(10, 10, 100, 15, ALIGN_LEFT, "hidden", (255, 255, 255))
    painter.text(10, 10, 100, 15, ALIGN_LEFT, "hidden", (255, 255, 255))
    painter.pop_clip()
    assert layout_problems(painter, (200, 100)) == []
