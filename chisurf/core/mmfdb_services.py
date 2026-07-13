"""ChiSurf-owned service bindings for the standalone MMFDB package."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

DEFAULT_DESKTOP_ADMIN_USER = "admin"
DEFAULT_DESKTOP_ADMIN_PASSWORD = "admin"


def ensure_default_desktop_admin(database_location: str | Path | None = None) -> bool:
    """Create ChiSurf's default administrator for an unclaimed local database.

    Standalone and server-hosted MMFDB deployments remain locked by default.
    ChiSurf's embedded desktop server, however, must have a login-capable local
    account. The account is created only for SQLite and only while no active
    administrator exists; established databases are never modified.

    Returns ``True`` only when the account was newly created. An existing
    identity is never promoted or assigned a new password by this bootstrap.
    """
    from mmfdb.config import AdminBootstrapConfig
    from mmfdb.repository import MFDatabase
    from mmfdb.security.bootstrap import ensure_configured_admin
    from mmfdb.store.database_resolver import resolve_database_path
    from mmfdb.store.sql_backend import parse_database_target

    location = database_location if database_location is not None else resolve_database_path()
    target = parse_database_target(location)
    if not target.is_sqlite:
        return False

    config = AdminBootstrapConfig(
        user=DEFAULT_DESKTOP_ADMIN_USER,
        password=DEFAULT_DESKTOP_ADMIN_PASSWORD,
        allow_weak_bootstrap=True,
    )
    with MFDatabase(target.location) as db:
        return ensure_configured_admin(db.conn, config).created


def prepare_embedded_mmfdb(
    mmfdb_settings: Mapping[str, Any] | None = None,
) -> bool:
    """Apply ChiSurf's embedded deployment config and claim its first admin.

    This is the shared initialization path for GUI, headless, and in-process
    ChiSurf use. Standalone/remote configurations are deliberately rejected so
    a desktop client can never mutate a server database while connecting.
    """
    from mmfdb.config import (
        AdminBootstrapConfig,
        apply_deployment_config,
        load_deployment_config,
    )
    from mmfdb.repository import MFDatabase
    from mmfdb.security.bootstrap import ensure_configured_admin
    from mmfdb.store.database_resolver import resolve_database_path
    from mmfdb.store.sql_backend import parse_database_target

    settings = dict(mmfdb_settings or {})
    config_file = settings.get("config_file")
    if config_file:
        deployment = load_deployment_config(str(config_file))
        if deployment.mode != "embedded" or deployment.client.mode != "embedded":
            raise ValueError(
                "ChiSurf embedded initialization requires mode: embedded and "
                "client.mode: embedded"
            )
        apply_deployment_config(deployment)
        admin = deployment.admin
        if admin.user is None:
            admin = AdminBootstrapConfig(
                user=DEFAULT_DESKTOP_ADMIN_USER,
                password=DEFAULT_DESKTOP_ADMIN_PASSWORD,
                allow_weak_bootstrap=True,
            )
    else:
        admin = AdminBootstrapConfig(
            user=DEFAULT_DESKTOP_ADMIN_USER,
            password=DEFAULT_DESKTOP_ADMIN_PASSWORD,
            allow_weak_bootstrap=True,
        )

    target = parse_database_target(resolve_database_path())
    if not target.is_sqlite:
        return False
    with MFDatabase(target.location) as db:
        return ensure_configured_admin(db.conn, admin).created


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
