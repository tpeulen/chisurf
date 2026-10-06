"""The Provenance Graph panel: a seed, its upstream / downstream / full graph, the export (Qt-free).

The Qt panel showed the edge table and the read-only node graph but kept the
seed controls on a hidden legacy tab, and *Use as provenance seed* only switched
panels without loading. Here the seed type and ID, the three loads and the two
exports are in the panel, and a seed handed over from another panel loads the
full graph at once. The graph is converted by
:func:`~..provenance_graph.mmfdb_graph_to_node_editor_graph` and drawn by the app.
"""

from __future__ import annotations

import json
from typing import Any

from ..provenance_graph import mmfdb_graph_to_node_editor_graph
from .base import Panel
from .dialogs import MessageDialog

SEED_TYPES = ("raw_data", "processing_run", "processed_data", "analysis_run", "analysis_parameter")

EDGE_KEYS = (
    ("edge_id", "edge id"),
    ("source_node_type", "source type"),
    ("source_node_id", "source id"),
    ("relationship_type", "relationship"),
    ("target_node_type", "target type"),
    ("target_node_id", "target id"),
    ("processing_id", "processing id"),
)


def unwrap_graph(response: Any) -> dict:
    """The graph of an export response (``{"graph": ...}``) or the response itself."""
    if isinstance(response, dict) and "graph" in response:
        graph = response.get("graph")
        return graph if isinstance(graph, dict) else {}
    return response if isinstance(response, dict) else {}


class ProvenancePanel(Panel):
    key = "provenance"
    name = "Provenance Graph"
    description = "Trace what an artifact came from and what was made from it."

    def __init__(self, admin: Any) -> None:
        super().__init__(admin)
        self.seed_type = "processed_data"
        self.seed_id = ""
        self.graph: dict = {}
        #: The node-editor document the app draws (``GraphDocument.from_dict``).
        self.document: dict = mmfdb_graph_to_node_editor_graph({})
        self.revision = 0
        self.edges: list[dict] = []
        self.selected_edge = ""
        self.details = ""

    def ensure_loaded(self) -> None:
        self.loaded = True

    def seed_options(self) -> list[str]:
        return list(SEED_TYPES)

    def hint_text(self) -> str:
        return (
            "Pick a seed record (or use 'Use as provenance seed' on a raw-data, processed-product "
            "or analysis row), then load its upstream, downstream or full graph."
        )

    def enabled(self, name: str) -> bool:
        if not self.admin.connected:
            return False
        if name in ("load_upstream", "load_downstream", "load_full", "export_json", "export_zip"):
            return bool(self.seed_id.strip())
        return True

    # ── loading ────────────────────────────────────────────────────────
    def _seed(self) -> tuple[str, str] | None:
        seed_id = self.seed_id.strip()
        if not seed_id:
            self.admin.show(MessageDialog("No Seed ID", "Please enter a seed node ID."))
            return None
        return self.seed_type, seed_id

    def _show(self, graph: dict) -> None:
        self.graph = graph or {}
        self.document = mmfdb_graph_to_node_editor_graph(self.graph)
        self.revision += 1
        self.edges = []
        for i, e in enumerate(self.graph.get("edges", []) or []):
            row = {key: str(e.get(key) or "") for key, _title in EDGE_KEYS}
            row["_row"] = str(e.get("edge_id") or i)
            self.edges.append(row)
        nodes = len(self.document.get("nodes", []))
        self.details = ""
        self.say(f"Provenance: {nodes} nodes, {len(self.edges)} edges")

    def _trace(self, label: str, fn) -> None:
        seed = self._seed()
        if seed is None:
            return
        seed_type, seed_id = seed
        self.run(
            label,
            lambda: fn(seed_type, seed_id),
            self._show,
            lambda error: self.admin.show(MessageDialog("Trace Failed", f"{label} failed:\n{error}")),
        )

    def load_upstream(self) -> None:
        self._trace(
            "Trace upstream",
            lambda t, i: self.client.dependencies_upstream(node_type=t, node_id=i),
        )

    def load_downstream(self) -> None:
        self._trace(
            "Trace downstream",
            lambda t, i: self.client.dependencies_downstream(node_type=t, node_id=i),
        )

    def load_full(self) -> None:
        self._trace(
            "Load full graph",
            lambda t, i: unwrap_graph(
                self.client.export_provenance_graph(seed_node_type=t, seed_node_id=i)
            ),
        )

    def set_seed(self, seed_type: str, seed_id: str) -> None:
        """A seed handed over from another panel: load its full graph."""
        self.seed_type = seed_type
        self.seed_id = seed_id
        self.load_full()

    # ── selection ──────────────────────────────────────────────────────
    def edge_rows(self) -> list[dict]:
        return self.edges

    def select_edge(self, record: dict | None) -> None:
        if record is None:
            return
        self.selected_edge = str(record.get("_row", ""))
        edge = next(
            (
                e
                for i, e in enumerate(self.graph.get("edges", []) or [])
                if str(e.get("edge_id") or i) == self.selected_edge
            ),
            None,
        )
        if edge is not None:
            self.details = json.dumps(edge, indent=2, default=str)

    def select_node(self, node_id: str) -> None:
        """A node was picked in the graph: show its record."""
        node = next((n for n in self.document.get("nodes", []) if n["id"] == node_id), None)
        if node is not None:
            record = node.get("config", {}).get("record", node)
            self.details = json.dumps(record, indent=2, default=str)

    def details_text(self) -> str:
        return self.details or "Pick an edge in the table or a node in the graph to see its record."

    # ── export ─────────────────────────────────────────────────────────
    def export_json(self) -> None:
        seed = self._seed()
        if seed is None:
            return
        seed_type, seed_id = seed

        def write(path: str) -> None:
            def call():
                result = self.client.export_provenance_graph(
                    seed_node_type=seed_type, seed_node_id=seed_id
                )
                with open(path, "w", encoding="utf-8") as handle:
                    json.dump(result, handle, indent=2, default=str)
                return path

            self.run(
                "Export JSON",
                call,
                lambda p: self.admin.show(MessageDialog("Export Complete", f"Exported successfully to:\n{p}")),
                lambda error: self.admin.show(
                    MessageDialog("Export Failed", f"Failed to export provenance JSON:\n{error}")
                ),
            )

        self.admin.request_file(
            "Export Provenance JSON", "save", f"{seed_id}_provenance.json", "JSON Files (*.json)", write
        )

    def export_zip(self) -> None:
        seed = self._seed()
        if seed is None:
            return
        seed_type, seed_id = seed

        def write(path: str) -> None:
            def call():
                self.client.export_zip_archive(
                    target_zip_path=path,
                    seed_node_type=seed_type,
                    seed_node_id=seed_id,
                    include_external_data=False,
                )
                return path

            self.run(
                "Export ZIP",
                call,
                lambda p: self.admin.show(MessageDialog("Export Complete", f"Exported successfully to:\n{p}")),
                lambda error: self.admin.show(
                    MessageDialog("Export Failed", f"Failed to export zip archive:\n{error}")
                ),
            )

        self.admin.request_file(
            "Export Provenance ZIP Archive", "save", f"{seed_id}_provenance.zip", "ZIP Archives (*.zip)", write
        )

    def status_line(self) -> str:
        return self.message
