"""Server service registration for Burst Selection."""

from __future__ import annotations

from typing import Any

from ..backend.services import list_methods as _list_methods
from ..backend.services import register_services as _register_services


def register_burst_selection_services(
    dispatcher: Any,
    *,
    mmfdb_db: Any = None,
    mmfdb_db_provider: Any = None,
    mmfdb_session: Any = None,
    mmfdb_session_provider: Any = None,
) -> None:
    """Register Burst Selection RPC handlers."""
    _register_services(
        dispatcher,
        mmfdb_db=mmfdb_db,
        mmfdb_db_provider=mmfdb_db_provider,
        mmfdb_session=mmfdb_session,
        mmfdb_session_provider=mmfdb_session_provider,
    )


def list_methods() -> dict[str, str]:
    """Return the Burst Selection RPC method catalogue."""
    return _list_methods()
