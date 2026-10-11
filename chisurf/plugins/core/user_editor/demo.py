"""A demo account list, so the guided tour can be walked without an MMFDB server.

The tour asks you to select an account and edit it; with no server there is nothing to select.
:class:`DemoUserClient` is an in-memory administrator client holding a few invented accounts, and the
editor's *Load example* hands it to that one editor window (``UserEditorModel.load_example``); it never
touches the real MMFDB, and edits to the demo accounts live in the window only. :func:`make_demo` keeps the
invented accounts as ``accounts.json`` in the settings cache so they can be read without starting a window.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

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


#: The demo, in one place so the guide and the tests agree.
DEMO: dict[str, Any] = dict(version=1, accounts=[dict(a) for a in DEMO_ACCOUNTS])

FILENAME = "accounts.json"


def demo_folder() -> Path:
    """Return the settings-owned demonstration folder for this plugin."""
    from chisurf.plugins.demo_cache import cache_folder

    return cache_folder("user_editor")


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


def make_demo(folder: str | Path | None = None, *, overwrite: bool = False) -> Path:
    """Write or reuse ``accounts.json``, the invented accounts the demo client serves.

    Parameters
    ----------
    folder : str or Path, optional
        Cache directory; defaults to :func:`demo_folder`.
    overwrite : bool, optional
        Write again even when the stamped parameters and checksum match.

    Returns
    -------
    Path
        The JSON file holding the accounts.
    """
    from chisurf.plugins.demo_cache import is_current, record

    folder = demo_folder() if folder is None else Path(folder)
    path = folder / FILENAME
    if not overwrite and path.is_file() and is_current(folder, [FILENAME], DEMO):
        return path
    folder.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(DEMO["accounts"], indent=2, sort_keys=True), encoding="utf-8")
    record(folder, [FILENAME], DEMO)
    return path
