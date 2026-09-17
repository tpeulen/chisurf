"""Test that archive -> restore produces identical project data."""

from __future__ import annotations

import copy
import uuid

import numpy as np
from mmfdb.project.project_archiver import (
    archive_project_to_mmfdb,
    restore_project_from_artifacts,
)
from mmfdb.repository import MFDatabase


def _make_test_payload() -> dict:
    """Create a minimal project payload with 2 datasets and 2 fits."""
    return {
        "project_format_version": 4,
        "meta": {
            "name": "test_project",
            "description": "Test project",
            "chisurf_version": "25.1.0",
            "created": "2025-01-01T00:00:00",
        },
        "datasets": {
            "ds_001": {
                "uid": "ds_001",
                "name": "sample.ptu",
                "filename": "sample.ptu",
                "x": [0.0, 1.0, 2.0, 3.0],
                "y": [100.0, 80.0, 60.0, 40.0],
                "data_reader": {
                    "module": "chisurf.fio.tcspc",
                    "class": "TCSPCReader",
                    "state": {},
                },
            },
            "ds_002": {
                "uid": "ds_002",
                "name": "donor_only.ptu",
                "filename": "donor_only.ptu",
                "x": [0.0, 1.0, 2.0, 3.0],
                "y": [200.0, 150.0, 100.0, 50.0],
                "data_reader": {
                    "module": "chisurf.fio.tcspc",
                    "class": "TCSPCReader",
                    "state": {},
                },
            },
        },
        "fits": [
            {
                "id": "fit_001",
                "name": "DA sample fit",
                "model_name": "FRET: FD (Gaussian)",
                "local_fits": [
                    {
                        "dataset_id": "ds_001",
                        "fit_state": {
                            "model_module": "chisurf.models.tcspc",
                            "model_class": "FRETGaussian",
                            "parameters": {
                                "p1": {
                                    "uid": "p1",
                                    "name": "p1",
                                    "value": 5.0,
                                    "fixed": False,
                                    "bounds": [0.0, 10.0],
                                    "bounds_on": True,
                                    "link_target": "p2",
                                    "link_target_fit_uid": "fit_002",
                                },
                                "p2": {
                                    "uid": "p2",
                                    "name": "p2",
                                    "value": 3.0,
                                    "fixed": True,
                                    "bounds": [0.0, 5.0],
                                    "bounds_on": False,
                                    "link_target": None,
                                    "link_target_fit_uid": None,
                                },
                            },
                        },
                    }
                ],
                "fit_range": [0, 100],
                "plot_state": {"log_scale": False, "x_range": [0, 100]},
            },
            {
                "id": "fit_002",
                "name": "Donor only fit",
                "model_name": "Lifetime",
                "local_fits": [
                    {
                        "dataset_id": "ds_001",
                        "fit_state": {
                            "model_module": "chisurf.models.tcspc",
                            "model_class": "LifetimeModel",
                            "parameters": {
                                "tau1": {
                                    "uid": "tau1",
                                    "name": "tau1",
                                    "value": 4.0,
                                    "fixed": False,
                                    "bounds": [0.0, 20.0],
                                    "bounds_on": False,
                                    "link_target": None,
                                    "link_target_fit_uid": None,
                                },
                            },
                        },
                    }
                ],
            },
        ],
        "ui": {"current_fit_index": 0, "active_tab": "fitting"},
        "experiments": {"exp_001": {"type": "tcspc"}},
    }


def _archive_and_restore(tmp_path, payload):
    """Helper: archive payload to temp MMFDB and restore it."""
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
    assert len(restored["datasets"]) == 2
    for ds_id in payload["datasets"]:
        assert ds_id in restored["datasets"], f"Dataset {ds_id} missing after restore"
        ds_restored = restored["datasets"][ds_id]
        assert "curves" in ds_restored, f"Dataset {ds_id} missing 'curves' field"
        assert len(ds_restored["curves"]) > 0, f"Dataset {ds_id} has empty curves list"
        for curve in ds_restored["curves"]:
            assert "x" in curve, "Curve missing 'x' array"
            assert "y" in curve, "Curve missing 'y' array"
            assert isinstance(curve["x"], dict), "Curve x should be encoded dict"
            assert isinstance(curve["y"], dict), "Curve y should be encoded dict"
    db.close()


def test_roundtrip_preserves_fit_structure(tmp_path) -> None:
    payload = _make_test_payload()
    db, restored, _, _ = _archive_and_restore(tmp_path, payload)
    assert restored is not None
    assert len(restored["fits"]) == 2
    for i, fit in enumerate(restored["fits"]):
        assert "id" in fit, f"Fit {i} missing 'id'"
        assert "name" in fit, f"Fit {i} missing 'name'"
        assert "model_name" in fit, f"Fit {i} missing 'model_name'"
        assert "local_fits" in fit, f"Fit {i} missing 'local_fits'"
        assert len(fit["local_fits"]) > 0, f"Fit {i} has empty local_fits"
    db.close()


def test_roundtrip_preserves_metadata(tmp_path) -> None:
    payload = _make_test_payload()
    db, restored, _, _ = _archive_and_restore(tmp_path, payload)
    assert restored is not None
    assert restored.get("ui_state") == payload["ui"]
    db.close()


def test_roundtrip_two_datasets_not_collapsed(tmp_path) -> None:
    """Regression: previously all datasets collapsed to key 'dataset'."""
    payload = _make_test_payload()
    db, restored, _, _ = _archive_and_restore(tmp_path, payload)
    assert restored is not None
    dataset_keys = list(restored["datasets"].keys())
    assert len(set(dataset_keys)) == 2, f"Dataset keys not unique: {dataset_keys}"
    db.close()


def test_roundtrip_preserves_parameters_and_edges(tmp_path) -> None:
    """Fit parameters and dependency edges are restored."""
    payload = _make_test_payload()
    db, restored, _, _ = _archive_and_restore(tmp_path, payload)
    assert restored is not None
    assert "parameters" in restored
    assert "dependency_edges" in restored
    assert len(restored["parameters"]) > 0

    has_p1 = any("p1" in str(params) for params in restored["parameters"].values())
    assert has_p1, "p1 parameter should exist in restored parameters"

    for op_id, params in restored["parameters"].items():
        for param in params:
            if param.get("uid") == "p1":
                assert param.get("value") == 5.0, (
                    f"p1 value should be 5.0, got {param.get('value')}"
                )
    db.close()


def test_roundtrip_preserves_experiments(tmp_path) -> None:
    """Experiments dict survives the round-trip."""
    payload = _make_test_payload()
    db, restored, _, _ = _archive_and_restore(tmp_path, payload)
    assert restored is not None
    assert restored.get("experiments") == payload["experiments"]
    db.close()


# --- New tests for R8-4: complex data types and edge cases ---


def test_roundtrip_array_values_decoded_correctly(tmp_path) -> None:
    """Verify that x/y array VALUES survive encode-decode, not just structure."""
    from chisurf.core.experiments.core.serialize import decode_array

    payload = _make_test_payload()
    db, restored, _, _ = _archive_and_restore(tmp_path, payload)
    assert restored is not None

    for ds_id in ("ds_001", "ds_002"):
        ds = restored["datasets"][ds_id]
        curves = ds["curves"]
        assert len(curves) >= 1
        curve = curves[0]
        x_decoded = decode_array(curve["x"])
        y_decoded = decode_array(curve["y"])
        x_orig = np.array(payload["datasets"][ds_id]["x"], dtype=float)
        y_orig = np.array(payload["datasets"][ds_id]["y"], dtype=float)
        np.testing.assert_allclose(x_decoded, x_orig, err_msg=f"{ds_id} x values differ")
        np.testing.assert_allclose(y_decoded, y_orig, err_msg=f"{ds_id} y values differ")
    db.close()


def test_roundtrip_error_arrays(tmp_path) -> None:
    """Error arrays (ex, ey) survive the round-trip."""
    from chisurf.core.experiments.core.serialize import decode_array

    payload = _make_test_payload()
    payload["datasets"]["ds_001"]["ex"] = [0.1, 0.2, 0.3, 0.4]
    payload["datasets"]["ds_001"]["ey"] = [5.0, 4.0, 3.0, 2.0]

    db, restored, _, _ = _archive_and_restore(tmp_path, payload)
    assert restored is not None

    ds = restored["datasets"]["ds_001"]
    curve = ds["curves"][0]
    assert "ex" in curve, "Error array ex missing from restored curve"
    assert "ey" in curve, "Error array ey missing from restored curve"

    ex_decoded = decode_array(curve["ex"])
    ey_decoded = decode_array(curve["ey"])
    np.testing.assert_allclose(ex_decoded, [0.1, 0.2, 0.3, 0.4])
    np.testing.assert_allclose(ey_decoded, [5.0, 4.0, 3.0, 2.0])
    db.close()


def test_roundtrip_multi_version_isolation(tmp_path) -> None:
    """Restoring version 1 must not include fits from version 2."""
    db = MFDatabase(tmp_path / "isolation.db")
    pid = f"proj_{uuid.uuid4().hex[:12]}"
    vid1 = f"ver_{uuid.uuid4().hex[:12]}"
    vid2 = f"ver_{uuid.uuid4().hex[:12]}"

    payload1 = _make_test_payload()
    payload1["fits"] = [payload1["fits"][0]]  # only fit_001

    payload2 = _make_test_payload()
    payload2["fits"] = [
        {
            "id": "fit_999",
            "name": "Version2Fit",
            "model_name": "SomeModel",
            "local_fits": [
                {
                    "dataset_id": "ds_001",
                    "fit_state": {
                        "model_module": "m",
                        "model_class": "C",
                        "parameters": {},
                    },
                }
            ],
        }
    ]

    archive_project_to_mmfdb(db, payload1, vid1, pid, 1)
    archive_project_to_mmfdb(db, payload2, vid2, pid, 2)

    r1 = restore_project_from_artifacts(db, vid1)
    r2 = restore_project_from_artifacts(db, vid2)

    assert r1 is not None
    assert r2 is not None
    assert len(r1["fits"]) == 1, f"Version 1 should have 1 fit, got {len(r1['fits'])}"
    assert len(r2["fits"]) == 1, f"Version 2 should have 1 fit, got {len(r2['fits'])}"
    assert r1["fits"][0]["id"] == "fit_001"
    assert r2["fits"][0]["name"] == "Version2Fit"
    db.close()


def test_roundtrip_dependency_edge_content(tmp_path) -> None:
    """Dependency edges contain correct source/target parameter UIDs."""
    payload = _make_test_payload()
    db, restored, _, _ = _archive_and_restore(tmp_path, payload)
    assert restored is not None

    edges = restored["dependency_edges"]
    assert len(edges) >= 1, "Should have at least 1 dependency edge (p1 -> p2)"

    edge = edges[0]
    assert edge["source_node_id"] == "p2", (
        f"Edge source should be p2 (link target), got {edge['source_node_id']}"
    )
    assert edge["target_node_id"] == "p1", (
        f"Edge target should be p1 (the linker), got {edge['target_node_id']}"
    )
    assert edge["relationship_type"] == "parameter_depends_on"
    db.close()


def test_roundtrip_large_arrays(tmp_path) -> None:
    """Arrays with 1000+ elements survive the round-trip."""
    from chisurf.core.experiments.core.serialize import decode_array

    payload = _make_test_payload()
    x_large = list(np.linspace(0, 100, 4096))
    y_large = list(np.random.default_rng(42).poisson(100, 4096).astype(float))
    payload["datasets"]["ds_001"]["x"] = x_large
    payload["datasets"]["ds_001"]["y"] = y_large

    db, restored, _, _ = _archive_and_restore(tmp_path, payload)
    assert restored is not None

    curve = restored["datasets"]["ds_001"]["curves"][0]
    x_decoded = decode_array(curve["x"])
    y_decoded = decode_array(curve["y"])
    assert len(x_decoded) == 4096
    np.testing.assert_allclose(x_decoded, x_large)
    np.testing.assert_allclose(y_decoded, y_large)
    db.close()


def test_roundtrip_fit_metadata_fields(tmp_path) -> None:
    """Fit record fields (fit_range, plot_state, model_name) survive."""
    payload = _make_test_payload()
    db, restored, _, _ = _archive_and_restore(tmp_path, payload)
    assert restored is not None

    fit = restored["fits"][0]
    assert fit["name"] == "DA sample fit"
    assert fit["model_name"] == "FRET: FD (Gaussian)"
    assert fit["fit_range"] == [0, 100]
    assert fit["plot_state"] == {"log_scale": False, "x_range": [0, 100]}
    db.close()


def _make_global_fit_payload(n_local: int = 3) -> dict:
    """Payload whose first fit is a *global* fit over ``n_local`` local fits.

    Global fitting is the point of the application, and it is the case the
    archive/restore asymmetry breaks: the archiver writes one ``fit_result``
    artifact per local fit, all sharing the fit UID.
    """
    payload = _make_test_payload()
    template = payload["fits"][0]["local_fits"][0]
    locals_ = []
    for i in range(n_local):
        lf = copy.deepcopy(template)
        lf["dataset_id"] = "ds_001" if i % 2 == 0 else "ds_002"
        lf["fit_state"]["parameters"]["p1"]["value"] = 5.0 + i
        locals_.append(lf)
    payload["fits"][0]["local_fits"] = locals_
    return payload


def test_roundtrip_global_fit_is_not_shattered(tmp_path) -> None:
    """A global fit must come back as ONE group holding all its local fits.

    Previously each local fit was restored as its own fit group, so a 3-way
    global fit turned into three groups -- all carrying the *same* fit id,
    which also collides downstream wherever fits are keyed by id.
    """
    payload = _make_global_fit_payload(n_local=3)
    db, restored, _, _ = _archive_and_restore(tmp_path, payload)
    assert restored is not None

    assert len(restored["fits"]) == len(payload["fits"]), (
        f"group count changed: {len(payload['fits'])} archived, {len(restored['fits'])} restored"
    )
    assert [len(f["local_fits"]) for f in restored["fits"]] == [3, 1]

    ids = [f["id"] for f in restored["fits"]]
    assert len(set(ids)) == len(ids), f"duplicate fit ids after restore: {ids}"
    db.close()


def test_roundtrip_global_fit_preserves_local_fit_order(tmp_path) -> None:
    """Local fits keep their original order and payloads within the group."""
    payload = _make_global_fit_payload(n_local=3)
    db, restored, _, _ = _archive_and_restore(tmp_path, payload)
    assert restored is not None

    original = payload["fits"][0]["local_fits"]
    restored_locals = restored["fits"][0]["local_fits"]
    assert len(restored_locals) == len(original)

    def _p1(local_fit):
        return local_fit["fit_state"]["parameters"]["p1"]["value"]

    assert [_p1(lf) for lf in restored_locals] == [_p1(lf) for lf in original]
    assert [lf["dataset_id"] for lf in restored_locals] == [lf["dataset_id"] for lf in original]
    db.close()


def test_roundtrip_global_fit_keeps_group_order(tmp_path) -> None:
    """Fit groups come back in the order they were archived."""
    payload = _make_global_fit_payload(n_local=2)
    db, restored, _, _ = _archive_and_restore(tmp_path, payload)
    assert restored is not None

    assert [f["id"] for f in restored["fits"]] == [f["id"] for f in payload["fits"]]
    db.close()


def test_regroup_falls_back_to_encounter_order_without_indices(tmp_path) -> None:
    """Archives predating the index metadata still regroup, in encounter order.

    ``lf_id`` is only the local-fit index when a local fit carries no id of its
    own, so artifact-id ordering cannot be relied on for older archives; the
    order the artifacts arrive in is the best available signal.
    """
    from mmfdb.project.project_archiver import _regroup_fit_artifacts

    entries = [
        {
            "artifact_id": f"fit_result:v1:fit_a:{name}",
            "envelope": {"id": "fit_a", "name": "A", "model_name": "M"},
            "local_fit": {"dataset_id": name},
            "fit_index": None,
            "local_fit_index": None,
        }
        for name in ("zebra", "alpha", "middle")
    ]
    records = _regroup_fit_artifacts(entries)

    assert len(records) == 1
    assert [lf["dataset_id"] for lf in records[0]["local_fits"]] == ["zebra", "alpha", "middle"]


def test_regroup_ignores_a_duplicated_artifact(tmp_path) -> None:
    """The same artifact reached twice must not duplicate its local fit."""
    from mmfdb.project.project_archiver import _regroup_fit_artifacts

    entry = {
        "artifact_id": "fit_result:v1:fit_a:0",
        "envelope": {"id": "fit_a", "name": "A", "model_name": "M"},
        "local_fit": {"dataset_id": "ds_001"},
        "fit_index": 0,
        "local_fit_index": 0,
    }
    records = _regroup_fit_artifacts([entry, dict(entry)])

    assert len(records) == 1
    assert len(records[0]["local_fits"]) == 1


def test_regroup_keeps_unidentified_fits_separate(tmp_path) -> None:
    """Fits archived without a UID must not all collapse into one group."""
    from mmfdb.project.project_archiver import _regroup_fit_artifacts

    entries = [
        {
            "artifact_id": f"fit_result:v1::{i}",
            "envelope": {"id": "", "name": f"anon {i}", "model_name": "M"},
            "local_fit": {"dataset_id": f"ds_{i}"},
            "fit_index": i,
            "local_fit_index": 0,
        }
        for i in range(3)
    ]
    records = _regroup_fit_artifacts(entries)

    assert len(records) == 3
    assert [r["name"] for r in records] == ["anon 0", "anon 1", "anon 2"]
