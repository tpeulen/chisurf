from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from chisurf.core.plugin.client import InProcessClient
from chisurf.plugins.core.mmfdb_admin.gui.client import MMFDBClient


class ProjectBrowserClient(MMFDBClient):
    """Client for project_browser RPC handlers."""

    def __init__(self, mmfdb_client: MMFDBClient | None = None, **kwargs: Any):
        if mmfdb_client is not None:
            self._client = mmfdb_client._client
            self._token = mmfdb_client.token
            self.mode = mmfdb_client.mode
            for field in ("base_url", "host", "cmd_port", "pub_port", "inprocess"):
                if hasattr(mmfdb_client, field):
                    setattr(self, field, getattr(mmfdb_client, field))
        else:
            super().__init__(**kwargs)

    def _make_inprocess_client(self) -> InProcessClient:
        from chisurf.core.mmfdb_services import register_services as register_mmfdb_services
        from chisurf.plugins.core.project_browser.backend.services import (
            register_services as register_project_browser_services,
        )
        from chisurf.server.dispatcher import ServiceDispatcher
        from chisurf.server.session import SessionState

        dispatcher = ServiceDispatcher(SessionState())
        register_mmfdb_services(dispatcher)
        register_project_browser_services(dispatcher)
        return InProcessClient(dispatcher)

    def list_projects(
        self,
        show_public: bool = True,
        search: str | None = None,
    ) -> list[dict[str, Any]]:
        return self._call(
            "project_browser.list",
            {
                "show_public": show_public,
                "search": search,
            },
        ).get("projects", [])

    def save_project(
        self,
        project_name: str,
        project_payload: dict[str, Any] | None = None,
        project_id: str | None = None,
        parent_version_id: str | None = None,
        notes: str | None = None,
        visibility: str = "private",
        fit_count: int = 0,
        dataset_count: int = 0,
    ) -> dict[str, Any]:
        return self._call(
            "project_browser.save",
            {
                "project_name": project_name,
                "project_payload": project_payload,
                "resource_bundle": project_resources(project_payload),
                "project_id": project_id,
                "parent_version_id": parent_version_id,
                "notes": notes,
                "visibility": visibility,
                "fit_count": fit_count,
                "dataset_count": dataset_count,
            },
        )

    def restore_project(self, version_id: str) -> dict[str, Any]:
        return self._call(
            "project_browser.restore",
            {
                "version_id": version_id,
            },
        )

    def export_csp(self, version_id: str, target_path: str | None = None) -> dict[str, Any]:
        """Fetch exact PTO content and optionally write the client-owned file."""
        result = self._call("project_browser.export_csp", {"version_id": version_id})
        if result.get("version_id") != version_id:
            raise ValueError("Export returned a different version identity")
        if result.get("ok") is not True or not result.get("project_id"):
            raise ValueError("Export returned no authenticated project identity")
        if target_path is not None:
            from chisurf.core.project.pto import publish_project_bytes

            publish_project_bytes(
                target_path, base64.b64decode(result["archive_bytes"], validate=True)
            )
        return result

    def import_preview(
        self, archive_base64: str | None = None, file_path: str | None = None
    ) -> dict[str, Any]:
        """Read chooser files locally and send only archive content."""
        if file_path is not None:
            archive_base64 = base64.b64encode(Path(file_path).read_bytes()).decode("ascii")
        return self._call("project_browser.import_preview", self._archive_content(archive_base64))

    def import_csp(
        self,
        archive_base64: str | None = None,
        file_path: str | None = None,
        resolve_collisions: bool = False,
    ) -> dict[str, Any]:
        """Import typed PTO bytes without sending a client filesystem path."""
        if file_path is not None:
            archive_base64 = base64.b64encode(Path(file_path).read_bytes()).decode("ascii")
        return self._call(
            "project_browser.import_csp",
            {
                **self._archive_content(archive_base64),
                "resolve_collisions": resolve_collisions,
            },
        )

    def _archive_content(self, encoded: str | None) -> dict[str, Any]:
        """Use authenticated blob transport for HTTP archives beyond RPC body limits."""
        if encoded and hasattr(self._client, "upload_object"):
            obj = self.put_object_bytes(
                encoded, "project.cs.pto", mime_type="application/octet-stream"
            )
            return {"archive_object_uuid": obj["object"]["object_uuid"]}
        return {"archive_base64": encoded}

    def delete_version(self, version_id: str) -> dict[str, Any]:
        return self._call(
            "project_browser.delete_version",
            {
                "version_id": version_id,
            },
        )

    def create_branch(
        self,
        project_id: str,
        from_version_id: str,
        branch_name: str,
    ) -> dict[str, Any]:
        return self._call(
            "project_browser.create_branch",
            {
                "project_id": project_id,
                "from_version_id": from_version_id,
                "branch_name": branch_name,
            },
        )

    def list_branches(self, project_id: str) -> list[dict[str, Any]]:
        return self._call(
            "project_browser.list_branches",
            {
                "project_id": project_id,
            },
        ).get("branches", [])

    def version_graph(self, project_id: str) -> dict[str, Any]:
        return self._call(
            "project_browser.version_graph",
            {
                "project_id": project_id,
            },
        ).get("graph", {})

    def list_artifacts(self, version_id: str) -> list[dict[str, Any]]:
        return self._call(
            "project_browser.artifacts",
            {
                "version_id": version_id,
            },
        ).get("artifacts", [])

    def list_parameters(self, version_id: str) -> list[dict[str, Any]]:
        return self._call(
            "project_browser.parameters",
            {
                "version_id": version_id,
            },
        ).get("parameters", [])


def project_resources(payload: Any) -> dict[str, str]:
    """Bundle actual referenced files on the client; labels never authorize server I/O."""
    resources = {}

    def visit(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if (
                    key in {"filename", "file_path", "source_file"}
                    and isinstance(item, str)
                    and item
                ):
                    path = Path(item)
                    if path.is_file():
                        resources[item] = base64.b64encode(path.read_bytes()).decode("ascii")
                elif isinstance(item, (dict, list)):
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(payload)
    return resources
