"""The real detector result publisher preserves setup/context through native close."""
from __future__ import annotations

import copy
import json

import pytest
from qtpy.QtCore import Qt

from chisurf.gui import dialogs
from chisurf.gui.widgets.wizard.tttr_channeldefinition import DetectorWizard
from chisurf.gui.widgets.wizard.tttr_channeldefinition import tttr_channel_definition_tttr_io as io
from chisurf.plugins.vv_vh_g_factor.gui.app import create_host
from chisurf.plugins.vv_vh_g_factor.gui.model import GFactorModel


@pytest.fixture
def setup_page(qtbot, tmp_path, monkeypatch):
    """Use the existing detector page and isolate the setup persistence boundary."""
    (tmp_path / "setups.json").write_text(json.dumps({"setups": {}, "last_used": ""}))
    wizard = DetectorWizard(json_file=str(tmp_path / "setups.json"))
    qtbot.addWidget(wizard)
    page = wizard.page(0)
    page._load_data({"windows": {"prompt": [0, 2048]},
                     "detectors": {"detector": {"chs": [0, 1], "micro_time_ranges": [[0, 4095]],
                                                "g_factor": 1.0, "l1": 0.17, "l2": 0.23}},
                     "tttr_reading": {"file_type": "SPC-130", "macro_time_resolution": 50.0,
                                      "micro_time_resolution": 50.0, "micro_time_binning": 1}})
    page.current_setup_name = "test_setup"
    page.current_setups_file = str(tmp_path / "setups.json")
    assert page.effective_micro_time_resolution == 50.0
    stored = {"setups": {"test_setup": {"retained": "metadata", "detectors": {"other": {"chs": [7]}}}}}
    saves = []
    monkeypatch.setattr(io, "load_detector_setups", lambda path: copy.deepcopy(stored))
    monkeypatch.setattr(io, "save_detector_setups", lambda data, path: saves.append((copy.deepcopy(data), path)))
    monkeypatch.setattr(dialogs, "information", lambda *args, **kwargs: None)
    yield page, stored, saves


def measured(tmp_path):
    """An authoritative native result snapshot; calculation arithmetic is unchanged."""
    model = GFactorModel()
    model.fast_file = str(tmp_path / "changed-reference.dat")
    model.result = {"g_factor": 1.25, "g_factor_uncorrected": 1.2, "g_factor_corrected": 1.25,
                    "g_factor_stddev_uncorrected": 0.1, "g_factor_stddev_corrected": 0.12,
                    "bg_parallel_avg": 3.0, "bg_perpendicular_avg": 4.0}
    model.background = True
    model.region = [400.0, 300.0]
    model.background_region = [10.0, 20.0]
    return model


@pytest.mark.parametrize("manual_zero", [False, True])
def test_actual_native_close_persists_g_tail_uuids_actor_sd_and_mixing(
    setup_page, tmp_path, monkeypatch, qtbot, manual_zero
):
    page, _, saves = setup_page
    seen = []
    monkeypatch.setattr("chisurf.core.fio.setup_store.resolve_active_user_id", lambda: "scratch_actor")

    class Archive:
        def archive_g_factor(self, **kwargs):
            seen.append(kwargs)
            return {"ok": True, "reference_decay_id": "owned-source-uuid", "calibration_id": "owned-calibration-uuid"}

    snapshot = measured(tmp_path)
    snapshot.fp_result = {"l1": None, "l2": None}
    if manual_zero:
        snapshot.manual_l = True
        snapshot.l_override = 0.0
    host = create_host(on_close=lambda result: io._publish_gfactor_result(
        page, result, {"row": 0, "name": "detector"}, client=Archive()))
    qtbot.addWidget(host)
    host.control.model = snapshot
    host.close()
    host.close()
    assert len(seen) == len(saves) == 1
    assert seen[0]["file_path"] == snapshot.fast_file and seen[0]["active_user"] == "scratch_actor"
    parameters = seen[0]["parameters"]
    assert parameters["g_factor_stddev"] == 0.12 and parameters["micro_time_resolution"] == 50.0
    assert [parameters["l1"], parameters["l2"]] == ([0.0, 0.0] if manual_zero else [0.17, 0.23])
    assert page.detectors_form.cellWidget(0, 3).text() == "1.250"
    assert page.detectors_form.cellWidget(0, 6).text() == "300-400"
    item = page.detectors_form.item(0, 0)
    assert item.data(Qt.UserRole + 1) == "owned-source-uuid"
    assert item.data(Qt.UserRole + 2) == "owned-calibration-uuid"
    assert saves[0][0]["setups"]["test_setup"]["retained"] == "metadata"
    assert "other" in saves[0][0]["setups"]["test_setup"]["detectors"]
    assert saves[0][0]["last_used"] == "test_setup"


def test_archive_failure_and_readonly_leave_detector_and_setup_unchanged(setup_page, tmp_path):
    page, _, saves = setup_page
    original = page.detectors_form.cellWidget(0, 3).text()

    class Failed:
        def archive_g_factor(self, **kwargs):
            return {"ok": False, "error": "controlled failure"}

    with pytest.raises(ValueError, match="controlled failure"):
        io._publish_gfactor_result(page, measured(tmp_path), {"row": 0, "name": "detector"}, Failed())
    assert not saves and page.detectors_form.cellWidget(0, 3).text() == original
    page.read_only = True
    assert not io._publish_gfactor_result(page, measured(tmp_path), {"row": 0, "name": "detector"}, Failed())
    assert not saves and page.detectors_form.cellWidget(0, 3).text() == original


@pytest.mark.parametrize("headless", [False, True])
@pytest.mark.parametrize("archive_ok", [False, True])
def test_real_detector_action_uses_native_model_and_effective_ps_to_ns(
    setup_page, monkeypatch, qtbot, headless, archive_ok, tmp_path
):
    """Exercise the actual launch/close seam with a deterministic polarized histogram."""
    import numpy as np
    from qtpy.QtWidgets import QFileDialog, QMessageBox

    from chisurf.plugins.vv_vh_g_factor.gui.client import VvVhGFactorClient

    page, _, saves = setup_page
    page.micro_binning_combo.setCurrentText("2")
    page.detectors_form.cellWidget(0, 6).setText("20-40")
    seen = []
    original = page.detectors_form.cellWidget(0, 3).text()
    real_mkstemp = io.tempfile.mkstemp
    monkeypatch.setattr(io.tempfile, "mkstemp", lambda **kw: real_mkstemp(dir=tmp_path, **kw))
    monkeypatch.setattr("chisurf.core.fio.setup_store.resolve_active_user_id", lambda: "scratch_actor")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **kw: ("owned.spc", ""))
    monkeypatch.setattr(dialogs, "question", lambda *a, **kw: QMessageBox.Yes if headless else QMessageBox.No)

    class Histograms:
        def __len__(self):
            return 200

        def get_microtime_histogram(self, binning, channels):
            assert binning == 2
            decay = np.exp(-np.arange(100) / 20) * 1000
            return decay if channels == [0] else decay / 1.25, np.arange(100)

    monkeypatch.setattr(io, "load_with_progress", lambda *a, **kw: Histograms())
    def archive(self, **kwargs):
        seen.append(kwargs)
        return {"ok": archive_ok, "error": "controlled archive failure", "reference_decay_id": "source", "calibration_id": "calibration"}
    monkeypatch.setattr(VvVhGFactorClient, "archive_g_factor", archive)
    errors = []
    monkeypatch.setattr(dialogs, "error", lambda *a, **kw: errors.append(a))
    try:
        io.on_calc_g_factor(page, row=0)
        if not headless:
            host = page.g_factor_calculator
            qtbot.addWidget(host)
            assert host.control.model.fp_dt_ns == 0.1
            assert host.control.model.region == [20.0, 40.0]
            host.close()
            host.close()
        assert len(seen) == 1
        assert len(saves) == int(archive_ok)
        assert bool(errors) is not archive_ok
        if not archive_ok:
            assert page.detectors_form.cellWidget(0, 3).text() == original
        assert seen[0]["parameters"]["micro_time_resolution"] == 100.0
        assert seen[0]["parameters"]["g_factor"] == pytest.approx(1.25)
        assert seen[0]["parameters"]["l1"] == 0.17
        assert seen[0]["parameters"]["l2"] == 0.23
    finally:
        if hasattr(page, "vv_vh_file"):
            from pathlib import Path
            Path(page.vv_vh_file).unlink(missing_ok=True)


def test_native_publisher_records_real_archive_ids_and_measured_sd(setup_page, tmp_path, monkeypatch):
    """Use the actual archive service against a scratch store, including provenance IDs."""
    import sqlite3
    from uuid import UUID

    import numpy as np
    from mmfdb.provenance.result_registry import read_result
    from mmfdb.repository import MFDatabase
    from mmfdb.schema import schema

    from chisurf.core.fio import write_vv_vh
    from chisurf.plugins.vv_vh_g_factor.gui.client import VvVhGFactorClient

    page, _, saves = setup_page
    database = tmp_path / "archive.sqlite"
    objects = tmp_path / "objects"
    objects.mkdir()
    with sqlite3.connect(database) as connection:
        schema.migrate_schema(connection)
    monkeypatch.setattr("mmfdb.store.database_resolver.resolve_database_path", lambda: database)
    monkeypatch.setattr("mmfdb.store.database_resolver.object_store_root", lambda: objects)
    monkeypatch.setattr("chisurf.core.fio.setup_store.resolve_active_user_id", lambda: "scratch_actor")
    snapshot = measured(tmp_path)
    decay = np.exp(-np.arange(512) / 60) * 1000
    write_vv_vh(snapshot.fast_file, np.concatenate([decay, decay / 1.25]))
    assert io._publish_gfactor_result(page, snapshot, {"row": 0, "name": "detector"}, VvVhGFactorClient())
    item = page.detectors_form.item(0, 0)
    source_id, calibration_id = item.data(Qt.UserRole + 1), item.data(Qt.UserRole + 2)
    assert UUID(source_id) != UUID(calibration_id)
    assert len(saves) == 1
    with MFDatabase(str(database)) as db:
        source = db.get_artifact(source_id)
        metadata = json.loads(source["metadata_json"])
        assert metadata["micro_time_resolution"] == 50.0
        assert metadata["active_user"] == "scratch_actor"
        payload = read_result(db, calibration_id)
        assert payload.data["g_factor_stddev"][0] == 0.12
        assert payload.data["l1"][0] == 0.17 and payload.data["l2"][0] == 0.23
        edge = db.conn.execute("SELECT relationship_type FROM mmfdb_edge WHERE source_node_id = ? AND target_node_id = ?", (calibration_id, source_id)).fetchone()
        assert edge[0] == "derived_from"


@pytest.mark.parametrize("state", ["readonly", "disabled", "cancelled"])
def test_detector_launch_readonly_disabled_or_cancelled_does_not_mutate(setup_page, monkeypatch, state):
    """Unavailable/cancelled calibration never loads data or publishes a result."""
    from qtpy.QtWidgets import QFileDialog

    page, _, saves = setup_page
    original = page.detectors_form.cellWidget(0, 3).text()
    if state == "readonly":
        page.read_only = True
    elif state == "disabled":
        page.detectors_form.setEnabled(False)
    seen = []
    def choose_cancelled(*args, **kwargs) -> tuple[str, str]:
        """Record the actual chooser boundary and return a cancelled input."""
        seen.append(True)
        return "", ""

    monkeypatch.setattr(QFileDialog, "getOpenFileName", choose_cancelled)
    monkeypatch.setattr(io, "load_with_progress", lambda *a, **kw: pytest.fail("cancelled input was read"))
    io.on_calc_g_factor(page, row=0)
    assert bool(seen) is (state == "cancelled")
    assert not saves and page.detectors_form.cellWidget(0, 3).text() == original
    assert not hasattr(page, "g_factor_calculator")
