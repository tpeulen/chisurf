"""A generic entity panel: the table, the dictionary form, New / Delete and the per-entity actions.

One class serves the 21 entities of :data:`~..entity_registry.ENTITY_REGISTRY`, as the
Qt ``EntityDock`` does: the columns and the form come from the entity's
:class:`~..entity_schema.FieldSpec` list (:func:`~..entity_schema.entity_field_specs`),
the calls from its RPC namespace (``mmfdb.<rpc>.list/get/save/delete``). An edit is
saved when the field is committed (the Qt auto-save). A foreign-key cell is a link:
a double click opens the record it names in its own panel.
"""

from __future__ import annotations

import base64
import tempfile
from pathlib import Path
from typing import Any

from ..entity_registry import EntitySpec
from ..entity_schema import FieldSpec, entity_columns
from ..entity_values import coerce_in, coerce_out, default_for, view_section
from .base import Panel, cell
from .dialogs import (
    AnalysisDetailsDialog,
    ChoiceDialog,
    ConfirmDialog,
    JumpBranchDialog,
    MessageDialog,
    PasswordDialog,
    TextDialog,
)

#: The validation states an artifact may be given (the server's list).
try:  # pragma: no cover - mmfdb is a hard dependency of the admin
    from mmfdb.models import VALIDATION_STATUS_VALUES
except Exception:  # noqa: BLE001
    VALIDATION_STATUS_VALUES = ("unvalidated", "valid", "invalid", "suspect")

#: Label keys tried, in order, for the text of a foreign-key option.
_LABEL_KEYS = ("name", "display_name", "description", "chromophore_name")


class EntityForm:
    """The record being edited, as attributes the generated form sections bind.

    Reading a field gives its edit value (:func:`~..entity_values.coerce_in`);
    writing one (a committed edit) stores it and saves the record. Choice options
    are methods: ``choices__<field>`` for an enumeration, ``fk__<field>`` for a
    foreign key.
    """

    def __init__(self, panel: EntityPanel) -> None:
        object.__setattr__(self, "_panel", panel)
        object.__setattr__(self, "_values", {})
        object.__setattr__(self, "_loading", False)

    def load(self, record: dict) -> None:
        panel = self._panel
        values = {fs.name: coerce_in(fs, record.get(fs.name)) for fs in panel.field_specs}
        object.__setattr__(self, "_values", values)

    def clear(self) -> None:
        values = {fs.name: default_for(fs) for fs in self._panel.field_specs}
        object.__setattr__(self, "_values", values)

    def data(self) -> dict:
        """The form as a record (:func:`~..entity_values.coerce_out`)."""
        return {
            fs.name: coerce_out(fs, self._values.get(fs.name)) for fs in self._panel.field_specs
        }

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__"):
            raise AttributeError(name)
        panel = object.__getattribute__(self, "_panel")
        if name.startswith("choices__"):
            field = panel.field(name[len("choices__") :])
            return lambda: list(field.choices) if field else []
        if name.startswith("fk__"):
            field_name = name[len("fk__") :]
            return lambda: panel.fk_choices(field_name)
        values = object.__getattribute__(self, "_values")
        if name in values:
            return values[name]
        field = panel.field(name)
        if field is not None:
            return default_for(field)
        raise AttributeError(name)

    def __setattr__(self, name: str, value: Any) -> None:
        self._values[name] = value
        self._panel.form_committed(name)

    def enabled(self, name: str) -> bool:  # noqa: ARG002 - view_form hook
        panel = self._panel
        return bool(panel.selected_id) and panel.admin.connected


class EntityPanel(Panel):
    """One entity: its table, its form, New / Delete and the actions declared for it."""

    def __init__(
        self, admin: Any, spec: EntitySpec, field_specs: list[FieldSpec], icon: str = ""
    ) -> None:
        super().__init__(admin)
        self.spec = "entity"
        self.entity = spec
        self.key = spec.key
        self.name = spec.title
        self.icon = icon
        self.description = f"Browse and edit {spec.title.lower()} ({spec.category})."
        self.field_specs = list(field_specs)
        self._by_name = {fs.name: fs for fs in self.field_specs}
        self.columns = entity_columns(spec, self.field_specs)
        self.records: dict[str, dict] = {}
        self.rows: list[dict] = []
        self.selected_id = ""
        self.form = EntityForm(self)
        self.form.clear()
        #: ``field -> [(value, label)]`` of every foreign key, fetched with the rows.
        self.fk_options: dict[str, list[tuple[str, str]]] = {}
        self._preview_dir: tempfile.TemporaryDirectory | None = None

    # ── schema ─────────────────────────────────────────────────────────
    def field(self, name: str) -> FieldSpec | None:
        return self._by_name.get(name)

    @property
    def writable(self) -> bool:
        return bool(self.entity.writable)

    def fk_target(self, name: str) -> str:
        """The registered entity a field links to ('' if none)."""
        fs = self._by_name.get(name)
        target = getattr(fs, "fk_target", None) if fs else None
        return target if target and target in self.admin.registry else ""

    def form_sections(self) -> list[dict]:
        """The form, as ``view.json`` sections generated from the field list."""
        locked = not self.writable
        return [
            view_section(fs, f"fk__{fs.name}" if self.fk_target(fs.name) else "", read_only=locked)
            for fs in self.field_specs
        ]

    def table_columns(self) -> list[dict]:
        """The table's columns: a check box, then the id and the fields (links for keys)."""
        out: list[dict] = [
            {
                "key": "checked",
                "title": "✓",
                "width": 30,
                "editable": True,
                "shade": False,
                "tooltip": "Tick rows to act on several at once (Delete deletes the ticked rows).",
            }
        ]
        for key, label in self.columns:
            fs = self._by_name.get(key)
            column = {
                "key": key,
                "title": label,
                "tooltip": (getattr(fs, "tooltip", "") or label)
                + (
                    " Double-click to open the record it names."
                    if self.fk_target(key)
                    else ""
                ),
            }
            if self.fk_target(key):
                column["display"] = "link"
            out.append(column)
        return out

    # ── rows ───────────────────────────────────────────────────────────
    def table_rows(self) -> list[dict]:
        return self.rows

    def _row(self, record: dict) -> dict:
        row = {key: cell(record.get(key)) for key, _ in self.columns}
        row["_id"] = str(record.get(self.entity.id_field, "") or "")
        row["checked"] = False
        return row

    def _list(self) -> list[dict]:
        result = self.client._call(f"mmfdb.{self.entity.rpc}.list", None) or {}
        return list(result.get(self.entity.list_key, []) or [])

    def _fetch_fk_options(self) -> dict[str, list[tuple[str, str]]]:
        options: dict[str, list[tuple[str, str]]] = {}
        for fs in self.field_specs:
            target = self.fk_target(fs.name)
            if not target:
                continue
            spec = self.admin.registry[target]
            try:
                result = self.client._call(f"mmfdb.{spec['rpc']}.list", None) or {}
            except Exception:  # noqa: BLE001 - a target the user may not list: no options
                options[fs.name] = []
                continue
            pairs = []
            for r in result.get(spec["list_key"], []) or []:
                value = str(r.get(spec["id_field"], ""))
                label = next((r.get(k) for k in _LABEL_KEYS if r.get(k)), value)
                pairs.append((value, f"{value} — {label}" if label != value else value))
            options[fs.name] = pairs
        return options

    def refresh(self) -> None:
        def fetch():
            return self._list(), self._fetch_fk_options()

        self.run(f"Load {self.name}", fetch, self._loaded, self.failed("Load"))

    def _loaded(self, result: tuple[list[dict], dict]) -> None:
        records, options = result
        self.fk_options = options
        self.records = {}
        rows = []
        for record in records:
            row = self._row(record)
            if row["_id"]:
                self.records[row["_id"]] = record
            rows.append(row)
        self.rows = rows
        self.message = f"{len(rows)} {self.name.lower()}"
        self.admin.set_summary(self.message)
        if self.selected_id and self.selected_id in self.records:
            self.form.load(self.records[self.selected_id])
        elif self.selected_id:
            self.selected_id = ""
            self.form.clear()

    def fk_choices(self, name: str) -> list[tuple[str, str]]:
        """Options of a foreign key: none, the target's records, and the current value."""
        pairs = [("", "(none)")] + list(self.fk_options.get(name, []))
        current = str(self.form._values.get(name, "") or "")
        if current and current not in {v for v, _ in pairs}:
            pairs.append((current, current))
        return pairs

    def status_line(self) -> str:
        return self.message

    # ── selection ──────────────────────────────────────────────────────
    def select_row(self, record: dict | None) -> None:
        """A row was picked in the table: open its record in the form."""
        record_id = str((record or {}).get("_id", "") or "")
        if record_id and record_id != self.selected_id:
            self.jump_to(record_id)

    def jump_to(self, record_id: str) -> None:
        """Select *record_id* and load it into the form (fetching it if it is not listed)."""
        self.selected_id = str(record_id)
        record = self.records.get(self.selected_id)
        if record is not None:
            self.form.load(record)
            return
        rid = self.selected_id

        def fetch():
            result = self.client._call(
                f"mmfdb.{self.entity.rpc}.get", {self.entity.id_field: rid}
            )
            return (result or {}).get(self.entity.item_key) or {}

        def got(record: dict) -> None:
            if record and self.selected_id == rid:
                self.records[rid] = record
                self.form.load(record)

        self.run(f"Open {rid}", fetch, got, self.failed("Open"))

    def activate_cell(self, record: dict, key: str) -> None:
        """Double click: a foreign-key cell opens the record it names in its panel."""
        target = self.fk_target(key)
        value = str((record or {}).get(key, "") or "")
        if target and value:
            self.admin.jump(target, value)

    def edited(self, record: dict, key: str, value: Any) -> None:
        """The check box column (the only editable cells)."""
        if key == "checked":
            record["checked"] = bool(value)

    def checked_ids(self) -> list[str]:
        return [r["_id"] for r in self.rows if r.get("checked") and r["_id"]]

    def selected_record(self) -> dict:
        """The selected record as the form holds it (falls back to the listed one)."""
        if not self.selected_id:
            return {}
        data = dict(self.records.get(self.selected_id, {}))
        data.update({k: v for k, v in self.form.data().items() if v not in (None, "")})
        return data

    # ── edits ──────────────────────────────────────────────────────────
    def form_committed(self, name: str) -> None:
        """A field was committed in the form: save the record (the Qt auto-save)."""
        if not self.selected_id or not self.writable or name not in self._by_name:
            return
        data = self.form.data()
        rid = self.selected_id

        def save():
            result = self.client._call(f"mmfdb.{self.entity.rpc}.save", {self.entity.key: data})
            return (result or {}).get(self.entity.item_key) or data

        def saved(record: dict) -> None:
            new_id = str(record.get(self.entity.id_field, "") or rid)
            self.records[new_id] = dict(self.records.get(rid, {}), **record)
            for row in self.rows:
                if row["_id"] == rid:
                    row.update(self._row(self.records[new_id]), checked=row.get("checked", False))
            self.selected_id = new_id
            self.say(f"Saved {self.entity.key}.")

        self.run(f"Save {rid}", save, saved, self.failed("Auto-save"))

    def enabled(self, name: str) -> bool:
        if not self.admin.connected:
            return False
        if name in ("new_record", "delete_checked"):
            return self.writable
        if name in ("refresh_panel",):
            return True
        return bool(self.selected_id)

    def new_record(self) -> None:
        """Create a record at once (an untitled id, or one the server assigns) and open it."""
        if not self.writable:
            return
        id_spec = self._by_name.get(self.entity.id_field)
        if id_spec is not None and id_spec.readonly:
            data: dict = {}
        else:
            n = 1
            while f"untitled_{n}" in self.records:
                n += 1
            data = {self.entity.id_field: f"untitled_{n}"}

        def create():
            result = self.client._call(f"mmfdb.{self.entity.rpc}.save", {self.entity.key: data})
            record = (result or {}).get(self.entity.item_key) or {}
            return record, self._list()

        def created(result: tuple[dict, list[dict]]) -> None:
            record, records = result
            self._loaded((records, self.fk_options))
            new_id = str(record.get(self.entity.id_field, data.get(self.entity.id_field, "")))
            if new_id:
                self.records.setdefault(new_id, record)
                self.jump_to(new_id)
            self.say(f"Created {self.entity.key}: {new_id or '(new)'}")

        self.run(f"Create {self.entity.key}", create, created, self.failed("Create"))

    def delete_checked(self) -> None:
        """Delete the ticked rows, after asking."""
        ids = self.checked_ids()
        title = self.name.lower()
        if not ids:
            self.admin.show(
                MessageDialog(
                    "Nothing checked",
                    f"Tick the check box in the first column to select {title} to delete.",
                )
            )
            return

        def delete():
            failures = []
            for item_id in ids:
                try:
                    self.client._call(
                        f"mmfdb.{self.entity.rpc}.delete", {self.entity.id_field: item_id}
                    )
                except Exception as exc:  # noqa: BLE001 - listed to the user
                    failures.append(f"{item_id}: {exc}")
            return failures, self._list()

        def deleted(result: tuple[list[str], list[dict]]) -> None:
            failures, records = result
            self._loaded((records, self.fk_options))
            if failures:
                self.admin.show(MessageDialog("Some deletes failed", "\n".join(failures[:10])))
            else:
                self.say(f"Deleted {len(ids)} {title}")

        self.admin.show(
            ConfirmDialog(
                f"Delete {self.name}",
                f"Delete {len(ids)} {title}?",
                lambda: self.run(f"Delete {title}", delete, deleted, self.failed("Delete")),
            )
        )

    def refresh_panel(self) -> None:
        self.refresh()

    # ── per-entity actions (declared in admin.view.json "entity_actions") ──────
    def _id_of(self, *keys: str) -> str:
        data = self.selected_record()
        return next((str(data[k]) for k in keys if data.get(k)), "")

    def _artifact_id(self) -> str:
        return self._id_of(self.entity.id_field, "processed_data_id")

    def copy_id(self) -> None:
        """Copy the selected record's id."""
        value = self._artifact_id()
        if value:
            self.admin.copy(value)
            self.say(f"Copied {value}")

    def copy_uuid(self) -> None:
        self.copy_id()

    def reveal(self) -> None:
        """Open the selected artifact's file or URL (Objects: a downloaded copy)."""
        if self.key == "object":
            self._reveal_object()
            return
        data = self.selected_record()
        location = str(
            data.get("location")
            or data.get("file_path")
            or data.get("url")
            or data.get("folder_path")
            or ""
        ).strip()
        if location:
            self.admin.open_location(location)
        else:
            self.say("The selected record has no file or URL.")

    def _reveal_object(self) -> None:
        data = self.selected_record()
        object_uuid = str(data.get("object_uuid") or "").strip()
        if not object_uuid:
            return
        if self._preview_dir is None:
            self._preview_dir = tempfile.TemporaryDirectory(prefix="chisurf-mmfdb-preview-")
        folder = Path(self._preview_dir.name)
        name = Path(str(data.get("original_filename") or object_uuid)).name

        def download():
            response = self.client.get_object(object_uuid)
            payload = base64.b64decode(response["data"], validate=True)
            path = folder / f"{object_uuid}-{name}"
            path.write_bytes(payload)
            return str(path)

        self.run("Reveal object", download, self.admin.open_location, self.failed("Reveal"))

    def use_as_seed(self) -> None:
        """Load the selected artifact's provenance graph (and show it)."""
        seed_type = {"raw_data": "raw_data", "processed_product": "processed_data"}.get(
            self.key, "analysis_run"
        )
        value = self._artifact_id()
        if value:
            self.admin.provenance_seed(seed_type, value)

    def validate(self) -> None:
        """Ask for a validation status and give it to the selected artifact."""
        artifact_id = self._artifact_id()
        if not artifact_id:
            self.admin.show(MessageDialog("No artifact selected", "Select an artifact row first."))
            return
        current = str(self.selected_record().get("validation_status") or "unvalidated")

        def apply(status: str) -> None:
            def call():
                self.client.set_artifact_validation(artifact_id, status)
                return self._list()

            def done(records: list[dict]) -> None:
                self._loaded((records, self.fk_options))
                self.say(f"Artifact {artifact_id} validation set to {status}.")

            self.run("Set validation", call, done, self.failed("Validation update"))

        self.admin.show(
            ChoiceDialog(
                "Set validation status",
                f"Validation status for {artifact_id}:",
                list(VALIDATION_STATUS_VALUES),
                current,
                apply,
            )
        )

    def delete_artifact(self) -> None:
        """Soft-delete the selected artifact (and its direct provenance links), after asking."""
        artifact_id = self._artifact_id()
        if not artifact_id:
            self.admin.show(MessageDialog("No artifact selected", "Select an artifact row first."))
            return
        label = {"raw_data": "raw-data artifact", "processed_product": "processed-data artifact"}.get(
            self.key, "artifact"
        )

        def call():
            self.client.delete_artifact(artifact_id)
            return self._list()

        def done(records: list[dict]) -> None:
            self.selected_id = ""
            self.form.clear()
            self._loaded((records, self.fk_options))
            self.say(f"Artifact {artifact_id} deleted.")

        self.admin.show(
            ConfirmDialog(
                "Delete artifact",
                f"Delete {label} '{artifact_id}'?\n\nThis soft-deletes the artifact and direct "
                "provenance links.",
                lambda: self.run("Delete artifact", call, done, self.failed("Artifact delete")),
            )
        )

    def delete_object(self) -> None:
        """Delete the selected object, or drop one reference to it, after asking."""
        data = self.selected_record()
        object_uuid = str(data.get("object_uuid") or self.selected_id or "")
        if not object_uuid:
            self.admin.show(MessageDialog("No object selected", "Select an object to delete."))
            return
        filename = data.get("original_filename") or object_uuid
        try:
            refcount = int(data.get("refcount") or 0)
        except (TypeError, ValueError):
            refcount = 0
        text = f"Delete object '{filename}'?\n\nRefcount: {refcount}\n\n" + (
            "This will only decrement the refcount; the blob will remain."
            if refcount > 1
            else "This will permanently delete the blob from disk."
        )

        def call():
            result = self.client.delete_object(object_uuid)
            return result, self._list()

        def done(result: tuple[Any, list[dict]]) -> None:
            outcome, records = result
            self._loaded((records, self.fk_options))
            self.say(f"Object delete result: {outcome}")

        self.admin.show(
            ConfirmDialog(
                "Delete object",
                text,
                lambda: self.run("Delete object", call, done, self.failed("Delete")),
            )
        )

    def details(self) -> None:
        """Show the selected analysis run's parameters and products."""
        analysis_id = self._artifact_id()
        if not analysis_id:
            self.admin.show(MessageDialog("No analysis selected", "Select an analysis row first."))
            return

        def got(detail: dict) -> None:
            if not detail:
                self.admin.show(
                    MessageDialog(
                        "Analysis not found",
                        f"No analysis details were found for {analysis_id}.",
                    )
                )
                return
            self.admin.show(AnalysisDetailsDialog(analysis_id, detail))

        self.run(
            "Analysis details",
            lambda: self.client.get_analysis_run_full(analysis_id),
            got,
            lambda error: self.admin.show(MessageDialog("Analysis details failed", error)),
        )

    def change_password(self) -> None:
        """Set or clear the selected user's password."""
        user_id = self.selected_id
        if not user_id:
            self.admin.show(MessageDialog("No user selected", "Select a user row first."))
            return
        is_admin = bool(self.records.get(user_id, {}).get("is_admin"))

        def done(password: str, cleared: bool) -> None:
            payload = {
                "user_id": user_id,
                "password": "" if cleared else password,
                "requester_id": self.admin.login_user or self.admin.user,
            }
            self.run(
                "Change password",
                lambda: self.client.save_user(payload),
                lambda _r: self.say(
                    f"Password {'cleared' if cleared else 'updated'} for '{user_id}'."
                ),
                lambda error: self.admin.show(
                    MessageDialog("Error", f"Could not change password: {error}")
                ),
            )

        self.admin.show(PasswordDialog(user_id, is_admin, done, self.admin.show))

    def jump_to_branch(self) -> None:
        """Create a branch at a past operation and activate it for the selected user."""
        user_id = self.selected_id
        if not user_id:
            self.admin.show(MessageDialog("No user selected", "Select a user row first."))
            return

        def go(values: dict) -> None:
            def call():
                branch = self.client.jump_user_to_operation(**values) or {}
                return branch, self._list()

            def done(result: tuple[dict, list[dict]]) -> None:
                branch, records = result
                self._loaded((records, self.fk_options))
                self.admin.show(
                    MessageDialog(
                        "Success",
                        f"User '{user_id}' jumped to branch '{branch.get('name', '')}'.",
                    )
                )

            self.run(
                "Jump to branch",
                call,
                done,
                lambda error: self.admin.show(
                    MessageDialog("Error", f"Could not create time branch: {error}")
                ),
            )

        self.admin.show(JumpBranchDialog(user_id, go))

    def set_head(self) -> None:
        """Move the selected branch's head to an operation (empty: none)."""
        branch_uuid = self.selected_id
        if not branch_uuid:
            self.admin.show(MessageDialog("No branch selected", "Select a branch row first."))
            return

        def apply(op_id: str) -> None:
            def call():
                self.client.update_branch_head(branch_uuid, op_id or None)
                return self._list()

            def done(records: list[dict]) -> None:
                self._loaded((records, self.fk_options))
                self.say(f"Branch {branch_uuid} head updated.")

            self.run(
                "Set head",
                call,
                done,
                lambda error: self.admin.show(MessageDialog("Update failed", error)),
            )

        self.admin.show(
            TextDialog(
                "Set branch head",
                "Operation ID (leave empty to reset to None):",
                apply,
                value=str(self.records.get(branch_uuid, {}).get("head_operation_id") or ""),
                label="Operation ID",
            )
        )

    def close(self) -> None:
        if self._preview_dir is not None:
            self._preview_dir.cleanup()
            self._preview_dir = None
