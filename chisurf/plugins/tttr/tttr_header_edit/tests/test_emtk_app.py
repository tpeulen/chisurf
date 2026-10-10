"""UI-level tests for the EMTK TTTR Header Editor app.

The model and the format round-trips are covered by test_header.py; these
drive the app: what a frame draws, the cell-edit → model-commit flow, and the
add/remove actions.
"""

from __future__ import annotations

import json
import os

import pytest
from chisurf.plugins.emtk_layout import action_caption




class RecordingPainter:
    """Counts operations and keeps the strings, instead of drawing."""

    def __init__(self) -> None:
        self.strings: list[str] = []
        self.tooltips: list[str] = []
        self.ops = 0

    def _op(self) -> None:
        self.ops += 1

    def fill_rect(self, *a) -> None:
        self._op()

    def stroke_rect(self, *a, width=1.0) -> None:
        self._op()

    def gradient_rect(self, *a) -> None:
        self._op()

    def fill_triangle(self, *a) -> None:
        self._op()

    def text(self, x, y, w, h, align, string, colour, bold=False) -> None:
        self.strings.append(string)
        self._op()

    def text_rotated(self, *a) -> None:
        self._op()

    def image(self, *a) -> None:
        self._op()

    def push_clip(self, *a) -> None:
        pass

    def pop_clip(self) -> None:
        pass

    def text_width(self, string) -> float:
        return len(str(string)) * 7.0

    def line_height(self) -> float:
        return 12.0

    def set_font(self, font) -> None:
        pass

    def set_font_scale(self, scale) -> None:
        pass


@pytest.fixture
def tool():
    from chisurf.plugins.tttr.tttr_header_edit.gui.native import create_app

    native = create_app()
    yield native
    native.close()


def test_the_native_app_owns_the_editor_gui(tool):
    assert hasattr(tool.header_gui, "start_guide") and hasattr(tool.header_gui, "show_help")
    assert tool.header_gui.docks is tool.docks


def test_a_frame_draws_actions_rows_and_json(tool, monkeypatch):
    """One frame renders the action row, every tag row, and the JSON view."""
    import emtk.im as im

    tooltips: list[str] = []
    monkeypatch.setattr(im, "set_item_tooltip", lambda s: tooltips.append(str(s)))

    painter = RecordingPainter()
    tool.draw(painter, 0.0, 0.0, 900.0, 620.0)

    assert painter.ops > 120
    assert action_caption("open") in painter.strings
    assert "💾 Save as PTU" in painter.strings
    # The sample header's tags are on screen…
    assert "File_GUID" in painter.strings
    assert "John Doe" in painter.strings
    # …and the JSON view mirrors the model.
    assert any('"tags"' in s for s in painter.strings)
    # The house rule: controls carry tooltips.
    assert len(tooltips) >= 5, tooltips


def test_editing_a_value_commits_to_the_model(tool, monkeypatch):
    """A cell edit flows through the string editors into the model's tags."""
    import emtk.im as im

    real_input = im.input_text

    def input_spy(label, value, *a, **k):
        if label == "##value0":
            return True, "1539705731.999"
        return real_input(label, value, *a, **k)

    monkeypatch.setattr(im, "input_text", input_spy)

    with __import__("emtk").frame(RecordingPainter(), (0.0, 0.0, 900.0, 620.0)):
        tool.header_gui.docks.draw((0.0, 0.0, 900.0, 620.0))

    tag = next(t for t in tool.model.tags if t["name"] == "File_CreatingTime")
    # The tag's type coerces the edited string to a float.
    assert tag["value"] == pytest.approx(1539705731.999)


def test_add_and_remove_rows_flow_through_the_model(tool, monkeypatch):
    gui = tool.header_gui
    n0 = len(gui._rows)
    gui._rows.append({"name": "NewTag", "type": "AnsiString", "value": "x", "idx": "-1"})
    gui._commit()
    assert len(tool.model.tags) == n0 + 1
    assert any(t["name"] == "NewTag" for t in tool.model.tags)

    gui._rows[:] = [r for r in gui._rows if r["name"] != "NewTag"]
    gui._commit()
    assert not any(t["name"] == "NewTag" for t in tool.model.tags)


def test_the_type_combo_converts_the_value(tool, monkeypatch):
    """Switching a tag's type re-coerces its stored value."""
    import emtk.im as im

    gui = tool.header_gui
    real_combo = im.combo

    def combo_spy(label, current, items, *a, **k):
        if label == "##type0":
            return True, items.index("Int8")
        return real_combo(label, current, items, *a, **k)

    monkeypatch.setattr(im, "combo", combo_spy)
    gui._rows[0]["value"] = "42"
    with __import__("emtk").frame(RecordingPainter(), (0.0, 0.0, 900.0, 620.0)):
        gui.docks.draw((0.0, 0.0, 900.0, 620.0))

    assert tool.model.tags[0]["type"] == gui.model.REVERSE_TYPE_MAPPING["Int8"]
    assert tool.model.tags[0]["value"] == 42


def test_a_load_rebuilds_the_editors(tool):
    """A new header (Open/drop) replaces the editors from the model."""
    other = json.dumps({"tags": [{"name": "TagX", "type": 0x4001FFFF, "value": "v", "idx": 3}]})
    tool.model.load_json(other)
    tool.header_gui.rebuild_rows()

    gui = tool.header_gui
    assert [r["name"] for r in gui._rows] == ["TagX"]
    assert [r["idx"] for r in gui._rows] == ["3"]
