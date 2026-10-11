"""The games' audio backend: shared GameAudio over emtk.audio, wired to the uniform Sound toggle."""

from __future__ import annotations

import importlib
import threading

import pytest

pytest.importorskip("emtk.audio")

from emtk.audio import AudioOutput
from emtk.testing import RecordingPainter

from chisurf.plugins.emtk_layout import SOUND_OFF_ICON, action_caption
from chisurf.plugins.misc.games._audio import GameAudio, default_audio

GAMES = {
    "pong": ("chisurf.plugins.misc.games.pong.app", "battle"),
    "tetris": ("chisurf.plugins.misc.games.tetris.app", "town"),
    "breakout": ("chisurf.plugins.misc.games.breakout.app", "overworld"),
    "number_quest": ("chisurf.plugins.misc.games.number_quest.gui.app", "town"),
    "minesweeper": ("chisurf.plugins.misc.games.minesweeper.gui.app", "underworld"),
}


class Proc:
    def __init__(self, argv):
        self.argv, self.done = argv, threading.Event()

    def poll(self):
        return 0 if self.done.is_set() else None

    def wait(self):
        self.done.wait(2)

    def terminate(self):
        self.done.set()


class Player:
    """A fake system player that records every launch."""

    def __init__(self):
        self.launched = []

    def __call__(self, argv):
        proc = Proc(argv)
        self.launched.append(proc)
        return proc

    def live(self, marker=""):
        return [p for p in self.launched if not p.done.is_set() and marker in p.argv[-1]]


@pytest.fixture
def player():
    return Player()


def make_audio(player, context="town"):
    out = AudioOutput(player=("/bin/play", ("{path}",)), launcher=player)
    return GameAudio(context, output=out)


def wait_for(predicate, seconds=5.0):
    end = threading.Event()
    for _ in range(int(seconds / 0.01)):
        if predicate():
            return True
        end.wait(0.01)
    return False


def test_audio_is_silent_until_switched_on(player):
    audio = make_audio(player)
    audio.sfx("guess", 880)
    assert player.launched == []
    audio.set_enabled(True)
    audio.sfx("guess", 880)
    assert player.live("sfx-guess")
    audio.close()


def test_music_loops_in_the_context_and_stops_when_muted(player):
    audio = make_audio(player, "battle")
    audio.set_enabled(True)
    assert wait_for(lambda: player.live("music"))
    audio.set_enabled(False)
    assert not player.live()
    audio.set_enabled(True)  # focus returns: the piece starts again
    assert wait_for(lambda: player.live("music"))
    audio.close()
    assert not player.live()


def test_a_render_that_finishes_after_mute_stays_silent(player):
    audio = make_audio(player, "town")
    audio.set_enabled(True)
    audio.set_enabled(False)
    threading.Event().wait(0.5)
    assert not player.launched or not player.live()
    audio.close()


def test_without_a_player_there_is_no_default_audio():
    # games/conftest.py makes emtk.audio.find_player find nothing
    assert default_audio("town") is None


@pytest.mark.parametrize("name", sorted(GAMES))
def test_every_game_toggle_is_enabled_with_audio_and_greyed_without(name, player, monkeypatch):
    module = importlib.import_module(GAMES[name][0])
    monkeypatch.setattr("emtk.audio.find_player", lambda *a, **k: ("/bin/play", ("{path}",)))
    monkeypatch.setattr("emtk.audio.AudioOutput._popen", staticmethod(player))
    app = module.make_app()
    assert app.audio is not None, name
    painter = RecordingPainter()
    app.draw(painter, 0, 0, 800, 650)
    assert action_caption("sound", SOUND_OFF_ICON) in painter.strings
    assert app.audio.available
    app.audio.set_context(None)  # keep this test about effects only
    app.key(ord("m"), "m") if name == "minesweeper" else app.set_sound()
    assert app.sound_enabled is True
    assert app.audio.enabled
    app.focus_lost()
    assert not app.audio.enabled and app.sound_enabled  # muted, preference kept
    app.focus_gained()
    assert app.audio.enabled
    app.close()
    assert app.audio.closed
    app_none = module.make_app(**({"audio": None}))
    assert getattr(app_none, "audio", None) is None
