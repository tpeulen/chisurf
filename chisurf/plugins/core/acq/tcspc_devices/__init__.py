"""Legacy Qt device wrappers, loaded only when the Qt acquisition tool asks.

The simulator's Qt-free engine lives under this package too.  Eagerly importing
the legacy device exports therefore made a simulator-only consumer import Qt
before it had chosen a UI.  Keep those compatibility exports lazy instead.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "TCSPCDeviceABC",
    "TCSPCDevice",
    "BHSPCCardSetupDialog",
    "SimulationSetupDialog",
    "PicoQuantSetupDialog",
]


def __getattr__(name: str) -> Any:
    """Lazily resolve legacy Qt device exports without burdening the simulator."""
    if name == "TCSPCDeviceABC":
        from .abc import TCSPCDeviceABC

        return TCSPCDeviceABC
    if name == "TCSPCDevice":
        from .device_factory import TCSPCDevice

        return TCSPCDevice
    if name == "BHSPCCardSetupDialog":
        from .bh_spc import BHSPCCardSetupDialog

        return BHSPCCardSetupDialog
    if name == "SimulationSetupDialog":
        from .simulation import SimulationSetupDialog

        return SimulationSetupDialog
    if name == "PicoQuantSetupDialog":
        from .picoquant import PicoQuantSetupDialog

        return PicoQuantSetupDialog
    raise AttributeError(name)
