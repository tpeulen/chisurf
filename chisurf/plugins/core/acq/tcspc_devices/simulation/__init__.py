"""Simulator compatibility exports, loaded lazily around the Qt-free core."""

from __future__ import annotations

from typing import Any

__all__ = ["SimulationDevice", "TttrlibSimulator", "BurbulatorSimulator", "SimulationSetupDialog"]


def __getattr__(name: str) -> Any:
    """Resolve a legacy simulator device only for clients that request it."""
    if name == "TttrlibSimulator":
        from .core.streaming import TttrlibSimulator

        return TttrlibSimulator
    if name == "SimulationSetupDialog":
        from .setup_dialog import EnhancedSimulationSetupDialog

        return EnhancedSimulationSetupDialog
    if name in {"BurbulatorSimulator", "SimulationDevice"}:
        from .wrapper import BurbulatorSimulator, SimulationDevice

        return {"BurbulatorSimulator": BurbulatorSimulator, "SimulationDevice": SimulationDevice}[
            name
        ]
    raise AttributeError(name)
