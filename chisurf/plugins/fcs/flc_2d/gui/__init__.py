"""2D-FLCS GUI: the Qt tool is resolved lazily so the native app imports without Qt."""

from __future__ import annotations

from typing import Any

__all__ = ["FlcTwoDTool"]


def __getattr__(attribute: str) -> Any:
    """Resolve the Qt tool on first access (PEP 562 lazy import)."""
    if attribute == "FlcTwoDTool":
        from .tool import FlcTwoDTool

        return FlcTwoDTool
    raise AttributeError(f"module {__name__!r} has no attribute {attribute!r}")
