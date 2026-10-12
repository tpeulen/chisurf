"""The QuEst card on its own: it draws (or says why QuEst cannot start) and keeps the host's keyboard entry point."""

from __future__ import annotations

import pytest
from emtk.testing import RecordingPainter

from chisurf.plugins.quenching_estimator.gui import card as qmod

SIZES = [(1200, 800), (800, 600)]


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "s"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "m"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "m.sqlite"))
    monkeypatch.setenv("HOME", str(tmp_path))


def test_quest_card_draws_and_reports_when_unavailable(monkeypatch):
    app = qmod.make_app(qmod.QuestSession())
    for size in SIZES:
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
        if not app.session.ready:
            assert any("QuEst cannot start here" in t for t in painter.strings)
            assert "retry" in app.item_rects
    app.close()


def test_a_card_keeps_the_hosts_keyboard_entry_point():
    """``CardShell`` stored its dock key in ``self.key``, which shadowed ``ImApp.key``: every typed key on a card raised ``TypeError: 'str' object is not callable``."""
    app = qmod.make_app()
    assert callable(app.key)
    app.key(ord("a"), "a", 0)
    app.close()
