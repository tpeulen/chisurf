"""The acting identity must be an account somebody can actually log in as.

MMFDB stamps every in-process write with ``mmfdb.default_user_id`` and
auto-creates that user as a plain, passwordless row. Two things have to hold for
that not to end in a workspace nobody can enter:

* the name must be one MMFDB is allowed to claim — the service identity or the
  configured acting identity — or the one-shot administrator bootstrap refuses
  it and every embedded ``MMFDBClient`` raises
  ``Bootstrap administrator 'admin' already exists`` from then on;
* ChiSurf must seed a credential for it, or the stub the first write leaves
  behind stays passwordless and the login screen has nothing to accept.

The desktop therefore ships `user`/`user` for everyday work, with `admin`/`admin`
kept for administration.
"""

from __future__ import annotations

import pathlib

import yaml

SETTINGS = (
    pathlib.Path(__file__).resolve().parents[2]
    / "chisurf"
    / "core"
    / "settings"
    / "settings_chisurf.yaml"
)


def _shipped() -> dict:
    return yaml.safe_load(SETTINGS.read_text(encoding="utf-8"))


def test_the_shipped_acting_identity_is_a_seeded_desktop_account():
    """Its auto-created stub must be completed with a password, not left blank."""
    from chisurf.core.mmfdb_services import desktop_user_configs

    acting = str(_shipped()["mmfdb"]["default_user_id"])
    seeded = {account.user_id: account for account in desktop_user_configs()}

    assert acting in seeded, (
        f"the acting identity {acting!r} is not seeded by the desktop bootstrap; "
        "the first write leaves a passwordless row nobody can sign in as"
    )
    assert seeded[acting].password, "a seeded acting identity needs a password"


def test_the_shipped_acting_identity_is_not_the_administrator():
    """Everyday writes are attributed to an unprivileged account."""
    from chisurf.core.mmfdb_services import DEFAULT_DESKTOP_ADMIN_USER

    assert str(_shipped()["mmfdb"]["default_user_id"]) != DEFAULT_DESKTOP_ADMIN_USER


def test_the_shipped_acting_identity_is_one_mmfdb_may_claim():
    """Otherwise its stub blocks the administrator bootstrap permanently."""
    from mmfdb.config import configure_runtime, reset_runtime_config
    from mmfdb.security.bootstrap import _promotable_identities

    acting = str(_shipped()["mmfdb"]["default_user_id"])
    try:
        configure_runtime(default_user_id=acting)
        assert acting in _promotable_identities()
    finally:
        reset_runtime_config()
