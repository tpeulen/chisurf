"""Integrated fluorescence lifetime analysis GUI."""

from __future__ import annotations

from qtpy import QtWidgets

from chisurf.gui.glyphs import Glyphs
from chisurf.gui.widgets.navigation import NavigationPanelTool, apply_manifest_flags


def _irf_estimator(parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
    """Create the IRF estimation panel."""
    from chisurf.plugins.fluorescence_decay.irf_estimator.gui.tool import (
        IRFEstimatorTool,
    )

    return IRFEstimatorTool(parent=parent)


def _maxent_mem(parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
    """Create the MaxEnt MEM panel."""
    from chisurf.plugins.fluorescence_decay.maxent_decay.gui.gui import (
        MaxentDecayWidget,
    )

    widget = MaxentDecayWidget()
    widget.setParent(parent)
    return widget


def _lazy_lifetime(parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
    """Create the Lazy Lifetime Analysis panel."""
    from chisurf.plugins.fluorescence_decay.lltf.lltf_gui import LLTFGUIWizard

    return LLTFGUIWizard(parent=parent)


def _microtime_histogram(parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
    """Create the microtime histogram panel."""
    from chisurf.plugins.tttr.microtime_histogram.wizard import MicrotimeHistogram

    return MicrotimeHistogram(parent=parent)


def _vv_vh_g_factor(parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
    """Create the VV/VH G-factor panel."""
    from chisurf.plugins.vv_vh_g_factor.gui.tool import VvVhGFactorCalculator

    widget = VvVhGFactorCalculator()
    widget.setParent(parent)
    return widget


#: The panels of this shell. Maturity flags are not written here: a panel names
#: its tool's ``manifest`` and the flags are read from it, so a tool declares its
#: maturity once instead of once per host that embeds it.
LIFETIME_PANELS = apply_manifest_flags(
    [
        {
            "name": "1. IRF Estimation",
            "icon": Glyphs.WAVE,
            "description": "Estimate instrument response functions from fluorescence decays.",
            "factory": _irf_estimator,
            "role": "irf",
        },
        {
            "name": "2. MaxEnt MEM",
            "icon": Glyphs.CHART_UP,
            "description": "Run maximum entropy lifetime and FRET-distance analysis.",
            "factory": _maxent_mem,
            "role": "maxent",
        },
        {
            "name": "3. Lazy Lifetime Analysis",
            "icon": Glyphs.TIMER,
            "description": "Analyze TCSPC decays with the LLTF workflow.",
            "manifest": "fluorescence_decay/lltf",
            "factory": _lazy_lifetime,
            "role": "lazy_lifetime",
        },
        {
            "name": "4. Histogram-Microtime",
            "icon": Glyphs.CHART,
            "description": "Build TTTR microtime histograms.",
            "factory": _microtime_histogram,
            "role": "microtime_histogram",
        },
        {
            "name": "5. VV/VH G-Factor",
            "icon": "⚖️",
            "description": "Calculate detector G-factors from VV/VH decays.",
            "factory": _vv_vh_g_factor,
            "role": "vv_vh_g_factor",
        },
    ]
)


class LifetimeAnalysisTool(NavigationPanelTool):
    """Integrated fluorescence lifetime analysis tool."""

    def __init__(self, parent=None):
        """Create the integrated lifetime analysis tool."""
        super().__init__(
            title="Decay Analysis",
            panels=LIFETIME_PANELS,
            parent=parent,
            minimum_size=(950, 620),
            initial_size=(1180, 760),
            navigation_width=270,
            navigation_min_width=250,
        )
