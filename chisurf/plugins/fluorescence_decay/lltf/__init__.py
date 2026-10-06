"""
LLTF: Lazy Lifetime Analysis.

This plugin provides tools for analyzing fluorescence lifetime data using the LLTF module.
It implements advanced fitting procedures for extracting fluorescence lifetimes from
time-correlated single photon counting (TCSPC) measurements.

Features:
- Load and analyze TCSPC data
- Fit decay curves with multiple exponential components
- Automatic determination of optimal number of lifetime components
- Convolution with instrument response function (IRF)
- Background estimation and correction
- IRF shift estimation and correction
- Pile-up correction
- Visualization of fits and residuals
- Export results for further analysis

Ideal for extracting detailed information about fluorophore environments and dynamics
from time-resolved fluorescence experiments.
"""

# Plugin brand icon (unified emoji set)
icon = "⏳"

# Define the plugin name - this will appear in the Plugins menu
name = "Spectroscopy:Fluorescence decay:Lazy Lifetime Analysis"

# Expose the plugin CLI through chisurf.core.cli
cli_entrypoint = "lltf=chisurf.plugins.fluorescence_decay.lltf.core.cli:cli"


__all__ = ["cli_entrypoint", "name"]
