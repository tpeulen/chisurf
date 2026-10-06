"""The help window renders Markdown emphasis instead of showing ``**`` and backticks."""

from __future__ import annotations

from emtk import im
from emtk.im_core import IO
from emtk.testing import RecordingPainter

from chisurf.emtk.help_guide import EmTkHelpWindow


def _strings(window):
    painter = RecordingPainter()
    with im.frame(painter, (0, 0, 900.0, 700.0), io=IO(), storage={}):
        window.draw((0, 0, 900.0, 700.0))
    return " ".join(painter.strings)


def test_emphasis_code_and_links_are_rendered_not_shown_raw():
    window = EmTkHelpWindow(
        title="Demo",
        text="# Use\n\nPress **Next** to run `run_step`, see [the guide](docs/guides/66_alex_suite.md).\n\n- *one* item\n",
    )
    window.show()
    shown = _strings(window)
    assert "Next" in shown and "run_step" in shown and "the guide" in shown and "one" in shown
    assert "**" not in shown and "`" not in shown and "](" not in shown
