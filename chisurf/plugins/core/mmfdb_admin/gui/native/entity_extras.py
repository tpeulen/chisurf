"""Per-entity extras of the native entity panel (Qt-free).

What the Qt ``sample_database`` tool offered besides plain CRUD, as model methods behind
the ``x_`` sources and actions declared in ``gui/entity_extras.view.json``: the
experiment's linked-data sub-table, Validate setup, Restore / Delete of an archived
project version, and the row helpers of the old right-click menu (copy, tick).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .base import cell
from .dialogs import ConfirmDialog, MessageDialog

_SPEC = Path(__file__).resolve().parent.parent / "entity_extras.view.json"
_URL = ("http://", "https://", "file://")

DATA_COLUMNS = (
    ("data_id", "id", False),
    ("data_type", "type", True),
    ("storage_mode", "mode", True),
    ("location", "path/url/folder", True),
    ("mime_type", "mime", True),
    ("checksum", "checksum", True),
    ("reading_options_json", "reading options", True),
    ("details", "details", True),
)

VERSION_COLUMNS = (
    ("version_id", "version", False),
    ("version_number", "no.", False),
    ("created_at", "created", False),
    ("status", "status", False),
    ("description", "notes", False),
)


def load_extras() -> dict[str, list[dict]]:
    """The declared extra sections per entity key (``*``: every entity)."""
    spec = json.loads(_SPEC.read_text(encoding="utf-8"))
    return {k: v for k, v in spec.items() if not k.startswith("_")}


def _columns(columns: tuple) -> list[dict]:
    return [{"key": k, "title": t, "editable": e} for k, t, e in columns]


class ExtrasMixin:
    """Mixed into :class:`~.entity.EntityPanel`; every ``x_`` name is routed here."""

    def _init_extras(self) -> None:
        self.data_rows: list[dict] = []
        self.data_selected = ""
        self.version_rows: list[dict] = []
        self.version_selected = ""
        self.validation_text = ""
        self._extras = load_extras()

    # ── spec ───────────────────────────────────────────────────────────
    def extra_sections(self) -> list[dict]:
        return list(self._extras.get(self.key, [])) + list(self._extras.get("*", []))

    def x_enabled(self, name: str) -> bool:
        if not self.admin.connected:
            return False
        if name in ("x_check_all", "x_uncheck_all", "x_invert_checks"):
            return bool(self.rows)
        if name == "x_copy_checked":
            return bool(self.checked_ids())
        return bool(self.selected_id)

    # ── selection hook ─────────────────────────────────────────────────
    def after_select(self) -> None:
        self.data_selected = ""
        self.version_selected = ""
        self.validation_text = ""
        if self.key == "experiment":
            self._load_experiment_data()
        elif self.key == "project":
            self._load_versions()

    # ── experiment data sub-table ──────────────────────────────────────
    def x_data_columns(self) -> list[dict]:
        return _columns(DATA_COLUMNS)

    def x_data_rows(self) -> list[dict]:
        return self.data_rows

    @staticmethod
    def _data_row(item: dict, n: int) -> dict:
        location = item.get("file_path") or item.get("url") or item.get("folder_path") or ""
        row = {
            "_id": str(item.get("data_id") or f"new_{n}"),
            "data_id": item.get("data_id") or "",
            "data_type": item.get("data_type") or "",
            "storage_mode": item.get("storage_mode") or "",
            "location": location,
            "mime_type": item.get("mime_type") or "",
            "checksum": item.get("checksum") or "",
            "reading_options_json": item.get("reading_options_json") or "",
            "details": item.get("details") or "",
        }
        return {k: cell(v) for k, v in row.items()}

    def _set_data(self, items: list[dict]) -> None:
        self.data_rows = [self._data_row(d, i + 1) for i, d in enumerate(items or [])]

    def _load_experiment_data(self) -> None:
        eid = self.selected_id
        if not eid:
            self.data_rows = []
            return

        def fetch():
            return (self.client.get_experiment(eid) or {}).get("data", [])

        def got(items: list[dict]) -> None:
            if self.selected_id == eid:
                self._set_data(items)

        self.run("Experiment data", fetch, got, self.failed("Experiment data"))

    def x_data_select(self, record: dict | None) -> None:
        self.data_selected = str((record or {}).get("_id", "") or "")

    def x_data_edited(self, record: dict, key: str, value: Any) -> None:
        if key in {k for k, _, e in DATA_COLUMNS if e}:
            record[key] = "" if value is None else str(value)

    def _picked_data(self) -> dict | None:
        return next((r for r in self.data_rows if r["_id"] == self.data_selected), None)

    def x_data_add(self) -> None:
        if not self.selected_id:
            return
        n = 1
        while any(r["_id"] == f"new_{n}" for r in self.data_rows):
            n += 1
        self.data_rows.append(self._data_row({"storage_mode": "link"}, n))
        self.data_rows[-1]["_id"] = f"new_{n}"
        self.data_selected = f"new_{n}"

    def _collect_data(self, row: dict) -> dict:
        location = str(row.get("location") or "")
        mode = str(row.get("storage_mode") or "link") or "link"
        is_url = location.startswith(_URL)
        data_id = str(row.get("data_id") or "")
        return {
            "data_id": int(data_id) if data_id else None,
            "experiment_id": self.selected_id,
            "data_type": str(row.get("data_type") or ""),
            "storage_mode": mode,
            "file_path": location if mode == "link" and not is_url and location else None,
            "url": location if is_url else None,
            "folder_path": location if mode == "folder" else None,
            "mime_type": str(row.get("mime_type") or ""),
            "checksum": str(row.get("checksum") or ""),
            "reading_options_json": str(row.get("reading_options_json") or ""),
            "details": str(row.get("details") or ""),
        }

    def x_data_save(self) -> None:
        row = self._picked_data()
        if row is None:
            self.say("Pick a data row first.")
            return
        data = self._collect_data(row)
        if not data["data_type"]:
            self.say("Data type is required.")
            return
        try:
            json.loads(data["reading_options_json"] or "{}")
        except json.JSONDecodeError as exc:
            self.say(f"Invalid reading options JSON: {exc}")
            return
        eid = self.selected_id

        def call():
            saved = self.client.save_experiment_data(data) or {}
            return saved.get("data", [])

        def done(items: list[dict]) -> None:
            if self.selected_id == eid:
                self._set_data(items)
                self.data_selected = ""
            self.say("Experiment data saved.")

        self.run("Save experiment data", call, done, self.failed("Save data"))

    def x_data_delete(self) -> None:
        row = self._picked_data()
        data_id = str((row or {}).get("data_id") or "")
        if not data_id:
            if row is not None:  # an unsaved row: just drop it
                self.data_rows.remove(row)
                self.data_selected = ""
            else:
                self.say("Pick a saved data row first.")
            return
        eid = self.selected_id

        def call():
            self.client.delete_experiment_data(int(data_id))
            return (self.client.get_experiment(eid) or {}).get("data", [])

        def done(items: list[dict]) -> None:
            if self.selected_id == eid:
                self._set_data(items)
                self.data_selected = ""
            self.say(f"Data record {data_id} deleted.")

        self.admin.show(
            ConfirmDialog(
                "Delete experiment data",
                f"Delete data record {data_id}?",
                lambda: self.run("Delete data", call, done, self.failed("Delete data")),
            )
        )

    def x_data_open(self) -> None:
        row = self._picked_data()
        location = str((row or {}).get("location") or "")
        if not location:
            self.admin.show(MessageDialog("Experiment data", "No data location is set"))
            return
        if not location.startswith(_URL) and not Path(location).exists():
            self.admin.show(MessageDialog("Data path not found", f"Missing: {location}"))
            return
        self.admin.open_location(location)

    # ── setup validation ───────────────────────────────────────────────
    def x_validation_text(self) -> str:
        return self.validation_text

    def x_validate_setup(self) -> None:
        setup_id = self.selected_id
        if not setup_id:
            return

        def done(res: dict) -> None:
            if (res or {}).get("valid"):
                self.validation_text = f"Validation OK: {setup_id}"
            else:
                self.validation_text = (
                    f"Validation FAIL: {(res or {}).get('message') or 'Unknown validation error'}"
                )
            self.say(self.validation_text)

        def failed(error: str) -> None:
            self.validation_text = f"Error validating setup: {error}"
            self.say(self.validation_text)

        self.run(
            "Validate setup",
            lambda: self.client._call("mmfdb.setups.validate", {"setup_id": setup_id}),
            done,
            failed,
        )

    # ── archived project versions ──────────────────────────────────────
    def x_version_columns(self) -> list[dict]:
        return _columns(VERSION_COLUMNS)

    def x_version_rows(self) -> list[dict]:
        return self.version_rows

    def x_version_select(self, record: dict | None) -> None:
        self.version_selected = str((record or {}).get("version_id", "") or "")

    def _load_versions(self) -> None:
        pid = self.selected_id
        if not pid:
            self.version_rows = []
            return

        def fetch():
            return self.client._call("mmfdb.projects.list", None).get("projects", [])

        def got(items: list[dict]) -> None:
            if self.selected_id != pid:
                return
            self.version_rows = [
                {**{k: cell(v.get(k)) for k, _, _ in VERSION_COLUMNS}, "_id": str(v["version_id"])}
                for v in items
                if str(v.get("project_id")) == pid and v.get("version_id")
            ]

        self.run("Project versions", fetch, got, self.failed("Project versions"))

    def _chosen_version(self) -> str:
        if self.version_selected:
            return self.version_selected
        return self.version_rows[0]["version_id"] if self.version_rows else ""

    def x_restore_version(self) -> None:
        """Fetch the chosen version from the database and hand it to ChiSurf."""
        version_id = self._chosen_version()
        pid = self.selected_id
        if not version_id:
            self.admin.show(MessageDialog("No Selection", "Please select a project to restore."))
            return

        def call():
            payload = self.client.restore_project(version_id)
            return self.admin.restore_project(pid, version_id, payload)

        def done(result: Any) -> None:
            self.say(f"Restored project version {version_id}.")

        def failed(error: str) -> None:
            self.admin.show(MessageDialog("Restore Failed", f"Failed to restore project: {error}"))

        self.run("Restore project", call, done, failed)

    def x_delete_version(self) -> None:
        version_id = self.version_selected
        if not version_id:
            self.admin.show(
                MessageDialog("No Selection", "Please select a project version to delete.")
            )
            return

        def call():
            self.client.delete_project(version_id)
            return self.client._call("mmfdb.projects.list", None).get("projects", [])

        def done(_items: list[dict]) -> None:
            self.version_selected = ""
            self.say(f"Project version {version_id} deleted.")
            self._load_versions()
            self.refresh()

        self.admin.show(
            ConfirmDialog(
                "Delete Project Version",
                f"Are you sure you want to delete the archived project version "
                f"'{version_id}' from the database?",
                lambda: self.run(
                    "Delete project version", call, done, self.failed("Delete project version")
                ),
            )
        )

    # ── row helpers (the old right-click menu) ─────────────────────────
    def x_copy_row(self) -> None:
        row = next((r for r in self.rows if r["_id"] == self.selected_id), None)
        if row is None:
            return
        self.admin.copy("\t".join(str(row.get(k, "")) for k, _ in self.columns))
        self.say("Copied the selected row.")

    def x_copy_checked(self) -> None:
        ids = self.checked_ids()
        if ids:
            self.admin.copy("\n".join(ids))
            self.say(f"Copied {len(ids)} IDs")

    def x_check_all(self) -> None:
        for r in self.rows:
            r["checked"] = True

    def x_uncheck_all(self) -> None:
        for r in self.rows:
            r["checked"] = False

    def x_invert_checks(self) -> None:
        for r in self.rows:
            r["checked"] = not r.get("checked")


def route(panel: Any, name: str) -> Callable | Any:
    """The panel attribute behind an ``x_`` name of the form."""
    return getattr(panel, name)
