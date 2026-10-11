"""The single canonical GUI retains rich controls and plugin-owned resources."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest
from emtk import i18n, im
from emtk.testing import Driver

from chisurf.plugins.misc.games.gui.registry import GAME_PANELS
from chisurf.plugins.misc.games.number_quest.gui import app as owner
from chisurf.plugins.misc.games.number_quest.gui import drawing


def test_canonical_factory_and_resources_use_the_rich_contract():
    """Discovery and resource ownership follow the move without an alternate API."""
    plugin = Path(owner.__file__).parent.parent
    manifest = json.loads((plugin / "manifest.json").read_text())
    factory = "chisurf.plugins.misc.games.number_quest.gui.app:make_app"
    assert manifest["entrypoints"]["emtk"] == factory
    assert next(row for row in GAME_PANELS if row["name"] == "Number Quest")["emtk"] == factory
    assert "target" not in inspect.signature(owner.NumberQuestApp).parameters
    assert drawing.GLYPHS == json.loads((plugin / "glyphs.json").read_text())
    app = owner.make_app()
    try:
        assert app.window_size == (560, 420)
        assert owner.tr("Sound") == i18n.tr("Sound", context="NumberQuest")
    finally:
        app.close()


@pytest.mark.parametrize("size", [(560, 420), (360, 420)])
def test_rich_pointer_inventory_and_optional_audio_survive_move(size, monkeypatch):
    """Exercise the real plot, guidance, footer halves and supplied sound control."""

    class Audio:
        """Record the explicit optional host interface without starting playback."""

        def __init__(self):
            """Start with no effects and disabled output."""
            self.enabled = False
            self.effects = []
            self.closed = False

        def set_enabled(self, enabled):
            """Remember the host's output switch."""
            self.enabled = enabled

        def sfx(self, *effect):
            """Retain effects requested by the real game model."""
            self.effects.append(effect)

        def close(self):
            """Record release of the supplied resource."""
            self.closed = True

    audio = Audio()
    app = owner.NumberQuestApp(audio=audio, clock=lambda: 0.0)
    app.game.reset(target=53)
    app.estimate = 45
    app.submit()
    app.estimate = 60
    app.submit()
    app.estimate = 50
    app.io.wall_clock = False
    tips = []
    monkeypatch.setattr(im, "set_item_tooltip", tips.append)
    driver = Driver(app, size)
    try:
        driver.draw(2)
        ox, oy, scale = app.board
        assert ox >= 0 and oy >= 34
        assert ox + 420 * scale <= size[0] and oy + 340 * scale <= size[1]
        before = app.export_settings()
        driver.click((ox + 100 * scale, oy + 306 * scale))
        assert app.export_settings() == before
        driver.click((ox + 40 * scale, oy + 140 * scale))
        assert app.estimate == 1
        driver.click((ox + 200 * scale, oy + 324 * scale))
        assert app.history == [45, 60, 1]
        driver.click((ox + 320 * scale, oy + 324 * scale))
        assert app.history == [] and app.estimate == 50
        driver.click((30, 15))
        assert audio.enabled and app.sound_enabled
        assert any("Submit with Enter" in tip for tip in tips)
        assert any("Q/E" in tip for tip in tips)
    finally:
        app.close()
    assert audio.closed and not audio.enabled
