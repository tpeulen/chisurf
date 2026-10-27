"""Shared helpers for native EMTK tools, independent of the Qt GUI package."""

from typing import Any


def __getattr__(name: str) -> Any:
    """``chisurf.emtk.active_shell`` without importing the shell until it is asked for."""
    if name == "active_shell":
        from chisurf.emtk.main_app import active_shell

        return active_shell
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
