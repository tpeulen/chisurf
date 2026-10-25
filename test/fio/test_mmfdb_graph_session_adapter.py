from __future__ import annotations

import json

import pytest

# The adapter runs on the IMP.bff-backed port runtime, which this file
# also exercises end to end.
from mmfdb.adapters import _port_runtime as cn
from mmfdb.adapters.graph_session import (
    GRAPH_SESSION_ARTIFACT,
    load_graph_session,
    store_graph_session,
)
from mmfdb.repository import MFDatabase

import chisurf  # noqa: F401 -- puts the bundled packages on sys.path


def _json(value: str | None):
    return json.loads(value) if value else None


def _connected_session() -> cn.Session:
    source = cn.Node(name="source")
    out = cn.Port(1.25, is_output=True, name="out")
    source.add_output_port("out", out)

    follower = cn.Node(name="follower")
    inp = cn.Port(0.0, is_bounded=True, lb=0.1, ub=10.0, name="in")
    follower.add_input_port("in", inp)
    inp.link = out

    return cn.Session({"source": source, "follower": follower})


def test_store_graph_session_writes_session_node_parameter_and_dependency_rows(tmp_path) -> None:
    db_path = tmp_path / "graph_session.db"
    session = _connected_session()
    source_out = session.nodes["source"].outputs["out"]
    follower_in = session.nodes["follower"].inputs["in"]

    with MFDatabase(db_path) as db:
        result = store_graph_session(
            db,
            session,
            operation_id="op_graph",
            experiment_id="exp_graph",
            fit_refs=[{"fit_uid": "fit-1", "operation_id": "op_graph"}],
        )

        assert result["session_artifact_id"].startswith("graph_session:")
        assert len(result["node_artifact_ids"]) == 2
        assert result["parameter_count"] == 2
        assert result["dependency_edge_count"] == 1

        artifacts = db.conn.execute(
            "SELECT artifact_id, artifact_kind, data_format, storage_mode "
            "FROM mmfdb_artifact ORDER BY artifact_id"
        ).fetchall()
        artifact_kinds = {row["artifact_kind"] for row in artifacts}
        assert {"graph_session", "graph_node"}.issubset(artifact_kinds)
        assert len([row for row in artifacts if row["artifact_kind"] == "graph_session"]) == 1
        assert len([row for row in artifacts if row["artifact_kind"] == "graph_node"]) == 2

        op_links = db.conn.execute(
            "SELECT artifact_id, direction, role "
            "FROM mmfdb_operation_artifact WHERE operation_id = ? "
            "ORDER BY role",
            ("op_graph",),
        ).fetchall()
        assert any(
            row["direction"] == "output" and row["role"] == "graph_session" for row in op_links
        )
        assert (
            sum(row["direction"] == "output" and row["role"] == "graph_node" for row in op_links)
            == 2
        )

        parameters = db.list_parameters(operation_id="op_graph")
        assert len(parameters) == 2
        metadata = [_json(row["metadata_json"]) for row in parameters]
        assert {item["graph_port_id"] for item in metadata} == {source_out.oid, follower_in.oid}
        follower_param = next(
            item for item in metadata if item["graph_port_id"] == follower_in.oid
        )
        assert follower_param["port_direction"] == "input"
        assert follower_param["schema_name"] == "mmfdb.parameter_ref.v1"

        edges = db.conn.execute(
            "SELECT source_node_id, target_node_id, relationship_type "
            "FROM mmfdb_edge WHERE relationship_type = 'parameter_depends_on'"
        ).fetchall()
        assert len(edges) == 1
        assert edges[0]["source_node_id"] == source_out.oid
        assert edges[0]["target_node_id"] == follower_in.oid

        restored = load_graph_session(db, result["session_artifact_id"])
        assert restored.oid == session.oid
        assert (
            restored.nodes["follower"].inputs["in"].link.oid
            == restored.nodes["source"].outputs["out"].oid
        )


def test_store_graph_session_rejects_invalid_parameter_before_writes(tmp_path) -> None:
    db_path = tmp_path / "graph_invalid_param.db"
    session = _connected_session()

    with MFDatabase(db_path) as db:
        with pytest.raises(ValueError, match="parameter_type"):
            store_graph_session(
                db,
                session,
                operation_id="op_invalid_param",
                parameters=[
                    {
                        "parameter_uuid": "bad_param",
                        "name": "bad",
                        "value": 0.0,
                        "parameter_type": "nonsense",
                    }
                ],
            )

        assert db.get_operation("op_invalid_param") is None
        assert db.conn.execute("SELECT COUNT(*) FROM mmfdb_artifact").fetchone()[0] == 0
        assert db.conn.execute("SELECT COUNT(*) FROM mmfdb_operation_artifact").fetchone()[0] == 0
        assert db.conn.execute("SELECT COUNT(*) FROM mmfdb_parameter").fetchone()[0] == 0


def test_store_graph_session_rejects_unknown_operation_type_before_writes(tmp_path) -> None:
    db_path = tmp_path / "graph_invalid_op_type.db"
    session = _connected_session()

    with MFDatabase(db_path) as db:
        with pytest.raises(ValueError, match="operation_type"):
            store_graph_session(
                db,
                session,
                operation_id="op_invalid_type",
                operation_type="quantum_computing",
            )

        assert db.get_operation("op_invalid_type") is None
        assert db.conn.execute("SELECT COUNT(*) FROM mmfdb_artifact").fetchone()[0] == 0


def test_store_graph_session_accepts_a_site_registered_operation_type(tmp_path) -> None:
    """A type registered in the extensible vocabulary is usable from the adapter.

    The adapter used to pre-check the static dictionary enum, which rejected a
    type the underlying ``record_operation`` accepts (DATA-05).
    """
    db_path = tmp_path / "graph_site_op_type.db"
    session = _connected_session()

    with MFDatabase(db_path) as db:
        db.register_vocabulary_value("operation_type", "external_tool")
        store_graph_session(
            db,
            session,
            operation_id="op_site_type",
            operation_type="external_tool",
        )

        assert db.get_operation("op_site_type")["operation_type"] == "external_tool"


def test_store_graph_session_rolls_back_on_artifact_failure(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "graph_artifact_failure.db"
    session = _connected_session()

    with MFDatabase(db_path) as db:

        def fail_register_artifact(*args, **kwargs):
            raise RuntimeError("artifact failure")

        monkeypatch.setattr(db, "register_artifact", fail_register_artifact)
        with pytest.raises(RuntimeError, match="artifact failure"):
            store_graph_session(db, session, operation_id="op_artifact_failure")

        assert db.get_operation("op_artifact_failure") is None
        assert db.conn.execute("SELECT COUNT(*) FROM mmfdb_artifact").fetchone()[0] == 0
        assert db.conn.execute("SELECT COUNT(*) FROM mmfdb_operation_artifact").fetchone()[0] == 0


def test_store_graph_session_rolls_back_on_link_failure(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "graph_link_failure.db"
    session = _connected_session()

    with MFDatabase(db_path) as db:

        def fail_record_operation_link(*args, **kwargs):
            raise RuntimeError("link failure")

        monkeypatch.setattr(db, "record_operation_link", fail_record_operation_link)
        with pytest.raises(RuntimeError, match="link failure"):
            store_graph_session(db, session, operation_id="op_link_failure")

        assert db.get_operation("op_link_failure") is None
        assert db.conn.execute("SELECT COUNT(*) FROM mmfdb_artifact").fetchone()[0] == 0
        assert db.conn.execute("SELECT COUNT(*) FROM mmfdb_operation_artifact").fetchone()[0] == 0


def test_store_graph_session_rolls_back_on_parameter_failure(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "graph_parameter_failure.db"
    session = _connected_session()

    with MFDatabase(db_path) as db:

        def fail_record_parameter(*args, **kwargs):
            raise RuntimeError("parameter failure")

        monkeypatch.setattr(db, "record_parameter", fail_record_parameter)
        with pytest.raises(RuntimeError, match="parameter failure"):
            store_graph_session(db, session, operation_id="op_parameter_failure")

        assert db.get_operation("op_parameter_failure") is None
        assert db.conn.execute("SELECT COUNT(*) FROM mmfdb_artifact").fetchone()[0] == 0
        assert db.conn.execute("SELECT COUNT(*) FROM mmfdb_operation_artifact").fetchone()[0] == 0
        assert db.conn.execute("SELECT COUNT(*) FROM mmfdb_parameter").fetchone()[0] == 0


def test_store_graph_session_accepts_explicit_parameter_uuid_for_link_mapping(tmp_path) -> None:
    db_path = tmp_path / "chinet_explicit.db"
    session = _connected_session()
    follower_port = session.nodes["follower"].inputs["in"]

    with MFDatabase(db_path) as db:
        store_graph_session(
            db,
            session,
            operation_id="op_explicit",
            parameters=[
                {
                    "parameter_uuid": "follower_param",
                    "name": "follower",
                    "value": 0.0,
                    "metadata": {
                        "schema_name": "mmfdb.parameter_ref.v1",
                        "graph_port_id": follower_port.oid,
                    },
                }
            ],
        )
        edges = db.conn.execute(
            "SELECT source_node_id, target_node_id "
            "FROM mmfdb_edge WHERE relationship_type = 'parameter_depends_on'"
        ).fetchall()
        assert edges[0]["target_node_id"] == "follower_param"


def test_store_graph_session_fast_mode_skips_node_artifacts(tmp_path) -> None:
    db_path = tmp_path / "graph_fast.db"
    session = _connected_session()

    with MFDatabase(db_path) as db:
        result = store_graph_session(
            db,
            session,
            operation_id="op_graph_fast",
            store_node_artifacts=False,
        )

        assert result["node_artifact_ids"] == []
        artifacts = db.list_artifacts(experiment_id=None)
        assert len([row for row in artifacts if row["artifact_kind"] == "graph_session"]) == 1
        assert len([row for row in artifacts if row["artifact_kind"] == "graph_node"]) == 0
        assert len(db.list_parameters(operation_id="op_graph_fast")) == 2




def test_load_accepts_the_legacy_chinet_era_kind(tmp_path) -> None:
    """Old rows carry artifact_kind 'chinet_session'; the loader accepts them."""
    with MFDatabase(tmp_path / "legacy.db") as db:
        db.record_operation(operation_id="op_legacy", operation_type="model_fitting")
        payload = {"schema_name": "mmfdb.graph_session.v1", "session": _connected_session().to_dict()}
        db.register_artifact(
            artifact_id="chinet_session:legacy-oid",
            artifact_kind="chinet_session",
            storage_mode="embedded_json",
            data_format="json",
            metadata={"schema_name": payload["schema_name"]},
            data_json=json.dumps(payload),
            validation_status="valid",
        )
        db.record_operation_link(
            operation_id="op_legacy",
            artifact_id="chinet_session:legacy-oid",
            direction="output",
            role="chinet_session",
        )
        restored = load_graph_session(db, "chinet_session:legacy-oid")
        assert set(restored.nodes) == {"source", "follower"}


def test_graph_session_artifact_constant_is_the_new_kind() -> None:
    assert GRAPH_SESSION_ARTIFACT == "graph_session"
