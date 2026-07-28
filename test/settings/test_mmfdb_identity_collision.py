"""The acting identity must not be named like the database's bootstrap admin.

MMFDB stamps every in-process write with ``mmfdb.default_user_id`` and
auto-creates that user as a plain row. Its one-shot bootstrap then *refuses* to
claim a name that already exists — deliberately, so a configured secret can
never take over an existing identity. Shipping the same name for both therefore
had a terminal end state: register anything, and the deployment could never
obtain an administrator, with every embedded ``MMFDBClient`` raising
``Bootstrap administrator 'admin' already exists`` from then on.
"""

from __future__ import annotations

import pathlib

import yaml

SETTINGS = (
    pathlib.Path(__file__).resolve().parents[2]
    / "chisurf" / "core" / "settings" / "settings_chisurf.yaml"
)


def _shipped() -> dict:
    return yaml.safe_load(SETTINGS.read_text(encoding="utf-8"))


def test_the_shipped_acting_identity_is_not_the_bootstrap_admin_name():
    """A fresh install must be able to bootstrap after it has written data."""
    from mmfdb.security.bootstrap import BOOTSTRAP_USER_ENV  # noqa: F401  (import guard)

    acting = str(_shipped()["mmfdb"]["default_user_id"])
    assert acting != "admin", (
        "the acting identity is named like the conventional bootstrap admin; "
        "the first write claims the name and the bootstrap can never run"
    )


def test_the_shipped_acting_identity_is_the_one_mmfdb_can_promote():
    """`user_default` is MMFDB's service identity, seeded and promotable."""
    from mmfdb.security.bootstrap import SERVICE_USER_ID
    from mmfdb.security.session import DEFAULT_USER_ID

    acting = str(_shipped()["mmfdb"]["default_user_id"])
    assert acting == DEFAULT_USER_ID == SERVICE_USER_ID
