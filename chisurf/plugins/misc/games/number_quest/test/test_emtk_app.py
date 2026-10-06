"""Native behavior and import-boundary coverage independent of GPU access."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
from emtk import i18n
from emtk.app import as_surface
from emtk.keys import KEY_LEFT, KEY_RETURN, KEY_RIGHT
from emtk.testing import RecordingPainter

from ..app import NumberQuestApp, make_app
from ..core.game import GuessStatus
from ..translations import LOCALES, STRINGS, install_translations


@pytest.fixture
def app():
    instance = NumberQuestApp(clock=lambda: 0)
    instance.game.reset(target=37)
    return instance


def test_qt_blocked_native_factory():
    script = """import sys
from importlib.abc import MetaPathFinder
class BlockQt(MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'qtpy','PyQt5','PyQt6','PySide2','PySide6'}:
            raise AssertionError('Qt import: '+fullname)
sys.meta_path.insert(0, BlockQt())
from emtk.app import load_app
app=load_app('chisurf.plugins.misc.games.number_quest.app:make_app')
assert app.estimate == 50
app.close()
assert not any(name.startswith(('qtpy','PyQt','PySide')) for name in sys.modules)
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_dial_fine_coarse_clamp_and_repeat(app):
    app.key(KEY_RIGHT)
    app.key(KEY_RIGHT)  # OS repeat is not a second edge
    assert app.estimate == 51
    for _ in range(3):
        app.advance(0.1)
    assert app.estimate == 51
    app.advance(0.05)
    assert app.estimate == 52
    app.key_release(KEY_RIGHT)
    app.key(ord("E"), "e")
    assert app.estimate == 62
    app._nudge(100)
    assert app.estimate == 100
    app._nudge(-200)
    assert app.estimate == 1
    app.key_release(ord("E"), "e")
    app.key(KEY_LEFT)
    assert app.estimate == 1


def test_focus_and_surface_key_release_stop_repeat(app):
    surface = as_surface(app)
    assert surface.on_key_press(KEY_RIGHT, "", 0)
    assert surface.on_key_release(KEY_RIGHT, "", 0)
    assert not app.animating()
    app.key(KEY_LEFT)
    app.focus_lost()
    before = app.estimate
    app.advance(0.1)
    assert app.estimate == before and not app.held and not app.repeat


def test_hints_win_score_history_and_confirm_new_round(app):
    for value, hint in ((20, "Longer"), (80, "Shorter"), (37, "You found")):
        app.estimate = value
        app.submit()
        assert hint in app.message
    assert app.game.status is GuessStatus.WON
    assert app.game.score == 700 and app.game.attempts_remaining == 4
    assert app.history == [20, 80, 37]
    app.key(KEY_RETURN)
    app.key(KEY_RETURN)
    assert not app.history and app.game.attempts_remaining == 7
    assert app.estimate == 50 and app.hint == "initial"


def test_losing_round_reveals_target_and_restart(app):
    app.estimate = 1
    for _ in range(7):
        app.submit()
    assert app.game.status is GuessStatus.LOST and "37" in app.message
    assert app.game.score == 300
    app.key(ord("R"), "r")
    assert app.game.status is GuessStatus.ACTIVE and app.history == []


def test_exponential_curve(app):
    assert app.tau == 5
    short = [app._decay_point(i, 1)[1] for i in range(0, 60, 10)]
    assert short == sorted(short)
    assert app._decay_point(30, 8)[1] < app._decay_point(30, 1)[1]


def test_saved_round_is_atomic_and_derives_status_from_rules(app):
    for value in (50, 25, 37):
        app.estimate = value
        app.submit()
    state = app.export_settings()
    other = NumberQuestApp()
    other.restore_settings(state)
    assert other.export_settings() == state and other.game.status is GuessStatus.WON
    for key, value in (
        ("target", 101),
        ("estimate", True),
        ("history", [37, 25]),
        ("sound_enabled", 1),
    ):
        invalid = copy.deepcopy(state)
        invalid[key] = value
        with pytest.raises(ValueError):
            other.restore_settings(invalid)
        assert other.export_settings() == state


def test_close_stops_inputs_and_releases_audio(app):
    class Audio:
        enabled = True
        closed = False
        played = []

        def set_enabled(self, value):
            self.enabled = value

        def close(self):
            self.closed = True

        def sfx(self, *effect):
            self.played.append(effect)

    audio = Audio()
    app.audio = audio
    app.set_sound()
    app.estimate = 37
    app.submit()
    assert audio.played == [("guess", 880)]
    app.key(KEY_RIGHT)
    app.close()
    assert audio.closed and not audio.enabled and not app.animating()
    estimate = app.estimate
    app.advance(0.1)
    assert app.estimate == estimate and not app.key(KEY_LEFT)


def click(app, x, y):
    painter = RecordingPainter()
    app.draw(painter, 0, 0, 560, 420)
    app.pointer_press(x, y, 1)
    app.draw(painter, 0, 0, 560, 420)
    app.pointer_release(x, y, 1)
    app.draw(painter, 0, 0, 560, 420)


def test_plot_dial_and_footer_mouse_actions(app):
    app.draw(RecordingPainter(), 0, 0, 560, 420)
    ox, oy, scale = app.board
    click(app, ox + 40 * scale, oy + 140 * scale)
    assert app.estimate == 1
    click(app, ox + 200 * scale, oy + 324 * scale)
    assert app.history == [1]
    click(app, ox + 320 * scale, oy + 324 * scale)
    assert app.history == [] and app.estimate == 50


def test_six_locales_tooltips_and_responsive_board():
    install_translations()
    try:
        for locale in LOCALES:
            i18n.set_locale(locale)
            for source, values in STRINGS.items():
                assert len(values) == 5
                assert i18n.tr(source, context="NumberQuest") == (
                    source if locale == "en" else values[LOCALES.index(locale) - 1]
                )
            app = make_app()
            app.clock = lambda: 0
            for w, h in ((560, 420), (360, 420)):
                app.draw(RecordingPainter(), 0, 0, w, h)
                ox, oy, scale = app.board
                assert ox >= 0 and oy >= 34
                assert ox + 420 * scale <= w and oy + 340 * scale <= h
    finally:
        i18n.set_locale("en")


def test_manifest_factory():
    manifest = json.loads((Path(__file__).parents[1] / "manifest.json").read_text())
    assert manifest["entrypoints"]["emtk"] == "chisurf.plugins.misc.games.number_quest.app:make_app"
