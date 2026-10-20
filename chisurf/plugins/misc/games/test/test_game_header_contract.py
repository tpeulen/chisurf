"""Real declared game header actions own overlays without changing the canvas."""

from __future__ import annotations

import copy

import pytest
from emtk import i18n, im
from emtk.keys import KEY_ESCAPE, KEY_RETURN
from emtk.testing import Driver
from emtk.view_form import icon_caption

from .test_game_lifecycle_contract import (
    APPS,
    RecordingAudio,
    close_game,
    make_game,
    press_direction,
)

NARROW = {
    "pong": (560, 420),
    "breakout": (560, 480),
    "tetris": (400, 480),
    "number": (400, 320),
    "mines": (400, 400),
}
ACTIONS = {"open_help", "restart_game", "start_guide"}


def click_header(app, driver, name):
    """Click the real spec-rendered action rectangle."""
    driver.click(app.header_form.rects[name])


@pytest.mark.parametrize("name", APPS)
@pytest.mark.parametrize("narrow", [False, True])
def test_declared_header_is_bounded_and_tooltipped(name, narrow):
    """All three declared actions stay beside Sound in the existing top strip."""
    app = make_game(name)
    size = NARROW[name] if narrow else app.window_size
    driver = Driver(app, size)
    app.io.wall_clock = False
    try:
        before = copy.deepcopy(app.export_settings())
        driver.draw(2)
        assert app.export_settings() == before
        assert set(app.header_form.rects) == ACTIONS
        for x, y, width, height in app.header_form.rects.values():
            assert x >= 90 and y >= 0 and x + width <= size[0] and y + height <= 34
        for button in app.header_spec["sections"][0]["buttons"]:
            driver.hover(app.header_form.rects[button["action"]])
            app.io.now += 1.0
            painter = driver.draw(2)
            assert button["description"] in " ".join(painter.strings)
    finally:
        close_game(app)


@pytest.mark.parametrize("name", APPS)
def test_help_owns_game_keys_and_pointer_until_closed(name):
    """Opening help cannot submit, launch, reveal, drag a paddle or reset a round."""
    app = make_game(name)
    driver = Driver(app, NARROW[name])
    try:
        driver.draw(2)
        before = copy.deepcopy(app.export_settings())
        click_header(app, driver, "open_help")
        assert app.help_window.open and app.overlay_active
        assert app.export_settings() == before
        driver.press(KEY_RETURN)
        driver.key(ord("R"), "r")
        app.key_release(ord("R"), "r")
        app.pointer_move(180, 200, buttons=1)
        driver.click((180, 250))
        assert app.export_settings() == before
        driver.press(KEY_ESCAPE)
        assert not app.overlay_active
        key = press_direction(app, name)
        app.key_release(key)
    finally:
        close_game(app)


@pytest.mark.parametrize("name", APPS)
def test_tour_waits_for_actual_restart_and_help(name):
    """Starting a guide changes no round; real target clicks satisfy its awaits."""
    app = make_game(name)
    driver = Driver(app, NARROW[name])
    try:
        driver.draw(2)
        before = copy.deepcopy(app.export_settings())
        click_header(app, driver, "start_guide")
        assert app.tour.active and app.tour.awaiting
        assert app.export_settings() == before
        driver.press(KEY_RETURN)
        assert app.export_settings() == before
        click_header(app, driver, "restart_game")
        assert not app.tour.awaiting
        driver.click("Next ►")
        assert app.tour.step_idx == 1 and app.tour.awaiting
        click_header(app, driver, "open_help")
        assert app.help_window.open and not app.tour.awaiting
        driver.press(KEY_ESCAPE)
        assert app.tour.active and not app.help_window.open
        after_help = copy.deepcopy(app.export_settings())
        driver.click("Next ►")
        assert app.tour.step_idx == 2 and app.tour.awaiting
        assert app.export_settings() == after_help
        click_header(app, driver, "restart_game")
        assert not app.tour.awaiting
        driver.click("Finish ✓")
        assert not app.overlay_active
    finally:
        close_game(app)


@pytest.mark.parametrize("difficulty", [0, 1, 2])
def test_mines_header_does_not_cover_any_difficulty(difficulty, monkeypatch):
    """The existing minefield geometry stays below the shared top-strip controls."""
    app = make_game("mines")
    driver = Driver(app, NARROW["mines"])
    cells = []
    original = im.invisible_button

    def record(label, size):
        """Observe the actual submitted cell rather than recomputing geometry."""
        pressed = original(label, size)
        if label == "##cell-0-0":
            cells.append(im.get_item_rect())
        return pressed

    monkeypatch.setattr(im, "invisible_button", record)
    try:
        if difficulty:
            app.change_difficulty(difficulty)
        before = copy.deepcopy(app.export_settings())
        driver.draw(2)
        assert app.export_settings() == before
        assert cells
        x, y, width, height = cells[-1]
        assert y >= 34
        assert width > 0 and height > 0
    finally:
        close_game(app)


def test_header_translation_preserves_single_row(monkeypatch):
    """Translated captions are measured before the row is fitted to its space."""
    from chisurf.plugins.misc.games import _base

    original = _base.tr
    translations = {"Help": "Spielhilfe", "Restart": "Neu starten", "Guide": "Anleitung"}
    monkeypatch.setattr(_base, "tr", lambda text: translations.get(text, original(text)))
    app = make_game("number")
    try:
        painter = Driver(app, NARROW["number"]).draw(2)
        captions = {
            icon_caption(b["icon"], translations[b["label"]])
            for b in app.header_spec["sections"][0]["buttons"]
        }
        assert captions <= set(painter.strings)
        assert len({rect[1] for rect in app.header_form.rects.values()}) == 1
        assert all(rect[1] + rect[3] <= 34 for rect in app.header_form.rects.values())
    finally:
        close_game(app)
        i18n.set_locale("en")


@pytest.mark.parametrize("name", APPS)
def test_closed_game_cannot_open_chrome_or_restart(name):
    """New declared actions retain the established closed-game boundary."""
    app = make_game(name)
    before = copy.deepcopy(app.export_settings())
    app.close()
    app.open_help()
    app.start_guide()
    app.restart_game()
    assert not app.overlay_active
    assert app.export_settings() == before


@pytest.mark.parametrize("locale", ["en", "de", "fr", "es", "pt", "ru"])
@pytest.mark.parametrize("name", APPS)
def test_actual_locales_keep_header_and_tooltip_reachable(name, locale):
    """Use installed shared translations and real delayed tooltip painting."""
    from chisurf.plugins.misc.games import _base

    old_locale = i18n.get_locale()
    i18n.set_locale(locale)
    app = make_game(name)
    app.io.wall_clock = False
    driver = Driver(app, NARROW[name])
    try:
        painter = driver.draw(2)
        buttons = app.header_spec["sections"][0]["buttons"]
        for button in buttons:
            label = icon_caption(button["icon"], _base.tr(button["label"]))
            description = _base.tr(button["description"])
            assert label in painter.strings
            if locale != "en":
                assert description != button["description"]
            rect = app.header_form.rects[button["action"]]
            assert rect[0] >= 90 and rect[1] + rect[3] <= 34
            assert rect[0] + rect[2] <= NARROW[name][0]
            driver.hover(rect)
            app.io.now += 1.0
            tooltip = driver.draw(2)
            assert description in " ".join(tooltip.strings)
        assert len({rect[1] for rect in app.header_form.rects.values()}) == 1
    finally:
        close_game(app)
        i18n.set_locale(old_locale)


@pytest.mark.parametrize("name", APPS)
def test_default_help_and_tour_protect_non_target_header_and_sound(name):
    """Controls outside the help dialog and non-awaited tour targets stay inert."""
    audio = RecordingAudio()
    app = make_game(name, audio=audio)
    callback_events = []
    if name == "mines":
        app.audio_callback = lambda *event: callback_events.append(event)
    driver = Driver(app, app.window_size)
    try:
        if name == "pong":
            app.game.player_score = 7
        elif name in {"tetris", "breakout"}:
            app.game.score = 17
        elif name == "number":
            app.estimate = 25
            app.submit()
        else:
            app.flag()
        driver.draw(2)
        before = copy.deepcopy(app.export_settings())
        click_header(app, driver, "open_help")
        assert app.help_window.open
        audio_before = (list(audio.enabled), list(audio.effects))
        callback_before = list(callback_events)
        click_header(app, driver, "restart_game")
        click_header(app, driver, "start_guide")
        driver.click((35, 10))
        assert app.help_window.open and not app.tour.active
        assert app.export_settings() == before
        assert (audio.enabled, audio.effects) == audio_before
        assert callback_events == callback_before
        driver.press(KEY_ESCAPE)
        click_header(app, driver, "start_guide")
        assert app.tour.active and app.tour.awaiting
        click_header(app, driver, "open_help")
        driver.click((35, 10))
        assert not app.help_window.open
        assert app.export_settings() == before
        click_header(app, driver, "restart_game")
        assert not app.tour.awaiting
        assert app.export_settings() != before
        after_restart = copy.deepcopy(app.export_settings())
        click_header(app, driver, "restart_game")
        assert app.export_settings() == after_restart
    finally:
        close_game(app)
