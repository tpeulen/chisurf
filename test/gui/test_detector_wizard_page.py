"""The public wizard page hosts real native calibration controls."""
from __future__ import annotations

from test.gui.test_detector_native_callers import isolated_detector_settings, native_driver


def test_detector_wizard_page_constructs(qapp):
    """Latest remains an actual rendered calibration choice without a fake Qt combo."""
    from chisurf.gui.widgets.wizard.tttr_channeldefinition import DetectorWizardPage
    page = DetectorWizardPage(allow_finish=False)
    try:
        ui = native_driver(page)
        ui.draw(2)
        assert page.editor.calibration == "Latest"
        assert "calibration" in ui.ids()
        ui.click("calibration")
        assert "Latest" in ui.draw(1).strings
    finally:
        page.close()
