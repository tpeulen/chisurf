"""ChiSurf's local desktop authentication bootstrap."""

from __future__ import annotations

from pathlib import Path

from mmfdb.repository import MFDatabase
from mmfdb.security.bootstrap import bootstrap_local_admin
from mmfdb.security.login import login

from chisurf.core.mmfdb_services import (
    ensure_default_desktop_admin,
    prepare_embedded_mmfdb,
)


def test_local_desktop_database_gets_default_admin(tmp_path: Path) -> None:
    database = tmp_path / "desktop.db"

    assert ensure_default_desktop_admin(database) is True
    assert ensure_default_desktop_admin(database) is False

    with MFDatabase(database) as db:
        row = db.conn.execute(
            "SELECT is_admin, allow_passwordless_login FROM flr_sample_users "
            "WHERE user_id = 'admin'"
        ).fetchone()
        authenticated = login(db.conn, user_id="admin", password="admin")

    assert tuple(row) == (1, 0)
    assert authenticated["authenticated"] is True
    assert authenticated["user"]["is_admin"] is True


def test_local_desktop_bootstrap_preserves_an_existing_admin(tmp_path: Path) -> None:
    database = tmp_path / "managed.db"
    with MFDatabase(database) as db:
        bootstrap_local_admin(
            db.conn,
            user_id="site-admin",
            password="Site-pass1!",
        )

    assert ensure_default_desktop_admin(database) is False

    with MFDatabase(database) as db:
        users = {
            row[0]
            for row in db.conn.execute(
                "SELECT user_id FROM flr_sample_users WHERE deleted_at IS NULL"
            )
        }

    assert "site-admin" in users
    assert "admin" not in users


def test_local_desktop_bootstrap_refuses_to_take_over_existing_identity(
    tmp_path: Path,
) -> None:
    database = tmp_path / "claimed.db"
    with MFDatabase(database) as db, db.conn:
        db.add_user("admin", "Existing non-admin user")

    import pytest

    with pytest.raises(ValueError, match="already exists"):
        ensure_default_desktop_admin(database)

    with MFDatabase(database) as db:
        row = db.conn.execute(
            "SELECT is_admin, password_hash FROM flr_sample_users "
            "WHERE user_id = 'admin'"
        ).fetchone()

    assert tuple(row) == (0, None)


def test_desktop_bootstrap_does_not_touch_server_databases() -> None:
    assert ensure_default_desktop_admin("postgresql://db.example/mmfdb") is False


def test_embedded_yaml_controls_storage_and_admin_bootstrap(tmp_path: Path) -> None:
    from mmfdb.config import configured_object_store_root, reset_runtime_config
    from mmfdb.store.database_resolver import resolve_database_path

    config_path = tmp_path / "embedded.yaml"
    database = tmp_path / "state" / "embedded.db"
    objects = tmp_path / "state" / "objects"
    config_path.write_text(
        "\n".join(
            (
                "version: 1",
                "mode: embedded",
                "database:",
                "  path: state/embedded.db",
                "object_store:",
                "  backend: local",
                "  root: state/objects",
                "admin:",
                "  user: admin",
                "  password: admin",
                "  allow_weak_bootstrap: true",
                "client:",
                "  mode: embedded",
            )
        ),
        encoding="utf-8",
    )

    try:
        assert prepare_embedded_mmfdb({"config_file": str(config_path)}) is True
        assert Path(resolve_database_path()) == database.resolve()
        with MFDatabase(database) as db:
            authenticated = login(db.conn, user_id="admin", password="admin")
        assert authenticated["authenticated"] is True
        assert configured_object_store_root() == objects.resolve()
    finally:
        reset_runtime_config()


def test_headless_server_prepares_embedded_but_not_remote_mmfdb(monkeypatch) -> None:
    import chisurf.core.mmfdb_services as host_services
    from chisurf.core.settings import cs_settings
    from chisurf.server.app import ChiSurfServer

    prepared = []
    monkeypatch.setattr(
        host_services,
        "prepare_embedded_mmfdb",
        lambda settings: prepared.append(dict(settings)),
    )
    monkeypatch.setitem(cs_settings, "mmfdb", {"client": {"mode": "embedded"}})
    ChiSurfServer._prepare_embedded_mmfdb()
    assert prepared == [{"client": {"mode": "embedded"}}]

    prepared.clear()
    monkeypatch.setitem(cs_settings, "mmfdb", {"client": {"mode": "remote"}})
    ChiSurfServer._prepare_embedded_mmfdb()
    assert prepared == []
