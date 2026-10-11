"""Keyboard shortcuts of the native Help Browser, pressed through the emtk host's key events."""

from __future__ import annotations

import pytest
from emtk.events import ALT_MODIFIER, CONTROL_MODIFIER, SHIFT_MODIFIER
from emtk.keys import KEY_HOME, KEY_LEFT, KEY_RIGHT

from chisurf.plugins.core.help.gui.help_app import HelpApp
from chisurf.plugins.emtk_test_input import Driver

CTRL = CONTROL_MODIFIER


@pytest.fixture
def help_driver(tmp_path):
    app = HelpApp()
    d = Driver(app)
    d.draw(3)
    yield d
    app.close()


def _press(d, key, text="", modifiers=0):
    d.app.key(key, text, modifiers)
    d.draw(3)


def _two_pages(d, tmp_path):
    a, b = tmp_path / "a.md", tmp_path / "b.md"
    a.write_text("# A\n\nfirst\n", encoding="utf-8")
    b.write_text("# B\n\nsecond\n", encoding="utf-8")
    m = d.app.model
    assert m.open_page(a) and m.open_page(b)
    d.draw(2)
    return a, b


def test_alt_left_and_right_walk_the_history_like_back_and_forward(help_driver, tmp_path):
    a, b = _two_pages(help_driver, tmp_path)
    m = help_driver.app.model
    assert m.current_path == b
    _press(help_driver, KEY_LEFT, "", ALT_MODIFIER)
    assert m.current_path == a
    _press(help_driver, KEY_RIGHT, "", ALT_MODIFIER)
    assert m.current_path == b


def test_alt_home_shows_the_start_page(help_driver, tmp_path):
    _two_pages(help_driver, tmp_path)
    _press(help_driver, KEY_HOME, "", ALT_MODIFIER)
    assert help_driver.app.model.current_path is None


def test_ctrl_f_puts_the_keyboard_in_the_search_field(help_driver):
    _press(help_driver, ord("F"), "f", CTRL)
    help_driver.type("zoom")
    assert help_driver.app.model.search_query == "zoom"


def test_ctrl_shift_a_brings_up_the_ask_pane(help_driver):
    docks = help_driver.app.help_gui.docks
    docks.focus("toc")
    help_driver.draw(2)
    calls = []
    orig = docks.focus
    docks.focus = lambda key: (calls.append(key), orig(key))[1]
    _press(help_driver, ord("A"), "a", CTRL | SHIFT_MODIFIER)
    assert calls == ["ask"]


@pytest.mark.parametrize(
    ("key", "text", "delta"),
    [(ord("="), "=", 0.5), (ord("+"), "+", 0.5), (ord("-"), "-", -0.5)],
)
def test_ctrl_equals_plus_minus_zoom_the_text(help_driver, key, text, delta):
    m = help_driver.app.model
    before = m.font_size
    _press(help_driver, key, text, CTRL)
    assert m.font_size == pytest.approx(before + delta)


def test_ctrl_zero_restores_the_interface_font_size(help_driver):
    m = help_driver.app.model
    base = m.font_size
    _press(help_driver, ord("="), "=", CTRL)
    _press(help_driver, ord("="), "=", CTRL)
    assert m.font_size != base
    _press(help_driver, ord("0"), "0", CTRL)
    from emtk.type_scale import ui_font_pt

    assert m.font_size == ui_font_pt()


def test_plain_keys_without_modifiers_are_not_shortcuts(help_driver):
    m = help_driver.app.model
    before = m.font_size
    _press(help_driver, ord("="), "=", 0)
    assert m.font_size == before
