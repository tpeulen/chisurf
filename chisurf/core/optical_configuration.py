"""Optical graph conversions extracted unchanged from the Qt easy-mode form."""

import copy
import uuid
from typing import Any


def _normalize_pid(pid):
    if pid is None:
        return None
    try:
        return int(pid)
    except (ValueError, TypeError):
        return pid


def _node_display_name(node: dict, config_key: str, default: str) -> str:
    """Return the visible node title before falling back to config metadata."""
    title = str(node.get("title") or "").strip()
    if title:
        return title
    return str(node.get("config", {}).get(config_key) or default)


def _clean_splitters_for_detector_count(
    splitters: list[dict],
    detector_count: int,
) -> list[dict]:
    """Drop optional trailing placeholder dichroics that do not affect topology."""
    cleaned = [dict(splitter) for splitter in splitters]
    while cleaned and len(cleaned) >= max(detector_count, 1):
        last = cleaned[-1]
        splitter_type = str(last.get("type") or "Dichroic")
        probe_id = _normalize_pid(last.get("probe_id"))
        if splitter_type != "Dichroic" or probe_id is not None:
            break
        cleaned.pop()
    return cleaned


def _graph_to_config(graph: dict) -> dict:
    """Convert a GraphDef graph dict back into an easy-mode config dict.

    Handles presets saved from the Full Simulator (which store the full
    node/edge graph) so the Easy Mode form can populate correctly.
    """
    nodes_list = graph.get("nodes", [])
    edges_list = graph.get("edges", [])
    nodes_map: dict[str, dict] = {n["id"]: n for n in nodes_list}

    # Build forward adjacency: source_id → [(source_port, target_id, target_port)]
    forward: dict[str, list[tuple[int, str, int]]] = {}
    for e in edges_list:
        src = e["source"]
        forward.setdefault(src, []).append((e["source_port"], e["target"], e["target_port"]))

    def node_type_of(nid: str) -> str:
        nd = nodes_map.get(nid)
        return nd["type"] if nd else ""

    config: dict = {}

    # --- Lasers ---
    for n in nodes_list:
        if n["type"] == "light_source":
            config["lasers"] = n.get("config", {}).get("manual_lines", "488:1.0, 640:1.0")
            break

    # --- Dyes ---
    for n in nodes_list:
        if n["type"] == "sample":
            dye_props = n.get("config", {}).get("dye_properties", {})
            if dye_props:
                config["dyes"] = dye_props
            else:
                pids = n.get("config", {}).get("probe_ids", [])
                if pids:
                    config["dyes"] = {str(pid): {"qy": 1.0, "ec": 1.0} for pid in pids}
            break

    # --- Förster parameters ---
    for n in nodes_list:
        if n["type"] == "forster_radius":
            fcfg = n.get("config", {})
            config["kappa2"] = fcfg.get("kappa2", 0.6667)
            config["n"] = fcfg.get("n", 1.33)
            break

    # --- Classify splitters ---
    sample_id: str | None = None
    for n in nodes_list:
        if n["type"] == "sample":
            sample_id = n["id"]
            break

    # Splitters fed by Sample's output port 1 are excitation dichroics
    exci_splitter_ids: set[str] = set()
    exci_bw_id: str | None = None
    if sample_id is not None:
        for sp, tgt, tp in forward.get(sample_id, []):
            if sp == 1 and node_type_of(tgt) == "splitter":
                exci_splitter_ids.add(tgt)
                exci_bw_id = tgt
                break

    # Excitation dichroic probe (from ExciBW)
    if exci_bw_id is not None:
        pid = nodes_map[exci_bw_id].get("config", {}).get("probe_id")
        if pid is not None:
            config["excitation_dichroic_probe_id"] = pid

    # --- Walk emission cascade from ExciBW's transmission (port 1) ---
    splitters: list[dict] = []
    detectors: list[dict] = []

    def _add_detector_from_chain(start_id: str) -> None:
        """Resolve a filter→detector chain and add the detector."""
        dname, bp_pid, qe_pid = _resolve_detector_chain(start_id, nodes_map, forward)
        detectors.append(
            {
                "name": dname,
                "bandpass_probe_id": bp_pid,
                "qe_probe_id": qe_pid,
            }
        )

    def _walk_splitter(splitter_id: str, visited: set[str]) -> str | None:
        """Record one emission splitter and find the next one."""
        nd = nodes_map.get(splitter_id, {})
        cfg = nd.get("config", {})
        splitters.append(
            {
                "type": cfg.get("splitter_type", "Dichroic"),
                "probe_id": cfg.get("probe_id"),
            }
        )
        # Detector on transmission port (port 1)
        for sp, tgt, tp in forward.get(splitter_id, []):
            if sp == 1:
                _add_detector_from_chain(tgt)
                break
        # Next splitter on reflection port (port 2)
        for sp, tgt, tp in forward.get(splitter_id, []):
            if sp == 2:
                next_type = node_type_of(tgt)
                if next_type == "splitter" and tgt not in visited:
                    return tgt
                # Reflection feeds a detector chain directly (last splitter)
                if next_type in ("filter", "detector"):
                    _add_detector_from_chain(tgt)
                break
        return None

    if exci_bw_id is not None:
        # Walk from ExciBW's transmission port
        for sp, tgt, tp in forward.get(exci_bw_id, []):
            if sp == 1:
                cur = tgt
                visited: set[str] = set()
                while cur is not None and cur not in visited:
                    visited.add(cur)
                    nt = node_type_of(cur)
                    if nt == "splitter":
                        nxt = _walk_splitter(cur, visited)
                        cur = nxt
                    elif nt in ("filter", "detector"):
                        # Direct connection to detector chain (no splitters)
                        _add_detector_from_chain(cur)
                        break
                    else:
                        # Unknown — follow single outgoing edge
                        nxt = None
                        for sp2, tgt2, tp2 in forward.get(cur, []):
                            nxt = tgt2
                            break
                        cur = nxt
                break

    # --- Fallbacks when edges are missing or cascade walk found nothing ---

    # Fallback 1: collect ALL detectors from the node list
    found_det_names = {d["name"] for d in detectors}
    for n in nodes_list:
        if n["type"] == "detector":
            dname = _node_display_name(n, "detector_name", "Detector")
            if dname not in found_det_names:
                detectors.append(
                    {
                        "name": dname,
                        "bandpass_probe_id": None,
                        "qe_probe_id": n.get("config", {}).get("probe_id"),
                    }
                )
                found_det_names.add(dname)

    # Fallback 2: if no splitters found but detectors exist, infer the
    # splitter that feeds them (the excitation dichroic itself is the
    # emission splitter in single-splitter topologies)
    if not splitters and len(detectors) >= 2:
        exci_pid = config.get("excitation_dichroic_probe_id")
        splitters.append({"type": "Dichroic", "probe_id": exci_pid})

    config["emission_splitters"] = splitters
    config["detectors"] = detectors
    return config


def _resolve_detector_chain(
    start_id: str,
    nodes_map: dict[str, dict],
    forward: dict[str, list[tuple[int, str, int]]],
) -> tuple[str, Any, Any]:
    """Walk from a node to find the detector, its bandpass, and QE probe."""
    cur = start_id
    bp_pid = None
    qe_pid = None
    det_name = "Channel"

    visited: set[str] = set()
    while cur and cur not in visited:
        visited.add(cur)
        nd = nodes_map.get(cur)
        if nd is None:
            break
        ntype = nd["type"]
        cfg = nd.get("config", {})

        if ntype == "filter":
            bp_pid = cfg.get("probe_id")

        elif ntype == "detector":
            det_name = _node_display_name(nd, "detector_name", "Detector")
            qe_pid = cfg.get("probe_id")
            break

        # Follow the single outgoing edge
        next_id: str | None = None
        for sp, tgt, tp in forward.get(cur, []):
            next_id = tgt
            break
        cur = next_id

    return det_name, bp_pid, qe_pid


def _node(
    id: str,
    type_: str,
    title: str,
    inputs: list,
    outputs: list,
    config: dict,
    pos: tuple[float, float],
) -> dict:
    """Build a validated node dict (auto-adds collapsed and version)."""
    return {
        "id": id,
        "type": type_,
        "title": title,
        "inputs": inputs,
        "outputs": outputs,
        "config": config,
        "pos": list(pos),
        "collapsed": False,
    }


def build_easy_graph(config: dict) -> dict:
    """Build a GraphDef-compatible dict from an easy-mode preset config.

    Optical path:
      Light Source → Sample
      Sample → Excitation Dichroic → cascaded Emission Splitters → N Detectors
      Sample → Förster Radius

    Supports two config formats:
    - New: ``emission_splitters`` (list of ``{type, probe_id}``)
    - Legacy: ``emission_splitter_probe_id`` + ``emission_splitter_type`` (single splitter)
    """
    nodes = []
    edges = []

    light_id = str(uuid.uuid4())
    sample_id = str(uuid.uuid4())
    exci_id = str(uuid.uuid4())
    forster_id = str(uuid.uuid4())

    # 1. Light source
    lasers = config.get("lasers", "488:1.0, 640:1.0")
    nodes.append(
        _node(
            id=light_id,
            type_="light_source",
            title="Light Source",
            inputs=[],
            outputs=["Light"],
            config={"source_mode": "manual", "manual_lines": lasers},
            pos=(50.0, 200.0),
        )
    )

    # 2. Sample
    dye_ids = []
    dye_props = {}
    for pid_str, props in config.get("dyes", {}).items():
        pid = _normalize_pid(pid_str)
        if pid is not None:
            dye_ids.append(pid)
            dye_props[pid_str] = props
    nodes.append(
        _node(
            id=sample_id,
            type_="sample",
            title="Sample / Fluorophore",
            inputs=["In"],
            outputs=["Out", "Dye Data"],
            config={
                "probe_ids": dye_ids,
                "probe_id": dye_ids[0] if dye_ids else None,
                "dye_properties": dye_props,
            },
            pos=(300.0, 200.0),
        )
    )

    # 3. Excitation dichroic — emission path
    exci_pid = _normalize_pid(config.get("excitation_dichroic_probe_id"))
    nodes.append(
        _node(
            id=exci_id,
            type_="splitter",
            title="Excitation Dichroic",
            inputs=["In"],
            outputs=["Transmission", "Reflection"],
            config={"probe_id": exci_pid},
            pos=(500.0, 200.0),
        )
    )
    # Schema port indices: source ports count through outputs, target ports
    # through inputs. The sample's "Out" is output 0, "Dye Data" output 1; a
    # splitter's Transmission is output 0, its Reflection output 1.
    edges.append({"source": light_id, "source_port": 0, "target": sample_id, "target_port": 0})
    edges.append({"source": sample_id, "source_port": 0, "target": exci_id, "target_port": 0})

    # 4. Emission splitters (cascaded) → Detector channels
    splitters = config.get("emission_splitters", [])
    if not splitters:
        # Legacy: single splitter from emission_splitter_probe_id + emission_splitter_type
        legacy_pid = _normalize_pid(config.get("emission_splitter_probe_id"))
        legacy_type = config.get("emission_splitter_type", "Dichroic")
        if legacy_pid is not None:
            splitters = [{"type": legacy_type, "probe_id": legacy_pid}]

    detectors = config.get("detectors", [])
    splitters = _clean_splitters_for_detector_count(splitters, len(detectors))
    n_detectors = len(splitters) + 1  # N splitters → N+1 detectors

    # Auto-generate splitters if more detectors than splitters allow
    while n_detectors < len(detectors):
        splitters.append({"type": "Dichroic", "probe_id": None})
        n_detectors = len(splitters) + 1

    # Ensure detector list has enough entries
    while len(detectors) < n_detectors:
        detectors.append({"name": f"Channel {len(detectors) + 1}"})

    # Build cascaded splitters
    prev_node_id = exci_id
    prev_port = 0  # Excitation dichroic transmission output
    splitter_ids = []

    for i, sp in enumerate(splitters):
        sp_id = str(uuid.uuid4())
        splitter_ids.append(sp_id)
        sp_pid = _normalize_pid(sp.get("probe_id"))
        sp_type = sp.get("type", "Dichroic")
        nodes.append(
            _node(
                id=sp_id,
                type_="splitter",
                title=f"{sp_type} Splitter {i + 1}",
                inputs=["In"],
                outputs=["Transmission", "Reflection"],
                config={"probe_id": sp_pid, "splitter_type": sp_type},
                pos=(550.0 + i * 30.0, 200.0 + i * 80.0),
            )
        )
        edges.append(
            {"source": prev_node_id, "source_port": prev_port, "target": sp_id, "target_port": 0}
        )

        # Transmission → detector i
        det = detectors[i] if i < len(detectors) else {}
        det_name = det.get("name", f"Channel {i + 1}")
        bp_pid = _normalize_pid(det.get("bandpass_probe_id"))
        dn_id = str(uuid.uuid4())

        chain_node = sp_id
        chain_port = 0  # Transmission output

        if bp_pid:
            bp_node_id = str(uuid.uuid4())
            nodes.append(
                _node(
                    id=bp_node_id,
                    type_="filter",
                    title=f"Bandpass: {det_name}",
                    inputs=["In"],
                    outputs=["Out"],
                    config={"probe_id": bp_pid},
                    pos=(700.0 + i * 30.0, 100.0 + i * 200.0),
                )
            )
            edges.append(
                {
                    "source": chain_node,
                    "source_port": chain_port,
                    "target": bp_node_id,
                    "target_port": 0,
                }
            )
            chain_node = bp_node_id
            chain_port = 0

        qe_pid = _normalize_pid(det.get("qe_probe_id"))
        nodes.append(
            _node(
                id=dn_id,
                type_="detector",
                title=det_name,
                inputs=["In"],
                outputs=[],
                config={"detector_name": det_name, "probe_id": qe_pid},
                pos=(850.0 + i * 30.0, 100.0 + i * 200.0),
            )
        )
        edges.append(
            {"source": chain_node, "source_port": chain_port, "target": dn_id, "target_port": 0}
        )

        # Next splitter feeds from this splitter's Reflection
        prev_node_id = sp_id
        prev_port = 1  # Reflection output

    # Last detector on the reflection port of the last splitter (or from ExciBW if no splitters)
    last_idx = len(splitters)
    if last_idx < len(detectors):
        det = detectors[last_idx]
        det_name = det.get("name", f"Channel {last_idx + 1}")
        bp_pid = _normalize_pid(det.get("bandpass_probe_id"))
        dn_id = str(uuid.uuid4())

        chain_node = prev_node_id
        chain_port = prev_port

        if bp_pid:
            bp_node_id = str(uuid.uuid4())
            nodes.append(
                _node(
                    id=bp_node_id,
                    type_="filter",
                    title=f"Bandpass: {det_name}",
                    inputs=["In"],
                    outputs=["Out"],
                    config={"probe_id": bp_pid},
                    pos=(700.0 + last_idx * 30.0, 100.0 + last_idx * 200.0),
                )
            )
            edges.append(
                {
                    "source": chain_node,
                    "source_port": chain_port,
                    "target": bp_node_id,
                    "target_port": 0,
                }
            )
            chain_node = bp_node_id
            chain_port = 0

        qe_pid = _normalize_pid(det.get("qe_probe_id"))
        nodes.append(
            _node(
                id=dn_id,
                type_="detector",
                title=det_name,
                inputs=["In"],
                outputs=[],
                config={"detector_name": det_name, "probe_id": qe_pid},
                pos=(850.0 + last_idx * 30.0, 100.0 + last_idx * 200.0),
            )
        )
        edges.append(
            {"source": chain_node, "source_port": chain_port, "target": dn_id, "target_port": 0}
        )

    # 5. Förster radius node
    kappa2 = config.get("kappa2", 0.6667)
    n_val = config.get("n", 1.33)
    nodes.append(
        _node(
            id=forster_id,
            type_="forster_radius",
            title="Förster Radius",
            inputs=[
                "Dye Data",
                {"name": "kappa2", "type": "number"},
                {"name": "n", "type": "number"},
            ],
            outputs=[],
            config={"kappa2": kappa2, "n": n_val, "_last_results": []},
            pos=(300.0, 500.0),
        )
    )
    edges.append({"source": sample_id, "source_port": 1, "target": forster_id, "target_port": 0})

    return {"nodes": nodes, "edges": edges, "version": 1}


def extract_forster(result):
    """Matrix displayed by the original easy optical configuration form."""
    for state in result.get("states", {}).values():
        rows = state.get("config", {}).get("_last_results", [])
        if rows:
            donors = sorted({row["donor"] for row in rows})
            acceptors = sorted({row["acceptor"] for row in rows})
            values = {(row["donor"], row["acceptor"]): row["r0"] for row in rows}
            return {
                "rows": donors,
                "columns": acceptors,
                "values": [
                    [values.get((donor, acceptor), 0.0) for acceptor in acceptors]
                    for donor in donors
                ],
            }
    return {"rows": [], "columns": [], "values": []}


def normalize_lightpath_graph(graph: dict) -> dict:
    """Return a graph dict with easy edges repaired, in graph-schema v1.

    The port indices here are the schema's: a ``source_port`` counts from zero
    through the node's ``outputs``, a ``target_port`` through its ``inputs``.
    Graphs saved by the retired scene editor used one flat per-node list
    (inputs, then outputs); such a file loads with its output-side edges
    either dropped — the loader warns loudly per edge — or attached to the
    wrong pin of a multi-output node, and is best rebuilt via Easy Mode or
    Reset to Default rather than translated back.
    """
    if not isinstance(graph, dict) or not isinstance(graph.get("nodes"), list):
        return graph

    normalized = copy.deepcopy(graph)
    _repair_easy_topology_edges(normalized)
    return normalized


def _repair_easy_topology_edges(graph: dict) -> None:
    """Restore missing edges in graphs generated by the easy-mode topology.

    The repaired edges carry schema port indices: a ``source_port`` counts
    through the source's ``outputs``, a ``target_port`` through the target's
    ``inputs`` — a splitter's Transmission is ``source_port`` 0, its
    Reflection 1, whatever its input count.
    """
    nodes = graph.get("nodes", [])
    edges = graph.setdefault("edges", [])
    if not isinstance(edges, list):
        graph["edges"] = []
        edges = graph["edges"]

    by_type: dict[str, list[dict]] = {}
    for node in nodes:
        by_type.setdefault(str(node.get("type", "")), []).append(node)

    splitters = by_type.get("splitter", [])
    exci_fw = _find_titled_node(splitters, "exci", "fw")
    exci = _find_titled_node(splitters, "exci", "bw")
    if exci is None:
        exci = _find_titled_node(splitters, "excitation", "dichroic")
    if exci is None:
        return

    light = _first_node(by_type, "light_source")
    sample = _first_node(by_type, "sample")
    forster = _first_node(by_type, "forster_radius")
    detectors = _sort_channel_nodes(by_type.get("detector", []))
    if light is None or sample is None or not detectors:
        return

    if exci_fw is not None and exci_fw in nodes:
        nodes.remove(exci_fw)
        edges[:] = [
            edge
            for edge in edges
            if edge.get("source") != exci_fw.get("id") and edge.get("target") != exci_fw.get("id")
        ]

    emission_splitters = _sort_channel_nodes(
        [node for node in splitters if node not in (exci, exci_fw)]
    )
    filter_by_detector = _match_filters_to_detectors(
        by_type.get("filter", []),
        detectors,
    )

    def add_edge(source: dict, source_port: int, target: dict, target_port: int) -> None:
        """Add an edge if the referenced ports exist and no duplicate exists.

        ``source_port`` indexes the source's ``outputs``, ``target_port`` the
        target's ``inputs`` — the schema's per-direction convention.
        """
        if not _has_output(source, source_port) or not _has_input(target, target_port):
            return
        key = (source.get("id"), source_port, target.get("id"), target_port)
        for existing in list(edges):
            existing_key = (
                existing.get("source"),
                existing.get("source_port"),
                existing.get("target"),
                existing.get("target_port"),
            )
            if existing_key == key:
                return
            if (
                existing.get("source") == source.get("id")
                and existing.get("target") == target.get("id")
                and existing.get("target_port") == target_port
            ):
                edges.remove(existing)
        edges.append(
            {
                "source": source.get("id"),
                "source_port": source_port,
                "target": target.get("id"),
                "target_port": target_port,
            }
        )

    # Output ports by name, schema-indexed: "Out" is 0, "Dye Data" 1.
    add_edge(light, 0, sample, 0)
    add_edge(sample, 0, exci, 0)
    if forster is not None:
        add_edge(sample, 1, forster, 0)

    previous = exci
    previous_port = 0  # Transmission
    for index, splitter in enumerate(emission_splitters):
        add_edge(previous, previous_port, splitter, 0)
        _add_detector_chain_edge(add_edge, splitter, 0, detectors[index], filter_by_detector)
        previous = splitter
        previous_port = 1  # Reflection

    last_index = len(emission_splitters)
    if last_index < len(detectors):
        _add_detector_chain_edge(
            add_edge,
            previous,
            previous_port,
            detectors[last_index],
            filter_by_detector,
        )


def _find_titled_node(nodes: list[dict], *needles: str) -> dict | None:
    """Find the first node whose title contains every needle."""
    for node in nodes:
        title = str(node.get("title") or "").lower()
        if all(needle.lower() in title for needle in needles):
            return node
    return None


def _first_node(nodes_by_type: dict[str, list[dict]], node_type: str) -> dict | None:
    """Return the first node of a type if one exists."""
    nodes = nodes_by_type.get(node_type) or []
    return nodes[0] if nodes else None


def _sort_channel_nodes(nodes: list[dict]) -> list[dict]:
    """Sort channel-like nodes by embedded number and then by screen position."""

    def key(node: dict) -> tuple[int, float, float, str]:
        title = str(node.get("title") or node.get("config", {}).get("detector_name") or "")
        number = _extract_first_int(title)
        pos = node.get("pos") or [0.0, 0.0]
        try:
            x_pos = float(pos[0])
            y_pos = float(pos[1])
        except (TypeError, ValueError, IndexError):
            x_pos = 0.0
            y_pos = 0.0
        return (number if number is not None else 10_000, y_pos, x_pos, title)

    return sorted(nodes, key=key)


def _extract_first_int(text: str) -> int | None:
    """Return the first integer embedded in text, if present."""
    digits = ""
    for char in text:
        if char.isdigit():
            digits += char
        elif digits:
            break
    return int(digits) if digits else None


def _match_filters_to_detectors(
    filters: list[dict],
    detectors: list[dict],
) -> dict[str, dict]:
    """Match bandpass filters to detectors by title, falling back to row order."""
    result: dict[str, dict] = {}
    remaining = list(filters)
    for detector in detectors:
        detector_name = _node_display_name(detector, "detector_name", "Detector")
        match = None
        for candidate in remaining:
            title = str(candidate.get("title") or "")
            if detector_name and detector_name.lower() in title.lower():
                match = candidate
                break
        if match is not None:
            result[str(detector.get("id"))] = match
            remaining.remove(match)

    if remaining:
        for detector, candidate in zip(detectors, _sort_channel_nodes(remaining)):
            result.setdefault(str(detector.get("id")), candidate)
    return result


def _has_output(node: dict, port_index: int) -> bool:
    """Return whether an output index exists on a node (schema convention)."""
    return 0 <= port_index < len(node.get("outputs", []))


def _has_input(node: dict, port_index: int) -> bool:
    """Return whether an input index exists on a node (schema convention)."""
    return 0 <= port_index < len(node.get("inputs", []))


def _add_detector_chain_edge(
    add_edge,
    source: dict,
    source_port: int,
    detector: dict,
    filter_by_detector: dict[str, dict],
) -> None:
    """Add source-to-filter-to-detector edges for one detector channel."""
    bandpass = filter_by_detector.get(str(detector.get("id")))
    if bandpass is None:
        add_edge(source, source_port, detector, 0)
        return
    add_edge(source, source_port, bandpass, 0)
    add_edge(bandpass, 0, detector, 0)


def apply_easy_graph_parameters(graph, configuration):
    """Project changed easy fields onto a graph without replacing its topology.

    Unknown nodes, connections, positions and configuration keys remain owned
    by the graph editor. A measured light source changes to manual only when
    the user edits its laser lines, rather than when an unrelated factor moves.
    """
    result = copy.deepcopy(graph)
    previous = _graph_to_config(graph)
    generated = build_easy_graph(copy.deepcopy(configuration))
    groups = {
        "light_source": ("lasers",),
        "sample": ("dyes",),
        "forster_radius": ("kappa2", "n"),
        "splitter": ("excitation_dichroic_probe_id", "emission_splitters"),
        "filter": ("detectors",),
        "detector": ("detectors",),
    }
    for kind, keys in groups.items():
        if not any(previous.get(key) != configuration.get(key) for key in keys):
            continue
        current = sorted(
            [node for node in result.get("nodes", []) if node.get("type") == kind],
            key=lambda node: tuple(node.get("pos") or (0.0, 0.0)),
        )
        fresh = sorted(
            [node for node in generated.get("nodes", []) if node.get("type") == kind],
            key=lambda node: tuple(node.get("pos") or (0.0, 0.0)),
        )
        for old, new in zip(current, fresh):
            old.setdefault("config", {}).update(new.get("config") or {})
    return result
