"""API endpoints for FRET modelling.

``operations`` is the transport-agnostic seam (used by the CLI and RPC
services). ``router``/``app`` provide an optional FastAPI surface and are only
available when ``fastapi`` is installed.
"""

from __future__ import annotations

from . import models, operations



def __getattr__(name: str):
    """Resolve the optional HTTP surface on first access.

    Importing ``fastapi`` costs ~0.3 s, and this package is reached from the
    RPC services every server start-up registers, which never use it.
    """
    if name not in ("app", "router"):
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    try:
        from . import router as _router_module
    except Exception:  # pragma: no cover - fastapi not installed
        value = None
    else:
        value = getattr(_router_module, name)
    globals()[name] = value
    return value
