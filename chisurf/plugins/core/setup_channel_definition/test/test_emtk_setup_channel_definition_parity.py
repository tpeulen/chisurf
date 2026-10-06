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
    qtpy = pytest.importorskip("qtpy")
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class QtRef:
    """The legacy Qt tool on a temporary setups file, with its modal dialogs answered."""

    def __init__(self, page, widget, file, answers):
        self.page, self.widget, self.file, self.answers = page, widget, file, answers

    def stored(self):
        data = json.loads(self.file.read_text()) if self.file.exists() else {}
        return {n: norm(s) for n, s in (data.get("setups") or {}).items()}

    def raw(self):
        return json.loads(self.file.read_text()) if self.file.exists() else {}


@pytest.fixture
def qt(qapp, tmp_path, monkeypatch):
    from chisurf.gui import dialogs
    from chisurf.gui.widgets.wizard.tttr_channeldefinition import tttr_channel_definition as mod
    from chisurf.plugins.core.setup_channel_definition.gui.tool import SetupChannelDefinitionWidget

    file = tmp_path / "qt_setups.json"
    file.write_text('{"setups": {}}')
    monkeypatch.setattr(mod, "DETECTOR_SETUPS_FILE", file)
    answers = {"name": "", "yes": True}
    for kind in ("information", "warning", "error"):
        monkeypatch.setattr(dialogs, kind, lambda *a, **k: None)
    monkeypatch.setattr(
        dialogs,
        "question",
        lambda *a, **k: mod.QMessageBox.Yes if answers["yes"] else mod.QMessageBox.No,
    )
    monkeypatch.setattr(
        mod.QInputDialog,
        "getText",
        staticmethod(lambda *a, **k: (answers["name"], bool(answers["name"]))),
    )
    widget = SetupChannelDefinitionWidget()
    widget.page._load_data(DATA)
    ref = QtRef(widget.page, widget, file, answers)
    yield ref
    widget.close()


def stored_emtk(path):
    data = json.loads(Path(path).read_text()) if Path(path).exists() else {}
    return {n: norm(s) for n, s in (data.get("setups") or {}).items()}


# ---------------------------------------------------------------------------
# 1. setup CRUD equals the Qt tool (setups file and MMFDB)
# ---------------------------------------------------------------------------
def test_save_rename_delete_in_a_setups_file_equal_the_qt_tool(qt, data_app, setups_file):
    bar = data_app.toolbar
    # Save: the same name, the same stored setup.
    qt.answers["name"] = "Lab A"
    qt.page._on_save_setup()
    bar.request_save()
    assert bar.dialog == "save" and bar.name_text == ""
    bar.name_text = "Lab A"
    bar.confirm()
    assert stored_emtk(setups_file) == qt.stored() != {}
    assert bar.selected == "Lab A" and qt.page.setup_combo.currentText() == "Lab A"
    # Rename.
    qt.answers["name"] = "Lab B"
    qt.page._on_rename_setup()
    bar.request_rename()
    assert bar.name_text == "Lab A"
    bar.name_text = "Lab B"
    bar.confirm()
    assert stored_emtk(setups_file) == qt.stored()
    assert list(qt.stored()) == ["Lab B"] and bar.selected == "Lab B"
    # Delete (confirmed).
    qt.page._on_delete_setup()
    bar.request_delete()
    assert bar.dialog == "delete"
    bar.confirm()
    assert stored_emtk(setups_file) == qt.stored() == {}
    assert bar.selected == "" and qt.page.setup_combo.currentText() == ""


def test_save_stores_every_edit_the_tables_hold(qt, data_app, setups_file):
    """Detector and window edits are in the stored setup exactly as the Qt tables are."""
    model = data_app.model
    model.data["detectors"]["red"]["g_factor"] = 2.5
    model.data["detectors"]["green"]["micro_time_ranges"] = [[0, 100], [200, 300]]
    model.data["windows"]["delayed"] = [2000, 4000]
    row = {
        qt.page.detectors_form.item(r, 0).text(): r
        for r in range(qt.page.detectors_form.rowCount())
    }
    qt.page._allow_g_update = True  # the Qt cell refuses programmatic G edits otherwise
    qt.page.detectors_form.cellWidget(row["red"], 3).setText("2.5")
    qt.page._allow_g_update = False
    qt.page.detectors_form.cellWidget(row["green"], 2).setText("0:100, 200:300")
    wrow = {
        qt.page.windows_form.item(r, 0).text(): r for r in range(qt.page.windows_form.rowCount())
    }
    qt.page.windows_form.cellWidget(wrow["delayed"], 1).setText("2000")
    qt.page.windows_form.cellWidget(wrow["delayed"], 2).setText("4000")
    qt.answers["name"] = "Edited"
    qt.page._on_save_setup()
    data_app.toolbar.save("Edited")
    a, b = stored_emtk(setups_file)["Edited"], qt.stored()["Edited"]
    for key in a:
        assert a[key] == b[key], (key, a[key], b[key])
    assert stored_emtk(setups_file) == qt.stored()
    assert qt.stored()["Edited"]["detectors"]["red"]["g_factor"] == 2.5


def test_public_flag_is_stored_with_save_and_survives_a_rename(qt, data_app, setups_file):
    bar = data_app.toolbar
    assert not bar.can_public()  # nothing saved yet: disabled, as the Qt checkbox
    assert not qt.page.public_checkbox.isEnabled()
    bar.save("Mine")
    assert bar.can_public()
    qt.answers["name"] = "Mine"
    qt.page._on_save_setup()
    assert qt.page.public_checkbox.isEnabled()
    qt.page.public_checkbox.setChecked(True)
    qt.page._on_save_setup()
    bar.select_public(True)
    bar.save("Mine")
    assert json.loads(setups_file.read_text())["setups"]["Mine"]["_is_public"] is True
    assert qt.raw()["setups"]["Mine"]["_is_public"] is True
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


def test_rename_onto_an_existing_name_asks_and_equals_the_qt_overwrite(qt, data_app, setups_file):
    bar = data_app.toolbar
    for name in ("One", "Two"):
        qt.answers["name"] = name
        qt.page._on_save_setup()
        bar.save(name)
    qt.page.setup_combo.setCurrentText("One")
    bar.select("One")
    # declined: nothing changes, in both
    qt.answers.update(name="Two", yes=False)
    before = qt.stored()
    qt.page._on_rename_setup()
    bar.request_rename()
    bar.name_text = "Two"
    bar.confirm()
    assert bar.dialog == "overwrite"
    bar.cancel()
    assert qt.stored() == before and stored_emtk(setups_file) == before
    assert bar.selected == "One"
    # accepted: One replaces Two
    qt.answers["yes"] = True
    qt.page._on_rename_setup()
    bar.request_rename()
    bar.name_text = "Two"
    bar.confirm()
    assert bar.dialog == "overwrite"
    bar.confirm()
    assert list(qt.stored()) == ["Two"] == list(stored_emtk(setups_file))
    assert stored_emtk(setups_file) == qt.stored()
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
def test_qt_and_emtk_hold_the_same_detectors_and_windows_for_the_same_setup(qt, data_app):
    assert norm(qt.page.get_settings()) == norm(data_app.get_settings())


# ---------------------------------------------------------------------------
# 3. reading a TTTR measurement
# ---------------------------------------------------------------------------
def test_reading_the_bh_sample_gives_the_timing_and_decays_the_qt_tool_shows(
    qt, data_app, measurement, monkeypatch
):
    from chisurf.gui.widgets.wizard.tttr_channeldefinition import (
        tttr_channel_definition_tttr_io as tio,
    )

    monkeypatch.setattr(
        tio.QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(measurement), ""))
    )
    qt.page._read_from_tttr_file()
    driver.populate(data_app, measurement)
    reading = data_app.model.data["tttr_reading"]
    assert reading["macro_time_resolution"] == pytest.approx(
        float(qt.page.macro_time_le.text()), rel=1e-12
    )
    assert reading["micro_time_resolution"] == pytest.approx(
        float(qt.page.micro_time_le.text()), rel=1e-12
    )
    assert reading["macro_time_resolution"] == pytest.approx(13.5)
    assert reading["micro_time_resolution"] == pytest.approx(3.2958984375)
    assert (
        sorted(data_app.model.preview)
        == sorted(qt.page._microtime_per_channel_counts)
        == [0, 1, 8, 9]
    )
    for channel, counts in qt.page._microtime_per_channel_counts.items():
        np.testing.assert_array_equal(data_app.model.preview[channel], counts)
    assert sum(float(c.sum()) for c in data_app.model.preview.values()) > 1000
    # the effective tick and the excitation period, as in the Qt "Eff. microtime" field
    settings = data_app.get_settings()["tttr_reading"]
    assert settings["effective_micro_time_resolution"] == pytest.approx(
        float(qt.page.effective_micro_time_le.text()), rel=1e-5
    )
    assert settings["excitation_period"] == pytest.approx(13.5)
    assert data_app.page.status == "Header timing and per-routing-channel decay histograms loaded."


def test_binning_scales_the_effective_tick_like_the_qt_combo(qt, data_app):
    data_app.model.data["tttr_reading"]["micro_time_binning"] = 4
    qt.page.micro_binning_combo.setCurrentText("4")
    assert data_app.get_settings()["tttr_reading"][
        "effective_micro_time_resolution"
    ] == pytest.approx(float(qt.page.effective_micro_time_le.text()), rel=1e-6)


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
    qt, data_app, tmp_path, file_type
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


def test_assigning_a_lut_stores_it_and_switches_the_gate_on_like_qt(
    qt, data_app, measurement, tmp_path, monkeypatch
):
    from chisurf.core.fio.lut_context import get_active_setup_lut
    from chisurf.gui.widgets.wizard.tttr_channeldefinition import tttr_channel_definition as mod

    lut = _lut_file(tmp_path)
    monkeypatch.setattr(
        mod.QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(lut), ""))
    )
    qt.page._lut_table.setCurrentCell(0, 0)
    channel = int(qt.page._lut_table.item(0, 0).text())
    qt.page._on_assign_lut_file()
    assert qt.page._apply_lut is True

    data_app.model.assign_lut(channel, str(lut))
    assert data_app.model.data["apply_lut"] is True  # the toolbar model applies the Qt rule
    np.testing.assert_array_equal(
        data_app.model.data["channel_luts"][str(channel)], qt.page._channel_luts[channel]
    )
    assert (
        norm(data_app.get_settings())["apply_lut"]
        is norm(qt.page.get_settings())["apply_lut"]
        is True
    )
    # the LUT rows the Qt table lists are the routing channels of the detectors
    assert [
        int(qt.page._lut_table.item(r, 0).text()) for r in range(qt.page._lut_table.rowCount())
    ] == sorted({c for d in DATA["detectors"].values() for c in d["chs"]})
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
    assert driver.click_text(tool, "Save")
    assert not tool.tour.awaiting
    assert tool.toolbar.dialog == "save"
    tool.close()


# ---------------------------------------------------------------------------
# 7. drawing, persistence, Qt-free
# ---------------------------------------------------------------------------
def test_the_manifest_opens_the_emtk_tool_and_keeps_the_qt_one():
    manifest = json.loads((PLUGIN / "manifest.json").read_text())
    assert (
        manifest["entrypoints"]["emtk"]
        == "chisurf.plugins.core.setup_channel_definition.gui.app:make_app"
    )
    assert manifest["entrypoints"]["gui"].endswith("gui.tool:SetupChannelDefinitionWidget")


def test_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    result = qt_free(ID)
    assert result["ok"], result["output"]
    source = " ".join((PLUGIN / "gui" / name).read_text() for name in ("app.py", "model.py"))
    for forbidden in ("qtpy", "PyQt", "PySide", "chisurf.gui"):
        assert forbidden not in source
