"""The canonical native app uses rich controls rather than the retired alternate."""

from __future__ import annotations

import json

from emtk import i18n, im
from emtk.keys import KEY_LEFT, KEY_RETURN, KEY_RIGHT
from emtk.testing import RecordingPainter

from chisurf.plugins.misc.games.number_quest.gui.app import NumberQuestApp


def test_native_rules_and_keyboard_controls():
    """Use explicit model state and physical press/release on the rich surface."""
    app = NumberQuestApp(clock=lambda: 0.0)
    try:
        app.game.reset(target=60)
        assert not app.key(ord("D"), "d")
        assert app.key(KEY_RIGHT)
        app.key_release(KEY_RIGHT)
        assert app.estimate == 51
        assert app.key(ord("E"), "e")
        app.key_release(ord("E"), "e")
        assert app.estimate == 61
        assert app.key(KEY_RETURN)
        app.key_release(KEY_RETURN)
        assert app.game.attempts_used == 1
        assert "Shorter" in app.message
        for _ in range(10):
            app.key(KEY_LEFT)
            app.key_release(KEY_LEFT)
        assert app.estimate == 51
        app.key(ord("R"), "r")
        app.key_release(ord("R"), "r")
        assert app.game.attempts_used == 0 and app.estimate == 50
    finally:
        app.close()


def test_native_render_contains_tooltips_and_serializable_state(monkeypatch):
    """The retained bitmap surface exposes help and its complete saved round."""
    app = NumberQuestApp(clock=lambda: 0.0)
    tips = []
    monkeypatch.setattr(im, "set_item_tooltip", tips.append)
    try:
        app.game.reset(target=50)
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *app.window_size)
        assert painter.calls
        assert any("Submit with Enter" in text for text in tips)
        assert app.window_size == (560, 420)
        assert json.loads(json.dumps(app.export_settings()))["target"] == 50
    finally:
        app.close()


def test_all_supported_locales_translate_core_labels():
    """The canonical factory still installs the Number Quest translation context."""
    from chisurf.plugins.misc.games.number_quest.gui.app import make_app

    app = make_app()
    try:
        for locale in ("en", "de", "fr", "es", "pt", "ru"):
            i18n.set_locale(locale)
            assert i18n.tr("Confirm", context="NumberQuest") != ""
    finally:
        i18n.set_locale("en")
        app.close()
