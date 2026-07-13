"""PRD-28: ndXplorer ← MMFDB launcher (the testable path-resolution core).

Runs under the hermetic harness, driving the real in-process MMFDBClient so the
resolve-path step is exercised end to end (the ndXplorer launch itself is
interactive and not tested here).
"""

from __future__ import annotations

from pathlib import Path

from mmfdb.provenance.result_registry import register_raw_measurement
from chisurf.plugins.ndxplorer.mmfdb_launcher import (
    BURST_KINDS,
    open_burst_selection_from_mmfdb,
    resolve_dataset_path,
)


def _authenticated_inprocess_client():
    """Return a real client carrying an explicitly issued test session."""
    from chisurf.plugins.core.mmfdb_admin.gui.client import MMFDBClient
    from mmfdb.repository import MFDatabase
    from mmfdb.security.auth import create_session
    from mmfdb.store.database_resolver import resolve_database_path

    with MFDatabase(resolve_database_path()) as db:
        db.ensure_user("ndx-launcher-user")
        token = create_session(db.conn, "ndx-launcher-user")["token"]
        db.conn.commit()
    client = MMFDBClient(inprocess=True)
    client.token = token
    return client


def test_resolve_dataset_path_via_real_client(tmp_path):
    from mmfdb.repository import MFDatabase
    from mmfdb.store.database_resolver import resolve_database_path

    f = tmp_path / "m.ptu"
    f.write_bytes(b"\x00\x01\x02\x03")
    with MFDatabase(resolve_database_path()) as db:
        artifact_id = register_raw_measurement(str(f), db=db, is_public=True)
    assert artifact_id

    client = _authenticated_inprocess_client()
    try:
        path = resolve_dataset_path(client, artifact_id)
        assert path, f"no local path resolved for {artifact_id}"
        assert Path(path).exists()
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()


def test_resolve_external_reference_directory_via_metadata(tmp_path):
    """A burst output folder is registered as an external_reference (no object,
    no file_path) with its on-disk path in metadata — resolve_dataset_path must
    return that path (the .bur folder co-located with the TTTR files, preserving
    the photon-index linkage), not fail."""
    from mmfdb.provenance.result_registry import register_raw_measurement, register_result
    from mmfdb.repository import MFDatabase
    from mmfdb.store.database_resolver import resolve_database_path

    burst_dir = tmp_path / "burstwise"
    burst_dir.mkdir()
    (burst_dir / "f1.bur").write_text("0 100\n")
    raw_file = tmp_path / "m.ptu"
    raw_file.write_bytes(b"\x00\x01")

    # Register into the resolved (hermetic) DB the in-process client also opens.
    with MFDatabase(resolve_database_path()) as db:
        raw = register_raw_measurement(str(raw_file), db=db, is_public=True)
        ext = register_result(
            kind="external_reference",
            data=None,
            parent_artifact_id=raw,
            operation_type="burst_selection",
            data_format="directory",
            metadata={
                "plugin": "burst_selection",
                "output_role": "output_folder",
                "path": str(burst_dir),
            },
            db=db,
            is_public=True,
        )
    assert ext

    client = _authenticated_inprocess_client()
    try:
        path = resolve_dataset_path(client, ext)
        assert path == str(burst_dir)
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()


def test_resolve_dataset_path_empty_artifact_returns_none():
    class _NoCall:
        def call(self, *a, **k):  # pragma: no cover - must not be reached
            raise AssertionError("should not call for empty artifact_id")

    assert resolve_dataset_path(_NoCall(), "") is None


def test_burst_kinds_target_the_on_disk_burst_folder():
    # The burst .bur files reference photons in the original TTTR file, so the
    # launcher opens the on-disk burst folder (a directory external_reference),
    # which is also the single group per multi-file run — not an object-store copy.
    from chisurf.plugins.ndxplorer.mmfdb_launcher import BURST_FORMATS

    assert BURST_KINDS == ["external_reference"]
    assert "directory" in BURST_FORMATS


def test_picker_uses_explicit_client_instead_of_constructing_ambient_client(monkeypatch):
    """GUI glue must preserve the authenticated client supplied by its owner."""
    class Selection:
        artifact_id = "artifact-1"

    class Client:
        def call(self, method, params):
            assert method == "mmfdb.datasets.open"
            assert params == {"artifact_id": "artifact-1"}
            return {"local_path": "/tmp/selection"}

    supplied = Client()
    captured = {}

    from chisurf.gui.widgets.mmfdb import dataset_browser
    import chisurf.plugins.ndxplorer.mmfdb_launcher as launcher

    def pick_dataset(**kwargs):
        captured.update(kwargs)
        return Selection()

    monkeypatch.setattr(
        dataset_browser.MmfdbDatasetPickerDialog,
        "pick_dataset",
        staticmethod(pick_dataset),
    )
    monkeypatch.setattr(launcher, "open_path_in_ndxplorer", lambda path: path)

    result = open_burst_selection_from_mmfdb(client=supplied)

    assert result == "/tmp/selection"
    assert captured["client"] is supplied
