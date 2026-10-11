"""The emtk Setup:Channel Definition tool against the Qt tool: setups, reading, LUTs, tabs, no Qt.

Hermetic: every setups file and MMFDB is a temporary one, the environment of the comparison
subprocess is pointed at a temporary folder before ChiSurf is imported, and the Qt tool is built
offscreen with its setups file redirected into ``tmp_path``. The measurement is a copy of
``test/data/tttr/BH/132/BH_SPC132.spc``.
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


@pytest.fixture
def qapp():
    pytest.importorskip("qtpy")
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def legacy_reference():
    """Load the immutable measured original form, with explicit source provenance."""
    return json.loads((HERE / "fixtures/detector_page_legacy.json").read_text())


@pytest.fixture
def legacy():
    """Provide frozen original Qt outputs without importing the deleted renderer."""
    return legacy_reference()


def stored_emtk(path):
    data = json.loads(Path(path).read_text()) if Path(path).exists() else {}
    return {n: norm(s) for n, s in (data.get("setups") or {}).items()}


# ---------------------------------------------------------------------------
# 1. setup CRUD equals the Qt tool (setups file and MMFDB)
# ---------------------------------------------------------------------------
def test_save_rename_delete_equal_frozen_original_file_store(legacy, data_app, setups_file):
    """Each named-store CRUD state equals the actual pre-retirement Qt output."""
    bar = data_app.toolbar
    bar.request_save()
    assert bar.dialog == "save" and bar.name_text == ""
    bar.name_text = "Lab A"
    bar.confirm()
    assert stored_emtk(setups_file) == legacy["crud_file"]["saved"]["stored"] != {}
    assert bar.selected == legacy["crud_file"]["saved"]["selected"] == "Lab A"
    bar.request_rename()
    assert bar.name_text == "Lab A"
    bar.name_text = "Lab B"
    bar.confirm()
    assert stored_emtk(setups_file) == legacy["crud_file"]["renamed"]["stored"]
    assert bar.selected == "Lab B"
    bar.request_delete()
    assert bar.dialog == "delete"
    bar.confirm()
    assert stored_emtk(setups_file) == legacy["crud_file"]["deleted"]["stored"] == {}
    assert bar.selected == ""


def test_save_stores_every_edit_equal_frozen_original(legacy, data_app, setups_file):
    """Scientific detector/window edits must equal the original independently captured storage."""
    model = data_app.model
    model.data["detectors"]["red"]["g_factor"] = 2.5
    model.data["detectors"]["green"]["micro_time_ranges"] = [[0, 100], [200, 300]]
    model.data["windows"]["delayed"] = [2000, 4000]
    data_app.toolbar.save("Edited")
    assert stored_emtk(setups_file)["Edited"] == legacy["edited"]
    assert stored_emtk(setups_file)["Edited"]["detectors"]["red"]["g_factor"] == 2.5


def test_public_flag_is_saved_like_frozen_original_and_survives_rename(
    legacy, data_app, setups_file
):
    """Native persistence retains the original public flag and its corrected rename behavior."""
    bar = data_app.toolbar
    assert not bar.can_public()
    bar.save("Mine")
    assert bar.can_public() is legacy["public_saved"]["public_enabled"] is True
    bar.select_public(True)
    bar.save("Mine")
    assert json.loads(setups_file.read_text())["setups"]["Mine"]["_is_public"] is True
    assert legacy["public_saved"]["raw"]["setups"]["Mine"]["_is_public"] is True
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


def test_rename_overwrite_matches_frozen_original_confirmation_states(
    legacy, data_app, setups_file
):
    """Decline and acceptance retain the original separate confirmation semantics."""
    bar = data_app.toolbar
    for name in ("One", "Two"):
        bar.save(name)
    bar.select("One")
    bar.request_rename()
    bar.name_text = "Two"
    bar.confirm()
    assert bar.dialog == "overwrite"
    bar.cancel()
    assert stored_emtk(setups_file) == legacy["overwrite_declined"]["stored"]
    assert bar.selected == "One"
    bar.request_rename()
    bar.name_text = "Two"
    bar.confirm()
    assert bar.dialog == "overwrite"
    bar.confirm()
    assert stored_emtk(setups_file) == legacy["overwrite_accepted"]["stored"]
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
    assert data_app.model.data["detectors"]["green"]["chs"] == [8, 0, 3]


def test_setup_choice_loads_a_saved_setup_and_the_blank_entry_keeps_the_tables(data_app):
    bar = data_app.toolbar
    bar.save("Lab")
    data_app.model.data["detectors"].pop("red")
    bar.select("Lab")
    assert set(data_app.model.data["detectors"]) == {"green", "red"}
    assert bar.selected == "Lab" and data_app.page.setup_name == "Lab"
    bar.select("")
    assert bar.selected == "" and set(data_app.model.data["detectors"]) == {"green", "red"}
    assert not bar.can_public() and data_app.page.calibrations == []


def test_crud_and_calibration_in_the_mmfdb_equal_the_qt_tool(tmp_path):
    """Save, Public, Calibration, Rename and Delete against a temporary MMFDB, Qt and emtk side by side."""
    pytest.importorskip("qtpy")
    pytest.importorskip("mmfdb.repository")
    env = dict(
        os.environ,
        QT_QPA_PLATFORM="offscreen",
        PYTHONPATH=os.pathsep.join([str(REPO), os.environ.get("PYTHONPATH", "")]),
    )
    done = subprocess.run(
        [sys.executable, str(HERE / "reference.py"), str(tmp_path / "ref")],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    lines = [line for line in done.stdout.splitlines() if line.startswith("RESULT ")]
    assert lines, done.stdout[-1500:] + done.stderr[-1500:]
    result = json.loads(lines[0][len("RESULT ") :])
    qt, emtk = result["qt"], result["emtk"]
    # saved, saved public and deleted: identical stored setups, owners and public flags
    for step in ("saved", "saved_public", "deleted"):
        assert emtk[step] == qt[step], step
    assert emtk["saved"]["rows"]["Lab A"] == {"public": False, "owner": "user"}
    assert emtk["saved_public"]["rows"]["Lab A"]["public"] is True
    assert emtk["public_enabled_after_save"] is qt["public_enabled_after_save"] is True
    # rename: the same setup under the new name
    assert emtk["renamed"]["names"] == qt["renamed"]["names"] == ["Lab B"]
    assert emtk["renamed"]["setups"] == qt["renamed"]["setups"]
    # The Qt tool drops the Public flag when it renames (its loader does not return it); the
    # emtk model keeps it. Not copied: the flag of a shared setup must not silently revert.
    assert emtk["renamed"]["rows"]["Lab B"]["public"] is True
    assert qt["renamed"]["rows"]["Lab B"]["public"] in (True, False)
    # calibration: the emtk choice lists the stored snapshot and applies it to the detectors
    assert (
        emtk["calibration_items"][0] == "Latest"
        and "2026-09-01T10:00:00" in emtk["calibration_items"]
    )
    assert emtk["calibration_cells"] == {"green": [1.7, 0.1, 0.2], "red": [0.9, 0.3, 0.4]}
    if qt["calibration_cells"] == emtk["calibration_cells"]:  # the day the Qt combo works
        assert qt["calibration_items"] == emtk["calibration_items"][: len(qt["calibration_items"])]
    else:
        # Qt defect: its combo calls setup_id_for_name(name, user) without the prefix argument,
        # swallows the TypeError and so never lists a snapshot nor applies one.
        assert qt["calibration_items"] == ["Latest"]
        assert qt["calibration_cells"] == {"green": [1.0, 0.0, 0.0], "red": [1.25, 0.01, 0.02]}


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
                {"channel_name": "green", "g_factor": 1.7, "l1": 0.1, "l2": 0.2},
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
    assert page.model.data["detectors"]["green"]["g_factor"] == 1.0
    bar.select_calibration("2026-09-01")
    assert page.model.data["detectors"]["green"]["g_factor"] == 1.7
    assert page.model.data["detectors"]["red"]["g_factor"] == 1.25  # not in the snapshot: untouched
    assert "Applied the calibration of 2026-09-01 to 2 detector(s)." == page.status


# ---------------------------------------------------------------------------
# 2. detectors and windows through the shared editor
# ---------------------------------------------------------------------------
def test_native_holds_frozen_original_detectors_windows_and_timing(legacy, data_app):
    """The same source setup has the immutable original scientific values."""
    assert norm(data_app.get_settings()) == legacy["initial"]


# ---------------------------------------------------------------------------
# 3. reading a TTTR measurement
# ---------------------------------------------------------------------------
def test_reading_the_physical_bh_sample_matches_frozen_original(legacy, data_app, measurement):
    """The real measurement's header and every routing histogram equal the original Qt output."""
    import hashlib

    expected = legacy["reading"]
    assert hashlib.sha256(measurement.read_bytes()).hexdigest() == expected["source_sha256"]
    driver.populate(data_app, measurement)
    reading = data_app.model.data["tttr_reading"]
    assert reading["macro_time_resolution"] == pytest.approx(expected["macro"], rel=1e-12)
    assert reading["micro_time_resolution"] == pytest.approx(expected["micro"], rel=1e-12)
    assert sorted(data_app.model.preview) == sorted(map(int, expected["counts"])) == [0, 1, 8, 9]
    for channel, counts in expected["counts"].items():
        np.testing.assert_array_equal(data_app.model.preview[int(channel)], counts)
    assert sum(float(c.sum()) for c in data_app.model.preview.values()) > 1000
    settings = data_app.get_settings()["tttr_reading"]
    assert settings["effective_micro_time_resolution"] == pytest.approx(
        expected["effective"], rel=1e-5
    )
    assert settings["excitation_period"] == pytest.approx(13.5)
    assert data_app.page.status == "Header timing and per-routing-channel decay histograms loaded."


def test_binning_scales_effective_tick_like_frozen_original(legacy, data_app):
    """The original four-fold binning value is retained without any Qt combo adapter."""
    data_app.model.data["tttr_reading"]["micro_time_binning"] = 4
    assert data_app.get_settings()["tttr_reading"][
        "effective_micro_time_resolution"
    ] == pytest.approx(legacy["binning4_effective"], rel=1e-6)


def test_reading_something_that_is_not_a_measurement_reports_and_keeps_the_timing(
    data_app, tmp_path
):
    bad = tmp_path / "not_a_measurement.ptu"
    bad.write_text("this is not photon data")
    data_app.model.data["tttr_reading"]["file_type"] = (
        "auto"  # detect the container, as the Qt tool does
    )
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
    """Qt detects the container from the file and refuses what it cannot read; so does the editor, keeping the timing."""
    bad = tmp_path / "not_a_measurement.ptu"
    bad.write_text("this is not photon data")
    with pytest.raises(Exception):
        import tttrlib

        tttrlib.TTTR(str(bad))  # what the Qt page calls
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


def test_assigned_lut_and_gate_equal_frozen_original(legacy, data_app, measurement, tmp_path):
    """The actual LUT file, routing rows and enable rule preserve the original values."""
    from chisurf.core.fio.lut_context import get_active_setup_lut

    expected = legacy["assigned_lut"]
    lut = _lut_file(tmp_path)
    channel = expected["channel"]
    data_app.model.assign_lut(channel, str(lut))
    assert data_app.model.data["apply_lut"] is expected["apply"] is True
    np.testing.assert_array_equal(
        data_app.model.data["channel_luts"][str(channel)], expected["values"]
    )
    assert expected["rows"] == sorted(
        {c for d in data_app.model.data["detectors"].values() for c in d["chs"]}
    )
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
# 7. drawing, persistence, Qt-free
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
