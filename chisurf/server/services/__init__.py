from __future__ import annotations

from typing import Any, Dict, Optional

from chisurf.server.session import SessionState

ServiceResult = dict[str, Any]
"""Standard shape returned by every service function: ``{"ok": bool, ...}``."""


# Service-level error codes (extend as needed)
NOT_FOUND = "NOT_FOUND"
INVALID_INPUT = "INVALID_INPUT"
OPERATION_FAILED = "OPERATION_FAILED"
INVALID_STATE = "INVALID_STATE"

# Maps service error codes to JSON-RPC error codes
_SERVICE_TO_JSONRPC = {
    NOT_FOUND: -32601,  # METHOD_NOT_FOUND semantics: resource not found
    INVALID_INPUT: -32602,  # INVALID_PARAMS semantics: bad input
    OPERATION_FAILED: -32603,  # INTERNAL_ERROR semantics: operation failed
    INVALID_STATE: -32603,  # INTERNAL_ERROR semantics: invalid state
}


def service_error(
    message: str,
    *,
    error_code: str,
    jsonrpc_code: int | None = None,
    exception: BaseException | None = None,
) -> ServiceResult:
    """Build a structured service error result.

    All service functions should use this helper (or :func:`service_error`)
    instead of raw ``{"ok": False, "error": ...}`` dicts so that callers
    can inspect ``error_code`` and ``jsonrpc_code`` without guessing.
    """
    if jsonrpc_code is None:
        jsonrpc_code = _SERVICE_TO_JSONRPC.get(error_code, -32603)
    result: ServiceResult = {
        "ok": False,
        "error": message,
        "error_code": error_code,
        "jsonrpc_code": jsonrpc_code,
    }
    if exception is not None:
        result["exception_type"] = type(exception).__name__
    return result


def _resolve_fit(
    state: SessionState,
    fit_index: int | None = None,
    fit_uid: str | None = None,
) -> tuple[Any, int]:
    """Look up a fit by index or uid. Returns ``(fit, index)`` or ``(None, -1)``.

    A ``fit_uid`` is matched against the top-level fits **and** the members of
    a :class:`FitGroup`: ``state.fits`` holds groups, whose member fits carry
    their own distinct uids, and the GUI addresses the member it is showing.  A
    member resolves to the member itself, paired with the index of the group
    that holds it.

    A **non-empty** ``fit_uid`` that matches nothing resolves to ``(None, -1)``
    rather than falling back to ``fit_index``: the caller named a specific fit,
    so silently retargeting the operation at another one would apply it to the
    wrong fit.  An empty or absent uid means "unspecified" and uses the index.
    """
    fits = list(state.fits)
    if fit_uid:
        for i, f in enumerate(fits):
            if str(getattr(f, "unique_identifier", "")) == fit_uid:
                return f, i
        for i, f in enumerate(fits):
            try:
                members = getattr(f, "grouped_fits", None) or []
            except Exception:
                continue
            for member in members:
                if str(getattr(member, "unique_identifier", "")) == fit_uid:
                    return member, i
        return None, -1
    if fit_index is not None and 0 <= fit_index < len(fits):
        return fits[fit_index], fit_index
    return None, -1
