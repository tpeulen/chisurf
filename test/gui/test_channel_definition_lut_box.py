"""Widget tests for the channel-definition LUT-handling box (Phase 4).

Verifies the editor reorganizes into foldable boxes, the LUT box reflects the
loaded setup's ``apply_lut`` + per-channel LUTs, and ``get_settings`` round-trips
the LUT keys.
"""

import json

import pytest


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
    from chisurf.gui.widgets.wizard.tttr_channeldefinition.tttr_channel_definition import (
        DetectorWizardPage,
    )

    return DetectorWizardPage(json_file=json_file, show_setup_selection=False)


def test_foldable_boxes_and_lut_box_present(qapp, lut_setup):
    page = _page(lut_setup)
    assert page._box_reading is not None
    assert page._box_windows is not None
    assert page._box_detectors is not None
    assert page._box_lut is not None
    assert page._box_reading.title() == "TTTR Reading routine"
    assert page._box_lut.title().startswith("LUT handling")


def test_lut_box_reflects_setup(qapp, lut_setup):
    page = _page(lut_setup)
    assert page._apply_lut_checkbox.isChecked() is True
    # channels union of both detectors: 0, 1, 8, 9
    chans = [int(page._lut_table.item(r, 0).text()) for r in range(page._lut_table.rowCount())]
    assert chans == [0, 1, 8, 9]
    # channel 0 shows its assigned source, others none
    labels = {
        int(page._lut_table.item(r, 0).text()): page._lut_table.item(r, 1).text()
        for r in range(page._lut_table.rowCount())
    }
    assert labels[0] == "uniform.spc"
    assert labels[1] == "— none —"


def test_get_settings_round_trips_lut_keys(qapp, lut_setup):
    page = _page(lut_setup)
    s = page.get_settings()
    assert s["apply_lut"] is True
    assert list(s["channel_luts"].keys()) == ["0"]
    assert s["channel_luts"]["0"] == [0.0, 1.0, 2.5, 4.0, 8.0]
    assert s["channel_shifts"]["8"] == 3


def test_toggle_apply_lut_updates_state(qapp, lut_setup):
    page = _page(lut_setup)
    page._apply_lut_checkbox.setChecked(False)
    assert page._apply_lut is False
    assert page.get_settings()["apply_lut"] is False
