"""MMFDB provenance contracts shared by the per-pixel imaging plugins."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from mmfdb.repository import MFDatabase
from mmfdb.security.auth import AuthenticatedPrincipal, create_default_acl_for_object
from chisurf.plugins.microscopy.imaging_common.base import ImagingMapViewModel


class _TestMapViewModel(ImagingMapViewModel):
    """Small concrete map tool that writes a deterministic file."""

    WINDOW_KIND = "test_map"

    def __init__(self, output: Path) -> None:
        super().__init__(output.with_suffix(".view.json"))

    def _window_params(self) -> dict:
        return {"threshold": 4, "frequency_mhz": 80.0}

    def _write_hdf5(self, path: str) -> list[str]:
        Path(path).write_bytes(b"HDF5")
        return list(self._columns)


def _source_artifact(db: MFDatabase, source: Path) -> str:
    db.ensure_user("imager")
    db.register_artifact(
        artifact_id="image-source",
        artifact_kind="raw_measurement",
        data_format=source.suffix.lstrip("."),
        storage_mode="local_file",
        file_path=str(source),
        metadata={"path": str(source)},
        created_by_user_id="imager",
    )
    create_default_acl_for_object(
        db.conn,
        "artifact",
        "image-source",
        owner_user_id="imager",
        mode=0o700,
    )
    db.conn.commit()
    return "image-source"


def test_imaging_map_persistence_registers_snapshot_and_complete_parameters(tmp_path):
    source = tmp_path / "source.ptu"
    source.write_bytes(b"PTU")
    output = tmp_path / "result.imaging.h5"

    with MFDatabase(tmp_path / "imaging.db") as db:
        artifact_id = _source_artifact(db, source)
        vm = _TestMapViewModel(output)
        vm.filename = str(source)
        vm.pipeline_hdf5 = str(output)
        vm.detectors = {
            "green": {"chs": [0, 1], "micro_time_ranges": [[2, 30]], "bg": 1.5}
        }
        vm._columns = {"mean lifetime": np.ones((2, 3))}
        vm.bind_mmfdb(
            db,
            source_artifact_id=artifact_id,
            sample_id="",
            principal=AuthenticatedPrincipal("imager"),
        )

        vm.flush_to_hdf5()

        assert vm.mmfdb_artifact_id
        artifact = db.get_artifact(vm.mmfdb_artifact_id)
        assert artifact["created_by_user_id"] == "imager"
        acl_owner = db.conn.execute(
            """SELECT owner_user_id FROM mmfdb_object_acl
               WHERE object_type = 'artifact' AND object_id = ?""",
            (vm.mmfdb_artifact_id,),
        ).fetchone()[0]
        assert acl_owner == "imager"
        metadata = artifact.get("metadata") or json.loads(artifact["metadata_json"])
        assert metadata["source_artifact_id"] == artifact_id
        assert metadata["analysis_kind"] == "test_map"
        assert metadata["parameters"] == {"threshold": 4, "frequency_mhz": 80.0}
        assert metadata["detectors"] == vm.detectors
        assert metadata["result_columns"] == ["mean lifetime"]
        assert metadata["shape"] == [2, 3]

        operation_type = db.conn.execute(
            """SELECT o.operation_type
               FROM mmfdb_operation AS o
               JOIN mmfdb_operation_artifact AS oa USING (operation_id)
               WHERE oa.artifact_id = ? AND oa.direction = 'output'""",
            (vm.mmfdb_artifact_id,),
        ).fetchone()[0]
        assert operation_type == "image_analysis"


def test_imaging_map_rejects_unreadable_source_at_binding_boundary(tmp_path):
    source = tmp_path / "source.ptu"
    source.write_bytes(b"PTU")

    with MFDatabase(tmp_path / "imaging.db") as db:
        artifact_id = _source_artifact(db, source)
        vm = _TestMapViewModel(tmp_path / "result.h5")

        from mmfdb.security.auth import AuthenticatedPrincipal, PermissionDenied

        db.ensure_user("not-owner")

        try:
            vm.bind_mmfdb(
                db,
                source_artifact_id=artifact_id,
                principal=AuthenticatedPrincipal("not-owner"),
            )
        except PermissionDenied:
            pass
        else:
            raise AssertionError("private imaging source was accepted for anonymous principal")


def test_imaging_map_requires_authenticated_principal_even_for_local_binding(tmp_path):
    source = tmp_path / "source.ptu"
    source.write_bytes(b"PTU")

    with MFDatabase(tmp_path / "imaging.db") as db:
        artifact_id = _source_artifact(db, source)
        vm = _TestMapViewModel(tmp_path / "result.h5")

        try:
            vm.bind_mmfdb(db, source_artifact_id=artifact_id)
        except TypeError as exc:
            assert "principal" in str(exc)
            pass
        else:
            raise AssertionError("imaging MMFDB binding accepted no principal")


def test_gui_runtime_session_is_revalidated_against_bound_database(tmp_path, monkeypatch):
    import chisurf.core.settings as cs_settings
    from chisurf.core.transform.mmfdb import runtime_session_for_database
    from mmfdb.security.auth import create_session
    from mmfdb.security.credentials import (
        delete_runtime_session_token,
        store_runtime_session_token,
    )

    host, port, user_id = "runtime-test", 18765, "imager"
    monkeypatch.setitem(
        cs_settings.cs_settings,
        "mmfdb",
        {"last_server": host, "last_port": port, "default_user_id": user_id},
    )
    with MFDatabase(tmp_path / "runtime.db") as db:
        db.ensure_user(user_id)
        issued = create_session(db.conn, user_id)
        db.conn.commit()
        store_runtime_session_token(host, port, user_id, issued["token"])
        try:
            session = runtime_session_for_database(db)
            assert session is not None
            assert session.user_id == user_id
            assert session.db is db
            assert session.auth == {"token": issued["token"]}
        finally:
            delete_runtime_session_token(host, port, user_id)
