"""A first native launch has no saved payload for a strict round restorer."""

import pytest
from emtk.app import ImApp

from chisurf.emtk.plugins import load_plugin
from chisurf.emtk.state import attach_native_state, save_settings


@pytest.mark.parametrize("plugin_id", ["pong", "breakout", "minesweeper", "number_quest", "tetris"])
def test_fresh_game_launch_and_saved_round_restore(plugin_id, tmp_path, monkeypatch):
    """Fresh defaults launch, then the complete saved round and geometry return."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    first = load_plugin(plugin_id, persist=True)
    try:
        expected = first.export_settings()
        first.window_resized(910, 680)
    finally:
        first.close()
    second = load_plugin(plugin_id, persist=True)
    try:
        assert second.export_settings() == expected
        assert second.window_size == (910, 680)
    finally:
        second.close()


def test_nonempty_invalid_saved_settings_still_fail(tmp_path, monkeypatch):
    """Skipping absent state must not suppress a real invalid stored payload."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    assert save_settings("strict_restore", {"unexpected": 1})
    app = ImApp(lambda: None)
    app.restore_settings = lambda settings: settings["required"]
    with pytest.raises(KeyError, match="required"):
        attach_native_state("strict_restore", app)


def test_empty_saved_settings_do_not_call_strict_restore(tmp_path, monkeypatch):
    """An explicit empty settings object is equivalent to no saved preferences."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    assert save_settings("empty_restore", {})
    restored = []
    app = ImApp(lambda: None)
    app.restore_settings = restored.append
    attach_native_state("empty_restore", app)
    assert restored == []
    assert app.window_size == (1200, 800)
    app.close()
