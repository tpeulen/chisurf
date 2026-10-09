"""Game host defaults are authored while saved geometry and game controls survive."""

import copy
import importlib
import json
from pathlib import Path

import pytest
from emtk.testing import Driver

from chisurf.emtk.state import attach_native_state

GAMES = [("breakout", (820, 690)), ("pong", (820, 640)), ("tetris", (520, 620))]


@pytest.fixture(params=GAMES, ids=[name for name, _ in GAMES])
def game_module(request, tmp_path, monkeypatch):
    """Load the actual game factory with fresh isolated native preferences."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    name, size = request.param
    module = importlib.import_module(f"chisurf.plugins.misc.games.{name}.app")
    return name, size, module


def test_authored_default_is_consumed_without_changing_game_or_controls(game_module):
    """The normal factory retains state and actionable pause input at the existing size."""
    _, size, module = game_module
    spec = json.loads(Path(module.__file__).with_name("app.view.json").read_text())
    assert spec["window"] == dict(zip(("width", "height"), size))
    app = module.make_app()
    try:
        assert app.window_size == size
        app.clock = lambda: 0.0
        assert not app.game.paused
        assert app.key(ord("P"), "p")
        app.key_release(ord("P"), "p")
        assert app.game.paused
        saved = copy.deepcopy(app.export_settings())
        driver = Driver(app, size=app.window_size)
        driver.draw(2)
        assert app.export_settings() == saved
        assert app.window_size == size
        assert app.key(ord("P"), "p")
        app.key_release(ord("P"), "p")
        assert not app.game.paused
    finally:
        app.close()


def test_changed_authored_size_reaches_the_real_host(game_module, monkeypatch):
    """The constructor rereads the actual declaration rather than a class-only fallback."""
    _, _, module = game_module
    path = Path(module.__file__).with_name("app.view.json")
    original = path.read_bytes()
    read_text = Path.read_text

    def read(source, *args, **kwargs):
        """Supply an alternate declaration through the production file-read path."""
        if source == path:
            return json.dumps({"window": {"width": 930, "height": 730}})
        return read_text(source, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read)
    app = module.make_app()
    try:
        assert app.window_size == (930, 730)
        app.clock = lambda: 0.0
        Driver(app, size=app.window_size).draw(2)
        assert app.window_size == (930, 730)
        assert path.read_bytes() == original
    finally:
        app.close()


def test_fresh_launch_and_saved_resize_preserve_the_round(game_module):
    """Fresh persistence needs no seed; saved host size then wins over the declaration."""
    name, size, module = game_module
    app = attach_native_state(name, module.make_app())
    assert app.window_size == size
    app.clock = lambda: 0.0
    assert app.key(ord("P"), "p")
    app.key_release(ord("P"), "p")
    assert app.game.paused
    state = copy.deepcopy(app.export_settings())
    app.window_resized(1040, 780)
    app.close()
    reopened = attach_native_state(name, module.make_app())
    try:
        assert reopened.window_size == (1040, 780)
        assert reopened.export_settings() == state
        reopened.clock = lambda: 0.0
        Driver(reopened, size=reopened.window_size).draw(2)
        assert reopened.window_size == (1040, 780)
        assert reopened.export_settings() == state
        assert reopened.game.paused
    finally:
        reopened.close()
