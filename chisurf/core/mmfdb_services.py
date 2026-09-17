"""ChiSurf-owned service bindings for the standalone MMFDB package."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

DEFAULT_DESKTOP_ADMIN_USER = "admin"
DEFAULT_DESKTOP_ADMIN_PASSWORD = "admin"
DEFAULT_DESKTOP_USER = "user"
DEFAULT_DESKTOP_USER_PASSWORD = "user"

#: The desktop accounts autologin may sign in with, in offer order. Everyday
#: work belongs to the unprivileged account; the administrator is offered too so
#: a workspace opened as ``admin`` keeps signing in without a prompt.
DESKTOP_CREDENTIALS = {
    DEFAULT_DESKTOP_USER: DEFAULT_DESKTOP_USER_PASSWORD,
    DEFAULT_DESKTOP_ADMIN_USER: DEFAULT_DESKTOP_ADMIN_PASSWORD,
}


def desktop_user_configs():
    """Return ChiSurf's ordinary (non-administrative) desktop accounts.

    Returns
    -------
    tuple of mmfdb.config.LocalAccountConfig
        The ``user``/``user`` working account, a member of the ``users`` group.
    """
    from mmfdb.config import LocalAccountConfig

    return (
        LocalAccountConfig(
            user_id=DEFAULT_DESKTOP_USER,
            password=DEFAULT_DESKTOP_USER_PASSWORD,
            display_name="Local user",
        ),
    )


def desktop_admin_config():
    """Return ChiSurf's default local administrator credentials.

    Returns
    -------
    mmfdb.config.AdminBootstrapConfig
        The ``admin``/``admin`` desktop account, exempt from the password
        strength rules that apply to server deployments.
    """
    from mmfdb.config import AdminBootstrapConfig

    return AdminBootstrapConfig(
        user=DEFAULT_DESKTOP_ADMIN_USER,
        password=DEFAULT_DESKTOP_ADMIN_PASSWORD,
        allow_weak_bootstrap=True,
    )


def register_admin_bootstrap(config=None) -> None:
    """Keep the desktop accounts available to every re-bootstrap.

    Creating them once is not enough: a database reset replaces the user
    database with the shipped seed, which carries no accounts at all, and left
    the workspace with nothing to log in as. Registering the credentials lets
    MMFDB restore them whenever it finds a database without them.

    Parameters
    ----------
    config : mmfdb.config.AdminBootstrapConfig, optional
        Administrator credentials to register. Defaults to
        :func:`desktop_admin_config`.
    """
    from mmfdb.config import set_admin_bootstrap_resolver, set_default_accounts_resolver

    resolved = config if config is not None else desktop_admin_config()
    accounts = desktop_user_configs()
    set_admin_bootstrap_resolver(lambda: resolved)
    set_default_accounts_resolver(lambda: accounts)


def _ensure_desktop_accounts(conn, admin) -> bool:
    """Claim the administrator and seed the ordinary desktop accounts.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open connection to the desktop database.
    admin : mmfdb.config.AdminBootstrapConfig
        Administrator credentials for the one-shot bootstrap.

    Returns
    -------
    bool
        Whether the administrator was newly created.
    """
    from mmfdb.security.bootstrap import ensure_configured_admin, ensure_local_account

    created = ensure_configured_admin(conn, admin).created
    seeded = False
    for account in desktop_user_configs():
        seeded |= ensure_local_account(conn, account)
    if seeded:
        conn.commit()
    return created


def ensure_default_desktop_admin(database_location: str | Path | None = None) -> bool:
    """Create ChiSurf's default accounts for an unclaimed local database.

    Standalone and server-hosted MMFDB deployments remain locked by default.
    ChiSurf's embedded desktop server, however, must have login-capable local
    accounts: an ``admin`` administrator and an unprivileged ``user`` for
    everyday work. They are created only for SQLite, the administrator only
    while no active administrator exists; established identities are never
    modified.

    Returns ``True`` only when the administrator was newly created. An existing
    identity is never promoted or assigned a new password by this bootstrap.
    """
    from mmfdb.repository import MFDatabase
    from mmfdb.store.database_resolver import resolve_database_path
    from mmfdb.store.sql_backend import parse_database_target

    location = database_location if database_location is not None else resolve_database_path()
    target = parse_database_target(location)
    if not target.is_sqlite:
        return False

    config = desktop_admin_config()
    register_admin_bootstrap(config)
    with MFDatabase(target.location) as db:
        return _ensure_desktop_accounts(db.conn, config)


def prepare_embedded_mmfdb(
    mmfdb_settings: Mapping[str, Any] | None = None,
) -> bool:
    """Apply ChiSurf's embedded deployment config and claim its desktop accounts.

    This is the shared initialization path for GUI, headless, and in-process
    ChiSurf use. Standalone/remote configurations are deliberately rejected so
    a desktop client can never mutate a server database while connecting.
    """
    from mmfdb.config import apply_deployment_config, load_deployment_config
    from mmfdb.repository import MFDatabase
    from mmfdb.store.database_resolver import resolve_database_path
    from mmfdb.store.sql_backend import parse_database_target

    settings = dict(mmfdb_settings or {})
    config_file = settings.get("config_file")
    admin = desktop_admin_config()
    if config_file:
        deployment = load_deployment_config(str(config_file))
        if deployment.mode != "embedded" or deployment.client.mode != "embedded":
            raise ValueError(
                "ChiSurf embedded initialization requires mode: embedded and client.mode: embedded"
            )
        apply_deployment_config(deployment)
        if deployment.admin.user is not None:
            admin = deployment.admin

    # After apply_deployment_config, which resets process-local resolvers.
    register_admin_bootstrap(admin)
    target = parse_database_target(resolve_database_path())
    if not target.is_sqlite:
        return False
    with MFDatabase(target.location) as db:
        return _ensure_desktop_accounts(db.conn, admin)


def register_services(dispatcher_or_context):
    """Register MMFDB plus the ChiSurf-owned execution and browsing services."""
    from mmfdb.admin.backend.services import register_services as register_mmfdb_services

    from chisurf.core.fluorescence.curation.ai_triage import run_deterministic_checks
    from chisurf.core.pipeline import get_pipeline, list_pipeline_runs, list_pipelines
    from chisurf.plugins.burst.burst_selection.backend.services import analyze_files_handler

    register_mmfdb_services(
        dispatcher_or_context,
        burst_selection_runner=analyze_files_handler,
        deterministic_checks=run_deterministic_checks,
        pipeline_list=list_pipelines,
        pipeline_get=get_pipeline,
        pipeline_runs=list_pipeline_runs,
    )
