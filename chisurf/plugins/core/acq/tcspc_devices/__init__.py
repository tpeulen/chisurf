"""TCSPC device wrappers (B&H SPC, PicoQuant, BrickMic, simulator) for the acquisition tool.

The device setup dialogs are the acquisition app's emtk cards
(``chisurf.plugins.core.acq.gui.setup_models`` and ``gui.sim_setup``); this package holds
only the device side. The exports stay lazy so a simulator-only consumer does not load
every vendor wrapper.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "TCSPCDeviceABC",
    "TCSPCDevice",
]


def __getattr__(name: str) -> Any:
    """Lazily resolve the device exports without burdening the simulator."""
    if name == "TCSPCDeviceABC":
        from .abc import TCSPCDeviceABC

        return TCSPCDeviceABC
    if name == "TCSPCDevice":
        from .device_factory import TCSPCDevice

        return TCSPCDevice
    raise AttributeError(name)
