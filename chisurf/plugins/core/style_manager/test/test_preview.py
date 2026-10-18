"""The style editor's live preview: what the buffer says, before Apply.

The preview answers "what does this stylesheet do" while it is being edited:
the buffer is parsed (via EMTK's stylesheet engine) and a panel of sample
widgets is drawn under the parsed colours -- without touching the theme the
rest of the process is using, which is what separates a *preview* from
Apply.
"""
from __future__ import annotations

import pytest
from emtk import im
from emtk.testing import RecordingPainter

from chisurf.plugins.core.style_manager.gui.app import (
    StyleManagerModel,
    StylePreview,
)


@pytest.fixture
def model(tmp_path):
    package = tmp_path / "package"
    package.mkdir()
    (package / "dark.css").write_text(
        "window { background-color: #112233; color: #eeeeee; }\n"
        "button { background-color: #abcdef; }\n"
    )
    return StyleManagerModel(tmp_path / "user", package)


def test_preview_parses_the_live_buffer_not_the_saved_file(model):
    """Editing the buffer must re-colour the preview without a save."""
    preview = StylePreview(model)
    model.editor.set_text("window { background-color: #010203; }")
    painter = RecordingPainter()
    with im.frame(painter, (0, 0, 800, 600)):
        preview.draw()
    assert preview.style is not None
    assert preview.style.color(im.Col.WINDOW_BG) == (1, 2, 3, 255)


def test_preview_is_cached_until_the_buffer_changes(model):
    """One parse per edit, not one per frame."""
    preview = StylePreview(model)
    model.editor.set_text("window { background-color: #040506; }")
    with im.frame(RecordingPainter(), (0, 0, 800, 600)):
        preview.draw()
    first = preview.style
    with im.frame(RecordingPainter(), (0, 0, 800, 600)):
        preview.draw()
    assert preview.style is first  # same object: cached
    model.editor.set_text("window { background-color: #070809; }")
    with im.frame(RecordingPainter(), (0, 0, 800, 600)):
        preview.draw()
    assert preview.style is not first
    assert preview.style.color(im.Col.WINDOW_BG) == (7, 8, 9, 255)


def test_preview_survives_a_broken_sheet(model):
    """A half-typed stylesheet previews as the base theme, never raises."""
    preview = StylePreview(model)
    model.editor.set_text("window { background-color: #gg")  # mid-edit
    with im.frame(RecordingPainter(), (0, 0, 800, 600)):
        preview.draw()  # must not raise
    assert preview.style is not None


def test_preview_draws_sample_widgets_in_the_parsed_colours(model):
    preview = StylePreview(model)
    model.editor.set_text("window { background-color: #100820; }")
    painter = RecordingPainter()
    with im.frame(painter, (0, 0, 800, 600)):
        preview.draw()
    # the preview surface itself is the parsed window colour
    fills = [c for c in painter.calls if c[0] == "fill_rect"]
    assert any(
        c[5] == (0x10, 0x08, 0x20, 255)
        for c in fills
    ), "preview background must use the buffer's window colour"
    # and the samples are there: text drawn in this frame
    assert painter.strings


def test_preview_does_not_restyle_the_application(model, monkeypatch):
    """Drawing the preview must not move the process-wide theme."""
    import emtk.style as emtk_style
    import emtk.theme as theme

    before = emtk_style.WINDOW_BG
    current = theme.current_theme()
    preview = StylePreview(model)
    model.editor.set_text("window { background-color: #ff00ff; }")
    with im.frame(RecordingPainter(), (0, 0, 800, 600)):
        preview.draw()
    assert emtk_style.WINDOW_BG == before
    assert theme.current_theme() == current
