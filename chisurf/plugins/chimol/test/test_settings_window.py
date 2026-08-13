"""Every display setting, editable inside the 3-D view.

Two claims are pinned here. The first is coverage: the panel's rows are
*derived* from the live configuration, so a section added tomorrow appears
without anybody editing the panel — a test that only checked "some rows exist"
would pass just as happily on a hand-written subset, which is the thing this
replaces.

The second is that the editor writes through :mod:`chimol.settings` rather than
poking the config dict, so a registered setting's stored/shown transform runs:
``transparency`` edits as transparency and is *kept* as alpha.
"""

from __future__ import annotations

import pytest

from chisurf.plugins.chimol.chimol import settings as settings_api
from chisurf.plugins.chimol.chimol.config import _DISPLAY_CONFIG
from chisurf.plugins.chimol.chimol.renderer import settings_window
from chisurf.plugins.chimol.chimol.cmtk import settings_editor


class RecordingPainter:
    """The painter interface, recording instead of drawing."""

    def __init__(self) -> None:
        self.strings: list[str] = []
        self.rects = 0

    def fill_rect(self, *a) -> None:
        self.rects += 1

    def stroke_rect(self, *a, **k) -> None:
        self.rects += 1

    def gradient_rect(self, *a, **k) -> None:
        self.rects += 1

    def text(self, x, y, w, h, align, string, colour, bold=False) -> None:
        self.strings.append(string)

    def push_clip(self, *a) -> None:
        pass

    def pop_clip(self) -> None:
        pass

    def text_width(self, string) -> float:
        return len(string) * 6.0

    def line_height(self) -> float:
        return 14.0


class Rect:
    """The body rectangle a GuiWindow hands its panel."""

    def __init__(self, x, y, w, h) -> None:
        self.x, self.y, self.w, self.h = x, y, w, h


def _leaf_count(node) -> int:
    """How many editable leaves the configuration has."""
    if isinstance(node, dict):
        return sum(_leaf_count(v) for k, v in node.items() if not str(k).startswith("_"))
    return 1


def test_every_configuration_leaf_is_a_row():
    """The panel shows all of the display config, not a curated subset.

    Plus one: the start-up prompt is a *preference*, not a display setting --
    it lives under a leading underscore, which is how the walk knows to skip
    it, and it is added by hand because the dialog that used to carry it is
    gone.
    """
    model = settings_window.build_model()
    assert len(model.settings) == _leaf_count(_DISPLAY_CONFIG) + 1
    assert any(one.key == settings_window.PROMPT_KEY for one in model.settings)
    # And enough of it that a regression to "a few hand-written rows" shows.
    assert len(model.settings) > 200
    assert "cartoon" in model.groups() and "surface" in model.groups()


def test_registered_settings_carry_their_name_and_documentation():
    """A row for a registered setting is addressed by its PyMOL name."""
    model = settings_window.build_model()
    by_key = {one.key: one for one in model.settings}
    spec = next(iter(settings_api.iter_settings()))
    assert spec.name in by_key
    assert by_key[spec.name].description == spec.doc


def test_numbers_get_a_usable_track():
    """A slider's range comes from what the setting means, not from its value."""
    model = settings_window.build_model()
    by_key = {one.key: one for one in model.settings}
    alpha = next(one for key, one in by_key.items() if key.endswith("alpha"))
    assert (alpha.v_min, alpha.v_max) == (0.0, 1.0)


def test_max_fps_gets_a_sensible_track_not_a_guessed_one():
    """Without a RANGES entry this would guess 0..120 from 2x the default --
    a bad track for a frame-rate ceiling, which wants headroom above 60."""
    model = settings_window.build_model()
    by_key = {one.key: one for one in model.settings}
    row = by_key["max_fps"]
    assert (row.v_min, row.v_max) == (1.0, 240.0)


def test_nerd_tick_gets_a_sensible_track_not_a_guessed_one():
    """A guessed range for a 0.1 s default would be 0..0.2 -- no room to set
    it coarser, which is the direction a slow machine actually wants to move."""
    model = settings_window.build_model()
    by_key = {one.key: one for one in model.settings}
    row = by_key["nerd_tick"]
    assert (row.v_min, row.v_max) == (0.02, 1.0)


def test_writing_goes_through_the_settings_api():
    """A change is coerced and transformed, not written raw."""
    model = settings_window.build_model()
    before = settings_api.get_setting("transparency")
    try:
        model.set("transparency", 0.25)
        assert settings_api.get_setting("transparency") == pytest.approx(0.25)
        # Stored as alpha, which is the transform doing its job.
        assert _DISPLAY_CONFIG["surface"]["alpha"] == pytest.approx(0.75)
    finally:
        settings_api.set_setting("transparency", before)


def test_adjusting_moves_a_value_and_reports_it():
    """Stepping a float moves it inside its track and stores the result."""
    rows = [settings_editor.Setting("demo.value", settings_editor.FLOAT,
                                    v_min=0.0, v_max=1.0, step=0.25)]
    store = {"demo.value": 0.5}
    model = settings_editor.SettingsModel(
        rows, store.__getitem__, lambda k, v: store.__setitem__(k, v))
    assert model.adjust(rows[0], 1) == pytest.approx(0.75)
    assert model.adjust(rows[0], 1) == pytest.approx(1.0)
    assert model.adjust(rows[0], 1) == pytest.approx(1.0)   # clamped, not wrapped
    assert store["demo.value"] == pytest.approx(1.0)


def test_the_panel_draws_and_a_press_changes_a_setting():
    """Drawing lays the rows out; a press on a row's control edits it."""
    changed: list[tuple[str, object]] = []
    panel = settings_window.SettingsWindow(on_change=lambda k, v: changed.append((k, v)))
    panel.editor.groups.index = panel.editor.groups.options.index("cartoon")

    painter = RecordingPainter()
    panel.draw(painter, Rect(0.0, 0.0, 420.0, 300.0))
    assert painter.strings and painter.rects > 10
    assert panel.editor._boxes, "no rows were laid out"

    setting, box = next((s, b) for s, b in panel.editor._boxes
                        if s.kind in (settings_editor.BOOL, settings_editor.FLOAT))
    before = panel.model.get(setting.key)
    panel.press(box[0] + box[2] * 0.9, box[1] + box[3] * 0.5, Rect(0, 0, 420, 300))
    try:
        assert panel.model.get(setting.key) != before
        assert changed and changed[-1][0] == setting.key
    finally:
        panel.model.set(setting.key, before)


def test_filtering_and_grouping_narrow_the_list():
    """The filter box searches keys and labels; tabs split by section."""
    panel = settings_window.SettingsWindow()
    editor = panel.editor
    editor.groups.index = editor.groups.options.index("surface")
    everything = len(editor.rows())
    editor.filter.set_text("alpha")
    narrowed = editor.rows()
    assert 0 < len(narrowed) < everything
    # `transparency` is stored as `surface.alpha`, so searching the config
    # spelling has to find it -- the name it is edited under is not the name
    # somebody reading the JSON knows it by.
    assert all("alpha" in (one.key + one.label + one.source).lower()
               for one in narrowed)
    assert any(one.key == "transparency" for one in narrowed)


def test_the_scrollbar_moves_the_window_without_moving_the_cursor():
    """A section of two hundred rows has to be reachable with the mouse."""
    panel = settings_window.SettingsWindow()
    panel.editor.groups.index = panel.editor.groups.options.index("cartoon")
    panel.draw(RecordingPainter(), Rect(0.0, 0.0, 420.0, 300.0))
    bar = panel.editor.bar._box
    assert bar is not None
    panel.press(bar[0] + 2.0, bar[1] + bar[3], Rect(0, 0, 420, 300))
    assert panel.editor.top > 0
    assert panel.editor.row == 0
    panel.release()
    assert panel.editor.drag(bar[0] + 2.0, bar[1]) is False
