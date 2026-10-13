"""Simulator exports, loaded lazily around the Qt-free core.

The setup dialog is the acquisition app's emtk ``SimulationSetupDialog``
(``chisurf.plugins.core.acq.gui.sim_setup``).
"""

from __future__ import annotations

from typing import Any

__all__ = ["SimulationDevice", "TttrlibSimulator", "BurbulatorSimulator"]


def __getattr__(name: str) -> Any:
    """Resolve a legacy simulator device only for clients that request it."""
    if name == "TttrlibSimulator":
        from .core.streaming import TttrlibSimulator

        return TttrlibSimulator
    if name in {"BurbulatorSimulator", "SimulationDevice"}:
        from .wrapper import BurbulatorSimulator, SimulationDevice

        return {"BurbulatorSimulator": BurbulatorSimulator, "SimulationDevice": SimulationDevice}[
            name
        ]
    raise AttributeError(name)
