"""The Spectra panel (optical-component curation) and its Find Duplicates dialog (Qt-free).

The model behind the Qt ``OpticalComponentDock``: the component types of
``optical_components/components.json`` (fluorophores, filters, dichroics,
detectors, light sources), a filterable table with a status column coloured by
value, the selected component's read-only detail form (the type's own
``*.view.json``), its spectra as plot traces (several when rows are ticked), and
the curation actions -- import the reference set, approve, reject, the review
queue, the deterministic triage and the duplicate finder.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..optical_components.duplicates import find_duplicate_groups
from .base import Panel, cell
from .dialogs import ConfirmDialog, Dialog, MessageDialog

HERE = Path(__file__).resolve().parents[1] / "optical_components"

#: Optical property names stored on a probe -> the detail form's attribute.
PROPERTY_MAP = {
    "Cut-On Wavelength (nm)": "cut_on",
    "Cut-Off Wavelength (nm)": "cut_off",
    "Center Wavelength (nm)": "center_wavelength",
    "Bandwidth (nm)": "bandwidth",
    "Optical Density": "optical_density",
    "d25_um2_s": "d25",
    "D25_um2_s": "d25",
    "diffusion_coefficient": "d25",
}

#: Background of a status cell, by value (the Qt colours).
STATUS_COLOURS = {
    "approved": "#d6f5dc",
    "rejected": "#ffdcdc",
    "unverified": "#fff4cc",
    "needs_review": "#ffebc8",
}

STATUS_FILTERS = ("all", "approved", "unverified", "rejected", "needs_review")


def load_components() -> list[dict]:
    """The component types (``components.json``) with each type's detail view spec."""
    registry = json.loads((HERE / "components.json").read_text(encoding="utf-8"))
    for item in registry:
        item["view_spec"] = json.loads((HERE / item["view"]).read_text(encoding="utf-8"))
    return registry


def detail_values(detail: dict) -> dict:
    """A ``fluorophores.get`` response as the detail form's values (properties merged in)."""
    data = dict(detail.get("probe", {}) or {})
    for prop in detail.get("optical_properties", []) or []:
        name = prop.get("property_name", "")
        data[PROPERTY_MAP.get(name, name)] = prop.get("property_value", "")
    return data


class Values:
    """Attribute access over a dict, for a read-only spec form ('' for what is missing)."""

    def __init__(self, data: dict | None = None) -> None:
        self.__dict__["_data"] = dict(data or {})

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__"):
            raise AttributeError(name)
        value = self._data.get(name, "")
        return "" if value is None else str(value)

    def __setattr__(self, name: str, value: Any) -> None:  # read-only form: ignore
        pass


class SpectraPanel(Panel):
    key = "spectra"
    name = "Spectra"
    description = "Curate fluorophores, filters, dichroics, detectors and light sources, with their spectra."

    def __init__(self, admin: Any) -> None:
        super().__init__(admin)
        self.components = load_components()
        self.component = self.components[0]["key"]
        self.search = ""
        self.status_filter = "all"
        self.review_queue = False
        self.rows: list[dict] = []
        self.total: Any = "?"
        self.selected_id = ""
        self.details: dict[str, dict] = {}
        self.values = Values()
        #: The traces the plot draws: the selected probe's, or every ticked one's.
        self.traces: list[dict] = []

    # ── component type ─────────────────────────────────────────────────
    @property
    def active(self) -> dict:
        return next(c for c in self.components if c["key"] == self.component)

    def component_options(self) -> list[tuple[str, str]]:
        return [(c["key"], c["label"]) for c in self.components]

    def set_component(self, _key: str) -> None:
        self.selected_id = ""
        self.details.clear()
        self.values = Values()
        self.traces = []
        self.refresh()

    def status_options(self) -> list[str]:
        return list(STATUS_FILTERS)

    def set_status_filter(self, _value: str) -> None:
        self.review_queue = self.status_filter == "unverified"
        self.refresh()

    def set_search(self, _value: str) -> None:
        self.refresh()

    def toggle_review_queue(self) -> None:
        """Review queue: show only the unverified items (again: everything)."""
        self.review_queue = not self.review_queue
        self.status_filter = "unverified" if self.review_queue else "all"
        self.refresh()

    def review_caption(self) -> str:
        return "Review queue (on)" if self.review_queue else "Review queue"

    def table_columns(self) -> list[dict]:
        columns = [
            {
                "key": "checked",
                "title": "✓",
                "width": 30,
                "editable": True,
                "shade": False,
                "tooltip": "Tick rows to overlay their spectra in the plot.",
            }
        ]
        for title, key in self.active["columns"]:
            column = {"key": key, "title": title, "tooltip": f"{title} ({key})."}
            if key == "verification_status":
                column["background"] = dict(STATUS_COLOURS)
                column["tooltip"] = "Curation status: approved, unverified, rejected or needs_review."
            columns.append(column)
        return columns

    def form_spec(self) -> dict:
        return self.active["view_spec"]

    # ── loading ────────────────────────────────────────────────────────
    def refresh(self) -> None:
        params: dict = {"limit": 500, "offset": 0, "category": list(self.active["categories"])}
        if self.status_filter != "all":
            params["verification_status"] = self.status_filter
        if self.search.strip():
            params["search"] = self.search.strip()
        keys = [key for _title, key in self.active["columns"]]

        def done(result: dict) -> None:
            probes = (result or {}).get("probes", []) or []
            self.total = (result or {}).get("total", "?")
            self.rows = []
            for p in probes:
                row = {key: cell(p.get(key)) for key in keys}
                row["_row"] = str(p.get("probe_id", ""))
                row["checked"] = False
                self.rows.append(row)
            self.message = f"{len(self.rows)} items (of {self.total} total)"
            if self.selected_id and self.selected_id not in {r["_row"] for r in self.rows}:
                self.selected_id = ""
                self.values = Values()
                self.traces = []

        self.run(
            "Spectra",
            lambda: self.client._call("fluorophores.list", params),
            done,
            lambda error: setattr(self, "message", f"Load failed: {error}"),
        )

    def component_rows(self) -> list[dict]:
        return self.rows

    def items_text(self) -> str:
        return self.message

    # ── selection, spectra ─────────────────────────────────────────────
    def _detail(self, probe_id: str, then) -> None:
        if probe_id in self.details:
            then(self.details[probe_id])
            return

        def got(detail: dict) -> None:
            self.details[probe_id] = detail or {}
            then(self.details[probe_id])

        self.run(
            f"Component {probe_id}",
            lambda: self.client._call("fluorophores.get", {"probe_id": int(probe_id)}),
            got,
            lambda error: setattr(self, "message", f"Load failed: {error}"),
        )

    def select_row(self, record: dict | None) -> None:
        probe_id = str((record or {}).get("_row", "") or "")
        if not probe_id or probe_id == self.selected_id:
            return
        self.selected_id = probe_id

        def show(detail: dict) -> None:
            if self.selected_id != probe_id:
                return
            self.values = Values(detail_values(detail))
            self.update_traces()

        self._detail(probe_id, show)

    def checked_ids(self) -> list[str]:
        return [r["_row"] for r in self.rows if r.get("checked")]

    def edited(self, record: dict, key: str, value: Any) -> None:
        if key == "checked":
            record["checked"] = bool(value)
            self.update_traces()

    def update_traces(self) -> None:
        """Plot the ticked components' spectra overlaid, else the selected one's."""
        from chisurf.core.fluorescence.spectrum_traces import overlay_traces, probe_traces

        checked = self.checked_ids()
        if not checked:
            detail = self.details.get(self.selected_id)
            self.traces = probe_traces(detail) if detail else []
            return
        missing = [pid for pid in checked if pid not in self.details]
        if missing:
            for pid in missing:
                self._detail(pid, lambda _d: self.update_traces())
            return
        self.traces = overlay_traces([self.details[pid] for pid in checked])

    # ── actions ────────────────────────────────────────────────────────
    def enabled(self, name: str) -> bool:
        if not self.admin.connected:
            return False
        if name in ("approve", "reject", "ai_triage"):
            return bool(self.selected_id)
        if name == "copy_checked_ids":
            return bool(self.checked_ids())
        return True

    def import_reference_set(self) -> None:
        def call():
            return self.client._call("fluorophores.import_reference_set", {"mark_verified": False})

        def done(result: dict) -> None:
            self.say(
                f"Imported: {result.get('probes', 0)} probes, {result.get('spectra', 0)} spectra, "
                f"{result.get('optical_properties', 0)} optical properties"
            )
            self.refresh()

        self.admin.show(
            ConfirmDialog(
                "Import reference set",
                "Import reference set data from the bundled database?\n\n"
                "All imported items will be marked as unverified.",
                lambda: self.run("Import reference set", call, done, self.failed("Import")),
            )
        )

    def _curate(self, method: str, verb: str, what: str) -> None:
        probe_id = self.selected_id
        if not probe_id:
            return
        verified_by = self.admin.login_user or "admin"

        def done(_r: Any) -> None:
            self.details.pop(probe_id, None)
            self.say(f"{verb} item {probe_id}")
            self.refresh()

        self.run(
            f"{verb} {probe_id}",
            lambda: self.client._call(method, {"probe_id": int(probe_id), "verified_by": verified_by}),
            done,
            self.failed(what),
        )

    def approve(self) -> None:
        self._curate("fluorophores.approve", "Approved", "Approve")

    def reject(self) -> None:
        self._curate("fluorophores.reject", "Rejected", "Reject")

    def ai_triage(self) -> None:
        probe_id = self.selected_id
        if not probe_id:
            return

        def done(result: dict) -> None:
            issues = (result or {}).get("issues", [])
            quality = (result or {}).get("proposed_quality", "unknown")
            if issues:
                text = "Issues found (queued for review):\n  - " + "\n  - ".join(issues)
            else:
                text = (
                    f"No issues found — proposed quality: {quality}.\n\n"
                    "Queued for review; use Approve to confirm."
                )
            self.admin.show(MessageDialog("AI Triage Result", text))
            self.refresh()

        self.run(
            "AI triage",
            lambda: self.client._call("fluorophores.ai_triage", {"probe_id": int(probe_id)}),
            done,
            self.failed("AI triage"),
        )

    def find_duplicates(self) -> None:
        categories = set(self.active.get("categories", []))

        def call():
            probes = self.client._call("fluorophores.find_duplicates", {}).get("probes", []) or []
            if categories:
                probes = [p for p in probes if p.get("category", "other") in categories]
            if not probes:
                return None
            return find_duplicate_groups(probes) or []

        def done(groups: list | None) -> None:
            if groups is None:
                self.admin.show(MessageDialog("Find Duplicates", "No probes found for the active category."))
                self.say("No probes found")
                return
            if not groups:
                self.admin.show(MessageDialog("Find Duplicates", "No potential duplicates found."))
                self.say("No duplicates found")
                return
            self.say(f"{len(groups)} potential duplicate groups")
            self.admin.show(DuplicatesDialog(groups, self))

        self.say("Finding duplicates…")
        self.run("Find duplicates", call, done, self.failed("Find duplicates"))

    def copy_checked_ids(self) -> None:
        ids = self.checked_ids()
        if ids:
            self.admin.copy(", ".join(ids))
            self.say(f"Copied {len(ids)} IDs")
        else:
            self.say("No checked items")

    def _set_checks(self, how: str) -> None:
        for row in self.rows:
            row["checked"] = {"all": True, "none": False}.get(how, not row.get("checked"))
        self.update_traces()

    def check_all(self) -> None:
        self._set_checks("all")

    def uncheck_all(self) -> None:
        self._set_checks("none")

    def invert_checks(self) -> None:
        self._set_checks("invert")

    def refresh_list(self) -> None:
        self.refresh()

    def status_line(self) -> str:
        return self.message


class DuplicatesDialog(Dialog):
    """Review groups of probably-duplicate probes and merge them into a primary.

    The groups are a tree in one table: a group row (ticked to merge it) and its
    probes under it, one of them the **primary** (the longest name, at first).
    Picking a row shows that group's spectra overlaid; merging keeps the primary's
    spectra and fills missing ones from the duplicates (overlaps are ignored).
    """

    spec = "duplicates"
    size = (1000.0, 600.0)

    def __init__(self, groups: list[dict], panel: SpectraPanel) -> None:
        super().__init__("Find and Merge Duplicates")
        self.panel = panel
        self.groups = [dict(g) for g in groups]
        self.primary: dict[str, int] = {}
        for g in self.groups:
            longest = max(g["probes"], key=lambda p: len(p.get("chromophore_name", "")))
            self.primary[g["norm_name"]] = longest["probe_id"]
        self.checked: set[str] = set()
        self.current = ""
        self.selected_probe: int | None = None
        self.spectra: dict[str, list[dict]] = {}
        self.expanded: set[str] = {f"g:{g['norm_name']}" for g in self.groups}

    def info_text(self) -> str:
        return (
            "Potential duplicates identified by name similarity. Select the primary probe for each "
            "group in the tree below. Use the panel on the right to compare spectra for the "
            "selected group. When you merge, the primary probe keeps its spectra and missing ones "
            "are filled from duplicates. Overlaps are ignored."
        )

    def tree_rows(self) -> list[dict]:
        rows = []
        for g in self.groups:
            name = g["norm_name"]
            rows.append(
                {
                    "_row": f"g:{name}",
                    "_parent": "",
                    "primary": name in self.checked,
                    "id": "",
                    "name": f"Group: {name} ({len(g['probes'])} items)",
                    "category": "",
                    "source": "",
                    "status": "",
                }
            )
            for p in g["probes"]:
                rows.append(
                    {
                        "_row": f"p:{name}:{p['probe_id']}",
                        "_parent": f"g:{name}",
                        "primary": self.primary.get(name) == p["probe_id"],
                        "id": str(p["probe_id"]),
                        "name": p.get("chromophore_name", ""),
                        "category": p.get("category", ""),
                        "source": p.get("source", "") or "",
                        "status": p.get("verification_status", "") or "",
                    }
                )
        return rows

    def edited(self, record: dict, key: str, value: Any) -> None:
        """Tick a group to merge it; tick a probe to make it its group's primary."""
        row = str(record.get("_row", ""))
        if key != "primary":
            return
        if row.startswith("g:"):
            name = row[2:]
            if value:
                self.checked.add(name)
            else:
                self.checked.discard(name)
        elif row.startswith("p:") and value:
            _, name, pid = row.split(":", 2)
            self.primary[name] = int(pid)

    def _group_of(self, row: str) -> str:
        if row.startswith("g:"):
            return row[2:]
        if row.startswith("p:"):
            return row.split(":", 2)[1]
        return ""

    def select_row(self, record: dict | None) -> None:
        row = str((record or {}).get("_row", "") or "")
        name = self._group_of(row)
        if not name:
            return
        self.current = name
        self.selected_probe = int(row.split(":", 2)[2]) if row.startswith("p:") else None
        if name in self.spectra:
            return
        group = next((g for g in self.groups if g["norm_name"] == name), None)
        if group is None:
            return
        pids = [p["probe_id"] for p in group["probes"]]
        self.panel.run(
            "Duplicate spectra",
            lambda: self.panel.client._call("fluorophores.get_spectra_batch", {"probe_ids": pids}),
            lambda res: self.spectra.__setitem__(name, (res or {}).get("spectra", []) or []),
            lambda _e: self.spectra.__setitem__(name, []),
        )

    def comparison(self) -> list[tuple[str, list[dict]]]:
        """``(spectrum type, traces)`` of the current group: the primary or picked probe bold."""
        group = next((g for g in self.groups if g["norm_name"] == self.current), None)
        if group is None:
            return []
        probes = group["probes"]
        palette = [(230, 200, 0), (0, 190, 210), (210, 0, 210), (0, 170, 0), (220, 60, 60)]
        spectra = [
            s for s in self.spectra.get(self.current, []) if s.get("wavelengths") and s.get("intensity_values")
        ]
        out = []
        for stype in sorted({s["spectrum_type"] for s in spectra}):
            traces = []
            for s in spectra:
                if s["spectrum_type"] != stype:
                    continue
                pid = s["probe_id"]
                probe = next((p for p in probes if p["probe_id"] == pid), None)
                index = probes.index(probe) if probe in probes else 0
                picked = self.selected_probe
                traces.append(
                    {
                        "name": f"ID {pid} - {probe.get('chromophore_name') if probe else ''}",
                        "x": s["wavelengths"],
                        "y": s["intensity_values"],
                        "color": palette[index % len(palette)] if picked in (None, pid) else (150, 150, 150),
                        "width": 3 if picked == pid else (2 if picked is None else 1),
                        "style": "solid" if picked in (None, pid) else "dash",
                    }
                )
            out.append((stype, traces))
        return out

    def metadata_text(self) -> str:
        group = next((g for g in self.groups if g["norm_name"] == self.current), None)
        if group is None:
            return "Pick a group or a probe to compare its spectra."
        lines = []
        for p in group["probes"]:
            lines.append(f"ID {p['probe_id']} - {p.get('chromophore_name', '')}")
            lines.append(f"  Category: {p.get('category', '')}   Source: {p.get('source', '') or ''}")
            for name, value in (p.get("optical_properties") or {}).items():
                lines.append(f"  {name.replace('_', ' ').title()}: {value}")
        return "\n".join(lines)

    def merge_caption(self) -> str:
        n = len(self.checked)
        return f"Merge {n} Checked Group{'s' if n > 1 else ''}" if n else "Merge Checked Groups"

    def enabled(self, name: str) -> bool:
        if name == "merge_selected":
            return bool(self.current)
        if name == "merge_checked":
            return bool(self.checked)
        return True

    def merge_selected(self) -> None:
        if self.current:
            self._merge([self.current])

    def merge_checked(self) -> None:
        self._merge(sorted(self.checked))

    def _merge(self, names: list[str]) -> None:
        jobs = []
        for g in self.groups:
            name = g["norm_name"]
            primary = self.primary.get(name)
            if name not in names or not primary:
                continue
            duplicates = [p["probe_id"] for p in g["probes"] if p["probe_id"] != primary]
            if duplicates:
                jobs.append((name, primary, duplicates))
        if not jobs:
            return
        client = self.panel.client

        def call():
            merged, errors = [], 0
            for name, primary, duplicates in jobs:
                try:
                    client._call("fluorophores.merge", {"primary_id": primary, "duplicate_ids": duplicates})
                    merged.append(name)
                except Exception:  # noqa: BLE001 - counted and reported
                    errors += 1
            return merged, errors

        def done(result) -> None:
            merged, errors = result
            self.groups = [g for g in self.groups if g["norm_name"] not in merged]
            self.checked -= set(merged)
            if self.current in merged:
                self.current = ""
            admin = self.panel.admin
            if merged:
                admin.show(MessageDialog("Merge Complete", f"Successfully merged {len(merged)} group(s)."))
            if errors:
                admin.show(MessageDialog("Merge Errors", f"Failed to merge {errors} group(s)."))
            if not self.groups:
                self.close()
            self.panel.refresh()

        self.panel.run("Merge duplicates", call, done, self.panel.failed("Merge"))

    def cancel_dialog(self) -> None:
        self.close()
