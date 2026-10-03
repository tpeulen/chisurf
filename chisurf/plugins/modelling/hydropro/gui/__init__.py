"""GUI of the HydroPro plugin: the Qt tool (AutoForm) and the Qt-free model the native window uses.

The Qt names load on first access so that ``gui.model`` (and the native app) import without Qt.
"""

from __future__ import annotations

__all__ = ["HydroProTool", "HydroGui"]


def __getattr__(name):
    if name in __all__:
        from . import tool

        return getattr(tool, name)
    raise AttributeError(name)
