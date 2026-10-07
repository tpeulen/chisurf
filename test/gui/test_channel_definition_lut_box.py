"""Widget tests for the channel-definition LUT-handling box (Phase 4).

Verifies the editor reorganizes into foldable boxes, the LUT box reflects the
loaded setup's ``apply_lut`` + per-channel LUTs, and ``get_settings`` round-trips
the LUT keys.
"""

import json
import pathlib

import numpy as np
import pytest

from test.gui.test_detector_native_callers import isolated_detector_settings, native_driver

_SPC = (
    pathlib.Path(__file__).resolve().parents[2]
    / "test"
    / "data"
    / "tttr"
    / "BH"
    / "132"
    / "BH_SPC132.spc"
)


@pytest.fixture(autouse=True)
def _clear_lut_context():
    """Reset the process-global active-setup LUT context around each test."""
    from chisurf.core.fio.lut_context import clear_active_setup_lut

    clear_active_setup_lut()
    yield
    clear_active_setup_lut()


@pytest.fixture
def lut_setup(tmp_path):
    data = {
        "windows": {"prompt": [0, 2048]},
        "detectors": {"green": {"chs": [0, 8]}, "red": {"chs": [1, 9]}},
        "tttr_reading": {
            "file_type": "SPC-130",
            "macro_time_resolution": 1.0,
            "micro_time_resolution": 0.032,
            "micro_time_binning": 1,
        },
        "apply_lut": True,
        "channel_luts": {"0": [0.0, 1.0, 2.5, 4.0, 8.0]},
        "channel_shifts": {"8": 3},
        "channel_lut_sources": {"0": "uniform.spc"},
    }
    p = tmp_path / "setup.json"
    p.write_text(json.dumps(data))
    return str(p)


def _page(json_file):
    from chisurf.gui.widgets.wizard.tttr_channeldefinition import (
        DetectorWizardPage,
    )

    return DetectorWizardPage(json_file=json_file, show_setup_selection=False)


def test_foldable_boxes_and_lut_box_present(qapp, lut_setup):
    """The native section controls actually collapse and reopen the reading fields."""
    page = _page(lut_setup)
    try:
        ui = native_driver(page)
        ui.draw(2)
        assert {"section_reading", "section_windows", "section_detectors", "section_lut"} <= set(ui.ids())
        assert "file_type" in ui.ids()
        ui.click("section_reading")
        assert "file_type" not in ui.ids()
        ui.click("section_reading")
        assert "file_type" in ui.ids() and "apply_lut" in ui.ids()
    finally:
        page.close()


def test_lut_box_reflects_setup(qapp, lut_setup):
    """The real native LUT rows display the loaded sources and routing-channel union."""
    page = _page(lut_setup)
    try:
        ui = native_driver(page)
        ui.draw(2)
        assert page.model.data["apply_lut"] is True
        rows = page.editor.lut_rows()
        assert [int(row["channel"]) for row in rows] == [0, 1, 8, 9]
        labels = {int(row["channel"]): row["lut"] for row in rows}
        assert labels[0] == "uniform.spc" and labels[1] == "— none —"
    finally:
        page.close()


def test_get_settings_round_trips_lut_keys(qapp, lut_setup):
    page = _page(lut_setup)
    s = page.get_settings()
    assert s["apply_lut"] is True
    assert list(s["channel_luts"].keys()) == ["0"]
    assert s["channel_luts"]["0"] == [0.0, 1.0, 2.5, 4.0, 8.0]
    assert s["channel_shifts"]["8"] == 3


def _wait_preview(page, ui):
    """Wait only for this actual editor's preview worker and render its completed result."""
    import time
    deadline = time.monotonic() + 15
    while page.editor._future is not None and time.monotonic() < deadline:
        ui.draw(1)
        time.sleep(0.01)
    assert page.editor._future is None
    ui.draw(2)


def test_microtime_preview_applies_lut(qapp, tmp_path):
    """The physical preview follows the actual LUT gate and returns exactly to raw counts."""
    from chisurf.plugins.tttr.tttr_lut_tools.api import compute
    data = {"windows": {"p": [0, 2048]}, "detectors": {"g": {"chs": [0]}},
            "tttr_reading": {"file_type": "SPC-130"}}
    setup = tmp_path / "s.json"
    setup.write_text(json.dumps(data))
    page = _page(str(setup))
    try:
        page.model.read_tttr(str(_SPC))
        raw = page.model.preview[0].copy()
        table = compute.compute_lut_from_files([str(_SPC)], channel=0, linear_start=1500, linear_stop=3000)
        correction = tmp_path / "computed.npy"
        np.save(correction, table["NTAC_fract"])
        page.model.assign_lut(0, correction)
        page.editor.refresh_preview()
        ui = native_driver(page)
        _wait_preview(page, ui)
        assert not np.array_equal(raw, page.model.preview[0])
        ui.click("apply_lut")
        _wait_preview(page, ui)
        assert np.array_equal(raw, page.model.preview[0])
    finally:
        page.close()


def test_assigning_a_lut_auto_enables_apply(qapp, tmp_path):
    """A real assigned LUT enables its master gate rather than storing an unused correction."""
    data = {"detectors": {"g": {"chs": [0]}}, "tttr_reading": {"file_type": "SPC-130"}}
    setup = tmp_path / "s.json"
    setup.write_text(json.dumps(data))
    page = _page(str(setup))
    try:
        assert page.get_settings()["apply_lut"] is False
        correction = tmp_path / "correction.npy"
        np.save(correction, np.linspace(0, 4096, 4096))
        page.model.assign_lut(0, correction)
        native_driver(page).draw(2)
        assert page.get_settings()["apply_lut"] is True
        assert page.model.data["channel_luts"]["0"] == np.load(correction).tolist()
    finally:
        page.close()


def test_shift_dialog_loads_lut_corrected_and_round_trips(qapp, tmp_path):
    """The real native shift modal edits corrected physical histograms and persists its draft."""
    from emtk.events import CONTROL_MODIFIER
    from emtk.keys import KEY_RETURN
    setup = tmp_path / "s.json"
    setup.write_text(json.dumps({"detectors": {"g": {"chs": [0, 1]}},
                                "tttr_reading": {"file_type": "SPC-130"},
                                "channel_luts": {"0": np.linspace(0, 4096, 4096).tolist(),
                                                 "1": np.linspace(0, 4096, 4096).tolist()},
                                "channel_shifts": {"0": 5}, "apply_lut": True}))
    page = _page(str(setup))
    try:
        page.model.read_tttr(str(_SPC))
        ui = native_driver(page)
        ui.draw(2)
        ui.click("Adjust shifts...")
        assert page.editor.shift_window.open and len(page.model.preview) > 1
        assert page.editor._shift_draft[0] == 5
        ui.click("shift_1")
        ui.key(0x41, "a", CONTROL_MODIFIER)
        ui.type("10")
        ui.press(KEY_RETURN)
        ui.click("OK")
        assert not page.editor.shift_window.open
        assert page.get_settings()["channel_shifts"] == {"0": 5, "1": 10}
    finally:
        page.close()


def test_polarization_resolved_flag_defaults_on_and_round_trips(qapp, tmp_path):
    """An actual native checkbox persists the portable polarization flag."""
    data = {"detectors": {"g": {"chs": [0]}}, "tttr_reading": {"file_type": "SPC-130"}}
    setup = tmp_path / "s.json"
    setup.write_text(json.dumps(data))
    page = _page(str(setup))
    try:
        ui = native_driver(page)
        ui.draw(2)
        assert page.get_settings()["polarization_resolved"] is True
        ui.click("polarization")
        assert page.get_settings()["polarization_resolved"] is False
    finally:
        page.close()


def test_toggle_apply_lut_updates_state(qapp, lut_setup):
    """The real checkbox changes the owning model and exported portable settings."""
    page = _page(lut_setup)
    try:
        ui = native_driver(page)
        ui.draw(2)
        ui.click("apply_lut")
        assert page.model.data["apply_lut"] is False
        assert page.get_settings()["apply_lut"] is False
    finally:
        page.close()
