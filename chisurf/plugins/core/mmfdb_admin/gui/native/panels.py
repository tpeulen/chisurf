"""The aggregate and workflow panels of the native MMFDB Admin (Qt-free).

Each class is the model one ``view.json`` panel of ``admin_panels.view.json`` is
drawn over: Overview, All items, Measurements, Sample Metadata, Import / Export,
eLabFTW, Studies, Protocols, Lifecycle, Calibrations, Reagent Lots and Pipelines.
They do what the Qt tool's tabs and ``*_view.py`` widgets do, through the same
client calls; every call runs off the drawing thread (:meth:`Panel.run`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Panel, cell, rows_of
from .dialogs import MessageDialog

# ── Overview ────────────────────────────────────────────────────────────


def connection_mode_label(client: Any) -> str:
    """Human-readable connection mode (embedded / remote / in-process)."""
    if getattr(client, "inprocess", False):
        return "in-process (embedded, no socket)"
    if str(getattr(client, "mode", "embedded")) == "remote":
        return "remote (standalone server, HTTP JSON-RPC)"
    return "embedded (local server, ZMQ)"


def connection_endpoint_label(client: Any) -> str:
    """The endpoint the client talks to, formatted per transport."""
    if getattr(client, "inprocess", False):
        return "in-process dispatcher"
    if str(getattr(client, "mode", "embedded")) == "remote":
        return str(getattr(client, "base_url", "—"))
    return f"{getattr(client, 'host', '127.0.0.1')}:{getattr(client, 'cmd_port', '—')}"


def database_type_label(status: dict) -> str:
    """The server's SQL dialect and (redacted) location."""
    dialect = str(status.get("database_dialect") or "—")
    pretty = {"sqlite": "SQLite", "postgresql": "PostgreSQL"}.get(dialect, dialect)
    location = status.get("database_location")
    return f"{pretty} — {location}" if location else pretty


def overview_text(client: Any, status: dict, samples: list[dict]) -> str:
    """The Overview report: connection, counts and quality warnings (the Qt text, verbatim)."""
    parts = [
        "=== MMFDB Connection ===",
        "",
        f"  Mode:          {connection_mode_label(client)}",
        f"  Endpoint:      {connection_endpoint_label(client)}",
        f"  Database:      {database_type_label(status)}",
        f"  Object store:  {status.get('object_store_backend', '—')}",
        "",
        "=== MMFDB Database Overview ===",
        "",
        f"  User DB:       {status.get('user_database', '—')}",
        f"  Source DB:     {status.get('source_database', '—')}",
        f"  Schema:        {status.get('schema_version', '?')}",
        f"  Samples:       {status.get('sample_count', '?')}",
        f"  Experiments:   {status.get('experiment_count', '?')}",
        f"  Raw data:      {status.get('raw_data_count', '?')}",
        f"  Processed:     {status.get('processed_run_count', '?')}",
        f"  Users:         {status.get('user_count', '?')}",
        f"  Devices:       {status.get('device_count', '?')}",
        f"  Prov. edges:   {status.get('provenance_edge_count', '?')}",
        "",
    ]
    warnings = [
        f"  Warning: sample '{s.get('sample_id', '')}' has no description"
        for s in samples
        if not s.get("description")
    ]
    if warnings:
        parts += ["=== Quality Warnings ===", *warnings, ""]
    else:
        parts += ["No quality warnings detected.", ""]
    return "\n".join(parts)


class OverviewPanel(Panel):
    key = "overview"
    name = "Overview"
    description = "The connection, the database's counts and quality warnings."

    def __init__(self, admin: Any) -> None:
        super().__init__(admin)
        self.text = "Connect to an MMFDB server to see its overview."

    def refresh(self) -> None:
        client = self.client

        def fetch():
            status = client.status() or {}
            try:
                samples = client.list_samples()
            except Exception:  # noqa: BLE001 - the warnings are optional
                samples = []
            return overview_text(client, status, samples)

        def failed(error: str) -> None:
            self.text = f"Failed to load overview: {error}"

        self.run("Overview", fetch, lambda text: setattr(self, "text", text), failed)

    def overview(self) -> str:
        return self.text

    def refresh_overview(self) -> None:
        self.refresh()


# ── All items ───────────────────────────────────────────────────────────

#: ``(type, client listing, id key, label key, summary keys)`` of the All items table.
ALL_ITEMS_SOURCES: tuple[tuple[str, str, str, str, tuple[str, ...]], ...] = (
    ("sample", "list_samples", "sample_id", "description", ("project_id", "sample_uuid")),
    ("experiment", "list_experiments", "experiment_id", "sample_id",
     ("experiment_type", "project_id", "status")),
    ("user", "list_users", "user_id", "display_name", ("email", "affiliation", "role")),
    ("device", "list_devices", "device_id", "name", ("device_type", "model", "serial_number")),
    ("probe", "list_probes", "probe_id", "chromophore_name", ("category", "probe_origin")),
    ("branch", "list_branches", "branch_uuid", "name", ("parent_branch_uuid", "head_operation_id")),
    ("experiment_type", "list_experiment_types", "type_id", "name", ("category",)),
    ("setup", "setups", "setup_id", "name", ("instrument_type",)),
    ("raw_data", "list_raw_data", "raw_data_id", "data_type", ("storage_mode", "experiment_id")),
    ("processing_run", "list_processing_runs", "processing_id", "processing_type",
     ("status", "experiment_id")),
    ("processed_data", "list_processed_data", "processed_data_id", "product_type",
     ("product_type", "processing_id")),
    ("analysis", "list_analysis_runs", "analysis_id", "model_name",
     ("analysis_type", "experiment_id")),
    ("project", "list_projects", "project_id", "name", ("experiment_id", "created_at")),
)

#: All items types whose entity panel has another key.
ALL_ITEMS_ALIAS = {"processed_data": "processed_product"}


def summarise(item: dict, keys: tuple[str, ...]) -> str:
    """A one-line summary: ``key=value`` of the keys that have a value."""
    return ", ".join(f"{k}={item.get(k)}" for k in keys if item.get(k))


class AllItemsPanel(Panel):
    key = "all_items"
    name = "All items"
    description = "Every record of every type in one table; a double click opens it in its panel."

    def __init__(self, admin: Any) -> None:
        super().__init__(admin)
        self.rows: list[dict] = []
        self.type_filter = "all"
        self.search = ""

    def type_options(self) -> list[str]:
        return ["all"] + [s[0] for s in ALL_ITEMS_SOURCES]

    def refresh(self) -> None:
        client = self.client

        def fetch():
            rows = []
            for kind, lister, id_key, label_key, keys in ALL_ITEMS_SOURCES:
                try:
                    if lister == "setups":
                        items = client._call("mmfdb.setups.list").get("setups", [])
                    else:
                        items = getattr(client, lister)() or []
                except Exception:  # noqa: BLE001 - a type the user may not list is skipped
                    items = []
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    item_id = str(item.get(id_key, "") or "")
                    rows.append(
                        {
                            "_row": f"{kind}:{item_id}:{len(rows)}",
                            "type": kind,
                            "id": item_id,
                            "label": str(item.get(label_key, "") or ""),
                            "details": summarise(item, keys),
                        }
                    )
            return rows

        self.run("All items", fetch, self._loaded, self.failed("All items"))

    def _loaded(self, rows: list[dict]) -> None:
        self.rows = rows

    def visible_rows(self) -> list[dict]:
        query = self.search.strip().lower()
        out = []
        for row in self.rows:
            if self.type_filter != "all" and row["type"] != self.type_filter:
                continue
            if query and not any(query in str(v).lower() for k, v in row.items() if k != "_row"):
                continue
            out.append(row)
        return out

    def count_text(self) -> str:
        return f"{len(self.visible_rows())} / {len(self.rows)}"

    def open_item(self, record: dict) -> None:
        """Double click: open the record in its entity panel."""
        kind = str((record or {}).get("type", ""))
        item_id = str((record or {}).get("id", ""))
        target = ALL_ITEMS_ALIAS.get(kind, kind)
        if item_id and target in self.admin.registry:
            self.admin.jump(target, item_id)

    def refresh_items(self) -> None:
        self.refresh()

    def status_line(self) -> str:
        return f"All items: {self.count_text()}"


# ── Measurements ────────────────────────────────────────────────────────

MEASUREMENT_KINDS = ("All", "Raw data", "Processing runs", "Processed products")


class MeasurementsPanel(Panel):
    key = "measurements"
    name = "Measurements"
    description = "Raw data, processing runs and processed products in one table."

    def __init__(self, admin: Any) -> None:
        super().__init__(admin)
        self.kind = "All"
        self.search = ""
        self.rows: list[dict] = []

    def kind_options(self) -> list[str]:
        return list(MEASUREMENT_KINDS)

    def refresh(self) -> None:
        client = self.client

        def fetch():
            sources = (
                ("Raw", "raw_data_id", client.list_raw_data),
                ("Processing", "processing_id", client.list_processing_runs),
                ("Processed", "processed_data_id", client.list_processed_data),
            )
            rows = []
            for kind, id_key, lister in sources:
                try:
                    items = lister() or []
                except Exception:  # noqa: BLE001
                    items = []
                for item in items:
                    rows.append(
                        {
                            "_row": f"{kind}:{len(rows)}",
                            "kind": kind,
                            "id": str(item.get(id_key, "")),
                            "sample": str(item.get("sample_id", "") or ""),
                            "experiment": str(item.get("experiment_id", "") or ""),
                            "status": str(item.get("status", "") or ""),
                            "created": str(item.get("created_at", "") or item.get("acquired_at", "") or ""),
                            "location": str(
                                item.get("file_path", "")
                                or item.get("url", "")
                                or item.get("folder_path", "")
                                or item.get("location", "")
                                or ""
                            ),
                            "project": str(item.get("project_id", "") or ""),
                            "sample_qa": str(item.get("sample_quality_status", "") or ""),
                        }
                    )
            return rows

        self.run("Measurements", fetch, self._loaded, self.failed("Measurements"))

    def _loaded(self, rows: list[dict]) -> None:
        self.rows = rows
        self.say(f"Measurements: {len(self.visible_rows())} rows")

    def visible_rows(self) -> list[dict]:
        wanted = {
            "Raw data": "Raw",
            "Processing runs": "Processing",
            "Processed products": "Processed",
        }.get(self.kind)
        query = self.search.strip().lower()
        out = []
        for row in self.rows:
            if wanted and row["kind"] != wanted:
                continue
            haystack = (row["kind"] + row["id"] + row["sample"] + row["project"]).lower()
            if query and query not in haystack:
                continue
            out.append(row)
        return out

    def refresh_measurements(self) -> None:
        self.refresh()

    def status_line(self) -> str:
        return f"Measurements: {len(self.visible_rows())} rows"


# ── Sample Metadata ─────────────────────────────────────────────────────


class MetadataPanel(Panel):
    """Per-sample key / value / details rows (``flr_sample_key_value``)."""

    key = "metadata"
    name = "Sample Metadata"
    description = "The metadata key / value pairs of one sample, with the mmCIF key catalogue."

    def __init__(self, admin: Any) -> None:
        super().__init__(admin)
        self.samples: list[tuple[str, str]] = []
        self.sample_id = ""
        self.rows: list[dict] = []
        self.selected_row = ""
        self.detail_key = ""
        self.detail_value = ""
        self.detail_details = ""
        self._catalogue: list[str] | None = None
        #: Values already stored for a key in any sample, for the value suggestions.
        self.known_values: dict[str, list[str]] = {}
        self._next = 0

    # catalogue
    def catalogue(self) -> list[str]:
        if self._catalogue is None:
            from chisurf.core.fio.mmcif.metadata_keys import all_metadata_keys

            self._catalogue = list(all_metadata_keys())
        extra = [r["key"] for r in self.rows if r["key"] and r["key"] not in self._catalogue]
        return [""] + extra + self._catalogue

    def key_options(self) -> list[tuple[str, str]]:
        return [(k, k or "(pick a key from the catalogue)") for k in self.catalogue()]

    def key_help(self) -> str:
        from chisurf.core.fio.mmcif.metadata_keys import key_description

        if not self.detail_key:
            return "Pick a key from the mmCIF catalogue (type to filter), or type one in the table."
        return f"{self.detail_key}: {key_description(self.detail_key) or 'no description in the dictionary.'}"

    def value_options(self) -> list[tuple[str, str]]:
        values = self.known_values.get(self.detail_key, [])
        return [("", "(values stored for this key)")] + [(v, v) for v in values]

    @property
    def suggested_value(self) -> str:
        return ""

    @suggested_value.setter
    def suggested_value(self, value: str) -> None:
        if value:
            self.detail_value = value

    def sample_options(self) -> list[tuple[str, str]]:
        return [("", "(select a sample)")] + self.samples

    # loading
    def refresh(self) -> None:
        client = self.client

        def fetch():
            samples = client.list_samples() or []
            known: dict[str, list[str]] = {}
            for s in samples:
                sid = s.get("sample_id", "")
                try:
                    sample = client.get_sample(sid) or {}
                except Exception:  # noqa: BLE001
                    continue
                for kv in sample.get("key_values") or []:
                    value = str(kv.get("value", "") or "")
                    if value and value not in known.setdefault(kv.get("key", ""), []):
                        known[kv.get("key", "")].append(value)
            return samples, known

        def done(result) -> None:
            samples, known = result
            self.known_values = known
            self.samples = [
                (str(s.get("sample_id", "")), f"{s.get('sample_id', '')} — {s.get('description') or s.get('sample_id', '')}")
                for s in samples
            ]
            if self.sample_id:
                self.load_sample(self.sample_id)

        self.run("Samples", fetch, done, self.failed("Load"))

    def choose_sample(self, sample_id: str) -> None:
        """The sample picker changed."""
        if sample_id:
            self.load_sample(sample_id)

    def load_sample(self, sample_id: str) -> None:
        """Load a sample's metadata (also the jump from another panel)."""
        self.sample_id = str(sample_id)
        sid = self.sample_id

        def done(sample: dict) -> None:
            self.rows = []
            for kv in (sample or {}).get("key_values") or []:
                self._add(str(kv.get("key", "") or ""), str(kv.get("value", "") or ""),
                          str(kv.get("details", "") or ""))
            self.selected_row = ""
            self.say(f"Sample {sid}: {len(self.rows)} metadata keys")

        self.run(
            f"Metadata of {sid}",
            lambda: self.client.get_sample(sid),
            done,
            lambda error: self.say(f"Failed to load sample '{sid}'"),
        )

    def jump_to(self, record_id: str) -> None:
        self.load_sample(record_id)

    def _add(self, key: str, value: str, details: str) -> dict:
        self._next += 1
        row = {"_row": str(self._next), "key": key, "value": value, "details": details}
        self.rows.append(row)
        return row

    # table
    def metadata_rows(self) -> list[dict]:
        return self.rows

    def edited(self, record: dict, key: str, value: Any) -> None:
        record[key] = str(value)
        if record.get("_row") == self.selected_row:
            self._show(record)

    def select_row(self, record: dict | None) -> None:
        if record is None:
            return
        self.selected_row = str(record.get("_row", ""))
        self._show(record)

    def _show(self, record: dict) -> None:
        self.detail_key = record.get("key", "")
        self.detail_value = record.get("value", "")
        self.detail_details = record.get("details", "")

    def _selected(self) -> dict | None:
        return next((r for r in self.rows if r["_row"] == self.selected_row), None)

    # actions
    def enabled(self, name: str) -> bool:
        if not self.admin.connected:
            return False
        if name in ("apply_to_row", "delete_row"):
            return self._selected() is not None
        if name in ("save_all", "add_row"):
            return bool(self.sample_id)
        return True

    def apply_to_row(self) -> None:
        row = self._selected()
        if row is None:
            self.say("Select a metadata row first.")
            return
        row.update(key=self.detail_key.strip(), value=self.detail_value.strip(),
                   details=self.detail_details.strip())
        self.say("Detail applied to row.")

    def add_row(self) -> None:
        row = self._add("", "", "")
        self.selected_row = row["_row"]
        self._show(row)

    def delete_row(self) -> None:
        row = self._selected()
        if row is not None:
            self.rows.remove(row)
            self.selected_row = ""

    def save_all(self) -> None:
        if not self.sample_id:
            self.say("No sample selected.")
            return
        rows = [
            {"key": r["key"], "value": r["value"], "details": r["details"]}
            for r in self.rows
            if r["key"].strip()
        ]
        sid = self.sample_id
        self.run(
            "Save metadata",
            lambda: self.client.save_sample_key_values(sid, rows),
            lambda _r: self.say(f"Saved {len(rows)} metadata keys for sample {sid}."),
            lambda error: self.admin.show(MessageDialog("Save failed", error)),
        )

    def refresh_samples(self) -> None:
        self.refresh()

    def status_line(self) -> str:
        return self.message or "Select a sample to edit its metadata."


# ── Import / Export ─────────────────────────────────────────────────────


class ImportExportPanel(Panel):
    key = "import_export"
    name = "Import / Export"
    description = "Import PDBx / PDB-IHM / FLR CIF files; export a sample as FLR CIF or the sample table."

    def __init__(self, admin: Any) -> None:
        super().__init__(admin)
        self.path = ""
        self.preview = ""

    def preview_text(self) -> str:
        return self.preview

    def enabled(self, name: str) -> bool:
        if name == "browse":
            return True
        return self.admin.connected

    def browse(self) -> None:
        self.admin.request_file(
            "Import PDBx/PDB-IHM/FLR CIF",
            "open",
            "",
            "CIF/mmCIF files (*.cif *.mmcif);;All files (*)",
            lambda path: setattr(self, "path", path),
        )

    def import_file(self) -> None:
        """Import the file in the path field (or ask for one)."""
        if not self.path.strip():
            self.admin.request_file(
                "Import PDBx/PDB-IHM/FLR CIF",
                "open",
                "",
                "CIF/mmCIF files (*.cif *.mmcif);;All files (*)",
                self._import,
            )
            return
        self._import(self.path.strip())

    def _import(self, path: str) -> None:
        self.path = path

        def done(summary: Any) -> None:
            self.preview = str(summary)
            self.say(f"Imported {Path(path).name}.")
            self.admin.refresh()

        self.run("Import", lambda: self.client.import_file(path), done, self.failed("Import"))

    def export_selected_sample(self) -> None:
        self.admin.export_selected_sample()

    def preview_cif(self) -> None:
        """Show the FLR CIF of the selected sample below."""
        sample_id = self.admin.selected_sample_id()
        if not sample_id:
            self.say("Select a sample to preview")
            return

        def fetch():
            result = self.client.export_sample(sample_id) or {}
            text = result.get("text", "")
            if not text and result.get("output_path"):
                text = Path(result["output_path"]).read_text(encoding="utf-8")
            return text

        def done(text: str) -> None:
            self.preview = text
            self.say(f"CIF preview for {sample_id}")

        self.run(
            "Preview CIF",
            fetch,
            done,
            lambda error: self.admin.show(MessageDialog("Preview failed", error)),
        )

    def export_table(self) -> None:
        def save(path: str) -> None:
            self.run(
                "Export table",
                lambda: self.client.export_table(path),
                lambda result: self.say(f"Exported {(result or {}).get('output_path', path)}"),
                self.failed("Export"),
            )

        self.admin.request_file(
            "Export sample table",
            "save",
            "samples.csv",
            "CSV/Excel files (*.csv *.tsv *.xlsx);;All files (*)",
            save,
        )


# ── eLabFTW ─────────────────────────────────────────────────────────────


class ElabPanel(Panel):
    """Connect to eLabFTW, browse and import its experiments, export ours.

    The API key is kept in memory only and cleared as soon as a connection
    attempt starts; the backend returns an opaque handle bound to this user.
    """

    key = "elabftw"
    name = "eLabFTW"
    description = "Synchronise experiments with an eLabFTW electronic lab notebook."

    def __init__(self, admin: Any) -> None:
        super().__init__(admin)
        self.endpoint = ""
        self.api_key = ""
        self.timeout = 15.0
        self.verify_tls = True
        self.allow_http = False
        self.connection_id: str | None = None
        self.query = ""
        self.remote: list[dict] = []
        self.conflict = "skip"
        self.sample_id = ""
        self.local: list[tuple[str, str]] = []
        self.local_experiment = ""
        self.export_mode = "create"
        self.remote_id = 1
        self.busy = False
        self.message = "Not connected"

    def ensure_loaded(self) -> None:
        self.loaded = True

    def status_text(self) -> str:
        return self.message

    def local_options(self) -> list[tuple[str, str]]:
        return self.local or [("", "(connect to list experiments)")]

    def enabled(self, name: str) -> bool:
        connected = self.connection_id is not None
        ready = not self.busy and self.admin.connected
        if name == "connect_remote":
            return ready and not connected
        if name in ("disconnect_remote", "refresh_remote", "import_checked"):
            return ready and connected
        if name == "export_selected":
            return ready and connected and bool(self.local)
        if name == "remote_id":
            return ready and connected and self.export_mode == "update"
        return True

    def _go(self, label: str, fn, done, redact: tuple[str, ...] = ()) -> None:
        self.busy = True

        def ok(result: Any) -> None:
            self.busy = False
            done(result)

        def bad(error: str) -> None:
            self.busy = False
            self.message = f"eLabFTW error: {error}"

        self.run(label, fn, ok, bad, redact)

    def connect_remote(self) -> None:
        endpoint, api_key = self.endpoint.strip(), self.api_key
        if not endpoint or not api_key:
            self.message = "Endpoint and API key are required."
            return
        self.api_key = ""
        timeout, verify, allow = float(self.timeout), bool(self.verify_tls), bool(self.allow_http)
        self._go(
            "Connect eLabFTW",
            lambda: self.client.connect_elabftw(
                endpoint, api_key, timeout=timeout, verify_tls=verify, allow_insecure_http=allow
            ),
            self._connected,
            redact=(api_key,),
        )

    def _connected(self, result: dict) -> None:
        self.connection_id = str(result["connection_id"])
        info = result.get("info") or {}
        version = info.get("version") or info.get("elabftw_version") or "unknown"
        self.message = f"Connected to {result.get('endpoint', '')} (eLabFTW {version})"
        self.refresh_remote()

    def disconnect_remote(self) -> None:
        if not self.connection_id:
            return
        cid = self.connection_id

        def done(_r: Any) -> None:
            self.connection_id = None
            self.api_key = ""
            self.remote = []
            self.local = []
            self.message = "Disconnected"

        self._go("Disconnect eLabFTW", lambda: self.client.disconnect_elabftw(cid), done)

    def refresh_remote(self) -> None:
        if not self.connection_id:
            return
        cid, query = self.connection_id, self.query.strip()

        def done(rows: list[dict]) -> None:
            self.remote = [
                {
                    "_row": str(r.get("id", i)),
                    "checked": False,
                    "id": cell(r.get("id")),
                    "title": cell(r.get("title")),
                    "date": cell(r.get("date")),
                    "status": cell(r.get("status")),
                    "modified": cell(r.get("modified_at")),
                    "tags": ", ".join(str(t) for t in r.get("tags") or []),
                }
                for i, r in enumerate(rows or [])
            ]
            self.message = f"Loaded {len(self.remote)} remote experiments."
            self.refresh_local()

        self._go(
            "List eLabFTW",
            lambda: self.client.list_elabftw_experiments(cid, query=query, page_size=50, max_items=500),
            done,
        )

    def refresh_local(self) -> None:
        def done(rows: list[dict]) -> None:
            self.local = []
            for row in rows or []:
                eid = str(row.get("experiment_id") or "")
                if eid:
                    status = str(row.get("status") or "")
                    self.local.append((eid, f"{eid} — {status}" if status else eid))
            if self.local and self.local_experiment not in {e for e, _ in self.local}:
                self.local_experiment = self.local[0][0]

        self._go("List experiments", self.client.list_experiments, done)

    def remote_rows(self) -> list[dict]:
        return self.remote

    def edited(self, record: dict, key: str, value: Any) -> None:
        if key == "checked":
            record["checked"] = bool(value)

    def import_checked(self) -> None:
        ids = []
        for row in self.remote:
            if row.get("checked"):
                try:
                    ids.append(int(row["id"]))
                except (TypeError, ValueError):
                    continue
        if not ids:
            self.message = "Check at least one remote experiment to import."
            return
        cid, conflict, sample = self.connection_id, self.conflict, self.sample_id.strip() or None

        def done(result: dict) -> None:
            self.message = (
                "Import complete: "
                f"{len(result.get('imported', []))} created, "
                f"{len(result.get('updated', []))} updated, "
                f"{len(result.get('skipped', []))} skipped."
            )
            self.refresh_local()

        self._go(
            "Import eLabFTW",
            lambda: self.client.import_elabftw_experiments(cid, ids, conflict=conflict, sample_id=sample),
            done,
        )

    def export_selected(self) -> None:
        experiment_id = self.local_experiment
        if not experiment_id:
            self.message = "Select an MMFDB experiment to export."
            return
        mode = self.export_mode
        remote_id = int(self.remote_id) if mode == "update" else None
        cid = self.connection_id
        self._go(
            "Export eLabFTW",
            lambda: self.client.export_elabftw_experiment(cid, str(experiment_id), mode=mode, remote_id=remote_id),
            lambda result: setattr(
                self,
                "message",
                f"Export {result.get('mode', mode)} complete: remote experiment {result.get('remote_id')}.",
            ),
        )

    def status_line(self) -> str:
        return self.message

    def close(self) -> None:
        self.api_key = ""


# ── Studies ─────────────────────────────────────────────────────────────


class StudiesPanel(Panel):
    key = "studies"
    name = "Studies"
    description = "Studies: their members (samples, artifacts) and configurable fields."

    def __init__(self, admin: Any) -> None:
        super().__init__(admin)
        self.scope = "all"
        self.studies: list[dict] = []
        self.selected = ""
        self.members: list[dict] = []
        self.fields: list[dict] = []
        self.new_name = ""
        self.member_type = "sample"
        self.member_id = ""
        self.field_key = ""
        self.field_value = ""

    def scope_options(self) -> list[str]:
        return ["all", "mine", "public"]

    def member_type_options(self) -> list[str]:
        return ["sample", "artifact"]

    def set_scope(self, _value: str) -> None:
        self.refresh()

    def refresh(self) -> None:
        scope = self.scope

        def done(studies: list[dict]) -> None:
            self.studies = [
                {
                    "_row": str(s.get("study_id") or ""),
                    "name": str(s.get("name") or ""),
                    "public": "yes" if s.get("is_public") else "no",
                    "study_id": str(s.get("study_id") or ""),
                }
                for s in studies or []
            ]
            if self.selected:
                self._load(self.selected)

        self.run("Studies", lambda: self.client.list_studies(scope), done, self.failed("Studies"))

    def study_rows(self) -> list[dict]:
        return self.studies

    def select_study(self, record: dict | None) -> None:
        sid = str((record or {}).get("study_id", "") or "")
        if sid:
            self.selected = sid
            self._load(sid)

    def _load(self, sid: str) -> None:
        def done(detail: dict) -> None:
            detail = detail or {}
            self.members = rows_of(detail.get("members", []), ("member_type", "member_id", "role"))
            self.fields = [
                {"_row": str(k), "key": str(k), "value": str(v)}
                for k, v in sorted((detail.get("fields") or {}).items())
            ]

        self.run("Study", lambda: self.client.get_study(sid), done, self.failed("Study"))

    def member_rows(self) -> list[dict]:
        return self.members

    def field_rows(self) -> list[dict]:
        return self.fields

    def enabled(self, name: str) -> bool:
        if not self.admin.connected:
            return False
        if name in ("add_member", "set_field"):
            return bool(self.selected)
        return True

    def create_study(self) -> None:
        name = self.new_name.strip()
        if not name:
            self.message = "Enter a study name."
            return

        def done(result: dict) -> None:
            if (result or {}).get("error"):
                self.message = f"Rejected: {result['error']}"
            else:
                self.message = f"Created study {name}."
                self.new_name = ""
            self.refresh()

        self.run("Create study", lambda: self.client.create_study(name), done, self.failed("Create"))

    def add_member(self) -> None:
        sid, member_id, kind = self.selected, self.member_id.strip(), self.member_type
        if not sid or not member_id:
            self.message = "Select a study and enter a member id."
            return

        def done(result: dict) -> None:
            if (result or {}).get("error"):
                self.message = f"Rejected: {result['error']}"
            else:
                self.message = "Member added."
                self.member_id = ""
            self._load(sid)

        self.run("Add member", lambda: self.client.add_study_member(sid, kind, member_id), done,
                 self.failed("Add member"))

    def set_field(self) -> None:
        sid, key, value = self.selected, self.field_key.strip(), self.field_value
        if not sid or not key:
            self.message = "Select a study and enter a field key."
            return

        def done(result: dict) -> None:
            if (result or {}).get("error"):
                self.message = f"Rejected: {result['error']}"
            else:
                self.message = f"Set {key}."
                self.field_key = self.field_value = ""
            self._load(sid)

        self.run("Set field", lambda: self.client.set_study_field(sid, key, value), done,
                 self.failed("Set field"))


# ── Protocols ───────────────────────────────────────────────────────────


class ProtocolsPanel(Panel):
    key = "protocols"
    name = "Protocols"
    description = "Versioned measurement, processing and analysis protocols."

    CATEGORIES = ("measurement", "processing", "analysis")

    def __init__(self, admin: Any) -> None:
        super().__init__(admin)
        self.scope = "all"
        self.protocols: list[dict] = []
        self.selected = ""
        self.versions: list[dict] = []
        self.schema: list[dict] = []
        self.new_name = ""
        self.new_category = "measurement"
        self.new_operation_type = ""

    def scope_options(self) -> list[str]:
        return ["all", "own", "public"]

    def category_options(self) -> list[str]:
        return list(self.CATEGORIES)

    def set_scope(self, _value: str) -> None:
        self.refresh()

    def refresh(self) -> None:
        scope = self.scope

        def done(items: list[dict]) -> None:
            self.protocols = rows_of(items, ("name", "version", "category", "operation_type"))
            for row in self.protocols:
                row["_row"] = str(row["name"])

        self.run("Protocols", lambda: self.client.list_protocols(scope), done, self.failed("Protocols"))

    def protocol_rows(self) -> list[dict]:
        return self.protocols

    def select_protocol(self, record: dict | None) -> None:
        name = str((record or {}).get("name", "") or "")
        if not name:
            return
        self.selected = name

        def fetch():
            versions = self.client.list_protocol_versions(name) or []
            schema = (self.client.get_protocol(name) or {}).get("parameter_schema", []) or []
            return versions, schema

        def done(result) -> None:
            versions, schema = result
            self.versions = rows_of(versions, ("version", "description", "created_at"))
            self.schema = rows_of(schema, ("name", "value_type", "required", "units"))

        self.run("Protocol", fetch, done, self.failed("Protocol"))

    def version_rows(self) -> list[dict]:
        return self.versions

    def schema_rows(self) -> list[dict]:
        return self.schema

    def create_protocol(self) -> None:
        name = self.new_name.strip()
        if not name:
            self.message = "Enter a protocol name."
            return
        category, op = self.new_category, self.new_operation_type.strip() or None

        def done(result: dict) -> None:
            if (result or {}).get("error"):
                self.message = f"Rejected: {result['error']}"
            else:
                self.message = f"Created {name} v{result.get('version')}."
                self.new_name = ""
            self.refresh()

        self.run(
            "Create protocol",
            lambda: self.client.create_protocol(name, category, operation_type=op),
            done,
            self.failed("Create"),
        )


# ── Lifecycle ───────────────────────────────────────────────────────────


class LifecyclePanel(Panel):
    key = "lifecycle"
    name = "Lifecycle"
    description = "An entity's lifecycle state, its history, and an administrator's transition."

    def __init__(self, admin: Any) -> None:
        super().__init__(admin)
        self.definitions: dict = {}
        self.entity_type = ""
        self.entity_id = ""
        self.current: str | None = None
        self.loaded_entity = ("", "")
        self.to_state = ""
        self.reason = ""
        self.history: list[dict] = []

    def refresh(self) -> None:
        def done(defs: dict) -> None:
            self.definitions = defs or {}
            if self.entity_type not in self.definitions and self.definitions:
                self.entity_type = sorted(self.definitions)[0]

        self.run("Lifecycle definitions", self.client.lifecycle_definitions, done,
                 lambda error: setattr(self, "message", f"Could not load lifecycle definitions: {error}"))

    def type_options(self) -> list[str]:
        return sorted(self.definitions)

    def set_entity(self, entity_type: str, entity_id: str) -> None:
        """Pre-select an entity (opening the panel from a record)."""
        self.entity_type = entity_type
        self.entity_id = entity_id

    def state_text(self) -> str:
        return f"Current state: {self.current or '—'}"

    def next_states(self) -> list[str]:
        spec = self.definitions.get(self.loaded_entity[0], {})
        return [to for frm, to in spec.get("transitions", []) if (frm if frm else None) == self.current]

    def to_options(self) -> list[str]:
        return self.next_states() or [""]

    def load(self) -> None:
        etype, eid = self.entity_type, self.entity_id.strip()
        if not eid:
            self.message = "Enter an entity ID."
            return

        def fetch():
            return (
                self.client.lifecycle_state(etype, eid),
                self.client.lifecycle_history(etype, eid) or [],
            )

        def done(result) -> None:
            self.current, history = result
            self.loaded_entity = (etype, eid)
            self.history = rows_of(history, ("from_state", "to_state", "created_at", "reason"))
            states = self.next_states()
            self.to_state = states[0] if states else ""
            self.message = ""

        self.run("Lifecycle", fetch, done, self.failed("Load"))

    def history_rows(self) -> list[dict]:
        return self.history

    def enabled(self, name: str) -> bool:
        if not self.admin.connected:
            return False
        if name == "apply_transition":
            return bool(self.loaded_entity[1]) and bool(self.to_state)
        return True

    def apply_transition(self) -> None:
        etype, eid = self.loaded_entity
        to_state, reason = self.to_state, self.reason.strip()
        if not eid or not to_state:
            self.message = "Pick an entity and a target state."
            return

        def done(result: dict) -> None:
            result = result or {}

            def after(_r=None) -> None:
                if result.get("error"):
                    self.message = f"Rejected: {result['error']}"
                elif result.get("changed"):
                    self.message = f"Transitioned to {result.get('state')}."
                    self.reason = ""
                else:
                    self.message = "No change (already in that state)."

            self.entity_type, self.entity_id = etype, eid
            self.load()
            self.run("Lifecycle", lambda: None, after)

        self.run(
            "Transition",
            lambda: self.client.lifecycle_transition(etype, eid, to_state, reason=reason),
            done,
            self.failed("Transition"),
        )


# ── Calibrations ────────────────────────────────────────────────────────


class CalibrationsPanel(Panel):
    key = "calibrations"
    name = "Calibrations"
    description = "Calibration values (γ, G-factor, R₀, …), user-registered ones, and uses gone stale."

    def __init__(self, admin: Any) -> None:
        super().__init__(admin)
        self.calibrations: list[dict] = []
        self.stale: list[dict] = []
        try:
            from mmfdb.lifecycle.staleness import CALIBRATION_TYPES

            self.types = list(CALIBRATION_TYPES)
        except Exception:  # noqa: BLE001
            self.types = ["forster_radius", "g_factor", "gamma"]
        self.new_type = self.types[0] if self.types else ""
        self.new_value = ""
        self.new_notes = ""

    def type_options(self) -> list[str]:
        return self.types

    def refresh(self) -> None:
        def fetch():
            return self.client.list_calibrations() or [], self.client.stale_calibrations() or []

        def done(result) -> None:
            cals, stale = result
            self.calibrations = rows_of(cals, ("calibration_type", "method", "value", "notes", "artifact_id"), "artifact_id")
            self.stale = rows_of(stale, ("used_by_id", "calibration_type", "used_artifact_id", "latest_artifact_id"))

        self.run("Calibrations", fetch, done, self.failed("Calibrations"))

    def calibration_rows(self) -> list[dict]:
        return self.calibrations

    def stale_rows(self) -> list[dict]:
        return self.stale

    def register(self) -> None:
        try:
            value = float(self.new_value.strip())
        except ValueError:
            self.message = "Enter a numeric value."
            return
        kind, notes = self.new_type, self.new_notes.strip()

        def done(result: dict) -> None:
            if (result or {}).get("error"):
                self.message = f"Rejected: {result['error']}"
            else:
                self.message = f"Registered {kind} = {value}."
                self.new_value = self.new_notes = ""
            self.refresh()

        self.run("Register calibration", lambda: self.client.create_calibration(kind, value, notes=notes),
                 done, self.failed("Register"))


# ── Reagent lots ────────────────────────────────────────────────────────


class ReagentsPanel(Panel):
    key = "reagents"
    name = "Reagent Lots"
    description = "Reagent lots (dyes, buffers, kits, filters …), their expiry, and new lots."

    LOT_KEYS = ("kind", "name", "lot_number", "vendor", "expiry", "lot_id")

    def __init__(self, admin: Any) -> None:
        super().__init__(admin)
        try:
            from mmfdb.samples.reagents import REAGENT_KINDS

            self.kinds = sorted(REAGENT_KINDS)
        except Exception:  # noqa: BLE001
            self.kinds = ["buffer", "fluorophore", "kit", "optical_filter", "other"]
        self.kind_filter = "all"
        self.show_expired = False
        self.lots: list[dict] = []
        self.selected = ""
        self.new_kind = self.kinds[0] if self.kinds else ""
        self.new_name = ""
        self.new_lot_number = ""
        self.new_vendor = ""
        self.new_expiry = ""

    def filter_options(self) -> list[str]:
        return ["all"] + self.kinds

    def kind_options(self) -> list[str]:
        return self.kinds

    def set_filter(self, _value: Any) -> None:
        self.refresh()

    def refresh(self) -> None:
        kind = None if self.kind_filter == "all" else self.kind_filter
        expired = bool(self.show_expired)

        def done(lots: list[dict]) -> None:
            self.lots = rows_of(lots, self.LOT_KEYS, "lot_id")
            self.selected = ""

        self.run("Reagent lots", lambda: self.client.list_reagent_lots(kind=kind, include_expired=expired),
                 done, self.failed("Reagent lots"))

    def lot_rows(self) -> list[dict]:
        return self.lots

    def select_lot(self, record: dict | None) -> None:
        self.selected = str((record or {}).get("_row", "") or "")

    def detail_rows(self) -> list[dict]:
        lot = next((r for r in self.lots if r["_row"] == self.selected), None)
        if lot is None:
            return []
        return [{"_row": k, "field": k, "value": lot[k]} for k in self.LOT_KEYS if lot.get(k) not in ("", None)]

    def create_lot(self) -> None:
        name = self.new_name.strip()
        if not name:
            self.message = "Enter a lot name."
            return
        args = dict(
            kind=self.new_kind,
            name=name,
            lot_number=self.new_lot_number.strip(),
            vendor=self.new_vendor.strip(),
            expiry=self.new_expiry.strip() or None,
        )

        def done(result: dict) -> None:
            if (result or {}).get("error"):
                self.message = f"Rejected: {result['error']}"
            else:
                self.message = f"Created lot {name}."
                self.new_name = self.new_lot_number = self.new_vendor = self.new_expiry = ""
            self.refresh()

        self.run("Create lot", lambda: self.client.create_reagent_lot(**args), done, self.failed("Create"))


# ── Pipelines ───────────────────────────────────────────────────────────


class PipelinesPanel(Panel):
    key = "pipelines"
    name = "Pipelines"
    description = "Registered analysis pipelines: their nodes, wiring and recorded runs."

    def __init__(self, admin: Any) -> None:
        super().__init__(admin)
        self.pipelines: list[dict] = []
        self.selected = ""
        self.nodes: list[dict] = []
        self.edges: list[dict] = []
        self.runs: list[dict] = []

    def refresh(self) -> None:
        def done(items: list[dict]) -> None:
            self.pipelines = rows_of(items, ("name", "version", "description", "pipeline_id"), "pipeline_id")
            self.nodes, self.edges, self.runs = [], [], []
            if not self.pipelines:
                self.message = "No pipelines are registered with this server."

        self.run("Pipelines", self.client.list_pipelines, done, self.failed("Pipelines"))

    def pipeline_rows(self) -> list[dict]:
        return self.pipelines

    def select_pipeline(self, record: dict | None) -> None:
        pid = str((record or {}).get("pipeline_id", "") or "")
        if not pid:
            return
        self.selected = pid

        def fetch():
            detail = self.client.get_pipeline(pid) or {}
            runs = [] if detail.get("error") else (self.client.list_pipeline_runs(pid) or [])
            return detail, runs

        def done(result) -> None:
            detail, runs = result
            if detail.get("error"):
                self.message = str(detail["error"])
                return
            self.nodes = rows_of(detail.get("nodes", []), ("name", "operation_type"))
            self.edges = [
                {
                    "_row": str(i),
                    "from": f"{e.get('source')}.{e.get('source_port')}",
                    "to": f"{e.get('target')}.{e.get('target_port')}",
                }
                for i, e in enumerate(detail.get("edges", []) or [])
            ]
            self.runs = rows_of(runs, ("name", "status", "operation_count", "pipeline_run_id"))

        self.run("Pipeline", fetch, done, self.failed("Pipeline"))

    def node_rows(self) -> list[dict]:
        return self.nodes

    def edge_rows(self) -> list[dict]:
        return self.edges

    def run_rows(self) -> list[dict]:
        return self.runs


__all__ = [
    "ALL_ITEMS_SOURCES",
    "AllItemsPanel",
    "CalibrationsPanel",
    "ElabPanel",
    "ImportExportPanel",
    "LifecyclePanel",
    "MeasurementsPanel",
    "MetadataPanel",
    "OverviewPanel",
    "PipelinesPanel",
    "ProtocolsPanel",
    "ReagentsPanel",
    "StudiesPanel",
    "overview_text",
]

