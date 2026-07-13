#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Integration tests for chisurf ndxplorer plugin CLI."""

import json
import pathlib
import subprocess
import sys
import pytest
from click.testing import CliRunner

from mmfdb.repository import MFDatabase
from chisurf.plugins.ndxplorer.cli import (
    filter_cmd,
    resolve_source_artifact,
    run_image_workflow,
)


@pytest.fixture
def temp_mmfdb(tmp_path):
    """Setup a temporary MFDatabase with a dummy raw and burst selection product."""
    db_path = tmp_path / "test_ndx_cli.db"
    
    # Create source burst directory
    bur_dir = tmp_path / "bur_source"
    bur_subdir = bur_dir / "bi4_bur"
    bur_subdir.mkdir(parents=True, exist_ok=True)
    
    dummy_bur = bur_subdir / "measurement_1.bur"
    dummy_bur.write_text(
        "First Photon\tLast Photon\tFirst File\tLast File\tproximity_ratio\tn_photons\tMean Macro Time (ms)\n"
        "100\t200\tfile1.ptu\tfile1.ptu\t0.5\t100\t1000\n"
        "300\t400\tfile1.ptu\tfile1.ptu\t0.2\t40\t2000\n"
        "500\t600\tfile1.ptu\tfile1.ptu\t0.8\t150\t3000\n"
        "700\t800\tfile1.ptu\tfile1.ptu\t0.4\t60\t4000\n",
        encoding="utf-8",
    )
    
    with MFDatabase(db_path) as db:
        db.ensure_user("ndx-user")
        db.add_sample("sample_1")
        db.add_experiment("exp_1", sample_id="sample_1", status="complete")
        
        # Add raw reference
        raw_id = db.add_raw_data_reference(
            experiment_id="exp_1",
            data_type="PTU",
            storage_mode="local_file",
            file_path=str(tmp_path / "dummy.ptu"),
            checksum="0" * 64,
        )
        
        # Add processing run
        run_id = db.add_processing_run(
            experiment_id="exp_1",
            input_raw_data_ids=[raw_id],
            settings={"burst_detection": {"min_photons": 10}},
            status="succeeded",
        )
        
        # Register the burst folder
        prod_id = db.add_processed_data_product(
            processing_id=run_id,
            product_type="derived_product",
            storage_mode="folder",
            folder_path=str(bur_dir),
            checksum="1" * 64,
            row_count=4,
            validation_status="valid",
        )
        
        # Add registration to the artifacts table
        db.register_artifact(
            artifact_id="art_burst_src",
            artifact_kind="external_reference",
            data_format="directory",
            storage_mode="folder",
            metadata={"path": str(bur_dir), "folder_path": str(bur_dir)},
            created_by_user_id="ndx-user",
        )
        db.link_artifact_to_sample("art_burst_src", "sample_1")
        from mmfdb.security.auth import create_default_acl_for_object, create_session

        create_default_acl_for_object(
            db.conn,
            "artifact",
            "art_burst_src",
            owner_user_id="ndx-user",
            mode=0o700,
        )
        token = create_session(db.conn, "ndx-user")["token"]
        db.conn.commit()

    return db_path, "art_burst_src", "sample_1", token


def test_csc_ndxplorer_filter(temp_mmfdb, tmp_path):
    """Test csc ndxplorer filter command registers filtered bursts in MMFDB."""
    db_path, art_id, sample_id, token = temp_mmfdb
    runner = CliRunner()
    
    out_dir = tmp_path / "filtered_output"
    
    result = runner.invoke(filter_cmd, [
        "--from-mmfdb", art_id,
        "--select", "proximity_ratio:0.3-0.6",
        "--out", str(out_dir),
        "--to-mmfdb",
        "--sample-id", sample_id,
        "--db", str(db_path),
        "--token", token,
        "--skip-nth-row", "1",
    ])
    
    assert result.exit_code == 0, result.output or repr(result.exception)
    res_data = json.loads(result.output)
    assert res_data["ok"] is True
    assert res_data["n_out"] == 2
    
    new_artifact_id = res_data["artifact_id"]
    assert new_artifact_id is not None
    
    # Check that artifact is registered in the database
    with MFDatabase(db_path) as db:
        artifact = db.get_artifact(new_artifact_id)
        assert artifact is not None
        assert artifact["artifact_kind"] == "external_reference"
        metadata = artifact.get("metadata") or json.loads(artifact.get("metadata_json") or "{}")
        assert metadata["query"] is None


def test_resolve_source_artifact_enforces_acl_when_principal_is_supplied(
    temp_mmfdb,
):
    """The headless API must not bypass MMFDB ACLs for authenticated callers."""
    from mmfdb.security.auth import AuthenticatedPrincipal

    db_path, artifact_id, _sample_id, _token = temp_mmfdb
    with MFDatabase(db_path) as db:
        db.ensure_user("other-user")
        db.conn.commit()

        with pytest.raises(Exception, match="Permission denied"):
            resolve_source_artifact(
                db,
                artifact_id,
                principal=AuthenticatedPrincipal("other-user"),
            )

        resolved = resolve_source_artifact(
            db,
            artifact_id,
            principal=AuthenticatedPrincipal("ndx-user"),
        )
        assert pathlib.Path(resolved).is_dir()


def test_image_workflow_uses_explicit_db_and_registers_outputs_atomically(
    temp_mmfdb,
    tmp_path,
):
    """Image and ROI outputs share one explicit transaction and preserve parameters."""
    from mmfdb.security.auth import AuthenticatedPrincipal

    db_path, artifact_id, sample_id, _token = temp_mmfdb
    output = tmp_path / "lifetime.png"
    selection = tmp_path / "selected"

    def fake_runner(args, **kwargs):
        assert args[:4] == [sys.executable, "-m", "ndxplorer", "image"]
        assert kwargs["check"] is False
        assert kwargs["capture_output"] is True
        output.write_bytes(b"PNG")
        selection.mkdir()
        return subprocess.CompletedProcess(
            args,
            0,
            stdout=json.dumps(
                {
                    "shape": [4, 5],
                    "n_selected_px": 7,
                    "out": str(output),
                }
            ),
            stderr="",
        )

    with MFDatabase(db_path) as db:
        vocab_before = db.conn.execute(
            "SELECT COUNT(*) FROM mmfdb_vocabulary"
        ).fetchone()[0]
        result = run_image_workflow(
            db=db,
            source_artifact_id=artifact_id,
            map_parameter="lifetime",
            output_path=output,
            output_selection_path=selection,
            selections=("proximity_ratio:0.2-0.8",),
            query="n_photons >= 50",
            roi_path=tmp_path / "mask.tif",
            skip_nth_row=2,
            sample_id=sample_id,
            register_outputs=True,
            principal=AuthenticatedPrincipal("ndx-user"),
            subprocess_runner=fake_runner,
        )

        assert result["artifact_id"]
        assert result["selection_artifact_id"]
        assert db.conn.execute(
            "SELECT COUNT(*) FROM mmfdb_vocabulary"
        ).fetchone()[0] == vocab_before

        image = db.get_artifact(result["artifact_id"])
        roi = db.get_artifact(result["selection_artifact_id"])
        assert image["created_by_user_id"] == "ndx-user"
        assert roi["created_by_user_id"] == "ndx-user"
        acl_owners = {
            row[0]
            for row in db.conn.execute(
                """SELECT owner_user_id FROM mmfdb_object_acl
                   WHERE object_type = 'artifact' AND object_id IN (?, ?)""",
                (result["artifact_id"], result["selection_artifact_id"]),
            )
        }
        assert acl_owners == {"ndx-user"}
        image_meta = image.get("metadata") or json.loads(image["metadata_json"])
        roi_meta = roi.get("metadata") or json.loads(roi["metadata_json"])
        for metadata in (image_meta, roi_meta):
            assert metadata["source_artifact_id"] == artifact_id
            assert metadata["map_parameter"] == "lifetime"
            assert metadata["selections"] == ["proximity_ratio:0.2-0.8"]
            assert metadata["query"] == "n_photons >= 50"
            assert metadata["roi_path"] == str((tmp_path / "mask.tif").resolve())
            assert metadata["skip_nth_row"] == 2

        operation_types = {
            row[0]
            for row in db.conn.execute(
                """SELECT DISTINCT o.operation_type
                   FROM mmfdb_operation AS o
                   JOIN mmfdb_operation_artifact AS oa
                     ON oa.operation_id = o.operation_id
                   WHERE oa.artifact_id IN (?, ?)""",
                (result["artifact_id"], result["selection_artifact_id"]),
            )
        }
        assert operation_types == {"image_analysis", "filtering"}


def test_image_output_registration_rolls_back_both_outputs_on_second_failure(
    temp_mmfdb,
    tmp_path,
    monkeypatch,
):
    """A failed ROI registration must not leave the image artifact committed."""
    import mmfdb.provenance.result_registry as registry

    from mmfdb.security.auth import AuthenticatedPrincipal

    db_path, artifact_id, sample_id, _token = temp_mmfdb
    output = tmp_path / "map.png"
    selection = tmp_path / "selection"
    original = registry.register_result
    calls = 0

    def fail_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated ROI registration failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(registry, "register_result", fail_second)

    def fake_runner(args, **kwargs):
        output.write_bytes(b"PNG")
        selection.mkdir()
        return subprocess.CompletedProcess(
            args,
            0,
            stdout=json.dumps(
                {"shape": [1, 1], "n_selected_px": 1, "out": str(output)}
            ),
            stderr="",
        )

    with MFDatabase(db_path) as db:
        before = db.conn.execute("SELECT COUNT(*) FROM mmfdb_artifact").fetchone()[0]
        with pytest.raises(RuntimeError, match="simulated ROI"):
            run_image_workflow(
                db=db,
                source_artifact_id=artifact_id,
                map_parameter="intensity",
                output_path=output,
                output_selection_path=selection,
                sample_id=sample_id,
                register_outputs=True,
                principal=AuthenticatedPrincipal("ndx-user"),
                subprocess_runner=fake_runner,
            )
        assert db.conn.execute("SELECT COUNT(*) FROM mmfdb_artifact").fetchone()[0] == before


def test_cli_rejects_invalid_token_before_running_ndxplorer(temp_mmfdb, tmp_path):
    """The CLI must authenticate before resolving or processing a source artifact."""
    db_path, artifact_id, sample_id, _token = temp_mmfdb
    result = CliRunner().invoke(
        filter_cmd,
        [
            "--from-mmfdb",
            artifact_id,
            "--out",
            str(tmp_path / "must-not-exist"),
            "--to-mmfdb",
            "--sample-id",
            sample_id,
            "--db",
            str(db_path),
            "--token",
            "invalid-token",
        ],
    )

    assert result.exit_code != 0
    assert "Authentication required" in result.output
    assert not (tmp_path / "must-not-exist").exists()
