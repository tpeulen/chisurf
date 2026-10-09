"""Native MMFDB picker -> measured bursts -> saved mask with authenticated lineage."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def native(tmp_path, monkeypatch):
    from mmfdb.provenance.result_registry import register_result
    from mmfdb.repository import MFDatabase
    from mmfdb.security.session import SessionContext

    from chisurf.core.mmfdb_services import prepare_embedded_mmfdb, register_services
    from chisurf.core.plugin.client import InProcessClient
    from chisurf.emtk import dataset_picker
    from chisurf.plugins.core.mmfdb_admin.gui.client import MMFDBClient
    from chisurf.plugins.ndxplorer.gui.app import make_app
    from chisurf.server.dispatcher import ServiceDispatcher
    from chisurf.server.session import SessionState

    monkeypatch.setenv("MMFDB_DATABASE_URL", f"sqlite:///{tmp_path / 'mmfdb.db'}")
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "chisurf"))
    monkeypatch.setenv("NDXPLORER_SETTINGS_DIR", str(tmp_path / "ndx"))
    prepare_embedded_mmfdb({})
    dispatcher = ServiceDispatcher(SessionState())
    register_services(dispatcher)
    client = MMFDBClient(client=InProcessClient(dispatcher), inprocess=True)
    assert client.login("user", "user", quiet=True).get("ok")
    monkeypatch.setattr(dataset_picker, "session_client", lambda: client)
    # Only suppress background browsing; refresh/resolve/accept use the real service.
    monkeypatch.setattr(
        dataset_picker.DatasetPicker, "open", lambda self: setattr(self, "is_open", True)
    )
    mfd = Path(__file__).resolve().parents[4] / "modules/ndxplorer/test/mfd/burstwise_All 0.1500#30"
    copied = tmp_path / mfd.name
    shutil.copytree(mfd, copied)
    with MFDatabase(str(tmp_path / "mmfdb.db")) as db:
        source_id = register_result(
            kind="external_reference",
            data=None,
            data_format="directory",
            metadata={"path": str(copied), "label": "Measured MFD bursts"},
            db=db,
            session=SessionContext(user_id="user", db=db),
        )
    assert source_id
    app = make_app(session_autosave=False)
    try:
        assert app.run_action("open_from_mmfdb")
        feature = next(f for f in app.features if f.name == "chisurf_mmfdb")
        assert feature.picker.refresh(), feature.picker.error
        assert feature.picker.select(source_id) is not None
        assert feature.picker.accept(), feature.picker.error
        assert app.model.has_data
        yield app, client, source_id
    finally:
        app.close()


def save_ids(app, folder):
    from emtk.testing import RecordingPainter

    folder.mkdir()
    assert app.run_action("save_burst_ids")
    app.io_service.answer(str(folder))
    io = next(f for f in app.features if f.name == "io")
    if io.task is not None:
        io.task.wait(120.0)
        io.task = None
    for _ in range(2):
        app.draw(RecordingPainter(), 0, 0, 1200, 800)
    assert list(folder.glob("*.bst"))


def test_native_picker_preserves_the_artifact_in_saved_selection_lineage(native, tmp_path):
    from mmfdb.repository import MFDatabase

    app, client, source_id = native
    before = client.call("mmfdb.v1.artifacts.get", {"artifact_id": source_id})["artifact"]
    app.model.set_parameter("x", "Tau (green)")
    app.model.set_parameter("y", "FRET efficiency")
    app.model.add_rectangle((0.5, 2.5), (0.2, 0.8))
    expected = app.model.source.selection_mask(app.model.gates.selections()).tolist()
    assert 0 < sum(expected) < len(expected)

    output = tmp_path / "bids"
    save_ids(app, output)

    assert app.status.startswith("Recorded the selection"), app.status
    with MFDatabase(str(tmp_path / "mmfdb.db")) as db:
        links = db.conn.execute(
            "SELECT operation_id FROM mmfdb_operation_artifact "
            "WHERE artifact_id=? AND direction='input'",
            (source_id,),
        ).fetchall()
        assert len(links) == 1
        op_id = links[0]["operation_id"]
        out_id = db.conn.execute(
            "SELECT artifact_id FROM mmfdb_operation_artifact "
            "WHERE operation_id=? AND direction='output'",
            (op_id,),
        ).fetchone()["artifact_id"]
    operation = client.call("mmfdb.v1.operations.get", {"operation_id": op_id})["operation"]
    settings = json.loads(operation["settings_json"])
    assert operation["status"] == "succeeded"
    assert operation["software_package"] == "ndxplorer"
    assert settings["source_artifact_id"] == source_id
    assert settings["folder"] == str(output)
    assert settings["n_selected"] == sum(expected)
    mask = client.call("mmfdb.v1.artifacts.get", {"artifact_id": out_id})["artifact"]
    assert mask["artifact_kind"] == "selection_mask"
    np.testing.assert_array_equal(json.loads(mask["data_json"])["mask"], expected)
    assert client.call("mmfdb.v1.artifacts.get", {"artifact_id": source_id})["artifact"] == before


def test_replacing_the_table_detaches_its_mmfdb_identity(native, tmp_path):
    app, _client, _source_id = native
    assert callable(app.burst_ids_recorder)
    other = tmp_path / "other.csv"
    other.write_text("x,y\n1,2\n3,4\n")

    assert app.open_path(str(other))

    assert app.burst_ids_recorder is None


def test_an_expired_session_keeps_bids_and_reports_the_recording_failure(native, tmp_path):
    from mmfdb.repository import MFDatabase

    app, client, _source_id = native
    client.token = None

    save_ids(app, tmp_path / "bids")

    assert "recording them failed" in app.status
    with MFDatabase(str(tmp_path / "mmfdb.db")) as db:
        assert (
            db.conn.execute(
                "SELECT COUNT(*) FROM mmfdb_operation WHERE software_package='ndxplorer'",
            ).fetchone()[0]
            == 0
        )


def test_a_failed_input_link_leaves_a_failed_operation_not_a_success(native, tmp_path, monkeypatch):
    from mmfdb.repository import MFDatabase

    app, client, _source_id = native
    real_call = client.call

    def call(method, params=None, **kwargs):
        if method == "mmfdb.v1.operations.link_artifact":
            raise RuntimeError("link service unavailable")
        return real_call(method, params, **kwargs)

    monkeypatch.setattr(client, "call", call)

    save_ids(app, tmp_path / "bids")

    assert "recording them failed: link service unavailable" in app.status
    with MFDatabase(str(tmp_path / "mmfdb.db")) as db:
        (op,) = db.conn.execute(
            "SELECT status, error_message FROM mmfdb_operation WHERE software_package='ndxplorer'",
        ).fetchall()
        assert op["status"] == "failed"
        assert op["error_message"] == "link service unavailable"
