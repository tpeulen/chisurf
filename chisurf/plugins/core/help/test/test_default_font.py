"""The documentation browser's text follows emtk's type scale, not the Qt font size.

The reader used to start at ``gui.application_font_size`` (13 Qt points) under an
interface drawn at emtk's 8 pt, so its prose was half again the size of everything
around it. Its body is now the interface size, and A-/A+ zoom the whole scale.
"""

from emtk import type_scale

from chisurf.core import settings
from chisurf.plugins.core.help.gui.help_app import HelpModel


def test_initial_and_reset_zoom_use_the_interface_font_size(monkeypatch):
    monkeypatch.setitem(settings.gui, "application_font_size", 15.0)
    model = HelpModel()
    try:
        assert model.font_size == type_scale.ui_font_pt()
        assert model.zoom_factor() == 1.0
        model.set_font_size(20)
        assert model.zoom_factor() > 1.0
        model.reset_zoom()
        assert model.font_size == type_scale.ui_font_pt()
    finally:
        model.close()


def test_the_body_follows_the_interface_setting():
    before = type_scale.ui_font_pt()
    try:
        type_scale.set_ui_font_pt(10.0)
        model = HelpModel()
        try:
            assert model.font_size == 10.0
            assert model.zoom_factor() == 1.0
        finally:
            model.close()
    finally:
        type_scale.set_ui_font_pt(before)
