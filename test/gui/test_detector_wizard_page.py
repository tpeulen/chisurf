"""The detector editor shows real native calibration controls."""

from __future__ import annotations

from test.gui.test_channel_definition_lut_box import (
    _Page,
    isolated_detector_settings,
    native_driver,
)


def test_detector_wizard_page_constructs(tmp_path):
    """Latest remains an actual rendered calibration choice without a fake Qt combo."""
    from chisurf.plugins.core.setup_channel_definition.gui.model import default_settings

    page = _Page(
        settings=default_settings(),
        setups_file=str(tmp_path / "setups.json"),
        show_setup_selection=True,
    )
    try:
        ui = native_driver(page)
        ui.draw(2)
        assert page.editor.calibration == "Latest"
        assert "calibration" in ui.ids()
        ui.click("calibration")
        assert "Latest" in ui.draw(1).strings
    finally:
        page.close()
