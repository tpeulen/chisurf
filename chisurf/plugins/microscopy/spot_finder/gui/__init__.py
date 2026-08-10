"""Qt GUI for the spot finder."""

from __future__ import annotations

__all__ = ["SpotFinderTool"]


def __getattr__(name: str):
    """Lazy Qt gate so importing the package stays Qt-free."""
    if name == "SpotFinderTool":
        from .tool import SpotFinderTool as _cls

        globals()["SpotFinderTool"] = _cls
        return _cls
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
