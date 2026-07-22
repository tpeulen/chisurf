"""The shared MMFDB file-picker helper: one global session, path resolution.

Every file selector routes database selection through this module, so the
client is built once and reused (a single embedded MMFDB session), and a chosen
dataset resolves to a local path whether its object store is local or S3.
"""

from __future__ import annotations

import pytest

from chisurf.gui.widgets.mmfdb import picker


@pytest.fixture(autouse=True)
def _reset_session():
    picker.reset_session_client()
    yield
    picker.reset_session_client()


def test_inprocess_client_is_a_shared_singleton(monkeypatch):
    built = []

    class _FakeClient:
        def __init__(self, **kwargs):
            built.append(self)

    import chisurf.plugins.core.mmfdb_admin.gui.client as client_mod

    monkeypatch.setattr(client_mod, "MMFDBClient", _FakeClient)

    a = picker.inprocess_client()
    b = picker.inprocess_client()
    assert a is b            # one global session, reused
    assert len(built) == 1   # built exactly once


def test_construction_failure_is_remembered(monkeypatch):
    calls = []

    def _boom():
        calls.append(1)
        raise RuntimeError("no mmfdb")

    import chisurf.plugins.core.mmfdb_admin.gui.client as client_mod

    monkeypatch.setattr(client_mod, "MMFDBClient", lambda *a, **k: _boom())

    assert picker.inprocess_client() is None
    assert picker.inprocess_client() is None
    assert len(calls) == 1   # the expensive attempt is not retried each click


def test_reset_forces_rebuild(monkeypatch):
    built = []

    class _FakeClient:
        def __init__(self, **kwargs):
            built.append(self)

    import chisurf.plugins.core.mmfdb_admin.gui.client as client_mod

    monkeypatch.setattr(client_mod, "MMFDBClient", _FakeClient)

    first = picker.inprocess_client()
    picker.reset_session_client()
    second = picker.inprocess_client()
    assert first is not second
    assert len(built) == 2


def test_shared_client_adopts_chisurf_login_session(monkeypatch):
    # The session is owned by the ChiSurf login flow; the picker must REUSE the
    # token it cached, never log in itself.
    from chisurf.plugins.core.mmfdb_admin.gui import session

    class _FakeClient:
        mode = "embedded"
        host = "127.0.0.1"
        cmd_port = 8765
        pub_port = 8766

        def __init__(self, **kwargs):
            self.token = None

        def login(self, *a, **k):  # must never be called
            raise AssertionError("picker must not log in; session is app-managed")

    import chisurf.plugins.core.mmfdb_admin.gui.client as client_mod

    monkeypatch.setattr(client_mod, "MMFDBClient", _FakeClient)

    session.clear_cached_session()
    try:
        # Not logged in -> client left unauthenticated, no login attempt.
        assert picker.inprocess_client().token is None

        # ChiSurf login caches a session token; a fresh shared client adopts it.
        session.cache_session("admin", "APP-LOGIN-TOKEN")
        picker.reset_session_client()
        assert picker.inprocess_client().token == "APP-LOGIN-TOKEN"
    finally:
        session.clear_cached_session()


def test_resolve_local_path_prefers_selection_then_opens():
    class _Sel:
        local_path = "/data/already.ptu"
        artifact_id = "a1"

    # local_path present -> no service call
    assert picker.resolve_local_path(None, _Sel()) == "/data/already.ptu"

    class _SelNoPath:
        local_path = None
        artifact_id = "a1"

    class _Client:
        def call(self, method, params):
            assert method == "mmfdb.datasets.open"
            assert params == {"artifact_id": "a1"}
            return {"local_path": "/cache/from_s3.ptu"}

    assert picker.resolve_local_path(_Client(), _SelNoPath()) == "/cache/from_s3.ptu"
