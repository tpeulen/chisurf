from __future__ import annotations

import json

from emtk import i18n
from emtk.keys import KEY_RETURN
from emtk.testing import RecordingPainter

from chisurf.plugins.misc.games.number_quest.gui.app import NumberQuestApp


def test_native_rules_and_keyboard_controls():
    app = NumberQuestApp(target=60)
    assert app.key(0, "d") is True
    assert app.estimate == 51
    assert app.key(0, "e") is True
    assert app.estimate == 61
    assert app.key(KEY_RETURN, "") is True
    assert app.game.attempts_used == 1
    assert "Shorter" in app.message
    for _ in range(10):
        app.key(0, "a")
    assert app.estimate == 51
    app.key(0, "r")
    assert app.game.attempts_used == 0 and app.estimate == 50


def test_native_render_contains_tooltips_and_serializable_state():
    app = NumberQuestApp(target=50)
    painter = RecordingPainter()
    app.draw(painter, 0, 0, 520, 620)
    assert any("LIFETIME ESTIMATION" in text for text in painter.strings)
    assert any("Confirm" in text for text in painter.strings)
    json.dumps({"estimate": app.estimate, "history": app.history})


def test_all_supported_locales_translate_core_labels():
    for locale in ("en", "de", "fr", "es", "pt", "ru"):
        i18n.set_locale(locale)
        assert i18n.tr("Confirm", context="Number Quest") != ""
    i18n.set_locale("en")
