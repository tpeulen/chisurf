"""The native FCS hub: the correlator workflow and, below it, the optional FCS tools, as the Qt ``FcsTool``.

The workflow is :class:`chisurf.plugins.fcs.fcs_correlator.gui.app.FcsHubApp`; this adds the tools, each its plugin's
own emtk app.
"""

from __future__ import annotations

from pathlib import Path

from chisurf.plugins.fcs.fcs_correlator.gui.app import FcsHubApp

HERE = Path(__file__).resolve().parent

#: The optional tools below the workflow (the Qt rail's ``TOOL_PANELS``), each its plugin's emtk app.
TOOLS = [
    {"name": "2D-FLCS", "icon": "🟦", "role": "flc_2d", "plugin": "fcs/flc_2d",
     "description": "Two-dimensional fluorescence lifetime correlation spectroscopy."},
    {"name": "Lifetime-FCS Sim", "icon": "🧬", "role": "lfcs_sim", "plugin": "fcs/fcs_lfcs_sim",
     "description": "Simulate diffusing lifetime species (+ interconversion) and recover them by "
                    "lifetime-filtered correlation."},
    {"name": "Burst-wise FCS", "icon": "🔬", "role": "burst_fcs", "plugin": "burst/burst_fcs_correlator",
     "description": "Per-burst fluorescence correlation."},
    {"name": "Diffusion Calc", "icon": "🧮", "role": "diffusion_calc", "plugin": "fcs/fcs_calculator",
     "description": "Confocal diffusion / volume calculator."},
    {"name": "Filter Calc", "icon": "🧪", "role": "filter_calc", "plugin": "fcs/fcs_filter_calculator",
     "description": "Filtered-FCS lifetime filter calculator."},
]



def make_app(**_kwargs) -> FcsHubApp:
    from chisurf.emtk.i18n import install

    install()
    return FcsHubApp(title="FCS", tools=TOOLS, help_resource=HERE.parent / "help.md", guide=HERE.parent / "guide.json")


__all__ = ["TOOLS", "make_app"]
