"""The ChiSurf Settings panel scrolls and takes typed numbers, operated with real pointer and keyboard input.

The panel lists every packaged setting (well over a thousand rows); an emtk window clips and never scrolls, so the
fields live in a child region that scrolls with the wheel and a draggable scrollbar.
"""

from __future__ import annotations

import pytest

from chisurf.plugins.core.setup.test import seeded
from chisurf.plugins.emtk_test_input import CTRL, SIZE, SMALL, Driver


@pytest.fixture(params=[SIZE, SMALL], ids=["1200x800", "800x600"])
def hub(request, tmp_path, monkeypatch):
    from chisurf.plugins.core.setup.gui.app import make_app

    folder = seeded.prepare(tmp_path, monkeypatch)
    app = make_app(settings_dir=folder)
    drv = Driver(app, size=request.param)
    drv.draw(3)
    drv.click(drv.rect("dest_chisurf"))
    drv.draw(3)
    assert type(app.child).__name__ == "ConfigurationApp"
    yield drv
    app.close()


def body(drv):
    """The scrolling field region in window coordinates."""
    x, y, w, h = drv.app.child.item_rects["settings_body"]
    bx, by = drv.app.child_box[:2]
    return bx + x, by + y, w, h


def field(drv, label):
    x, y, w, h = drv.app.child.item_rects["field:" + label]
    bx, by = drv.app.child_box[:2]
    return bx + x, by + y, w, h


def label_y(drv, label):
    """The top of a setting's row (its field) in window coordinates; rows show their key, the full name is the tooltip."""
    return field(drv, label)[1]


def visible(drv, label, region):
    drv.draw(1)
    _, y, _, h = field(drv, label)
    _, y0, _, h0 = region
    return y0 <= y and y + h <= y0 + h0


def scrollbar_track(painter, region):
    x, y, w, h = region
    return [f for f in painter.fills if f[2] == 8.0 and abs(f[0] - (x + w - 10.0)) < 0.5 and f[1] >= y - 0.5]


def test_the_fields_overflow_into_a_scrollbar_and_the_wheel_brings_hidden_rows_into_view(hub):
    painter = hub.draw(2)
    region = body(hub)
    labels = [k[len("field:"):] for k in hub.app.child.item_rects if k.startswith("field:")]
    below = [lb for lb in labels if label_y(hub, lb) > region[1] + region[3]]
    assert below, "nothing below the fold: the test needs an overflowing settings document"
    assert scrollbar_track(painter, region), "the overflowing field region draws no scrollbar"
    target = below[0]
    assert not visible(hub, target, region)
    cx, cy = region[0] + region[2] * 0.4, region[1] + region[3] * 0.5
    for _ in range(80):
        hub.wheel(cx, cy, -3)
        if visible(hub, target, region):
            break
    assert visible(hub, target, region), f"{target} never scrolled into view"
    # the header above the body (language, buttons, search) does not scroll away
    assert "setting_search" in hub.app.child.item_rects
    assert any(t[5] == "Find a setting" and t[1] < region[1] for t in hub.draw(1).texts)


def test_a_setting_is_one_row_its_key_beside_the_field(hub):
    """A label above every field halved how many settings fit: the key sits in a column left of its field."""
    painter = hub.draw(2)
    _, fy, _, fh = field(hub, "correlator.split")
    keys = [t for t in painter.texts if t[5] == "split"]
    assert keys and any(fy - 2 <= t[1] <= fy + fh for t in keys), "the key is not on its field's row"
    assert not any(t[5] == "correlator.split" for t in painter.texts)  # the full name is the tooltip


def test_dragging_the_scrollbar_to_the_bottom_shows_the_last_setting(hub):
    painter = hub.draw(2)
    region = body(hub)
    labels = [k[len("field:"):] for k in hub.app.child.item_rects if k.startswith("field:")]
    last = max(labels, key=lambda lb: label_y(hub, lb))
    assert not visible(hub, last, region)
    x, y, w, h = region
    bar_x = x + w - 6.0
    hub.drag((bar_x, y + 6.0), (bar_x, y + h + 40.0))
    hub.draw(2)
    assert visible(hub, last, region), f"{last} is not reachable through the scrollbar"


def type_into_field(drv, label, text, commit="enter"):
    drv.app.child.setting_filter = label
    drv.draw(2)
    drv.click(field(drv, label), fx=0.3)
    assert drv.app.child.io.want_capture_keyboard, f"{label} did not take the keyboard"
    drv.app.key(0x41, "a", CTRL)
    drv.draw(1)
    drv.type(text)
    if commit == "enter":
        drv.enter()
    elif commit == "click-away":
        # a click on the panel's own "Find a setting" caption, away from the field
        caption = [t for t in drv.draw(1).texts if t[5] == "Find a setting"][-1]
        drv.click(caption[:4])


def test_an_integer_setting_is_typed_and_a_fraction_is_refused(hub):
    import yaml

    editor = hub.app.child
    type_into_field(hub, "gui.plot.font_size", "14")
    assert yaml.safe_load(editor.document.text)["gui"]["plot"]["font_size"] == 14
    type_into_field(hub, "gui.plot.font_size", "1.5")
    assert yaml.safe_load(editor.document.text)["gui"]["plot"]["font_size"] == 14
    assert "gui.plot.font_size" in editor.error


def test_a_float_setting_commits_on_click_away(hub):
    import yaml

    editor = hub.app.child
    type_into_field(hub, "gui.plot.line_width", "2.25", commit="click-away")
    assert yaml.safe_load(editor.document.text)["gui"]["plot"]["line_width"] == 2.25


def test_parse_number_clamps_and_refuses_fractions_for_integers():
    from chisurf.emtk.typed_field import parse_number

    assert parse_number(" 12 ") == 12 and parse_number("3.0") == 3
    assert parse_number("1e3", integer=False) == 1000.0
    assert parse_number("-5", minimum=0) == 0 and parse_number("9", maximum=4) == 4
    for bad, integer in (("1.5", True), ("abc", True), ("", False)):
        with pytest.raises(ValueError):
            parse_number(bad, integer=integer)


def test_save_pressed_straight_after_typing_writes_the_typed_number(hub):
    import os
    from pathlib import Path

    import yaml

    type_into_field(hub, "gui.plot.font_size", "17", commit=None)
    bx = hub.app.child_box[0]
    save = [t for t in hub.draw(2).texts if t[5] == "Save" and t[0] >= bx][-1]
    hub.click(save[:4])
    written = yaml.safe_load((Path(os.environ["CHISURF_SETTINGS_DIR"]) / "settings_chisurf.yaml").read_text())
    assert written["gui"]["plot"]["font_size"] == 17
