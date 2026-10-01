from __future__ import annotations

from emtk.testing import RecordingPainter

from ..app import BoardingApp


def test_native_boarding_pages_and_state_roundtrip():
    app = BoardingApp()
    app.page = "status"
    assert app.export_settings()["page"] == "status"
    other = BoardingApp()
    other.restore_settings({"page": "finish"})
    assert other.page == "finish"


def test_native_boarding_renders_tooltips():
    app = BoardingApp()
    painter = RecordingPainter()
    app.draw(painter, 0, 0, 980, 700)
    assert "Welcome to ChiSurf" in " ".join(painter.strings)
