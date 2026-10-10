"""A demo account list, so the guided tour can be walked without an MMFDB server.

The tour asks you to select an account and edit it; with no server there is
nothing to select. :func:`make_demo` installs an in-memory administrator client
holding a few invented accounts. It never touches the real MMFDB: the demo
accounts live in this process only and vanish with it.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from chisurf.plugins.core.user_editor.api import client as client_seam

#: Invented accounts shown by the demo (none is a real person).
DEMO_ACCOUNTS: tuple[dict[str, Any], ...] = (
    {
        "user_uuid": "demo-0001",
        "user_id": "alice",
        "display_name": "Alice Archer",
        "email": "alice@example.org",
        "role": "Principal Investigator",
        "affiliation": "Institute of Biophysics",
        "department": "Single-molecule group",
        "is_admin": 1,
    },
    {
        "user_uuid": "demo-0002",
        "user_id": "bob",
        "display_name": "Bob Baker",
        "email": "bob@example.org",
        "role": "Postdoc",
        "department": "FCS",
    },
    {
        "user_uuid": "demo-0003",
        "user_id": "carol",
        "display_name": "Carol Chen",
        "role": "PhD Student",
        "department": "smFRET",
        "allow_passwordless_login": 1,
    },
)


class DemoUserClient:
    """In-memory stand-in for the MMFDB client's user calls (administrator)."""

    def __init__(self) -> None:
        self._users = {a["user_id"]: copy.deepcopy(a) for a in DEMO_ACCOUNTS}

    def list_users(self) -> list[dict[str, Any]]:
        """All demo accounts."""
        return [copy.deepcopy(u) for u in self._users.values()]

    def save_user(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create, update or rename an account, as ``mmfdb.users.save`` does."""
        record = {k: v for k, v in payload.items() if k not in ("old_user_id", "requester_id")}
        old = payload.get("old_user_id")
        if old and old != record["user_id"]:
            record = {**self._users.pop(old, {}), **record}
        elif record["user_id"] in self._users:
            record = {**self._users[record["user_id"]], **record}
        record.setdefault("user_uuid", f"demo-{len(self._users) + 1:04d}")
        self._users[record["user_id"]] = record
        return {"user_id": record["user_id"]}

    def delete_user(self, user_id: str, **_: Any) -> dict[str, Any]:
        """Remove an account."""
        self._users.pop(user_id, None)
        return {"deleted": user_id}


def make_demo(folder: str | Path | None = None) -> Path | None:
    """Install the demo client; ``make_mmfdb_client`` returns it from now on.

    Parameters
    ----------
    folder : str or Path, optional
        Unused (the demo needs no files); returned unchanged so callers that
        expect a demo folder keep working.

    Returns
    -------
    Path or None
        *folder* as a path, or None when not given.
    """
    demo = DemoUserClient()
    client_seam.use_demo_client(lambda: demo)
    return Path(folder) if folder is not None else None
