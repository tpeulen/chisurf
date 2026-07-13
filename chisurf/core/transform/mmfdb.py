"""Authenticated MMFDB registration boundary shared by ChiSurf transforms."""

from __future__ import annotations

from typing import Any


def require_authenticated_session(db: Any, session: Any) -> Any:
    """Validate and return a caller-supplied MMFDB session.

    Registration code must not manufacture identity from settings. For local
    repositories the session token is re-authenticated against the injected
    database and its principal must match ``session.user_id``.
    """
    from mmfdb.security.auth import (
        AuthError,
        principal_from_rpc_auth,
        require_authenticated,
    )

    if db is None or session is None:
        raise AuthError("Authenticated MMFDB session required")
    if getattr(session, "db", None) is not db:
        raise AuthError("MMFDB session belongs to a different database")
    conn = getattr(db, "conn", None)
    if conn is None:
        raise AuthError("MMFDB registration requires a locally verifiable session")
    principal = principal_from_rpc_auth(conn, getattr(session, "auth", None))
    require_authenticated(principal)
    if principal.user_id != getattr(session, "user_id", None):
        raise AuthError("MMFDB session identity mismatch")
    return session


def session_from_auth(db: Any, auth: dict[str, Any] | None) -> Any:
    """Build a verified :class:`SessionContext` at a composition root."""
    from mmfdb.security.auth import principal_from_rpc_auth, require_authenticated
    from mmfdb.security.session import SessionContext

    if db is None:
        raise ValueError("MMFDB database required")
    conn = getattr(db, "conn", None)
    if conn is None:
        raise ValueError("MMFDB database does not expose an authentication connection")
    principal = principal_from_rpc_auth(conn, auth)
    require_authenticated(principal)
    return SessionContext(
        user_id=str(principal.user_id),
        db=db,
        is_admin=bool(principal.is_admin),
        auth=dict(auth or {}),
    )


def runtime_session_for_database(db: Any) -> Any | None:
    """Resolve the current ChiSurf runtime credential against *db*.

    This is the GUI composition-root adapter: it uses the token produced by the
    application login flow, then re-authenticates it against the exact local
    repository instance. It never falls back to a configured user id alone.
    """
    try:
        from mmfdb.security.credentials import load_runtime_session_token

        import chisurf.core.settings as cs_settings

        config = cs_settings.cs_settings.get("mmfdb", {})
        host = str(config.get("last_server", "127.0.0.1"))
        port = int(config.get("last_port", 8765))
        user_id = str(config.get("default_user_id", ""))
        token = load_runtime_session_token(host, port, user_id) if user_id else None
        if not token:
            # The admin plugin maintains a compatible process cache for
            # in-process clients. Keep this import local so core remains Qt-free.
            from chisurf.plugins.core.mmfdb_admin.gui.session import cached_token

            token = cached_token(host, port, port + 1)
        if not token:
            return None
        return session_from_auth(db, {"token": token})
    except Exception:
        return None
