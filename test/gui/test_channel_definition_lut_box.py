"""Widget tests for the channel-definition LUT-handling box (Phase 4).

Verifies the editor reorganizes into foldable boxes, the LUT box reflects the
loaded setup's ``apply_lut`` + per-channel LUTs, and ``get_settings`` round-trips
the LUT keys.
"""

import json
import pathlib

import numpy as np
import pytest

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


@pytest.mark.skipif(not _SPC.is_file(), reason="sample SPC not available")
def test_microtime_preview_applies_lut(qapp, tmp_path):
    """The decay preview reflects the configured LUT (regression: it read raw)."""
    from chisurf.plugins.tttr.tttr_lut_tools.api import compute

    data = {
        "windows": {"p": [0, 2048]},
        "detectors": {"g": {"chs": [0]}},
        "tttr_reading": {"file_type": "SPC-130"},
    }
    setup = tmp_path / "s.json"
    setup.write_text(json.dumps(data))
    page = _page(str(setup))
    page._microtime_decay_file_path = str(_SPC)

    page._apply_lut = False
    page._refresh_preview_lut()
    raw = np.asarray(page._microtime_counts).copy()

    tbl = compute.compute_lut_from_files(
        [str(_SPC)], channel=0, linear_start=1500, linear_stop=3000
    )
    page._channel_luts[0] = np.asarray(tbl["NTAC_fract"])
    page._apply_lut = True
    page._refresh_preview_lut()
    corrected = np.asarray(page._microtime_counts)

    n = min(raw.size, corrected.size)
    assert not np.array_equal(raw[:n], corrected[:n])  # LUT changed the decay
    # toggling the gate off returns the raw decay
    page._apply_lut = False
    page._refresh_preview_lut()
    assert np.array_equal(raw, np.asarray(page._microtime_counts))


def test_assigning_a_lut_auto_enables_apply(qapp, tmp_path):
    """General rule: adding a LUT turns the master gate ON (else it's never applied)."""
    data = {"detectors": {"g": {"chs": [0]}}, "tttr_reading": {"file_type": "SPC-130"}}
    setup = tmp_path / "s.json"
    setup.write_text(json.dumps(data))
    page = _page(str(setup))
    assert page._apply_lut is False

    class _Panel:
        class settings_panel:
            channel_luts = {0: np.linspace(0, 4096, 4096)}
            channel_shifts = {}

    page._pull_luts_from_panel(_Panel())
    assert page._apply_lut is True
    assert page._apply_lut_checkbox.isChecked() is True
    assert page.get_settings()["apply_lut"] is True


@pytest.mark.skipif(not _SPC.is_file(), reason="sample SPC not available")
def test_shift_dialog_loads_lut_corrected_and_round_trips(qapp):
    """The visual shift adjuster opens LUT-corrected and returns per-channel shifts."""
    from chisurf.gui.widgets.wizard.tttr_channeldefinition.shift_dialog import (
        MicrotimeShiftDialog,
    )

    ntac = np.linspace(0, 4096, 4096)
    dlg = MicrotimeShiftDialog(
        str(_SPC),
        routine="SPC-130",
        channel_luts={0: ntac, 1: ntac},
        channel_shifts={0: 5},
        apply_lut=True,
    )
    assert len(dlg._hists) > 1  # per-channel histograms
    assert dlg._spins[0].value() == 5  # seeded from current shifts
    dlg._spins[1].setValue(10)
    assert dlg.shifts() == {0: 5, 1: 10}


def test_polarization_resolved_flag_defaults_on_and_round_trips(qapp, tmp_path):
    data = {"detectors": {"g": {"chs": [0]}}, "tttr_reading": {"file_type": "SPC-130"}}
    setup = tmp_path / "s.json"
    setup.write_text(json.dumps(data))
    page = _page(str(setup))
    # default ON (no key in the setup)
    assert page._polarization_resolved is True
    assert page._pol_resolved_checkbox.isChecked() is True
    assert page.get_settings()["polarization_resolved"] is True
    # toggle off -> persisted
    page._pol_resolved_checkbox.setChecked(False)
    assert page.get_settings()["polarization_resolved"] is False


def test_toggle_apply_lut_updates_state(qapp, lut_setup):
    page = _page(lut_setup)
    page._apply_lut_checkbox.setChecked(False)
    assert page._apply_lut is False
    assert page.get_settings()["apply_lut"] is False
