"""
FCS Correlator

This plugin provides a two-pane navigation-based correlator tool for computing
and merging fluorescence correlation spectroscopy (FCS) data. Features include:

- Detector and PIE window definition
- TTTR file selection with drag-and-drop
- Optional photon/burst filtering
- Multi-tau correlation with configurable parameters (bins, cascades, fine grid)
- FCS curve merging and export

The tool replaces the legacy QWizard with a modern navigation panel layout
(left step list, right view/display), built using the AutoForm declarative
UI framework for the correlator settings panel.

The correlator workflow is no longer a standalone menu entry: it is hosted as
the first section of the unified **FCS** tool (``fcs_toolbox``), which merges the
correlator workflow with the optional FCS tools (2D-FLCS, Lifetime-FCS Sim,
Burst-wise FCS, calculators). This module remains the reusable building block
(``FcsCorrelatorTool`` + the correlator/filter/merger AutoForm panels) and is
therefore hidden from the plugin menu.
"""

name = "Spectroscopy:Fluorescence Correlation Spectroscopy:Correlator"

# Hidden from the ribbon menu: the correlator is surfaced through the merged
# "FCS" tool (fcs_toolbox), not as its own entry.
menu_hidden = True
