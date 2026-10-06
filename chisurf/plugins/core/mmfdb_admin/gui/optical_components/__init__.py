"""Optical component manager view, generalized from the fluorophore_view.

The Qt dock is loaded on first access (PEP 562), so the Qt-free pieces of this
package (``duplicates``, the ``*.view.json`` detail forms) import without Qt --
the native admin uses them.
"""

__all__ = ["OpticalComponentDock"]


def __getattr__(name):
    if name == "OpticalComponentDock":
        from .component_dock import OpticalComponentDock

        return OpticalComponentDock
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
