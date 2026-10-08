"""The occlusion-aware helper coexists with the SDK's recorded visible-text metadata."""

from chisurf.plugins.core.project_browser.test.driving import (
    ClipPainter,
    clipped_texts,
    layout_problems,
)

COLOUR = (240, 240, 240, 255)


def test_sdk_visible_text_list_does_not_shadow_the_fragment_iterator():
    """The real layout checker retains occlusion beyond the SDK's plain clipped bounds."""
    painter = ClipPainter()
    painter.text(0, 0, 200, 20, 0, "Covered", COLOUR)
    painter.fill_rect(0, 0, 200, 20, (0, 0, 0, 255))
    painter.text(5, 0, 200, 20, 0, "Foreground", COLOUR)
    assert isinstance(painter.visible_texts, list)
    assert len(painter.visible_texts) == 2
    assert layout_problems(painter, (300, 100)) == []
    assert [shown[1] for shown, _ink, _pieces in painter.visible_text_fragments()] == ["Foreground"]


def test_clipping_and_true_visible_collisions_remain_detectable():
    """Renaming the iterator preserves clipped-label diagnostics and actual overlap detection."""
    painter = ClipPainter()
    painter.push_clip(10, 0, 28, 40)
    painter.text(12, 0, 200, 20, 0, "Long caption", COLOUR)
    painter.text(20, 0, 200, 20, 0, "Second", COLOUR)
    painter.pop_clip()
    problems = layout_problems(painter, (300, 100))
    assert len(problems) == 1 and problems[0].startswith("overlap:")
    assert all("outside" not in problem for problem in problems)
    assert len(clipped_texts(painter)) == 2
