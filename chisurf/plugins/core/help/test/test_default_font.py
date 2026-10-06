"""The documentation browser inherits the application font size."""

import pytest

from chisurf.core import settings
from chisurf.plugins.core.help.gui.help_app import HelpModel


def test_initial_and_reset_zoom_use_application_font_size(monkeypatch):
    monkeypatch.setitem(settings.gui, "application_font_size", 15.0)
    model = HelpModel()
    try:
        assert model.font_size == 15.0
        model.set_font_size(20)
        model.reset_zoom()
        assert model.font_size == 15.0
    finally:
        model.close()
