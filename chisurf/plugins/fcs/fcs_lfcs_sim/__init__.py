"""Lifetime-FCS (FLCS) simulator plugin.

Simulate diffusing species with distinct fluorescence lifetimes and optional
interconversion, then recover them by lifetime-filtered correlation. The GUI is the
declarative AutoForm tool
:class:`chisurf.plugins.fcs.fcs_lfcs_sim.gui.tool.LifetimeFcsSimWidget`, hosted inside
the FCS Tools window; the Qt-free simulation core lives in
:mod:`chisurf.core.fluorescence.fcs.simulate`.
"""

try:
    from chisurf.plugins.fcs.fcs_lfcs_sim.gui.tool import LifetimeFcsSimWidget
except Exception:  # noqa: BLE001 - discovery must never hard-fail
    LifetimeFcsSimWidget = None

name = "Spectroscopy:Fluorescence Correlation Spectroscopy:Lifetime-FCS Simulator"

__all__ = ["LifetimeFcsSimWidget"]
