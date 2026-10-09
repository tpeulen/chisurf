"""A temporary MMFDB with known users, reached through the real RPC services.

The user editor lists and saves accounts through the MMFDB client; this module
gives tests (and the evidence scripts) a client that talks to the in-process
MMFDB services over a **temporary** SQLite file, never the user's own database.
The caller points ``CHISURF_SETTINGS_DIR``, ``MMFDB_SETTINGS_DIR`` and
``MMFDB_DATABASE_PATH`` at a temporary folder first (see :func:`use_folder`).
"""

from __future__ import annotations

import os
from pathlib import Path

#: The embedded desktop bootstrap creates ``admin`` (password ``admin``) and
#: ``user`` (password ``user``); both are public defaults of the desktop build.
ADMIN = ("admin", "admin")
PLAIN_USER = ("user", "user")

#: Accounts seeded on top of the bootstrap ones: ``(user_id, fields)``.
SEED = (
    (
        "alice",
        dict(
            display_name="Alice Archer",
            email="alice@example.org",
            role="Principal Investigator",
            affiliation="Institute of Biophysics",
            department="Single-molecule group",
            phone="+49 211 000 111",
            website="https://example.org/alice",
            address="Main Street 1, Duesseldorf",
            details="Runs the confocal setup.",
            is_admin=1,
        ),
    ),
    (
        "bob",
        dict(
            display_name="Bob Baker",
            email="bob@example.org",
            role="Postdoc",
            affiliation="Institute of Biophysics",
            department="FCS",
        ),
    ),
    (
        "carol",
        dict(
            display_name="Carol Chen",
            email="carol@example.org",
            role="PhD Student",
            department="smFRET",
            allow_passwordless_login=1,
        ),
    ),
    ("dave", dict(display_name="Dave Dunn", role="Facility Manager")),
    ("erin", dict(display_name="Erin Evans", email="erin@example.org", role="Technician")),
)


def use_folder(folder: Path, monkeypatch=None) -> Path:
    """Point settings and the MMFDB at *folder* (a temporary directory)."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    env = {
        "CHISURF_SETTINGS_DIR": str(folder),
        "MMFDB_SETTINGS_DIR": str(folder),
        "MMFDB_DATABASE_PATH": str(folder / "mmfdb.db"),
    }
    for key, value in env.items():
        if monkeypatch is not None:
            monkeypatch.setenv(key, value)
        else:
            os.environ[key] = value
    return folder


def admin_client(login: tuple[str, str] = ADMIN):
    """An in-process MMFDB client logged in as *login* (admin by default)."""
    from chisurf.plugins.core.mmfdb_admin.gui.client import MMFDBClient

    client = MMFDBClient(inprocess=True)
    client.login(*login, quiet=True)
    return client


def seed(client=None) -> list[str]:
    """Create :data:`SEED` through the RPC API; returns the seeded user ids."""
    client = client or admin_client()
    for user_id, fields in SEED:
        payload = {
            "user_id": user_id,
            "requester_id": "admin",
            "is_admin": 0,
            "allow_passwordless_login": 0,
            "role": "Generic",
        }
        payload.update(fields)
        client.save_user(payload)
    return [user_id for user_id, _ in SEED]
