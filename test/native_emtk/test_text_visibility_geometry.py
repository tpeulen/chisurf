"""Visual diagnostics ignore nondrawn text while preserving real visible defects."""

import pytest
from emtk.painter import ALIGN_HCENTER, ALIGN_LEFT, ALIGN_VCENTER

from chisurf.plugins.core.project_browser.test.driving import (
    ClipPainter,
    clipped_texts,
    layout_problems,
)


def _text(painter, x=10, y=10, width=40, caption="label"):
    """Draw one ordinary left-aligned line with enough allocated width."""
    painter.text(x, y, width, 15, ALIGN_LEFT | ALIGN_VCENTER, caption, (235, 235, 240, 255))


def test_fully_scissored_horizontal_text_is_not_a_visual_clip_failure():
    """A cell outside a table viewport paints no glyphs."""
    painter = ClipPainter()
    painter.push_clip(0, 0, 100, 50)
    _text(painter, x=130)
    painter.pop_clip()
    assert clipped_texts(painter) == []
    assert layout_problems(painter, (200, 100)) == []


def test_opaque_cell_overlay_removes_underpaint_overlap():
    """The real table's opaque button fill hides its previously painted caption."""
    painter = ClipPainter()
    _text(painter, x=398, y=318, width=15, caption="G")
    painter.fill_rect(394, 319, 19, 15, (25, 25, 28, 255))
    painter.text(394, 319, 19, 15, ALIGN_HCENTER | ALIGN_VCENTER, "G", (235, 235, 240))
    assert layout_problems(painter, (500, 400)) == []


@pytest.mark.parametrize("alpha", [128, 254])
def test_translucent_overpaint_does_not_hide_real_overlap(alpha):
    """A visible underlying glyph remains part of the diagnostic."""
    painter = ClipPainter()
    _text(painter)
    painter.fill_rect(0, 0, 100, 50, (25, 25, 28, alpha))
    _text(painter)
    assert any(problem.startswith("overlap:") for problem in layout_problems(painter, (200, 100)))


def test_earlier_opaque_fill_does_not_hide_later_text():
    """Occlusion follows paint order rather than matching any rectangle."""
    painter = ClipPainter()
    painter.fill_rect(0, 0, 100, 50, (25, 25, 28, 255))
    _text(painter)
    _text(painter)
    assert any(problem.startswith("overlap:") for problem in layout_problems(painter, (200, 100)))


def test_partial_right_clipping_remains_a_failure():
    """A partially visible label retains the real right-edge tripwire."""
    painter = ClipPainter()
    painter.push_clip(0, 0, 30, 50)
    _text(painter, caption="a long label", width=200)
    painter.pop_clip()
    assert any(problem.startswith("cut at the right edge:") for problem in clipped_texts(painter))


def test_clipped_opaque_fill_cannot_hide_text_outside_its_clip():
    """Coverage respects the fill's own scissor instead of its allocation rectangle."""
    painter = ClipPainter()
    _text(painter)
    painter.push_clip(150, 0, 40, 50)
    painter.fill_rect(0, 0, 200, 50, (25, 25, 28, 255))
    painter.pop_clip()
    _text(painter)
    assert any(problem.startswith("overlap:") for problem in layout_problems(painter, (200, 100)))


def test_real_detector_delete_cell_is_reachable_after_public_horizontal_scroll():
    """Visual scissoring does not waive the actual action's existence or delivery."""
    from emtk import im
    from emtk.app import ImApp

    from chisurf.core.setup_channel_definition import ChannelDefinition
    from chisurf.emtk.channel_definition import ChannelDefinitionWidget

    editor = ChannelDefinitionWidget()
    editor.model = ChannelDefinition(
        {
            "detectors": {
                "measured": {
                    "chs": [0, 1],
                    "micro_time_ranges": [[0, 4095]],
                    "g_factor": 1.0,
                }
            }
        }
    )

    def render():
        """Render the actual shared table in a narrow ordinary window."""
        im.set_next_window_pos((0, 0))
        im.set_next_window_size((380, 620))
        if im.begin(
            "table-visibility", flags=im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE
        ):
            editor.draw()
        im.end()

    app = ImApp(render)
    try:
        painter = None
        for _ in range(3):
            painter = ClipPainter()
            app.draw(painter, 0, 0, 380, 620)
        buttons = editor._detector_buttons
        _, _, key, rect = next(cell for cell in buttons.cells() if cell[2] == "delete")
        x, y, width, height = rect
        assert buttons.hit(x + width / 2, y + height / 2) is None
        control = editor._detector_table.control
        control.scroll_columns(len(control.visible_columns()) - 1)
        for _ in range(2):
            painter = ClipPainter()
            app.draw(painter, 0, 0, 380, 620)
        _, _, key, rect = next(cell for cell in buttons.cells() if cell[2] == "delete")
        x, y, width, height = rect
        hit = buttons.hit(x + width / 2, y + height / 2)
        assert hit is not None, (control.first_column, control._hbar_box, rect, control._body_box)
        assert hit[1] == key
        assert buttons.press(x + width / 2, y + height / 2)
        assert "measured" not in editor.model.data["detectors"]
    finally:
        editor.close()
