"""PRD-18 Task 2: integration test against the REAL in-process MMFDBClient.

Drives ``MMFDBClient(inprocess=True)`` end to end through its public ``call``
method (not a mock), so interface drift like the historical ``.call`` vs
``_call`` bug fails loudly instead of silently returning zero datasets.

Runs under the hermetic harness (PRD-18 Task 1): registration and the client's
handlers both resolve the same temp database, so this exercises a real round trip
without touching ``~/.chisurf``.
"""

from __future__ import annotations

from pathlib import Path

from mmfdb.provenance.result_registry import register_raw_measurement


def _register_one_raw(tmp_path: Path) -> tuple[str, str]:
    """Register one raw measurement into the resolved (temp) user database."""
    from chisurf.core.transform.mmfdb import session_from_auth
    from mmfdb.repository import MFDatabase
    from mmfdb.security.auth import create_session
    from mmfdb.store.database_resolver import resolve_database_path

    f = tmp_path / "measurement.ptu"
    f.write_bytes(b"\x00\x01\x02\x03")
    # Registration is explicit and authenticated; the in-process client's
    # handlers resolve this same hermetic test database for the read side.
    db = MFDatabase(resolve_database_path())
    db.ensure_user("client-integration-user")
    token = create_session(db.conn, "client-integration-user")["token"]
    db.conn.commit()
    session = session_from_auth(db, {"token": token})
    try:
        artifact_id = register_raw_measurement(str(f), db=db, session=session)
    finally:
        db.close()
    assert artifact_id
    return artifact_id, token


def test_real_inprocess_client_browse_and_open(tmp_path):
    from chisurf.plugins.core.mmfdb_admin.gui.client import MMFDBClient

    artifact_id, token = _register_one_raw(tmp_path)
    client = MMFDBClient(inprocess=True)
    client.token = token
    try:
        # Public contract: .call must exist and round-trip through the real
        # dispatcher (the bug this guards: .call missing -> AttributeError
        # swallowed -> browser shows 0).
        assert hasattr(client, "call")
        browse = client.call("mmfdb.datasets.browse", {"scope": "all", "limit": 50})
        ids = {d.get("artifact_id") or d.get("id") for d in browse.get("datasets", [])}
        assert artifact_id in ids, f"registered {artifact_id} not in browse {ids}"

        opened = client.call("mmfdb.datasets.open", {"artifact_id": artifact_id})
        # The open handler returns a readable local path for the artifact.
        path = opened.get("path") or opened.get("local_path")
        assert path, f"datasets.open returned no path: {opened}"
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()
