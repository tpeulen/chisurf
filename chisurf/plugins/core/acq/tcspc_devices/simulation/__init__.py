"""
Simulation TCSPC Device Module

This module provides a simulated TCSPC acquisition device using tttrlib's photon
simulator.
"""

from .core.streaming import TttrlibSimulator
from .setup_dialog import EnhancedSimulationSetupDialog as SimulationSetupDialog
from .wrapper import BurbulatorSimulator, SimulationDevice

__all__ = ["SimulationDevice", "TttrlibSimulator", "BurbulatorSimulator", "SimulationSetupDialog"]
