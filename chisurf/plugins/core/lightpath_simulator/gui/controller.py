"""Native light-path graph, backend execution, files and MMFDB workflows."""

import copy
import json
import uuid
from concurrent.futures import CancelledError, ThreadPoolExecutor
from pathlib import Path
from threading import Event

import numpy as np

from chisurf.core.optical_configuration import (
    _graph_to_config,
    apply_easy_graph_parameters,
    build_easy_graph,
    normalize_lightpath_graph,
)
from chisurf.emtk.node_editor.document import GraphDocument, GraphEdge, GraphNode

from ..core import workflow
from .node_types import build_optical_registry, optical_registry


def json_safe(value):
    if callable(value):
        return None
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {
            key: json_safe(item)
            for key, item in value.items()
            if not str(key).startswith("_") and not callable(item)
        }
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value if not callable(item)]
    return value


def deserialize(value):
    if isinstance(value, list):
        if value and all(isinstance(item, (int, float)) for item in value):
            return np.asarray(value, dtype=float)
        return [deserialize(item) for item in value]
    if isinstance(value, dict):
        return {key: deserialize(item) for key, item in value.items()}
    return value


class LightPathController:
    def __init__(self, db_path=None, client=None, state_path=None, owner_id="lightpath"):
        build_optical_registry()
        self.owner_id = owner_id
        self.db_path = str(db_path) if db_path is not None else None
        self.client = client
        self.remote = client is not None
        self.document = GraphDocument()
        self.result = {}
        self.probes = []
        self.saved = []
        self.status = "Configure the optical path, then press Calculate Emission Intensity."
        self.running = False
        self.auto_update = True
        self.pending = False
        self.on_document = None
        self.on_result = None
        self.on_probes = None
        self.on_easy_sync = None
        self.revision = 0
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="lightpath")
        self._future = None
        self._cancel = Event()
        self.state_path = Path(state_path) if state_path is not None else None
        self.operation_name = "Light path simulation"
        self.last_operation_id = ""
        self.reset()
        self._default_revision = self.revision
        if self.state_path is not None and self.state_path.exists():
            self.load_graph(self.state_path)

    def graph(self):
        return json_safe(self.document.to_dict())

    def changed(self):
        self.revision += 1
        self.pending = self.auto_update
        self.status = (
            "Optical path changed; simulation update queued."
            if self.pending
            else "Optical path changed; press Calculate Emission Intensity to update."
        )
        if callable(self.on_easy_sync):
            self.on_easy_sync(_graph_to_config(self.graph()))

    def load_document(self, graph, update=False):
        document = GraphDocument.from_dict(normalize_lightpath_graph(graph))
        entries = graph.get("nodes", []) if isinstance(graph, dict) else []
        if document.nodes and not any(
            "pos" in entry or "position" in entry or "x" in entry for entry in entries
        ):
            self._arrange_document(document)
        for node in document.nodes:
            if node.type == "light_source" and node.config.get("source_mode") == "probe":
                node.config["source_mode"] = "database"
            descriptor = optical_registry.get(node.type)
            if descriptor is not None:
                for ports, defaults in (
                    (node.inputs, descriptor.inputs),
                    (node.outputs, descriptor.outputs),
                ):
                    for port, default in zip(ports, defaults):
                        if not port.port_type and port.name == default.name:
                            port.port_type = default.port_type
        self.document = document
        self.result = {}
        self.revision += 1
        self.pending = update and self.auto_update
        if callable(self.on_document):
            self.on_document(document)
        if callable(self.on_easy_sync):
            self.on_easy_sync(_graph_to_config(self.graph()))

    @staticmethod
    def _arrange_document(document):
        from chisurf.core.graph_definition import GraphDef

        order = GraphDef.from_dict(document.to_dict()).topological_node_ids()
        levels, rows = {}, {}
        for node_id in order:
            parents = [edge.source for edge in document.edges if edge.target == node_id]
            level = max((levels.get(parent, 0) + 1 for parent in parents), default=0)
            levels[node_id] = level
        for node in document.nodes:
            level = levels[node.id]
            row = rows.get(level, 0)
            rows[level] = row + 1
            node.pos = (level * 300.0, row * 280.0)

    def arrange(self):
        self._arrange_document(self.document)
        if callable(self.on_document):
            self.on_document(self.document, True)
        self.status = "Optical nodes arranged by signal flow."

    def reset(self):
        """Restore the Qt tool's default path: laser, sample, dichroic, a filter and a detector per colour, Foerster radius."""
        self.load_document(self.default_graph(self.probes))
        self.status = "Default optical path restored."

    @staticmethod
    def default_graph(probes):
        """The canonical default light-path graph of the Qt tool's ``_build_default_path`` (same nodes, ids, positions, wiring)."""
        green_dye = red_dye = dichroic = green_filter = red_filter = None
        for p in probes:
            name = str(p.get("name", "")).lower().replace("-", " ")
            pid = p["probe_id"]
            if "atto 488" in name and not green_dye and p.get("has_em"):
                green_dye = pid
            if "atto 647n" in name and not red_dye and p.get("has_em"):
                red_dye = pid
            if "561lp" in name and not dichroic and p.get("has_trans"):
                dichroic = pid
            if "bp" in name and "500" in name and not green_filter and p.get("has_trans"):
                green_filter = pid
            if "bp" in name and "650" in name and not red_filter and p.get("has_trans"):
                red_filter = pid

        def node(type_id, pos, node_id=None):
            d = optical_registry.get(type_id)
            return GraphNode(
                node_id or type_id,
                d.id,
                d.title,
                list(d.inputs),
                list(d.outputs),
                copy.deepcopy(d.default_config or {}),
                pos,
            )

        document = GraphDocument()
        source = node("light_source", (30.0, 260.0))
        source.config["source_mode"] = "manual"
        source.config["manual_lines"] = "488:1.0, 640:1.0"
        sample = node("sample", (300.0, 260.0))
        dyes = [d for d in (green_dye, red_dye) if d]
        if dyes:
            sample.config["probe_ids"] = dyes
        splitter = node("splitter", (570.0, 260.0))
        if dichroic:
            splitter.config["probe_id"] = dichroic
        red_f = node("filter", (840.0, 90.0), "red_filter")
        if red_filter:
            red_f.config["probe_id"] = red_filter
        red_d = node("detector", (1110.0, 90.0), "red_detector")
        red_d.config["detector_name"] = "Red Channel"
        green_f = node("filter", (840.0, 430.0), "green_filter")
        if green_filter:
            green_f.config["probe_id"] = green_filter
        green_d = node("detector", (1110.0, 430.0), "green_detector")
        green_d.config["detector_name"] = "Green Channel"
        forster = node(
            "forster_radius", (300.0, 560.0)
        )  # the Qt tool put it at y=460, over the sample node
        for n in (source, sample, splitter, red_f, red_d, green_f, green_d, forster):
            document.add_node(n)
        for src, sp, dst, dp in (
            (source, 0, sample, 0),
            (sample, 0, splitter, 0),
            (sample, 1, forster, 0),
            (splitter, 0, red_f, 0),
            (red_f, 0, red_d, 0),
            (splitter, 1, green_f, 0),
            (green_f, 0, green_d, 0),
        ):
            document.add_edge(GraphEdge(src.id, sp, dst.id, dp))
        return document.to_dict()

    def add_node(self, type_id, pos=(50.0, 50.0)):
        if self.running:
            raise RuntimeError("Wait for the current simulation to finish.")
        descriptor = optical_registry.get(type_id)
        if descriptor is None:
            raise ValueError(f"Unknown optical component type: {type_id}")
        node = GraphNode(
            uuid.uuid4().hex,
            descriptor.id,
            descriptor.title,
            descriptor.inputs,
            descriptor.outputs,
            copy.deepcopy(descriptor.default_config),
            pos,
        )
        self.document.add_node(node)
        self.changed()
        if callable(self.on_document):
            self.on_document(self.document, False)
        return node

    def connect(self, source, source_port, target, target_port):
        source_node, target_node = self.document.node(source), self.document.node(target)
        if source_node is None or target_node is None:
            raise ValueError("Choose existing source and target nodes.")
        output, input_ = (
            source_node.port(int(source_port), True),
            target_node.port(int(target_port), False),
        )
        if output is None or input_ is None:
            raise ValueError("Choose valid source-output and target-input ports.")
        if output.port_type != input_.port_type:
            raise ValueError("These optical port types are incompatible.")
        if source == target:
            raise ValueError("A node cannot feed itself.")
        if any(
            edge.target == target and edge.target_port == int(target_port)
            for edge in self.document.edges
        ):
            raise ValueError("This input already has an optical source; disconnect it first.")
        changed = self.document.add_edge(
            GraphEdge(source, int(source_port), target, int(target_port))
        )
        if changed:
            self.changed()
        return changed

    def remove_node(self, node_id):
        self.document.remove_node(node_id)
        self.changed()

    def remove_edge(self, edge):
        self.document.remove_edge(edge)
        self.changed()

    def apply_easy(self, config):
        generated = GraphDocument.from_dict(build_easy_graph(copy.deepcopy(config)))
        current_by_type, generated_by_type = {}, {}
        for node in self.document.nodes:
            current_by_type.setdefault(node.type, []).append(node)
        for node in generated.nodes:
            generated_by_type.setdefault(node.type, []).append(node)
        same_structure = {key: len(value) for key, value in current_by_type.items()} == {
            key: len(value) for key, value in generated_by_type.items()
        }
        if same_structure or any(kind not in generated_by_type for kind in current_by_type):
            projected = apply_easy_graph_parameters(self.graph(), config)
            for value in projected["nodes"]:
                node = self.document.node(value["id"])
                if node is not None:
                    node.config.update(value.get("config") or {})
            self.changed()
        else:
            self.load_document(generated.to_dict(), update=True)

    def load_graph(self, path):
        graph = json.loads(Path(path).read_text())
        if "_graph" in graph:
            graph = graph["_graph"]
        elif "nodes" not in graph:
            graph = build_easy_graph(graph.get("config", graph))
        self.load_document(graph, update=True)
        self.status = f"Optical graph loaded: {path}"

    def save_graph(self, path):
        Path(path).write_text(json.dumps(self.graph(), indent=2))
        self.status = f"Optical graph saved: {path}"

    def save_preset(self, path):
        Path(path).write_text(json.dumps(self.graph(), indent=2))
        self.status = f"Optical preset saved: {path}"

    def export_instrument(self, path):
        setting = self.result.get("instrument_setting")
        if not setting:
            raise ValueError(
                "Simulate a configured optical path before exporting its instrument setting."
            )
        Path(path).write_text(json.dumps(workflow.serialize_numpy(setting), indent=2))
        self.status = f"Instrument setting exported: {path}"

    def _backend(self, action, graph=None, operation_id=None):
        if self.remote:
            if self.client is None:
                from ..api.client import LightPathClient

                self.client = LightPathClient.from_settings(timeout_ms=3000)
            if action == "simulate":
                return self.client.simulate(graph, db_path=self.db_path)
            if action == "catalogue":
                return self.client.get_probes_info(db_path=self.db_path)
            if action == "save":
                return self.client.save(graph, name=self.operation_name, db_path=self.db_path)
            if action == "list":
                return self.client.list_saved(db_path=self.db_path)
            if action == "get":
                return self.client.get(operation_id, db_path=self.db_path)
        if action == "simulate":
            return workflow.simulate_lightpath(graph, db_path=self.db_path)
        if action == "catalogue":
            return workflow.get_probes_info(db_path=self.db_path).get("probes", [])
        if action == "save":
            return workflow.save_lightpath(graph, name=self.operation_name, db_path=self.db_path)
        if action == "list":
            return workflow.list_lightpaths(db_path=self.db_path).get("simulations", [])
        if action == "get":
            return workflow.get_lightpath(operation_id, db_path=self.db_path)
        raise ValueError(f"Unknown lightpath action: {action}")

    def _execute(self, action, graph, operation_id):
        if self._cancel.is_set():
            raise CancelledError()
        result = self._backend(action, graph, operation_id)
        if self._cancel.is_set() and action != "save":
            raise CancelledError()
        return result

    def start(self, action="simulate", operation_id=None):
        if self.running:
            return False
        self._cancel.clear()
        self._action = action
        self._run_revision = self.revision
        self.running = True
        self.pending = False
        self.status = {
            "simulate": "Propagating spectral light …",
            "catalogue": "Loading optical spectra catalogue …",
            "save": "Saving simulation to MMFDB …",
            "list": "Loading saved simulations …",
            "get": "Loading saved optical path …",
        }[action]
        self._future = self._executor.submit(self._execute, action, self.graph(), operation_id)
        return True

    def stop(self):
        if self.running:
            self._cancel.set()
            self.status = (
                "Finishing the current MMFDB save …"
                if self._action == "save"
                else "Stopping; the current backend call will finish before results are discarded …"
            )

    def adopt_result(self, result):
        self.result = result
        for node_id, state in result.get("states", {}).items():
            node = self.document.node(node_id)
            if node is not None:
                node.config.update(
                    _input_spectra=deserialize(state.get("input_spectra", {})),
                    _output_spectra=deserialize(state.get("output_spectra", {})),
                    _node_char=deserialize(state.get("node_char")),
                    _last_signals=state.get("config", {}).get("_last_signals", {}),
                    _last_results=state.get("config", {}).get("_last_results", []),
                )
        matrices = result.get("crosstalk_matrices") or {}
        if matrices:
            from ..core.parameters import register_lightpath_parameters

            self.parameters = register_lightpath_parameters(
                matrices, owner_id=self.owner_id, label="Optical path"
            )
        if callable(self.on_result):
            self.on_result(result)
        self.status = (
            f"Simulation produced {len(result.get('detector_signals', []))} detector/dye signals."
        )

    def poll(self):
        if self._future is not None and self._future.done():
            future, self._future = self._future, None
            try:
                result = future.result()
                if self._cancel.is_set() and self._action != "save":
                    raise CancelledError()
                if self._action == "simulate":
                    if self._run_revision == self.revision:
                        self.adopt_result(result)
                    else:
                        self.pending = self.auto_update
                elif self._action == "catalogue":
                    self.probes = result
                    if callable(self.on_probes):
                        self.on_probes(result)
                    if self.revision == self._default_revision:
                        # Nothing was edited yet: the default path picks its components from the catalogue (as the Qt tool did).
                        self.load_document(self.default_graph(result))
                        self._default_revision = self.revision
                    self.status = f"{len(result)} optical spectra available."
                elif self._action == "save":
                    self.last_operation_id = str(result.get("operation_id", ""))
                    self.status = f"Simulation saved: {self.last_operation_id}"
                elif self._action == "list":
                    self.saved = result
                    self.status = f"{len(result)} saved light paths available."
                elif self._action == "get":
                    self.load_document(result["graph"], update=self.auto_update)
                    self.adopt_result(result)
            except CancelledError:
                self.status = "Backend operation cancelled; previous results retained."
            except Exception as exc:
                self.status = f"Error: {exc}"
            finally:
                self.running = False
        if self.pending and not self.running:
            self.start()

    def close(self):
        self.stop()
        if self.state_path is not None:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self.save_graph(self.state_path)
        from ..core.parameters import unregister_lightpath_parameters

        unregister_lightpath_parameters(self.owner_id)
        if self.client is not None:
            self._executor.submit(self.client.close)
        self._executor.shutdown(wait=False, cancel_futures=False)
