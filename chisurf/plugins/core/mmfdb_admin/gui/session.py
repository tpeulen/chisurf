"""Helpers for reusing the current MMFDB user session / permissions.

The goal: don't force a login when the session already has permission. The
active user comes from settings; an administrator can act without
re-authenticating. These helpers answer "is the current session user an admin?"
for both a local MMFDB file and a running server, so callers can skip the login
prompt for authorized users.
"""

from __future__ import annotations

# Process-wide MMFDB session cache. The first successful login (e.g. in
# mmfdb-admin) stores its token here; every other surface in the same ChiSurf
# process (re-opening mmfdb-admin, the spectra scraper's "Add to MMFDB") reuses it
# so the user is not asked for a password again. Keyed loosely by endpoint.
_SESSION: dict = {
    "user": None, "token": None,
    "host": "127.0.0.1", "cmd_port": 8765, "pub_port": 8766,
}


def cache_session(user: str, token: str | None, host: str = "127.0.0.1",
                  cmd_port: int = 8765, pub_port: int = 8766) -> None:
    """Remember an authenticated MMFDB session for reuse across the process."""
    _SESSION.update(
        user=user, token=token, host=host,
        cmd_port=int(cmd_port), pub_port=int(pub_port),
    )


def cached_token(host: str = "127.0.0.1", cmd_port: int = 8765, pub_port: int = 8766) -> str | None:
    """Return a cached token for this endpoint, or ``None``."""
    if (_SESSION.get("token")
            and _SESSION.get("host") == host
            and int(_SESSION.get("cmd_port") or 0) == int(cmd_port)):
        return _SESSION["token"]
    return None


def cached_user() -> str | None:
    """Return the user of the cached session, if any."""
    return _SESSION.get("user")


def clear_cached_session() -> None:
    """Forget the cached session (on logout)."""
    _SESSION.update(user=None, token=None)


def active_user_id() -> str:
    """Return the active MMFDB user id from the canonical client settings."""
    try:
        import chisurf.core.settings as cs_settings
        from chisurf.plugins.core.mmfdb_admin.gui.client import client_config

        return client_config(cs_settings.cs_settings.get("mmfdb", {}))["username"]
    except Exception:
        return "admin"


def local_admin_status(db_path: str, user: str | None = None) -> tuple[bool, bool]:
    """Return ``(user_is_admin, any_admin_exists)`` for a local MMFDB file.

    During bootstrap (no admin user exists yet) ``user_is_admin`` is reported
    ``True`` so the first import can proceed, mirroring the server's bootstrap
    rule.
    """
    import os
    import sqlite3

    if not isinstance(db_path, (str, os.PathLike)):
        # sqlite3.connect() stringifies its argument, so a stray object here
        # would silently create a database named after its repr.
        raise TypeError(
            f"local_admin_status db_path must be a str or Path, got {type(db_path).__name__}"
        )
    user = user or active_user_id()
    try:
        conn = sqlite3.connect(db_path)
        has_users_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='flr_sample_users'"
        ).fetchone() is not None
        if not has_users_table:
            return True, False  # fresh DB (no user table yet) → bootstrap
        any_admin = conn.execute(
            "SELECT 1 FROM flr_sample_users WHERE is_admin = 1 AND deleted_at IS NULL LIMIT 1"
        ).fetchone() is not None
        if not any_admin:
            return True, False
        row = conn.execute(
            "SELECT is_admin FROM flr_sample_users WHERE user_id = ? AND deleted_at IS NULL",
            (user,),
        ).fetchone()
        return bool(row and row[0]), True
    except Exception:
        return False, False
    finally:
        try:
            conn.close()
        except Exception:
            pass


def client_is_admin(client, user: str | None = None) -> bool:
    """Return whether ``user`` is an administrator on a connected MMFDB client."""
    user = user or active_user_id()
    try:
        users = client.list_users()
    except Exception:
        return False
    if not any(u.get("is_admin") for u in users):
        return True  # bootstrap: no admin exists yet
    return any(u.get("user_id") == user and u.get("is_admin") for u in users)
