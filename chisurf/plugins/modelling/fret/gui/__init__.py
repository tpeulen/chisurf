"""GUI for FRET modelling.

``FretDockingTool`` is the AutoForm-based docking widget (the maintained Qt GUI, driven by ``fret_dock.view.json``
and the IMP/IMP.bff engine). ``FretDockWizard`` is the legacy Qt wizard, kept importable while the legacy spring
engine is phased out. The native emtk app is :mod:`.app`. The Qt classes load on first use, so importing the native
app needs no Qt.
"""

from __future__ import annotations

__all__ = ["FretDockWizard", "FretDockingTool"]


def __getattr__(name: str):
    """Lazily expose the Qt GUI classes."""
    if name == "FretDockingTool":
        from .dock_tool import FretDockingTool

        return FretDockingTool
    if name == "FretDockWizard":
        try:  # legacy wizard depends on the legacy spring engine
            from .wizard import FretDockWizard
        except Exception:  # pragma: no cover
            return None
        return FretDockWizard
    raise AttributeError(name)
