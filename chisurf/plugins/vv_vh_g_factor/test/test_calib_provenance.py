from __future__ import annotations

import json
import sqlite3

import numpy as np
import pytest
from mmfdb.repository import MFDatabase
from mmfdb.schema import schema

from chisurf.plugins.vv_vh_g_factor.gui.client import VvVhGFactorClient


def test_archive_g_factor_provenance(tmp_path, monkeypatch):
    """Verify archive_g_factor registers the reference decay and parented calibration."""
    db_path = tmp_path / "test_mmfdb.sqlite"
    object_root = tmp_path / "objects"
    object_root.mkdir()

    # Create and migrate empty test DB
    conn = sqlite3.connect(str(db_path))
    schema.migrate_schema(conn)
    conn.commit()
    conn.close()

    # Monkeypatch the database resolver
    monkeypatch.setattr(
        "mmfdb.store.database_resolver.resolve_database_path",
        lambda: db_path,
    )
    monkeypatch.setattr(
        "mmfdb.store.database_resolver.object_store_root",
        lambda: object_root,
    )

    # Create dummy VV/VH file (parallel and perpendicular decays)
    vv_vh_file = tmp_path / "dummy_vv_vh.txt"
    vv = np.exp(-np.linspace(0, 10, 1000) / 2.0)
    vh = vv / 1.5
    merged = np.concatenate([vv, vh])
    np.savetxt(vv_vh_file, merged)

    # Run service archival via client
    params = {
        "g_factor": 1.5,
        "region_min": 700.0,
        "region_max": 900.0,
        "decay_shift": 0.0,
        "flip": False,
        "use_bg": False,
        "l1": 0.0308,
        "l2": 0.0308,
        "micro_time_resolution": 0.032,
    }

    client = VvVhGFactorClient()
    res = client.archive_g_factor(
        file_path=str(vv_vh_file),
        parameters=params,
        active_user="test_user",
    )

    assert res.get("ok") is True
    calib_id = res.get("calibration_id")
    ref_decay_id = res.get("reference_decay_id")
    assert calib_id != ""
    assert ref_decay_id != ""

    # Verify DB records
    with MFDatabase(str(db_path)) as db:
        # Check raw measurement
        artifact = db.get_artifact(ref_decay_id)
        assert artifact is not None
        assert artifact["artifact_kind"] == "raw_measurement"
        meta = json.loads(artifact["metadata_json"])
        assert meta["filename"] == "dummy_vv_vh.txt"
        assert meta["micro_time_resolution"] == 0.032

        # Check calibration
        calib = db.get_artifact(calib_id)
        assert calib is not None
        assert calib["artifact_kind"] == "calibration_data"
        calib_meta = json.loads(calib["metadata_json"])
        assert calib_meta["calibration_type"] == "g_factor"

        # Check calibration payload
        from mmfdb.provenance.result_registry import read_result

        payload = read_result(db, calib_id)
        assert payload is not None
        assert np.allclose(payload.data["g_factor"], 1.5)
        assert np.allclose(payload.data["l1"], 0.0308)
        assert np.allclose(payload.data["l2"], 0.0308)
        # r_inf is automatically computed
        assert "r_inf" in payload.data
        r_inf_val = payload.data["r_inf"][0]
        assert (
            np.isnan(r_inf_val)
            or isinstance(r_inf_val, float)
            or isinstance(r_inf_val, np.floating)
        )

        # The whole point: the calibration must be parented to the reference
        # decay via a derived_from provenance edge.
        edge = db.conn.execute(
            "SELECT relationship_type FROM mmfdb_edge "
            "WHERE source_node_id = ? AND target_node_id = ? AND deleted_at IS NULL",
            (calib_id, ref_decay_id),
        ).fetchone()
        assert edge is not None, "calibration must be parented to the reference decay"
        assert edge[0] == "derived_from"

        # The derived decays (corrected VV/VH + anisotropy) are stored as a
        # processed_data artifact, also parented to the reference decay.
        derived_id = res.get("derived_decay_id")
        assert derived_id, "derived decays must be archived"
        derived = db.get_artifact(derived_id)
        assert derived is not None
        assert derived["artifact_kind"] == "processed_data"
        d_edge = db.conn.execute(
            "SELECT relationship_type FROM mmfdb_edge "
            "WHERE source_node_id = ? AND target_node_id = ? AND deleted_at IS NULL",
            (derived_id, ref_decay_id),
        ).fetchone()
        assert d_edge is not None and d_edge[0] == "derived_from"
        d_payload = read_result(db, derived_id)
        assert d_payload is not None
        assert "anisotropy" in d_payload.data
        assert "vv_corrected" in d_payload.data


def test_archive_g_factor_graceful_failure(tmp_path, monkeypatch):
    """Verify that archive_g_factor fails gracefully without raising when database is missing."""
    # Resolve to a db path in a non-existent subdirectory
    monkeypatch.setattr(
        "mmfdb.store.database_resolver.resolve_database_path",
        lambda: tmp_path / "nonexistent_dir" / "db.sqlite",
    )

    vv_vh_file = tmp_path / "dummy_vv_vh.txt"
    np.savetxt(vv_vh_file, np.ones(100))

    client = VvVhGFactorClient()
    res = client.archive_g_factor(
        file_path=str(vv_vh_file),
        parameters={"g_factor": 1.5, "region_min": 10, "region_max": 20},
        active_user="test_user",
    )

    assert res.get("ok") is False
    assert res.get("calibration_id") == ""
    assert "unavailable" in res.get("error", "").lower()


@pytest.mark.parametrize("mode", ["explicit", "authenticated", "fallback", "explicit-and-auth"])
def test_real_archival_session_owns_all_records_and_preserves_context(tmp_path, monkeypatch, mode):
    """Actual client/service/SQLite writes agree on actor, ACL and complete input context."""
    from mmfdb import config
    from mmfdb.security.auth import create_session

    # Preserve the prior process configuration while isolating all storage/account writes.
    monkeypatch.setattr(config, "_CONFIG", config.get_runtime_config())
    db_path = tmp_path / "actor.sqlite"
    config.configure_runtime(
        settings_dir=tmp_path / "settings",
        database_path=db_path,
        object_store_root=tmp_path / "objects",
        default_user_id="configured_actor",
    )
    auth = None
    with MFDatabase(db_path) as db:
        db.ensure_user("authenticated_actor")
        if "auth" in mode:
            auth = {"token": create_session(db.conn, "authenticated_actor")["token"]}
            db.conn.commit()
    vv = np.exp(-np.arange(100) / 20.0)
    source = tmp_path / "reference.txt"
    np.savetxt(source, np.concatenate([vv, vv / 1.5]))
    parameters = {
        "g_factor": 1.5,
        "region_min": 70.0,
        "region_max": 90.0,
        "source_measurement": "actual-independent-reference.spc",
        "micro_time_resolution": 25.0,
        "bg_region_min": 1.0,
        "bg_region_max": 8.0,
        "fp_file_path": "protein.txt",
        "fp_dt_ns": 0.025,
        "fp_rho_ns": 16.0,
        "fp_r0": 0.38,
        "fp_tau_ns": 4.0,
        "fp_r_s_expected": 0.076,
        "future_primitive_context": {"kind": "known", "values": [True, None, 3, 0.5]},
    }
    explicit = "explicit_actor" if mode.startswith("explicit") else None
    expected = explicit or ("authenticated_actor" if auth else "configured_actor")
    client = VvVhGFactorClient()
    if auth:
        response = client._client.call(
            "vv_vh_g_factor.archive_g_factor",
            {
                "file_path": str(source),
                "parameters": parameters,
                "active_user": explicit,
                "auth": auth,
            },
        )
        result = response.get("result", response)
    else:
        result = client.archive_g_factor(str(source), parameters, active_user=explicit)
    assert result["ok"], result
    ids = [result[key] for key in ("reference_decay_id", "derived_decay_id", "calibration_id")]
    assert all(ids)
    with MFDatabase(db_path) as db:
        rows = db.conn.execute(
            "SELECT a.artifact_kind, a.created_by_user_id, o.operator_user_id, "
            "aa.owner_user_id, oa.owner_user_id FROM mmfdb_artifact a "
            "JOIN mmfdb_operation_artifact link ON link.artifact_id=a.artifact_id "
            "AND link.direction='output' "
            "JOIN mmfdb_operation o ON o.operation_id=link.operation_id "
            "JOIN mmfdb_object_acl aa ON aa.object_type='artifact' AND aa.object_id=a.artifact_id "
            "JOIN mmfdb_object_acl oa ON oa.object_type='operation' AND oa.object_id=o.operation_id "
            "WHERE a.artifact_id IN (?,?,?)",
            ids,
        ).fetchall()
        assert {row[0] for row in rows} == {"raw_measurement", "processed_data", "calibration_data"}
        assert len(rows) == 3
        assert all(tuple(row)[1:] == (expected,) * 4 for row in rows)
        for artifact_id in ids:
            assert db.list_artifact_owners(artifact_id) == [expected]
        raw = db.get_artifact(ids[0])
        metadata = json.loads(raw["metadata_json"])
        assert metadata["active_user"] == expected
        assert metadata["source_measurement"] == parameters["source_measurement"]
        assert metadata["calibration_parameters"] == parameters
        raw_operation_metadata = db.conn.execute(
            "SELECT o.metadata_json FROM mmfdb_operation o "
            "JOIN mmfdb_operation_artifact link ON link.operation_id=o.operation_id "
            "WHERE link.artifact_id=? AND link.direction='output'",
            (ids[0],),
        ).fetchone()[0]
        assert json.loads(raw_operation_metadata)["calibration_parameters"] == parameters
        for derived_id in ids[1:]:
            assert db.conn.execute(
                "SELECT 1 FROM mmfdb_edge WHERE source_node_id=? AND target_node_id=? "
                "AND relationship_type='derived_from' AND deleted_at IS NULL",
                (derived_id, ids[0]),
            ).fetchone()
