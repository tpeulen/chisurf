from __future__ import annotations

import json
import threading
from importlib import resources
from typing import Any


def encode_request(
    method: str,
    params: dict[str, Any] | None = None,
    request_id: int | None = None,
) -> dict[str, Any]:
    """Build a JSON-RPC 2.0 request dict."""
    msg: dict[str, Any] = {
        "jsonrpc": "2.0",
        "method": method,
        "id": request_id if request_id is not None else _next_id(),
    }
    if params is not None:
        msg["params"] = params
    return msg


def decode_request(msg: dict[str, Any]) -> tuple[str, dict[str, Any], int | None] | None:
    """Validate and split a JSON-RPC request into (method, params, id).

    Returns ``None`` if the message is not a valid request.
    """
    if not isinstance(msg, dict):
        return None
    method = msg.get("method")
    if not isinstance(method, str) or not method:
        return None
    params = msg.get("params", {})
    if not isinstance(params, dict):
        params = {}
    req_id = msg.get("id")
    return method, params, req_id


def encode_response(
    result: Any,
    request_id: int | None = None,
) -> dict[str, Any]:
    """Build a JSON-RPC 2.0 success response dict."""
    return {
        "jsonrpc": "2.0",
        "result": result,
        "id": request_id,
    }


def encode_error(
    code: int,
    message: str,
    data: Any = None,
    request_id: int | None = None,
) -> dict[str, Any]:
    """Build a JSON-RPC 2.0 error response dict."""
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {
        "jsonrpc": "2.0",
        "error": err,
        "id": request_id,
    }


def decode_response(msg: dict[str, Any]) -> tuple[Any | None, dict[str, Any] | None, int | None]:
    """Split a JSON-RPC response into (result, error, id).

    Exactly one of *result* or *error* will be non-``None``.
    """
    if not isinstance(msg, dict):
        return None, None, None
    result = msg.get("result")
    error = msg.get("error")
    req_id = msg.get("id")
    return result, error, req_id


def is_valid_request(msg: Any) -> bool:
    """Return ``True`` if *msg* is a structurally valid JSON-RPC request."""
    if not isinstance(msg, dict):
        return False
    return (
        msg.get("jsonrpc") == "2.0"
        and isinstance(msg.get("method"), str)
        and bool(msg.get("method"))
    )


def is_valid_response(msg: Any) -> bool:
    """Return ``True`` if *msg* is a structurally valid JSON-RPC response."""
    if not isinstance(msg, dict):
        return False
    if msg.get("jsonrpc") != "2.0":
        return False
    return "result" in msg or "error" in msg


# ── internal helpers ────────────────────────────────────────────────

_ID_COUNTER: int = 0
_ID_LOCK = threading.Lock()


def _next_id() -> int:
    """Return the next monotonically increasing request ID."""
    global _ID_COUNTER
    with _ID_LOCK:
        _ID_COUNTER += 1
        return _ID_COUNTER


# Standard JSON-RPC error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# ChiSurf server protocol version
PROTOCOL_VERSION = "1.0"


def load_method_specs() -> list[dict[str, Any]]:
    """Return the declarative RPC method table.

    ``server_methods.json`` is the single registry of the server's wire
    surface: it names every RPC method, the service function behind it and
    the event topics it publishes.  Both the dispatcher's handler
    registration and the ``meta.protocol`` description are derived from it,
    so there is exactly one place a method can be added.

    Returns
    -------
    list of dict
        One specification per registered method, in declaration order.
    """
    with resources.files("chisurf.server").joinpath("server_methods.json").open() as fp:
        return json.load(fp)["methods"]


# Prose for each RPC namespace.  Only the description is hand-written — which
# methods a namespace contains is read from ``server_methods.json``.
NAMESPACE_DESCRIPTIONS = {
    "meta": "Liveness, metadata, method discovery",
    "dataset": "Dataset CRUD and data access",
    "fit": "Fit CRUD, execution, sampling, scans, groups and results",
    "parameter": "Parameter inspection and mutation",
    "project": "Project serialisation (save/load)",
    "session": "Session lifecycle and snapshots",
    "model": "Model configuration, components and state",
    "graph": "Fit graph construction for visualisation",
    "log": "Log writing",
    "editor": "Open editor document access and linting",
    "detector_setups": "Detector/PIE-window setup presets",
    "flr": "Fluorescence metadata, photon streams and flrCIF export",
    "plot": "Server-rendered plot data",
    "pda": "Photon distribution analysis",
    "tcspc": "Fluorescence decays from a gated burst selection",
    "pch": "Photon-counting histograms from a gated burst selection",
    "bursts": "What a gated burst population can be handed to",
}

# Methods that carry no namespace prefix are catalogued under this namespace.
# ``list_methods`` is the one deliberate survivor of the retired flat surface
# (the companion exploration tool probes it before it knows the protocol
# version); see the INC-03 note in the cleanup backlog.
_UNNAMESPACED_METHODS = {"list_methods": "meta"}


def build_method_catalogue(
    specs: list[dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Group the registered methods into the per-namespace ``meta.protocol`` catalogue.

    Parameters
    ----------
    specs : list of dict, optional
        Method table to group; defaults to :func:`load_method_specs`.

    Returns
    -------
    dict
        Namespace name mapped to ``{"description": str, "methods": list}``,
        with the methods in registration order.
    """
    if specs is None:
        specs = load_method_specs()
    catalogue: dict[str, dict[str, Any]] = {}
    for spec in specs:
        rpc = spec["rpc"]
        if "." in rpc:
            namespace = rpc.split(".", 1)[0]
        else:
            namespace = _UNNAMESPACED_METHODS.get(rpc, rpc)
        entry = catalogue.setdefault(
            namespace,
            {
                "description": NAMESPACE_DESCRIPTIONS.get(
                    namespace, f"{namespace} methods (undocumented namespace)"
                ),
                "methods": [],
            },
        )
        if rpc not in entry["methods"]:
            entry["methods"].append(rpc)
    return catalogue


# Per-method parameter/result contract.  The ``events`` a method publishes are
# *not* repeated here — they are merged in from the registry by
# :func:`build_method_schemas`, so the two cannot drift apart.
METHOD_PARAM_SCHEMAS = {
    "meta.ping": {
        "required_params": [],
        "optional_params": [],
        "result": "PingResult",
    },
    "meta.methods": {
        "required_params": [],
        "optional_params": [],
        "result": "MethodListResult",
    },
    "meta.protocol": {
        "required_params": [],
        "optional_params": [],
        "result": "ProtocolResult",
    },
    "dataset.list": {
        "required_params": [],
        "optional_params": [],
        "result": "DatasetListResult",
    },
    "dataset.get": {
        "required_params": [],
        "optional_params": ["dataset_index", "dataset_uid"],
        "result": "DatasetDetailResult",
    },
    "dataset.curve_data": {
        "required_params": [],
        "optional_params": ["dataset_index", "dataset_uid"],
        "result": "DatasetCurveDataResult",
    },
    "dataset.remove": {
        "required_params": [],
        "optional_params": ["dataset_indices", "dataset_uids"],
        "result": "ActionResult",
    },
    "dataset.clear": {
        "required_params": [],
        "optional_params": [],
        "result": "ActionResult",
    },
    "dataset.rename": {
        "required_params": ["dataset_index", "name"],
        "optional_params": ["dataset_uid"],
        "result": "ActionResult",
    },
    "dataset.group": {
        "required_params": ["dataset_indices"],
        "optional_params": ["name"],
        "result": "ActionResult",
    },
    "dataset.ungroup": {
        "required_params": ["dataset_index"],
        "optional_params": [],
        "result": "ActionResult",
    },
    "dataset.load": {
        "required_params": [],
        "optional_params": ["reader_name", "filename", "name", "curve_data"],
        "result": "DatasetCreateResult",
    },
    "fit.list": {
        "required_params": [],
        "optional_params": [],
        "result": "FitListResult",
    },
    "fit.get": {
        "required_params": [],
        "optional_params": ["fit_index", "fit_uid"],
        "result": "FitDetailResult",
    },
    "fit.run": {
        "required_params": [],
        "optional_params": ["fit_index", "fit_uid"],
        "result": "FitRunResult",
    },
    "fit.remove": {
        "required_params": [],
        "optional_params": ["fit_indices", "fit_uids"],
        "result": "ActionResult",
    },
    "fit.clear": {
        "required_params": [],
        "optional_params": [],
        "result": "ActionResult",
    },
    "fit.set_dataset": {
        "required_params": ["fit_index", "dataset_index"],
        "optional_params": ["fit_uid", "dataset_uid"],
        "result": "ActionResult",
    },
    "fit.set_result_idx": {
        "required_params": ["fit_index", "result_idx"],
        "optional_params": ["fit_uid"],
        "result": "ActionResult",
    },
    "fit.set_fit_range": {
        "required_params": ["fit_index"],
        "optional_params": ["fit_uid", "xmin", "xmax", "data_range"],
        "result": "ActionResult",
    },
    "fit.create": {
        "required_params": [],
        "optional_params": [
            "dataset_index",
            "dataset_indices",
            "model_name",
            "fit_name",
            "model_kw",
        ],
        "result": "FitCreateResult",
    },
    "fit.update": {
        "required_params": [],
        "optional_params": ["fit_index", "fit_uid"],
        "result": "ActionResult",
    },
    "fit.save": {
        "required_params": ["filename"],
        "optional_params": ["fit_index", "fit_uid", "file_type", "save_curves"],
        "result": "ActionResult",
    },
    "fit.curve_data": {
        "required_params": [],
        "optional_params": ["fit_index", "fit_uid"],
        "result": "FitCurveDataResult",
    },
    "editor.document.list": {
        "required_params": [],
        "optional_params": [],
        "result": "EditorDocumentListResult",
    },
    "editor.document.get": {
        "required_params": [],
        "optional_params": ["document_id", "path", "include_content"],
        "result": "EditorDocumentResult",
    },
    "editor.document.set": {
        "required_params": ["content"],
        "optional_params": ["document_id", "path", "expected_revision", "source"],
        "result": "EditorDocumentActionResult",
    },
    "editor.document.apply_edits": {
        "required_params": ["edits"],
        "optional_params": ["document_id", "path", "expected_revision", "source"],
        "result": "EditorDocumentActionResult",
    },
    "editor.document.ruff_check": {
        "required_params": [],
        "optional_params": ["document_id", "path", "content", "extra_args", "timeout_ms"],
        "result": "EditorRuffResult",
    },
    "editor.document.ruff_fix": {
        "required_params": [],
        "optional_params": [
            "document_id",
            "path",
            "expected_revision",
            "apply_to_document",
            "extra_args",
            "timeout_ms",
        ],
        "result": "EditorRuffResult",
    },
    "parameter.get": {
        "required_params": [],
        "optional_params": ["parameter_name", "fit_index", "fit_uid", "parameter_uid", "owner_uid"],
        "result": "ParameterDetailResult",
    },
    "parameter.set_value": {
        "required_params": ["value"],
        "optional_params": [
            "parameter_name",
            "fit_index",
            "fit_uid",
            "local_idx",
            "parameter_uid",
            "owner_uid",
        ],
        "result": "ActionResult",
    },
    "parameter.set_fixed": {
        "required_params": ["fixed"],
        "optional_params": [
            "parameter_name",
            "fit_index",
            "fit_uid",
            "local_idx",
            "parameter_uid",
            "owner_uid",
        ],
        "result": "ActionResult",
    },
    "parameter.set_bounds": {
        "required_params": ["bounds"],
        "optional_params": [
            "parameter_name",
            "fit_index",
            "fit_uid",
            "local_idx",
            "parameter_uid",
            "owner_uid",
        ],
        "result": "ActionResult",
    },
    "parameter.set_bounds_on": {
        "required_params": ["bounds_on"],
        "optional_params": [
            "parameter_name",
            "fit_index",
            "fit_uid",
            "local_idx",
            "parameter_uid",
            "owner_uid",
        ],
        "result": "ActionResult",
    },
    "parameter.set_prior": {
        "required_params": ["prior"],
        "optional_params": [
            "parameter_name",
            "fit_index",
            "fit_uid",
            "local_idx",
            "parameter_uid",
            "owner_uid",
        ],
        "result": "ActionResult",
    },
    "parameter.link": {
        "required_params": [],
        "optional_params": [
            "parameter_name",
            "target_parameter_name",
            "fit_index",
            "target_fit_index",
            "fit_uid",
            "target_fit_uid",
            "local_idx",
            "target_local_idx",
            "parameter_uid",
            "owner_uid",
            "target_parameter_uid",
            "target_owner_uid",
        ],
        "result": "ActionResult",
    },
    "parameter.unlink": {
        "required_params": [],
        "optional_params": [
            "parameter_name",
            "fit_index",
            "fit_uid",
            "local_idx",
            "parameter_uid",
            "owner_uid",
        ],
        "result": "ActionResult",
    },
    "project.info": {
        "required_params": [],
        "optional_params": [],
        "result": "ProjectInfoResult",
    },
    "project.save": {
        "required_params": ["filename"],
        "optional_params": [],
        "result": "ActionResult",
    },
    "project.load": {
        "required_params": ["filename"],
        "optional_params": [],
        "result": "ActionResult",
    },
    "session.describe": {
        "required_params": [],
        "optional_params": [],
        "result": "SessionDescriptionResult",
    },
    "session.clear": {
        "required_params": [],
        "optional_params": [],
        "result": "ActionResult",
    },
    "session.snapshot": {
        "required_params": [],
        "optional_params": [],
        "result": "SessionSnapshotResult",
    },
    "session.restore": {
        "required_params": [],
        "optional_params": ["project_path"],
        "result": "ActionResult",
    },
    "model.finalize": {
        "required_params": [],
        "optional_params": [],
        "result": "ActionResult",
    },
    "model.set_parse_function": {
        "required_params": [],
        "optional_params": ["fit_index", "parse_function_str"],
        "result": "ActionResult",
    },
    "graph.build": {
        "required_params": [],
        "optional_params": ["fit_indices", "fit_uids", "include_fixed", "connect_owners"],
        "result": "GraphBuildResult",
    },
    "graph.build_fits": {
        "required_params": [],
        "optional_params": ["fit_indices", "fit_uids", "include_fixed", "connect_owners"],
        "result": "GraphBuildResult",
    },
    "log.write": {
        "required_params": ["message"],
        "optional_params": ["level", "logger_name", "extra"],
        "result": "ActionResult",
    },
}


def build_method_schemas(
    specs: list[dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Combine the hand-written parameter contract with the registry's event topics.

    Only methods that carry a :data:`METHOD_PARAM_SCHEMAS` entry appear; the
    remaining registered methods are discoverable through the catalogue but
    have no documented parameter contract yet.

    Parameters
    ----------
    specs : list of dict, optional
        Method table to read event topics from; defaults to
        :func:`load_method_specs`.

    Returns
    -------
    dict
        Method name mapped to ``required_params``/``optional_params``/
        ``result``/``events``.
    """
    if specs is None:
        specs = load_method_specs()
    events = {spec["rpc"]: list(spec.get("events", [])) for spec in specs}
    return {
        method: {**schema, "events": events.get(method, [])}
        for method, schema in METHOD_PARAM_SCHEMAS.items()
    }


_METHOD_SPECS = load_method_specs()

# Namespaced RPC method catalogue and per-method schemas (for meta.protocol).
METHOD_CATALOGUE = build_method_catalogue(_METHOD_SPECS)
METHOD_SCHEMAS = build_method_schemas(_METHOD_SPECS)
