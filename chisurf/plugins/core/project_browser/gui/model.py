"""Qt-free project browsing and the existing MMFDB version/archive contract."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def current_context():
    import chisurf

    return getattr(chisurf, "cs", None) or chisurf


def current_payload(name):
    from chisurf.macros.core_fit import get_project_payload

    payload = get_project_payload(name)
    return payload.to_dict() if hasattr(payload, "to_dict") else payload


def restore_payload(payload):
    from chisurf.emtk.project import load_project_payload

    return load_project_payload(payload, project_path=None)


def restore_fit_windows(payload):
    """Reopen the restored fits' windows, as the Qt tool did after a restore.

    ``load_project_payload`` here skips window creation (it must run without Qt); inside
    ChiSurf the main window then opens each fit's window, and without one this is a no-op.
    """
    from chisurf.macros.core_fit import restore_gui_from_fits

    uids = [
        f.get("uid", f.get("uuid", "")) for f in (payload.get("fits") or []) if isinstance(f, dict)
    ]
    return restore_gui_from_fits(uids, payload.get("ui"))


class ProjectBrowserModel:
    def __init__(
        self,
        client=None,
        payload_provider=None,
        payload_loader=None,
        context=None,
        window_restorer=None,
    ):
        self._client = client
        self.payload_provider = payload_provider or current_payload
        self.payload_loader = payload_loader or restore_payload
        self._restore_observer = payload_loader
        self.window_restorer = window_restorer or restore_fit_windows
        self.context = context if context is not None else current_context()
        self.projects = []
        self.selected_id = ""
        self.search = ""
        self.show_public = True
        self.status = "Refresh to browse the project database."
        self.artifacts = []
        self.parameters = []
        self.branches = []
        self.graph = {}
        self.last_directory = ""

    @property
    def client(self):
        if self._client is None:
            from chisurf.core.project.storage import (
                ProjectStorageError,
                _real_client,
                _settings,
                select_backend,
            )

            if select_backend() != "mmfdb":
                raise ProjectStorageError(
                    "No real MMFDB is configured; use Save Project for a .cs.pto file"
                )
            self._client = _real_client(_settings(None))
        return self._client

    @staticmethod
    def checked(result):
        if not isinstance(result, dict):
            raise ValueError("The project service returned an invalid response.")
        if result.get("ok") is not True:
            raise RuntimeError(result.get("error") or "The project operation failed.")
        return result

    @property
    def selected(self):
        for project in self.projects:
            if project.get("project_id") == self.selected_id:
                return project
            for version in project.get("versions", []):
                if version.get("version_id") == self.selected_id:
                    return version
        return None

    def selected_version(self, latest=False):
        selected = self.selected
        if selected and selected.get("version_id"):
            return selected
        if latest and selected:
            versions = selected.get("versions", [])
            return next(
                (v for v in versions if v.get("version_id") == selected.get("latest_version_id")),
                versions[0] if versions else None,
            )
        return None

    def require_version(self, latest=False):
        version = self.selected_version(latest)
        if version is None:
            raise ValueError(
                "Select a project or version to restore."
                if latest
                else "Select a version for this action."
            )
        return version

    def refresh(self):
        projects = self.client.list_projects(
            show_public=self.show_public, search=self.search.strip() or None
        )
        if not isinstance(projects, list):
            raise ValueError("The project list is invalid.")
        self.projects = projects
        if self.selected is None:
            self.selected_id = ""
        self.status = f"{len(projects)} projects loaded."
        return projects

    def fetch_restore(self, version):
        result = self.checked(self.client.restore_project(version_id=version["version_id"]))
        self._check_restore_identity(result, version["version_id"], version.get("project_id"))
        if not result.get("project_payload"):
            raise ValueError("This version has no project payload.")
        return result

    def _check_restore_identity(self, result, version_id, project_id=None):
        """Require the exact selected database identity before using its payload."""
        self.checked(result)
        if project_id is None:
            for project in self.projects:
                for version in project.get("versions", []):
                    if version.get("version_id") == version_id:
                        project_id = version.get("project_id") or project.get("project_id")
                        break
        if result.get("version_id") != version_id:
            raise ValueError("The project service returned a different version identity.")
        if not result.get("project_id") or (
            project_id is not None and result["project_id"] != project_id
        ):
            raise ValueError("The project service returned a different project identity.")

    def apply_restore(self, result, version_id):
        """Replace at the scientific owner and accept identity after presentation."""
        from chisurf.core.project.transition import replace_project

        self._check_restore_identity(result, version_id)
        project, staged = self._stage_current(result, version_id)
        document = getattr(self.context, "_project_document", None)

        def present(fit_uids, ui):
            payload = {**result["project_payload"], "ui": ui}
            # The authoritative result supplies the installed identities in both
            # local and server modes; proxy objects are never treated as fits.
            payload["fits"] = [{"uid": uid} for uid in fit_uids]
            if self._restore_observer is not None:
                self._restore_observer(result["project_payload"])
            return self.window_restorer(payload)

        restored = replace_project(
            project,
            gui=self.context,
            document=document,
            target_identity=staged,
            present=present,
        )
        if restored.get("ok") is not True:
            self.status = "Restore cancelled; the current project is still open."
            return False
        self.context._current_project_visibility = document.visibility
        self.status = f"Restored {result.get('project_name', 'project')}."
        return True

    def _stage_current(self, result, version_id=None):
        """Validate payload and database identity before replacing live state."""
        from chisurf.core.project import Project

        if version_id is not None and result.get("backend") != "file":
            self._check_restore_identity(result, version_id)
        payload = result.get("project_payload")
        if not isinstance(payload, dict):
            raise ValueError("The project service response has no project payload.")
        project = Project.from_dict(payload)
        document = getattr(self.context, "_project_document", None)
        if document is None:
            from chisurf.core.project.lifecycle import ProjectDocument

            document = ProjectDocument()
            self.context._project_document = document
        if result.get("backend") == "file":
            staged = document.stage_file_save(project, result.get("file_path"))
        else:
            staged = document.stage_database_save(project, result)
        return project, staged

    def _publish_current(self, result, project, staged, version_id=None):
        """Adopt prevalidated identity and synchronize legacy GUI fields."""
        document = getattr(self.context, "_project_document", None)
        if document is not None and staged is not None:
            document.adopt(staged)
        file_backend = result.get("backend") == "file"
        setattr(self.context, "_current_project_path", staged.path if file_backend else None)
        for attr, value in (
            ("_current_project_id", None if file_backend else result.get("project_id")),
            (
                "_current_project_version_id",
                None if file_backend else version_id or result.get("version_id"),
            ),
            ("_current_project_name", result.get("project_name", project.name)),
            ("_current_project_visibility", result.get("visibility", "private")),
        ):
            setattr(self.context, attr, value)

    def update_current(self, result, version_id=None):
        """Publish database identity and the accepted document baseline."""
        project, staged = self._stage_current(result, version_id)
        self._publish_current(result, project, staged, version_id)

    def save_snapshot(self, name):
        if not name.strip():
            raise ValueError("A project name is required.")
        payload = self.payload_provider(name.strip())
        if hasattr(payload, "to_dict"):
            payload = payload.to_dict()
        if not isinstance(payload, dict):
            raise ValueError("The current project payload is invalid.")
        return payload

    def save_remote(self, name, visibility, notes, payload):
        if visibility not in ("private", "public"):
            raise ValueError("Visibility must be private or public.")
        from chisurf.core.project import Project, storage

        project = Project.from_dict(payload)
        if storage.select_backend() == "file":
            save = getattr(self.context, "_save_project_snapshot", None)
            if not callable(save):
                raise storage.ProjectStorageError(
                    "Portable project save requires the main Save Project UI"
                )
            if save() is not True:
                raise storage.ProjectStorageError("Portable project save was cancelled or failed")
            document = self.context._get_project_document()
            return {
                "ok": True,
                "backend": "file",
                "file_path": str(document.path),
                "project_name": project.name,
                "project_payload": payload,
            }
        result = storage.save_database(
            project,
            project_id=getattr(self.context, "_current_project_id", None),
            parent_version_id=getattr(self.context, "_current_project_version_id", None),
            visibility=visibility,
            notes=notes.strip(),
        )
        return self.checked({**result, "project_name": project.name, "project_payload": payload})

    def export(self, version, path):
        path = Path(path)
        if not path.name.endswith(".cs.pto"):
            path = path.with_name(path.name + ".cs.pto")
        result = self.checked(self.client.export_csp(version_id=version["version_id"]))
        if result.get("version_id") != version["version_id"]:
            raise ValueError("The service returned a different export version.")
        if version.get("project_id") and result.get("project_id") != version["project_id"]:
            raise ValueError("The service returned a different export project.")
        import base64

        encoded = result.get("archive_bytes")
        if not encoded:
            raise OSError("The service did not return exported project content.")
        data = base64.b64decode(encoded, validate=True)
        from chisurf.core.project.pto import publish_project_bytes

        publish_project_bytes(path, data)
        self.last_directory = str(path.parent)
        return path

    def preview_import(self, path):
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(path)
        return self.checked(self.client.import_preview(file_path=str(path)))

    def import_archive(self, path, preview):
        collisions = preview.get("collisions", {})
        result = self.checked(
            self.client.import_csp(
                file_path=str(path),
                resolve_collisions=any(bool(values) for values in collisions.values()),
            )
        )
        self.last_directory = str(Path(path).parent)
        return result

    def delete(self, version):
        return self.checked(self.client.delete_version(version_id=version["version_id"]))

    def details(self, version):
        return {
            "artifacts": self.client.list_artifacts(version["version_id"]),
            "parameters": self.client.list_parameters(version["version_id"]),
            "branches": self.client.list_branches(version["project_id"]),
            "graph": self.client.version_graph(version["project_id"]),
        }

    def export_preferences(self):
        return {
            "search": self.search,
            "show_public": self.show_public,
            "last_directory": self.last_directory,
        }

    def restore_preferences(self, settings):
        self.search = str(settings.get("search", ""))
        self.show_public = bool(settings.get("show_public", True))
        self.last_directory = str(settings.get("last_directory", ""))
