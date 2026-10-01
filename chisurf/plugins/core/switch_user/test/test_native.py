"""The earlier stream's two smoke tests, moved onto the model (the app no longer owns the login)."""
from __future__ import annotations

from emtk.testing import RecordingPainter

from chisurf.plugins.core.switch_user.app import SwitchUserApp


def test_native_switch_user_render_has_labels():
    app = SwitchUserApp()
    painter = RecordingPainter()
    app.draw(painter, 0, 0, 460, 460)
    assert "Login" in painter.strings and "Cancel" in painter.strings
