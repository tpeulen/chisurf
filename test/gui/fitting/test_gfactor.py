"""The detector editor uses the genuine native detector model and controls."""

from test.gui.test_channel_definition_lut_box import (
    _Page,
    isolated_detector_settings,
    native_driver,
)


def test_add_detector_rows(tmp_path):
    """Two actual Add actions populate portable detector rows and their numeric defaults."""
    page = _Page(
        settings={"detectors": {}, "windows": {}}, setups_file=str(tmp_path / "setups.json")
    )
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
