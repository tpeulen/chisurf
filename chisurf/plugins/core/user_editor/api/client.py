"""The MMFDB client seam, in one place.

``host``/``port``/``default_user_id`` plus a session-token lookup was written
out four times across the tree (here, the light-path simulator, the project
browser, the transform layer). This is that, once.
"""

from __future__ import annotations

from typing import Any

# Imported at module load, not inside the functions below. Importing
# ``chisurf.core.settings`` runs ``env_bootstrap``, which mutates Qt-related
# environment variables; doing that lazily meant it could happen *after* Qt was
# loaded but before a QApplication existed, which aborts the macOS platform
# plugin. Importing here pins it to a predictable moment.
from chisurf.core.settings import cs_settings


def mmfdb_settings() -> dict[str, Any]:
    """The ``mmfdb`` settings block."""
    block = cs_settings.get("mmfdb", {})
    return dict(block) if isinstance(block, dict) else {}


def active_user_id() -> str:
    """The user id ChiSurf uses for its own MMFDB connections."""
    return str(mmfdb_settings().get("default_user_id", "user_default"))


def server_address() -> tuple[str, int]:
    """The configured ``(host, command port)``."""
    block = mmfdb_settings()
    return str(block.get("last_server", "127.0.0.1")), int(block.get("last_port", 8765))


def make_mmfdb_client(user_id: str | None = None):
    """Build an authenticated MMFDB client.

    Raises
    ------
    RuntimeError
        When the ``mmfdb_admin`` plugin -- which owns the client class -- is not
        installed. The manifest declares that dependency, and this turns an
        ImportError deep in a callback into one sentence naming the cause.

    """
    host, port = server_address()
    user_id = user_id or active_user_id()

    try:
        from chisurf.plugins.core.mmfdb_admin.gui.client import MMFDBClient
    except ImportError as exc:  # pragma: no cover - depends on the install
        raise RuntimeError(
            "The MMFDB Admin plugin provides the database client and is not "
            "available, so users cannot be listed or edited."
        ) from exc

    client = MMFDBClient(host=host, cmd_port=port, pub_port=port + 1)

    try:
        from mmfdb.security.credentials import (
            load_runtime_session_token,
            load_session_token,
            store_runtime_session_token,
        )
    except ImportError:  # pragma: no cover
        return client

    token = load_runtime_session_token(host, port, user_id)
    if token is None:
        token = load_session_token(host, port, user_id)
    if token:
        client.token = token
        store_runtime_session_token(host, port, user_id, token)
    return client
