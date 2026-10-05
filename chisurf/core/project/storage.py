"""Storage policy and transports for ChiSurf projects.

The portable PTO and MMFDB paths deliberately share :meth:`Project.to_dict`
as their only scientific-state codec.  MMFDB is imported only after policy has
selected a real configured deployment; file saves therefore remain usable in
installations where the optional package is absent.
"""

from __future__ import annotations

import importlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .project import Project
from .pto import PROJECT_SUFFIX, _validate_project_payload, write_project


class ProjectStorageError(RuntimeError):
    """A project storage operation failed without changing live session state."""


def _settings(settings: Mapping[str, Any] | None) -> dict[str, Any]:
    if settings is not None:
        return dict(settings)
    try:
        from chisurf.core.settings import cs_settings
    except (ImportError, AttributeError):
        return {}
    return dict(cs_settings.get("mmfdb", {}) or {})


def select_backend(mmfdb_settings: Mapping[str, Any] | None = None) -> str:
    """Choose portable file storage or a configured real MMFDB deployment.

    The shipped embedded SQLite/bootstrap configuration is intentionally not a
    project persistence backend.  Only the documented resolved remote client
    configuration selects MMFDB; arbitrary database/deployment keys and port
    changes do not silently change the storage backend.
    """
    settings = _settings(mmfdb_settings)
    client = settings.get("client") or {}
    if not isinstance(client, Mapping):
        raise ProjectStorageError("mmfdb.client must be a mapping")
    # The portable default is self-contained: even backend discovery must not
    # import MMFDB or a GUI database client in a file-only installation.
    if not settings.get("config_file"):
        mode = str(client.get("mode", "embedded")).lower()
        if mode == "embedded":
            return "file"
        if mode != "remote":
            raise ProjectStorageError("mmfdb.client.mode must be 'embedded' or 'remote'")
    try:
        module = importlib.import_module("chisurf.plugins.core.mmfdb_admin.gui.client")
        resolved = module.client_config(settings)
    except Exception as exc:
        if settings.get("config_file") or str(client.get("mode", "")).lower() == "remote":
            raise ProjectStorageError(f"Invalid configured MMFDB client: {exc}") from exc
        resolved = {"mode": str(client.get("mode", "embedded")).lower()}
    mode = str(resolved.get("mode", "embedded")).lower()
    if mode == "remote":
        return "mmfdb"
    if mode != "embedded":
        raise ProjectStorageError("mmfdb.client.mode must be 'embedded' or 'remote'")
    return "file"


def save_file(project: Project, path: str | Path) -> Path:
    """Atomically save and exactly read back a portable ``.cs.pto`` project."""
    target = _canonical_path(path)
    payload = project.to_dict()
    try:
        _validate_project_payload(payload)
        if not project.resources.entries and not project.resources.sources:
            return write_project(target, payload)
        return project.save(target)
    except Exception as exc:
        raise ProjectStorageError(f"Could not save project file {target}: {exc}") from exc


def _canonical_path(path: str | Path) -> Path:
    """Return a path with the exact lowercase ChiSurf project suffix."""
    target = Path(path)
    if str(target).lower().endswith(PROJECT_SUFFIX):
        if str(target).endswith(PROJECT_SUFFIX):
            return target
        return Path(str(target)[: -len(PROJECT_SUFFIX)] + PROJECT_SUFFIX)
    return Path(f"{target}{PROJECT_SUFFIX}")


def load_file(path: str | Path) -> Project:
    """Load one explicit PTO document without mutating process globals."""
    source = Path(path)
    try:
        return Project.load(source)
    except Exception as exc:
        raise ProjectStorageError(f"Could not load project file {source}: {exc}") from exc


def _real_client(settings: Mapping[str, Any]) -> Any:
    """Build an authenticated transport without ever creating a local seed DB."""
    try:
        module = importlib.import_module("chisurf.plugins.core.mmfdb_admin.gui.client")
        browser_module = importlib.import_module("chisurf.plugins.core.project_browser.gui.client")
        config = module.client_config(settings)
        base_client = module.MMFDBClient(
            mode=config["mode"],
            base_url=config["base_url"],
            host=config["host"],
            cmd_port=config["cmd_port"],
            pub_port=config["pub_port"],
            timeout_ms=config["timeout_ms"],
            allow_insecure_http=config["allow_insecure_http"],
            inprocess=False,
        )
        if not getattr(base_client, "token", None):
            _attach_runtime_token(base_client, module, config)
        if not getattr(base_client, "token", None):
            raise ProjectStorageError(
                "MMFDB is configured for project storage but no authenticated runtime token is available; log in first"
            )
        return browser_module.ProjectBrowserClient(mmfdb_client=base_client)
    except ProjectStorageError:
        raise
    except Exception as exc:
        raise ProjectStorageError(f"Could not configure real MMFDB transport: {exc}") from exc


def _attach_runtime_token(client: Any, module: Any, config: Mapping[str, Any]) -> None:
    try:
        credentials = importlib.import_module("mmfdb.security.credentials")
        endpoint = module.credential_endpoint(config)
        user = str(config.get("username", ""))
        key = f"{endpoint[0]}:{endpoint[1]}:{user}"
        token = credentials._RUNTIME_SESSION_TOKENS.get(key)
        if token:
            client.token = token
    except Exception:
        return


def _client_for(settings: Mapping[str, Any], client: Any | None) -> Any:
    return client if client is not None else _real_client(settings)


def save_database(
    project: Project,
    *,
    project_id: str | None = None,
    parent_version_id: str | None = None,
    notes: str = "",
    visibility: str = "private",
    mmfdb_settings: Mapping[str, Any] | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    """Save a complete project version and verify its exact-version readback."""
    settings = _settings(mmfdb_settings)
    if select_backend(settings) != "mmfdb":
        raise ProjectStorageError("MMFDB save requested without a configured real MMFDB deployment")
    from .pto import _validate_project_payload

    try:
        payload = _validate_project_payload(project.to_dict())
    except Exception as exc:
        raise ProjectStorageError(f"Invalid MMFDB project snapshot: {exc}") from exc
    transport = _client_for(settings, client)
    try:
        save_inputs = dict(
            project_name=project.name,
            project_payload=payload,
            project_id=project_id,
            parent_version_id=parent_version_id,
            notes=notes,
            visibility=visibility,
        )
        if project.resources.sources or project.resources.entries:
            # Owned bytes travel as the backend's declared resource_bundle.
            # Browser convenience collection must never substitute client paths.
            result = transport._call(
                "project_browser.save",
                {
                    **save_inputs,
                    "resource_bundle": project.resources.database_bundle(),
                },
            )
        else:
            result = transport.save_project(**save_inputs)
        if result.get("ok") is not True:
            raise ProjectStorageError("MMFDB save did not return ok=true")
        version_id = result.get("version_id")
        if not version_id:
            raise ProjectStorageError("MMFDB save returned no version_id")
        saved_project_id = result.get("project_id")
        if not saved_project_id or (project_id is not None and saved_project_id != project_id):
            raise ProjectStorageError("MMFDB save returned an unexpected project identity")
        restored = transport.restore_project(version_id)
        if restored.get("ok") is not True:
            raise ProjectStorageError(f"MMFDB version readback was not ok for {version_id}")
        if restored.get("version_id") != version_id:
            raise ProjectStorageError(f"MMFDB version id readback mismatch for {version_id}")
        if restored.get("project_id") != saved_project_id:
            raise ProjectStorageError(f"MMFDB project id readback mismatch for {version_id}")
        actual = restored.get("project_payload")
        if actual != payload:
            raise ProjectStorageError(f"MMFDB version readback mismatch for {version_id}")
        version_number = result.get("version_number")
        if type(version_number) is not int or version_number < 1:
            raise ProjectStorageError("MMFDB save returned an invalid version number")
        restored_number = restored.get("version_number")
        if type(restored_number) is not int or restored_number != version_number:
            raise ProjectStorageError(f"MMFDB version number readback mismatch for {version_id}")
    except ProjectStorageError:
        raise
    except Exception as exc:
        raise ProjectStorageError(f"MMFDB project save failed: {exc}") from exc
    return {
        "ok": True,
        "project_id": result.get("project_id", project_id),
        "version_id": version_id,
        "version_number": version_number,
        "project_name": result.get("project_name", project.name),
        "visibility": result.get("visibility", visibility),
    }


def load_database(
    version_id: str,
    *,
    mmfdb_settings: Mapping[str, Any] | None = None,
    client: Any | None = None,
) -> tuple[Project, dict[str, Any]]:
    """Restore exactly ``version_id`` without mutating live session state."""
    settings = _settings(mmfdb_settings)
    if select_backend(settings) != "mmfdb":
        raise ProjectStorageError("MMFDB load requested without a configured real MMFDB deployment")
    transport = _client_for(settings, client)
    try:
        result = transport.restore_project(version_id)
        if result.get("ok") is not True:
            raise ProjectStorageError(f"MMFDB version {version_id} readback was not ok")
        if result.get("version_id") != version_id:
            raise ProjectStorageError(
                f"MMFDB returned version {result.get('version_id')!r}, expected {version_id!r}"
            )
        payload = result.get("project_payload")
        if not isinstance(payload, dict):
            raise ProjectStorageError(f"MMFDB version {version_id} has no complete project_payload")
        project = Project.from_dict(payload)
        export = getattr(transport, "export_csp", None)
        if callable(export):
            import base64
            import tempfile

            exported = export(version_id)
            if exported.get("ok") is not True:
                raise ProjectStorageError("MMFDB resource export failed")
            content = base64.b64decode(exported["archive_bytes"], validate=True)
            with tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "resources.cs.pto"
                source.write_bytes(content)
                exported_project = load_file(source)
            if exported_project.to_dict() != payload:
                raise ProjectStorageError("MMFDB resource export science mismatch")
            project.resources = exported_project.resources
        return project, {
            "project_id": result.get("project_id"),
            "version_id": version_id,
            "project_name": result.get("project_name"),
            "visibility": result.get("visibility"),
        }
    except ProjectStorageError:
        raise
    except Exception as exc:
        raise ProjectStorageError(f"MMFDB project restore failed for {version_id}: {exc}") from exc


__all__ = [
    "ProjectStorageError",
    "select_backend",
    "save_file",
    "load_file",
    "save_database",
    "load_database",
]
