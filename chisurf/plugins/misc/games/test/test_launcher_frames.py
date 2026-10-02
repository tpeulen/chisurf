"""The launcher asks for frames while the open game needs them, and only then."""

from __future__ import annotations

from emtk.testing import RecordingPainter

from chisurf.plugins.misc.games.gui.app import make_app


def test_frames_follow_the_open_game(monkeypatch):
    app = make_app()
    try:
        app.draw(RecordingPainter(), 0, 0, 1200, 800)
        child = app.child
        assert child is not None
        monkeypatch.setattr(child, "animating", lambda: False)
        assert not app.animating()                    # a paused game: no frames
        monkeypatch.setattr(child, "animating", lambda: True)
        assert app.animating()                        # a running game (Pong, Tetris): frames
    finally:
        app.close()
