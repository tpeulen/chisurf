"""The Qt-free view model behind the project browser window: what the specs of ``project_browser_emtk.view.json`` read and call."""

from __future__ import annotations

import json
from typing import Any


def _cell(value: Any) -> str:
    """A cell's text; a long stored blob (the version's metadata) is cut, the tooltip of the row has no more either."""
    text = "" if value is None else (json.dumps(value, default=str) if isinstance(value, (dict, list)) else str(value))
    return text if len(text) <= 160 else text[:157] + "..."


def _created(row: dict) -> str:
    return str(row.get("created_at") or "")[:19].replace("T", " ")


def _flatten(value: Any, path: str = "") -> list[dict]:
    """A nested value as ``{"path", "value"}`` rows, one per leaf."""
    if isinstance(value, dict):
        out: list[dict] = []
        for key, inner in value.items():
            out += _flatten(inner, f"{path}.{key}" if path else str(key))
        return out
    if isinstance(value, list):
        out = []
        for i, inner in enumerate(value):
            out += _flatten(inner, f"{path}[{i}]")
        return out
    return [{"path": path, "value": _cell(value)}]


class ProjectPanel:
    """The actions, the fields and the table sources of the window; the app owns the dialogs and the background jobs."""

    def __init__(self, app) -> None:
        self.app = app

    @property
    def model(self):
        return self.app.model

    # -- fields -------------------------------------------------------------------------------------------- #
    search = property(lambda s: s.model.search, lambda s, v: setattr(s.model, "search", str(v)))
    show_public = property(lambda s: s.model.show_public, lambda s, v: setattr(s.model, "show_public", bool(v)))
    expanded = property(lambda s: s.app.expanded)
    name = property(lambda s: s.app.name, lambda s, v: setattr(s.app, "name", str(v)))
    notes = property(lambda s: s.app.notes, lambda s, v: setattr(s.app, "notes", str(v)))

    @property
    def visibility_name(self) -> str:
        return ["Private", "Public"][int(self.app.visibility)]

    @visibility_name.setter
    def visibility_name(self, value: str) -> None:
        self.app.visibility = 1 if str(value).lower() == "public" else 0

    show_id = property(lambda s: s.app.column_shown("show_id"), lambda s, v: setattr(s.app, "show_id", bool(v)))
    show_status = property(lambda s: s.app.column_shown("show_status"), lambda s, v: setattr(s.app, "show_status", bool(v)))

    def columns_changed(self, *_value) -> None:
        """The Show ID / Show status toggles: the table re-reads :meth:`browser_columns` on the next frame."""

    def browser_columns(self) -> list[dict]:
        """The columns of the project table; ID and Status only while their toggles are on."""
        from .app import SPEC

        out = []
        for column in SPEC["_columns"]:
            shown = (column["key"] != "id" or self.show_id) and (column["key"] != "status" or self.show_status)
            out.append({**column, "visible": shown})
        return out

    def search_changed(self, *_value) -> None:
        self.app.error(self.app.refresh)

    public_changed = search_changed

    # -- state the specs ask for ------------------------------------------------------------------------ #
    def busy(self) -> bool:
        return self.app.jobs.future is not None

    def has_version(self) -> bool:
        return self.model.selected_version() is not None

    def enabled(self, name: str) -> bool:
        if name in ("guide", "help"):
            return True
        if name in ("name",):
            return self.app.allow_name_edit
        if self.busy():
            return False
        if name == "clear_search":
            return bool(self.model.search)
        if name in ("export", "delete"):
            return self.has_version()
        if name in ("open", "inspect"):
            return self.model.selected is not None
        return True

    # -- table sources ------------------------------------------------------------------------------------- #
    def tree_rows(self) -> list[dict]:
        """One record per project, and one per version under it (``parent_id`` is the project's ``row_id``)."""
        rows = []
        for project in self.model.projects:
            pid = project.get("project_id", "")
            rows.append({
                "row_id": pid, "parent_id": "",
                "project_name": f"{project.get('project_name', '(unnamed)')} ({project.get('version_count', 0)} versions)",
                "id": pid, "owner_user_id": project.get("owner_user_id", ""), "status": "",
                "visibility": project.get("visibility", "private"), "dataset_count": "", "fit_count": "",
                "created_at": _created(project), "notes": "",
                "tooltip": f"Project: {pid}\nOwner: {project.get('owner_user_id', '')}\nVersions: {project.get('version_count', 0)}",
            })
            for version in project.get("versions", []):
                rows.append({
                    "row_id": version.get("version_id", ""), "parent_id": pid,
                    "project_name": f"v{version.get('version_number', '?')} {version.get('project_name', '')}",
                    "id": version.get("version_id", ""), "owner_user_id": version.get("owner_user_id", ""),
                    "status": version.get("status", ""), "visibility": version.get("visibility", project.get("visibility", "private")),
                    "dataset_count": version.get("dataset_count", 0), "fit_count": version.get("fit_count", 0),
                    "created_at": _created(version), "notes": str(version.get("notes") or "")[:60],
                    "tooltip": (f"Version: {version.get('version_id', '')}\nProject: {version.get('project_id', '')}\nOwner: {version.get('owner_user_id', '')}\n"
                                f"Created: {version.get('created_at', '')}\nDatasets: {version.get('dataset_count', 0)}  Fits: {version.get('fit_count', 0)}\n"
                                f"{version.get('notes') or ''}"),
                })
        return rows

    def summary_rows(self) -> list[dict]:
        selected = self.model.selected
        if selected is None:
            return []
        return [{"field": k, "value": _cell(v)} for k, v in selected.items() if k != "versions"]

    def artifact_rows(self) -> list[dict]:
        return [{k: _cell(v) for k, v in dict(r).items()} for r in self.model.artifacts]

    def parameter_rows(self) -> list[dict]:
        return [{k: _cell(v) for k, v in dict(r).items()} for r in self.model.parameters]

    def branch_rows(self) -> list[dict]:
        return [{k: _cell(v) for k, v in dict(r).items()} for r in self.model.branches]

    def graph_rows(self) -> list[dict]:
        return _flatten(self.model.graph)

    # -- the table's calls ------------------------------------------------------------------------------- #
    def select_row(self, record: Any) -> None:
        if isinstance(record, dict):
            self.app.select(record.get("row_id", ""))

    def activate_row(self, record: Any) -> None:
        self.select_row(record)
        self.app.error(self.app.open_selected)

    def context_row(self, record: Any, key: Any = None, position: Any = None) -> None:
        if isinstance(record, dict):
            self.select_row(record)
            self.app.open_context_menu(record, position)

    # -- the toolbar's actions ------------------------------------------------------------------------- #
    def open(self) -> None:
        self.app.error(self.app.open_selected)

    def save(self) -> None:
        self.app.error(self.app.begin_save)

    def export(self) -> None:
        self.app.error(lambda: self.app.choose_file("export"))

    def import_project(self) -> None:
        self.app.error(lambda: self.app.choose_file("import"))

    def delete(self) -> None:
        self.app.error(self.app.begin_delete)

    def refresh(self) -> None:
        self.app.error(self.app.refresh)

    def clear_search(self) -> None:
        if self.model.search:
            self.model.search = ""
            self.app.error(self.app.refresh)

    def inspect(self) -> None:
        self.app.error(self.app.inspect)

    def guide(self) -> None:
        self.app.tour.start()

    def help(self) -> None:
        self.app.help_window.show()

    # -- the dialogs' actions ------------------------------------------------------------------------- #
    def confirm_save(self) -> None:
        self.app.error(self.app.save)

    def cancel_dialog(self) -> None:
        self.app.modal = ""
