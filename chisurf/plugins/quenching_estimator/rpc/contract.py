"""The stable API/RPC contract: names, envelopes, error codes, and where data
stops being objects and becomes JSON.

Modelled on ChiSurf's per-plugin contract (`chisurf/plugins/modelling/
fps_json_editor/api/contract.py`), because QuEst is one of its plugins and a
host that can introspect every other plugin the same way is the point of
`LAY-05`. Method names were already namespaced (`quest.simulate`, like
`lightpath.simulate`); what was missing was a version, an error taxonomy, a
machine-readable descriptor, and a statement of where serialization happens.

# Errors carry a code, not just a sentence

`fail("Simulation failed: ...")` gave a host nothing to branch on but the text
of a message, so improving a message was a breaking change. Every failure now
carries a stable `error_code` from :data:`ERROR_CODES`, and the exception type
that produced it. ChiSurf's `RemoteError` reads exactly these fields.

# Serialization belongs to the transport, not to the handler

`result_payload` used to run *inside* `simulate_handler`, so an in-process
caller paid a numpy→list conversion it did not want — including the fitting loop
`OBJ-02` chose as QuEst's primary consumer, which calls `simulate` thousands of
times. The handlers return native objects; a transport that needs JSON calls
:func:`to_payload` at its boundary.

That trade is real and worth naming: **the payload shape now depends on the
transport.** What keeps the two honest is
`tests/test_contract.py`, which round-trips every method's native result through
`to_payload` and validates it against the same schema `quest/manifest.json`
declares. If they drift, that test fails rather than a host.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Mapping

__all__ = [
    "PLUGIN_ID",
    "CONTRACT_VERSION",
    "ERROR_CODES",
    "service_success",
    "service_error",
    "error_code_for",
    "contract_descriptor",
    "to_payload",
]

#: Identity, matching the plugin's `manifest.json`.
PLUGIN_ID = "quenching_estimator"

#: Version of *this contract*, not of QuEst. Bump it when a method's params,
#: result shape or error codes change in a way a host must notice; QuEst's own
#: version moves for reasons a caller does not care about.
CONTRACT_VERSION = "1.0.0"

_MANIFEST_PATH = Path(__file__).resolve().parents[1] / "manifest.json"


def _manifest() -> dict[str, Any]:
    with _MANIFEST_PATH.open("r", encoding="utf8") as handle:
        return json.load(handle)


#: Stable failure codes. **A host branches on these; it must never branch on a
#: message.** Add a code rather than reusing `operation_failed` when a caller
#: could plausibly react differently — an unlabelable site is a different thing
#: from a malformed project, and a UI should say so differently.
ERROR_CODES: dict[str, str] = {
    "invalid_project": "The project document is malformed or incomplete.",
    "unlabelable_site": "The accessible volume is empty — the site is buried or the linker cannot reach.",
    "structure_unreadable": "The structure file could not be found, fetched or parsed.",
    "unsupported_option": "A parameter carried a value QuEst does not implement.",
    "backend_unavailable": "No accessible-volume backend is usable in this interpreter.",
    "unknown_method": "No such RPC method.",
    "invalid_request": "The request envelope itself is malformed — unparsable payload, or no method named. The caller is at fault, not the operation.",
    "operation_failed": "Anything else. A host can only report this one.",
}

#: Exception → code. Ordered most specific first; the first match wins.
_EXCEPTION_CODES: tuple[tuple[str, str], ...] = (
    ("ProjectValidationError", "invalid_project"),
    ("FileNotFoundError", "structure_unreadable"),
    ("NotADirectoryError", "structure_unreadable"),
)

#: Substrings of a message that identify a code when the exception type cannot.
#: A blunt instrument, and deliberately small: the domain raises `ValueError`
#: for several distinguishable conditions, and widening this table is worse
#: than giving those conditions their own exception types.
_MESSAGE_CODES: tuple[tuple[str, str], ...] = (
    ("Accessible Volume is empty", "unlabelable_site"),
    ("accessible-volume backend", "backend_unavailable"),
    ("is not supported", "unsupported_option"),
    ("must be one of", "unsupported_option"),
    ("kappa2 must be", "invalid_project"),
)


def error_code_for(exc: BaseException) -> str:
    """Classify *exc* into one of :data:`ERROR_CODES`."""

    name = type(exc).__name__
    for exception_name, code in _EXCEPTION_CODES:
        if name == exception_name:
            return code
    message = str(exc)
    for needle, code in _MESSAGE_CODES:
        if needle in message:
            return code
    return "operation_failed"


def service_success(result: Any) -> dict[str, Any]:
    """Wrap *result* in the envelope ChiSurf's client understands."""

    return {"ok": True, "result": result}


def service_error(
    error: str,
    error_code: str = "operation_failed",
    exception_type: str | None = None,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Wrap a failure, with a code a host can branch on.

    `error_code` is validated: a typo would otherwise produce an envelope no
    host recognises, and fail silently as "some error".
    """

    if error_code not in ERROR_CODES:
        raise ValueError(
            f"Unknown error_code {error_code!r}; add it to ERROR_CODES with a "
            f"description before using it. Known: {', '.join(sorted(ERROR_CODES))}."
        )
    envelope: dict[str, Any] = {"ok": False, "error": error, "error_code": error_code}
    if exception_type is not None:
        envelope["exception_type"] = exception_type
    if details:
        envelope["details"] = dict(details)
    return envelope


def contract_descriptor() -> dict[str, Any]:
    """A JSON-compatible description of everything QuEst offers.

    Built **from the plugin's `manifest.json`** rather than beside it. A second
    hand-written copy of the method list is the shape of defect this project
    keeps finding, and `test/test_contract.py` asserts the two agree.
    """

    manifest = _manifest()
    methods = {}
    for method in manifest["rpc_methods"]:
        methods[method["name"]] = {
            "summary": method.get("summary") or method.get("description", ""),
            "params": method.get("params"),
            "result": method.get("result"),
            "long_running": bool(method.get("long_running", False)),
        }
    return {
        "plugin_id": PLUGIN_ID,
        "contract_version": CONTRACT_VERSION,
        "quest_version": manifest.get("version"),
        "transport": {
            "rpc": "JSON-RPC over ChiSurf ServiceDispatcher/ZMQ",
            "cli": "quest",
            "api": "chisurf.plugins.quenching_estimator.api.local",
        },
        "methods": methods,
        "error_codes": dict(ERROR_CODES),
        # Stated because it is the one thing a caller cannot infer from the
        # schemas: in-process results are native objects, and only a transport
        # converts them.
        "serialization": {
            "in_process": "native Python objects (numpy arrays preserved)",
            "wire": "JSON, produced by chisurf.plugins.quenching_estimator.rpc.contract.to_payload",
        },
    }


#: Result type name → converter. Registered rather than hard-coded so a new
#: result type is a local change.
_PAYLOAD_CONVERTERS: dict[str, Callable[[Any], Any]] = {}


def register_payload_converter(type_name: str, converter: Callable[[Any], Any]) -> None:
    """Teach :func:`to_payload` how to serialise a result type."""

    _PAYLOAD_CONVERTERS[type_name] = converter


def to_payload(value: Any) -> Any:
    """Convert a native result into JSON-compatible data.

    Called by a **transport** — the HTTP routes, or an RPC server — never by a
    handler. An in-process caller gets `value` untouched.
    """

    import numpy as np

    converter = _PAYLOAD_CONVERTERS.get(type(value).__name__)
    if converter is not None:
        return converter(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Mapping):
        return {str(key): to_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_payload(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value
