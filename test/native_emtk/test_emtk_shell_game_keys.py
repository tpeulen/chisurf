"""A game docked in the shell stops when its key goes up.

The owner's report: "in games, when I press a button, too many presses land and do not
stop landing". The shell forwarded a key's press to the focused tool but never its
release, so a game opened from Tools > Games kept the key held for good: Tetris
auto-repeated the move forever and Pong's paddle never stopped. Standalone, through
the native host, the same games were fine -- the gap was only in the shell's routing.
Driven through :class:`emtk.testing_realistic.RealisticDriver`, i.e. real ``key_down``
/ ``key_up`` canvas events through ``emtk.native`` (with its synthesised key repeat).
"""

from __future__ import annotations

import pytest
from emtk import i18n as toolkit_i18n
from emtk.keys import KEY_LEFT, KEY_UP
from emtk.testing_realistic import RealisticDriver

from chisurf.emtk.main_app import EmtkShellApp


@pytest.fixture(autouse=True)
def _settings(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    before = toolkit_i18n.get_locale()
    yield
    toolkit_i18n.set_locale(before)


def _open(game, factory):
    from chisurf.emtk import i18n

    i18n.install("en")
    catalog = {game: {"display_name": f"Tools:Games:{game}", "entrypoints": {"emtk": "x:y"}}}
    shell = EmtkShellApp(catalog, loader=lambda plugin_id: factory())
    driver = RealisticDriver(shell, (1200, 800), real_painter=False)
    driver.frame(2)
    hosted = shell.open_plugin(game, new=True)
    for _ in range(200):
        if hosted.build is None:
            break
        driver.frame(1)
    shell.docks.focus(hosted.key)
    driver.frame(2)
    app = getattr(hosted.app, "_control", hosted.app)
    app.clock = lambda: driver.loop.now  # the game's simulation runs on the driver's time
    app.last_frame = None
    driver.frame(1)
    shell._focus = hosted.key  # the tool has the keys, as after a click into it
    return shell, driver, app


def test_tetris_in_the_shell_moves_once_per_tap_and_stops_after_a_hold():
    from chisurf.plugins.misc.games.tetris.app import TetrisApp

    shell, driver, app = _open("tetris", TetrisApp)
    try:
        app.game.restart()
        app.game.x = 4
        driver.press(KEY_LEFT)
        assert app.game.x == 3, "a tap moves the piece one cell"
        driver.frame(60)  # a second of frames after the release
        assert not app.keys.held, "the release reached the game"
        assert app.game.x == 3, "nothing keeps landing after the key went up"
        driver.hold_key(KEY_LEFT, 1.0)
        after_hold = app.game.x
        assert after_hold == 0, "a held direction repeats to the wall"
        app.game.x = 5
        driver.frame(60)
        assert app.game.x == 5, "the repeat stops when the key goes up"
    finally:
        shell.close()


def test_pong_paddle_in_the_shell_stops_when_the_key_goes_up():
    from chisurf.plugins.misc.games.pong.app import PongApp

    shell, driver, app = _open("pong", PongApp)
    try:
        app.game.paused = False
        driver.hold_key(KEY_UP, 0.2)
        assert "up" not in app.keys.held, "the release reached the game"
        stopped = app.game.paddle_y
        driver.frame(60)
        assert app.game.paddle_y == stopped, "the paddle stops with the key"
    finally:
        shell.close()


def test_pong_second_player_letter_key_in_the_shell_releases():
    """W is typed through the OS ``char`` event; its key_up must still say "w"."""
    from chisurf.plugins.misc.games.pong.app import PongApp

    shell, driver, app = _open("pong", PongApp)
    try:
        app.game.paused = False
        driver.key(0, "w")
        assert "up" in app.p2.held
        driver.release_key()
        assert not app.p2.held, "the W release reached the game"
    finally:
        shell.close()


def test_a_release_goes_to_the_tool_that_took_the_press_after_a_focus_change():
    from types import SimpleNamespace

    from chisurf.emtk.tool_hub import ToolHubApp

    calls = []

    class Tool:
        def __init__(self, name):
            self.name = name

        def key(self, key, text="", modifiers=0):
            calls.append((self.name, "press", key))
            return True

        def key_release(self, key, text="", modifiers=0):
            calls.append((self.name, "release", key))
            return True

    first, second = Tool("first"), Tool("second")
    hub = SimpleNamespace(child=first, _child_focus=True, _child_keys={}, _overlay_open=lambda: False)
    ToolHubApp.key(hub, KEY_LEFT)
    hub.child = second  # the hub switched tools while the key was held
    ToolHubApp.key_release(hub, KEY_LEFT)
    ToolHubApp.key(hub, KEY_UP)
    ToolHubApp.focus_lost(hub)
    assert calls == [
        ("first", "press", KEY_LEFT),
        ("first", "release", KEY_LEFT),
        ("second", "press", KEY_UP),
        ("second", "release", KEY_UP),
    ]
