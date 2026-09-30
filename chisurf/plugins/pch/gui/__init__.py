"""Client-side GUI components for PCH analysis.

* :class:`PCHClient` — typed RPC wrapper communicating with backend services
* :class:`PCHApp` — legacy Qt analysis window (QMainWindow), resolved lazily so
  that the Qt-free emtk app in :mod:`.app` imports without a Qt binding
"""

from __future__ import annotations

from typing import Any

from .client import PCHClient

__all__ = ["PCHClient", "PCHApp"]


def __getattr__(name: str) -> Any:
    """Resolve the Qt tool on first access (PEP 562 lazy import)."""
    if name == "PCHApp":
        from .tool import PCHApp

        return PCHApp
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
