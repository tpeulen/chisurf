"""Games tests never make a sound: no system audio player is found unless a test supplies its own."""

import pytest


@pytest.fixture(autouse=True)
def _no_system_audio_player(monkeypatch):
    """``make_app()`` builds its default audio from ``emtk.audio.find_player``; make that find nothing."""
    try:
        import emtk.audio as emtk_audio
    except ImportError:  # an emtk older than emtk.audio: the games then have no audio either
        return
    monkeypatch.setattr(emtk_audio, "find_player", lambda *a, **k: None)
