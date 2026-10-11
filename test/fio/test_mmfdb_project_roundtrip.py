"""Archive -> restore of a v5 project through MMFDB.

Payloads come from the real session writer (``capture_session``), never from
hand-rolled dicts: the archiver indexes the validated v5 snapshot.
"""

from __future__ import annotations

import json
import uuid

import numpy as np
import pytest
from mmfdb.project.project_archiver import (
    _collect_fit_records,
    archive_project_to_mmfdb,
    restore_project_from_artifacts,
)
from mmfdb.repository import MFDatabase

from test.fio.v5_payload import (
    make_curves,
    make_global_group,
    make_single_fit,
    v5_payload,
)


def _make_test_payload() -> dict:
    """Two datasets, a global fit (linked parameter) and an independent fit."""
    first, second = make_curves()
    group = make_global_group(first, second, "fit_001")
    single = make_single_fit(first, "fit_002")
    return v5_payload(
        [first, second],
        [group, single],
        name="test_project",
        ui_state={"current_fit_index": 0, "active_tab": "fitting"},
    )


def _archive_and_restore(tmp_path, payload):
    db = MFDatabase(tmp_path / "roundtrip.db")
    version_id = f"ver_{uuid.uuid4().hex[:12]}"
    project_id = f"proj_{uuid.uuid4().hex[:12]}"
    archive_project_to_mmfdb(
        db=db,
        project_payload=payload,
        version_id=version_id,
        project_id=project_id,
        version_number=1,
    )
    restored = restore_project_from_artifacts(db, version_id)
    return db, restored, version_id, project_id


def test_roundtrip_preserves_datasets(tmp_path) -> None:
    payload = _make_test_payload()
    db, restored, _, _ = _archive_and_restore(tmp_path, payload)
    assert restored is not None
    assert set(restored["datasets"]) == set(payload["datasets"])
    for uid, record in payload["datasets"].items():
        assert restored["datasets"][uid] == record
    db.close()


def test_roundtrip_two_datasets_not_collapsed(tmp_path) -> None:
    """Regression: previously all datasets collapsed to key 'dataset'."""
    db, restored, _, _ = _archive_and_restore(tmp_path, _make_test_payload())
    assert len(set(restored["datasets"])) == 2
    db.close()


def test_roundtrip_array_values(tmp_path) -> None:
    payload = _make_test_payload()
    db, restored, _, _ = _archive_and_restore(tmp_path, payload)
    for uid in ("ds_001", "ds_002"):
        for name in ("x", "y", "ex", "ey"):
            np.testing.assert_array_equal(
                restored["datasets"][uid]["arrays"][name]["values"],
                payload["datasets"][uid]["arrays"][name]["values"],
            )
    db.close()


def test_roundtrip_large_arrays(tmp_path) -> None:
    from test.fio.v5_payload import make_curve

    curve = make_curve("big", n=4096)
    curve.y = np.random.default_rng(42).poisson(100, 4096).astype(float)
    payload = v5_payload([curve], [])
    db, restored, _, _ = _archive_and_restore(tmp_path, payload)
    np.testing.assert_array_equal(restored["datasets"]["big"]["arrays"]["y"]["values"], curve.y)
    db.close()


def test_roundtrip_preserves_fit_records(tmp_path) -> None:
    """Each fit comes back once, whole, in archive order."""
    payload = _make_test_payload()
    db, restored, _, _ = _archive_and_restore(tmp_path, payload)
    assert restored["fits"] == payload["fits"]
    assert [f["uid"] for f in restored["fits"]] == ["fit_001", "fit_002"]
    db.close()


def test_roundtrip_global_fit_is_not_shattered(tmp_path) -> None:
    """A two-member global fit is one record, not one record per member."""
    payload = _make_test_payload()
    db, restored, _, _ = _archive_and_restore(tmp_path, payload)
    assert [len(f["members"]) for f in restored["fits"]] == [2, 1]
    uids = [f["uid"] for f in restored["fits"]]
    assert len(set(uids)) == len(uids)
    db.close()


def test_roundtrip_preserves_ui_state_and_experiments(tmp_path) -> None:
    payload = _make_test_payload()
    db, restored, _, _ = _archive_and_restore(tmp_path, payload)
    assert restored["ui_state"] == payload["ui"]
    assert restored["experiments"] == payload["experiments"]
    db.close()


def test_roundtrip_preserves_parameters(tmp_path) -> None:
    """Every captured model parameter is indexed with its value."""
    payload = _make_test_payload()
    db, restored, _, _ = _archive_and_restore(tmp_path, payload)
    expected = {
        p["uid"]: p["value"]
        for fit in payload["fits"]
        for member in fit["members"]
        for p in member["model"]["parameters"]
    }
    indexed = {
        json.loads(row["metadata_json"])["fit_parameter_uid"]: row["value"]
        for rows in restored["parameters"].values()
        for row in rows
    }
    assert indexed == expected
    assert 5.0 in indexed.values()
    db.close()


def test_roundtrip_dependency_edge_content(tmp_path) -> None:
    """The cross-member link yields one parameter_depends_on edge."""
    payload = _make_test_payload()
    db, restored, _, _ = _archive_and_restore(tmp_path, payload)
    link_params = [
        p
        for fit in payload["fits"]
        for member in fit["members"]
        for p in member["model"]["parameters"]
        if p.get("link_target")
    ]
    assert len(link_params) == 1
    edges = restored["dependency_edges"]
    assert len(edges) == 1
    assert edges[0]["relationship_type"] == "parameter_depends_on"
    assert edges[0]["metadata_json"] and link_params[0]["uid"] in edges[0]["metadata_json"]
    db.close()


def test_roundtrip_multi_version_isolation(tmp_path) -> None:
    """Restoring version 1 must not include fits from version 2."""
    db = MFDatabase(tmp_path / "isolation.db")
    pid = f"proj_{uuid.uuid4().hex[:12]}"
    vid1, vid2 = f"ver_{uuid.uuid4().hex[:12]}", f"ver_{uuid.uuid4().hex[:12]}"

    first, second = make_curves()
    payload1 = v5_payload([first, second], [make_global_group(first, second, "fit_001")])
    first, second = make_curves()
    payload2 = v5_payload([first, second], [make_single_fit(first, "fit_999")])

    archive_project_to_mmfdb(db, payload1, vid1, pid, 1)
    archive_project_to_mmfdb(db, payload2, vid2, pid, 2)

    r1 = restore_project_from_artifacts(db, vid1)
    r2 = restore_project_from_artifacts(db, vid2)
    assert [f["uid"] for f in r1["fits"]] == ["fit_001"]
    assert [f["uid"] for f in r2["fits"]] == ["fit_999"]
    db.close()


def test_archive_rejects_a_pre_v5_fit_record(tmp_path) -> None:
    """A fit without the v5 identity is refused with a clear error, not a KeyError."""
    db = MFDatabase(tmp_path / "legacy.db")
    payload = _make_test_payload()
    payload["fits"] = [{"id": "fit_001", "name": "legacy", "local_fits": []}]
    with pytest.raises(ValueError, match="v5 fit record"):
        archive_project_to_mmfdb(db, payload, "ver_x", "proj_x", 1)
    db.close()


def test_collect_fit_records_orders_by_archive_index_and_dedupes() -> None:
    a = {"uid": "a", "members": []}
    b = {"uid": "b", "members": []}
    entries = [
        {"artifact_id": "2", "fit": b, "fit_index": 1},
        {"artifact_id": "1", "fit": a, "fit_index": 0},
        {"artifact_id": "1", "fit": a, "fit_index": 0},
        {"artifact_id": "x", "fit": None, "fit_index": 2},
    ]
    assert _collect_fit_records(entries) == [a, b]
