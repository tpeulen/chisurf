"""Public wizard navigation uses the genuine native detector model and controls."""

from test.gui.test_detector_native_callers import isolated_detector_settings, native_driver


def test_detector_wizard_page_creation(qtbot):
    """The existing Qt navigation page contains the real native host."""
    from qtpy.QtWidgets import QWidget

    from chisurf.gui.widgets.wizard.tttr_channeldefinition import DetectorWizardPage

    page = DetectorWizardPage()
    qtbot.addWidget(page)
    assert isinstance(page.host, QWidget) and page.host.control is page.app
    page.close()


def test_add_detector_rows(qtbot):
    """Two actual Add actions populate portable detector rows and their numeric defaults."""
    from chisurf.gui.widgets.wizard.tttr_channeldefinition import DetectorWizardPage

    page = DetectorWizardPage(settings={"detectors": {}, "windows": {}})
    qtbot.addWidget(page)
    try:
        ui = native_driver(page)
        ui.draw(2)
        ui.click("add_detector")
        ui.click("add_detector")
        detectors = page.get_settings()["detectors"]
        assert len(detectors) == 2 and all(name.startswith("New Detector") for name in detectors)
        for detector in detectors.values():
            assert detector["chs"] == [0, 1]
            assert detector["micro_time_ranges"] == [[0, 2048]]
            assert detector["g_factor"] == 1.0 and detector["l1"] == detector["l2"] == 0.0
        rows = page.editor.detector_rows()
        assert [row["name"] for row in rows] == list(detectors)
    finally:
        page.close()
