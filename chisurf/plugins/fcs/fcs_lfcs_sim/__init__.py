"""Lifetime-FCS (FLCS) simulator plugin.

Simulate diffusing species with distinct fluorescence lifetimes and optional
interconversion, then recover them by lifetime-filtered correlation. The GUI is the
native emtk app :class:`chisurf.plugins.fcs.fcs_lfcs_sim.app.LifetimeFcsSimApp`; the
Qt-free simulation core lives in :mod:`chisurf.core.fluorescence.fcs.simulate`.
"""

name = "Spectroscopy:Fluorescence Correlation Spectroscopy:Lifetime-FCS Simulator"

__all__: list[str] = []
