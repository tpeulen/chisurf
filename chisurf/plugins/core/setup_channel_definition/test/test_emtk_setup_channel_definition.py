"""The emtk Setup:Channel Definition tool: setups, reading, LUTs, prompts, no Qt.

Hermetic: every setups file and MMFDB is a temporary one, and the environment of the MMFDB
subprocess is pointed at a temporary folder before ChiSurf is imported. The expected values are
the inputs: the setup the tool shows is :data:`driver.DATA`, a stored setup is that setup
(``norm(DATA)``), and the reading of ``test/data/tttr/BH/132/BH_SPC132.spc`` is checked against
the file's header and a per-channel histogram of its micro times, read with tttrlib directly.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.core.setup_channel_definition.test import driver
from chisurf.plugins.core.setup_channel_definition.test.driver import DATA, norm
from chisurf.plugins.emtk_layout import action_caption

HERE = Path(__file__).parent
PLUGIN = HERE.parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
SAMPLE = REPO / "test" / "data" / "tttr" / "BH" / "132" / "BH_SPC132.spc"
SIZES = [(1200, 800), (800, 600)]
ID = "setup_channel_definition"


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Nothing of the user's settings, MMFDB or LUT context is touched or leaked."""
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "unused.sqlite"))
    yield
    from chisurf.core.fio.lut_context import clear_active_setup_lut

    clear_active_setup_lut()


@pytest.fixture
def measurement(tmp_path):
    """A copy of the BH SPC-132 sample in the temporary folder."""
    path = tmp_path / "BH_SPC132.spc"
    shutil.copy(SAMPLE, path)
    return path


@pytest.fixture
def setups_file(tmp_path):
    return tmp_path / "emtk_setups.json"


@pytest.fixture
def app(setups_file):
    """The emtk tool on a temporary setups file, with the toolbar's setups loaded."""
    from chisurf.plugins.core.setup_channel_definition.gui.app import make_app

    tool = make_app(file_path=str(setups_file))
    driver.settle(tool)
    yield tool
    tool.close()


@pytest.fixture
def data_app(setups_file):
    """The tool showing :data:`DATA` (two detectors, two windows, timing)."""
    from chisurf.plugins.core.setup_channel_definition.gui.app import make_app

    tool = make_app(settings=DATA, file_path=str(setups_file))
    driver.settle(tool)
    yield tool
    tool.close()


#: What a saved copy of :data:`DATA` holds.
SAVED = norm(DATA)


def stored_emtk(path):
    data = json.loads(Path(path).read_text()) if Path(path).exists() else {}
    return {n: norm(s) for n, s in (data.get("setups") or {}).items()}


# ---------------------------------------------------------------------------
# 1. setup CRUD (setups file and MMFDB)
# ---------------------------------------------------------------------------
def test_save_rename_delete_in_the_setups_file(data_app, setups_file):
    """Save stores the shown setup under the name; rename moves it; delete empties the file."""
    bar = data_app.toolbar
    bar.request_save()
    assert bar.dialog == "save" and bar.name_text == ""
    bar.name_text = "Lab A"
    bar.confirm()
    assert stored_emtk(setups_file) == {"Lab A": SAVED}
    assert bar.selected == "Lab A"
    bar.request_rename()
    assert bar.name_text == "Lab A"
    bar.name_text = "Lab B"
    bar.confirm()
    assert stored_emtk(setups_file) == {"Lab B": SAVED}
    assert bar.selected == "Lab B"
    bar.request_delete()
    assert bar.dialog == "delete"
    bar.confirm()
    assert stored_emtk(setups_file) == {}
    assert bar.selected == ""


def test_save_stores_every_edit(data_app, setups_file):
    """Detector and window edits are stored as made; everything else stays as shown."""
    model = data_app.model
    model.data["detectors"]["R|G"]["g_factor"] = 2.5
    model.data["detectors"]["G|G"]["micro_time_ranges"] = [[0, 100], [200, 300]]
    model.data["windows"]["delayed"] = [2000, 4000]
    data_app.toolbar.save("Edited")
    import copy

    expected = copy.deepcopy(SAVED)
    expected["detectors"]["R|G"]["g_factor"] = 2.5
    expected["detectors"]["G|G"]["micro_time_ranges"] = [[0, 100], [200, 300]]
    expected["windows"]["delayed"] = [2000, 4000]
    assert stored_emtk(setups_file)["Edited"] == expected


def test_public_flag_is_saved_and_survives_rename(data_app, setups_file):
    """The owner can mark a saved setup public; the flag is stored and kept by a rename."""
    bar = data_app.toolbar
    assert not bar.can_public()
    bar.save("Mine")
    assert bar.can_public() is True
    bar.select_public(True)
    bar.save("Mine")
    assert json.loads(setups_file.read_text())["setups"]["Mine"]["_is_public"] is True
    assert data_app.page.public is True
    bar.request_rename()
    bar.name_text = "Ours"
    bar.confirm()
    assert json.loads(setups_file.read_text())["setups"]["Ours"]["_is_public"] is True


def test_public_is_available_only_to_the_owner(data_app):
    bar = data_app.toolbar
    bar.save("Mine")
    bar.definition.setups["Mine"]["_owner"] = "someone_else"
    assert not bar.can_public()
    bar.select_public(True)
    assert data_app.page.public is False  # refused: the flag did not change
    bar.definition.setups["Mine"]["_owner"] = None
    assert bar.can_public()


def test_rename_onto_an_existing_name_asks_before_overwriting(data_app, setups_file):
    """Declining keeps both setups; accepting replaces the other one."""
    bar = data_app.toolbar
    for name in ("One", "Two"):
        bar.save(name)
    bar.select("One")
    bar.request_rename()
    bar.name_text = "Two"
    bar.confirm()
    assert bar.dialog == "overwrite"
    bar.cancel()
    assert stored_emtk(setups_file) == {"One": SAVED, "Two": SAVED}
    assert bar.selected == "One"
    bar.request_rename()
    bar.name_text = "Two"
    bar.confirm()
    assert bar.dialog == "overwrite"
    bar.confirm()
    assert stored_emtk(setups_file) == {"Two": SAVED}
    assert bar.selected == "Two"


def test_declining_the_delete_confirmation_changes_nothing(data_app, setups_file):
    bar = data_app.toolbar
    bar.save("Keep me")
    bar.request_delete()
    assert bar.dialog == "delete"
    bar.cancel()
    assert bar.selected == "Keep me" and "Keep me" in stored_emtk(setups_file)
    assert bar.dialog == ""


def test_actions_without_a_selection_say_so_and_an_empty_name_does_nothing(data_app, setups_file):
    bar = data_app.toolbar
    for action in (bar.request_rename, bar.request_delete):
        action()
        assert data_app.page.status == "No setup selected." and bar.dialog == ""
    bar.request_save()
    bar.name_text = "   "
    bar.confirm()
    assert not setups_file.exists() and bar.selected == ""
    assert bar.rename("x") is False and bar.delete() is False


def test_a_failed_store_keeps_the_working_state_and_says_so(data_app, tmp_path):
    blocked = tmp_path / "blocked"
    blocked.write_text("a file where the setups folder should be")
    data_app.model.file_path = str(blocked / "setups.json")
    bar = data_app.toolbar
    assert bar.save("Nope") is False
    assert "Failed to save setup 'Nope'" in data_app.page.status
    assert bar.selected == "" and bar.definition.setups == {}
    assert data_app.model.data["detectors"]["G|G"]["chs"] == [8, 0, 3]


def test_setup_choice_loads_a_saved_setup_and_the_blank_entry_keeps_the_tables(data_app):
    bar = data_app.toolbar
    bar.save("Lab")
    data_app.model.data["detectors"].pop("R|G")
    bar.select("Lab")
    assert set(data_app.model.data["detectors"]) == {"G|G", "R|G"}
    assert bar.selected == "Lab" and data_app.page.setup_name == "Lab"
    bar.select("")
    assert bar.selected == "" and set(data_app.model.data["detectors"]) == {"G|G", "R|G"}
    assert not bar.can_public() and data_app.page.calibrations == []


def test_crud_and_calibration_in_the_mmfdb(tmp_path):
    """Save, Public, Calibration, Rename and Delete of the toolbar against a temporary MMFDB."""
    pytest.importorskip("mmfdb.repository")
    env = dict(
        os.environ,
        PYTHONPATH=os.pathsep.join([str(REPO), os.environ.get("PYTHONPATH", "")]),
    )
    done = subprocess.run(
        [sys.executable, str(HERE / "mmfdb_session.py"), str(tmp_path / "ref")],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    lines = [line for line in done.stdout.splitlines() if line.startswith("RESULT ")]
    assert lines, done.stdout[-1500:] + done.stderr[-1500:]
    log = json.loads(lines[0][len("RESULT ") :])
    assert log["saved"]["names"] == ["Lab A"] and log["saved"]["setups"] == {"Lab A": SAVED}
    assert log["saved"]["rows"]["Lab A"] == {"public": False, "owner": "user"}
    assert log["public_enabled_after_save"] is True
    assert log["saved_public"]["rows"]["Lab A"] == {"public": True, "owner": "user"}
    assert log["saved_public"]["setups"] == {"Lab A": SAVED}
    # rename: the same setup under the new name, still public
    assert log["renamed"]["names"] == ["Lab B"] and log["renamed"]["setups"] == {"Lab B": SAVED}
    assert log["renamed"]["rows"]["Lab B"]["public"] is True
    assert log["deleted"]["names"] == [] and log["deleted"]["rows"] == {}
    # calibration: the choice lists the stored snapshot and applies it (driver.CAL) to the detectors
    assert log["calibration_items"][0] == "Latest" and driver.STAMP in log["calibration_items"]
    assert log["calibration_cells"] == {n: list(v) for n, v in driver.CAL.items()}


def test_calibration_latest_is_a_no_op_and_a_snapshot_applies_to_named_detectors(tmp_path):
    from chisurf.core.setup_channel_definition import ChannelDefinition
    from chisurf.emtk.channel_definition import ChannelDefinitionWidget
    from chisurf.plugins.core.setup_channel_definition.gui.model import SetupToolbar

    class Database:
        def list_setup_calibration_dates(self, key):
            return ["2026-09-01"]

        def get_setup_calibration(self, key, calibrated_at=None):
            assert calibrated_at == "2026-09-01"
            return [
                {"channel_name": "G|G", "g_factor": 1.7, "l1": 0.1, "l2": 0.2},
                {"channel_name": "ghost", "g_factor": 9},
            ]

    page = ChannelDefinitionWidget(
        model=ChannelDefinition(DATA, file_path=str(tmp_path / "s.json"), db=Database())
    )
    bar = SetupToolbar(page)
    bar.definition.current_name = "Inst"
    bar.definition.setups = {"Inst": {}}
    page.calibrations = bar.definition.calibration_dates()
    assert bar.calibration_items() == ["Latest", "2026-09-01"]
    bar.select_calibration("Latest")
    assert page.model.data["detectors"]["G|G"]["g_factor"] == 1.0
    bar.select_calibration("2026-09-01")
    assert page.model.data["detectors"]["G|G"]["g_factor"] == 1.7
    assert page.model.data["detectors"]["R|G"]["g_factor"] == 1.25  # not in the snapshot: untouched
    assert "Applied the calibration of 2026-09-01 to 2 detector(s)." == page.status


# ---------------------------------------------------------------------------
# 2. detectors and windows through the shared editor
# ---------------------------------------------------------------------------
def test_the_tool_holds_the_given_detectors_windows_and_timing(data_app):
    """The setup handed to the tool is what it shows."""
    assert norm(data_app.get_settings()) == SAVED


# ---------------------------------------------------------------------------
# 3. reading a TTTR measurement
# ---------------------------------------------------------------------------
def test_reading_the_bh_sample_gives_its_header_timing_and_channel_histograms(data_app, measurement):
    """The header timing and every routing channel's micro-time histogram, as tttrlib reads the file."""
    import tttrlib

    tttr = tttrlib.TTTR(str(measurement), "SPC-130")
    header = tttr.get_header()
    routing = np.asarray(tttr.routing_channels)
    micro = np.asarray(tttr.micro_times)
    n_micro = int(header.number_of_micro_time_channels)
    driver.populate(data_app, measurement)
    reading = data_app.model.data["tttr_reading"]
    assert reading["macro_time_resolution"] == pytest.approx(header.macro_time_resolution * 1e9, rel=1e-12)
    assert reading["micro_time_resolution"] == pytest.approx(header.micro_time_resolution * 1e12, rel=1e-12)
    assert sorted(data_app.model.preview) == sorted(set(routing.tolist())) == [0, 1, 8, 9]
    for channel, counts in data_app.model.preview.items():
        np.testing.assert_array_equal(counts, np.bincount(micro[routing == channel], minlength=n_micro))
    settings = data_app.get_settings()["tttr_reading"]
    # the effective tick is the micro-time resolution times the binning (DATA bins by 2)
    assert settings["effective_micro_time_resolution"] == pytest.approx(
        header.micro_time_resolution * 1e12 * 2, rel=1e-5
    )
    assert settings["excitation_period"] == pytest.approx(13.5)
    assert data_app.page.status == "Header timing and per-routing-channel decay histograms loaded."


def test_binning_scales_the_effective_tick(data_app):
    """Effective micro-time resolution = micro-time resolution x binning."""
    data_app.model.data["tttr_reading"]["micro_time_binning"] = 4
    assert data_app.get_settings()["tttr_reading"][
        "effective_micro_time_resolution"
    ] == pytest.approx(DATA["tttr_reading"]["micro_time_resolution"] * 4, rel=1e-6)


def test_reading_something_that_is_not_a_measurement_reports_and_keeps_the_timing(
    data_app, tmp_path
):
    bad = tmp_path / "not_a_measurement.ptu"
    bad.write_text("this is not photon data")
    data_app.model.data["tttr_reading"]["file_type"] = "auto"  # detect the container
    before = json.dumps(data_app.model.data["tttr_reading"], sort_keys=True)
    data_app.page.read(str(bad))
    driver.finish_read(data_app)
    assert data_app.page.status.startswith("Error:")
    assert json.dumps(data_app.model.data["tttr_reading"], sort_keys=True) == before
    assert data_app.model.preview == {}


@pytest.mark.parametrize("file_type", ["SPC-130", "Auto", "PTU", "PTO"])
def test_a_file_that_is_not_photon_data_is_refused_whatever_the_file_type(
    data_app, tmp_path, file_type
):
    """The editor detects the container from the file and refuses what it cannot read, keeping the timing."""
    bad = tmp_path / "not_a_measurement.ptu"
    bad.write_text("this is not photon data")
    with pytest.raises(Exception):
        import tttrlib

        tttrlib.TTTR(str(bad))  # tttrlib itself refuses it
    data_app.model.data["tttr_reading"]["file_type"] = file_type
    before = dict(data_app.model.data["tttr_reading"])
    data_app.page.read(str(bad))
    driver.finish_read(data_app)
    assert data_app.page.status.startswith("Error:")
    assert data_app.model.data["tttr_reading"] == before


def test_a_read_in_progress_is_not_started_twice_and_can_be_cancelled(data_app, measurement):
    page = data_app.page
    page.read(str(measurement))
    page.read(str(measurement))
    assert page.status == "A calibration read is already running." or page._future is None
    page.cancel_read()
    driver.finish_read(data_app)
    assert page._future is None


# ---------------------------------------------------------------------------
# 4. LUT handling
# ---------------------------------------------------------------------------
def _lut_file(tmp_path):
    path = tmp_path / "channel.npy"
    np.save(path, np.linspace(0.0, 4095.0, 4096))
    return path


def test_an_assigned_lut_is_the_file_and_turns_the_gate_on(data_app, measurement, tmp_path):
    """The LUT file's values are assigned to the channel and the gate is switched on."""
    from chisurf.core.fio.lut_context import get_active_setup_lut

    lut = _lut_file(tmp_path)
    channel = 0
    data_app.model.assign_lut(channel, str(lut))
    assert data_app.model.data["apply_lut"] is True
    np.testing.assert_array_equal(data_app.model.data["channel_luts"][str(channel)], np.load(lut))
    luts, _shifts, apply = get_active_setup_lut()
    assert apply and channel in {int(k) for k in luts}


def test_loading_a_setup_with_the_gate_off_does_not_switch_it_on(data_app, tmp_path):
    bar = data_app.toolbar
    data_app.model.data["channel_luts"] = {"0": [0.0, 1.0, 2.0]}
    data_app.model.data["apply_lut"] = False
    bar.save("With LUT but off")
    bar.select("")
    bar.select("With LUT but off")
    assert data_app.model.data["apply_lut"] is False


def test_compute_shift_export_and_remove_a_lut(data_app, measurement, tmp_path):
    driver.populate(data_app, measurement)
    page, model = data_app.page, data_app.model
    channel = 8
    page.selected_channel = channel
    page._compute_lut()  # auto-detected linear region, as the editor's button does
    driver.finish_read(data_app)  # a new LUT re-reads the preview through itself
    assert str(channel) in model.data["channel_luts"]
    table = np.asarray(model.data["channel_luts"][str(channel)])
    assert table.size == model.raw_preview[channel].size and np.isfinite(table).all()
    assert model.data["apply_lut"] is True  # computing a LUT also turns the gate on
    out = tmp_path / "exported.json"
    model.export_lut(channel, out)
    from chisurf.plugins.tttr.tttr_lut_tools.api.io import load_lut_file

    np.testing.assert_allclose(load_lut_file(str(out)), table)
    model.data["channel_shifts"][str(channel)] = 3
    model.changed()
    from chisurf.core.fio.lut_context import get_active_setup_lut

    luts, shifts, apply = get_active_setup_lut()
    assert apply and {int(k): int(v) for k, v in shifts.items()}[channel] == 3
    page._remove_lut()
    assert str(channel) not in model.data["channel_luts"]


def test_compute_lut_without_a_measurement_says_what_to_do(data_app):
    data_app.page._compute_lut()
    assert (
        data_app.page.status == "Error: Read a uniform-illumination calibration measurement first."
    )


# ---------------------------------------------------------------------------
# 5. prompts, tooltips
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("prompt", ["save", "rename", "delete", "overwrite"])
def test_every_control_of_the_prompts_has_a_tooltip(data_app, prompt):
    from test.gui.emtk_port_parity import emtk_inventory

    bar = data_app.toolbar
    bar.save("One")
    bar.save("Two")
    bar.select("One")
    if prompt == "save":
        bar.request_save()
    elif prompt == "rename":
        bar.request_rename()
    elif prompt == "delete":
        bar.request_delete()
    else:
        bar.request_rename()
        bar.name_text = "Two"
        bar.confirm()
    assert bar.dialog == prompt
    inventory = emtk_inventory(data_app)
    assert any(
        row["label"] in ("Save", "Rename", "Delete", "Overwrite")
        for row in inventory["interactive"]
    )
    assert inventory["controls_without_tooltip"] == []


def test_the_window_has_the_plugins_name_as_its_title(data_app):
    assert "Setup: Channel Definition" in driver.settle(data_app).strings
    assert (
        json.loads((PLUGIN / "manifest.json").read_text())["display_name"]
        == "Setup:Channel Definition"
    )


# ---------------------------------------------------------------------------
# 6. help and guide
# ---------------------------------------------------------------------------
def test_the_guide_advances_when_the_user_presses_save(setups_file):
    from chisurf.plugins.core.setup_channel_definition.gui.app import make_app

    tool = make_app(settings=DATA, file_path=str(setups_file))
    driver.settle(tool)
    tool.tour.start(2)  # the "Save under a name" step awaits the Save button
    driver.settle(tool)
    assert tool.tour.awaiting
    assert driver.click_text(tool, action_caption("save"))
    assert not tool.tour.awaiting
    assert tool.toolbar.dialog == "save"
    tool.close()


# ---------------------------------------------------------------------------
# 7. manifest, no Qt
# ---------------------------------------------------------------------------
def test_the_manifest_opens_the_emtk_tool_only():
    manifest = json.loads((PLUGIN / "manifest.json").read_text())
    assert (
        manifest["entrypoints"]["emtk"]
        == "chisurf.plugins.core.setup_channel_definition.gui.app:make_app"
    )
    assert "gui" not in manifest["entrypoints"]


def test_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    result = qt_free(ID)
    assert result["ok"], result["output"]
    source = " ".join((PLUGIN / "gui" / name).read_text() for name in ("app.py", "model.py"))
    for forbidden in ("qtpy", "PyQt", "PySide", "chisurf.gui"):
        assert forbidden not in source
