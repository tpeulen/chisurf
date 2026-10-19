"""
FCS (the correlator workflow)

The FCS entry of the Spectroscopy › Correlation ribbon group: a five-step workflow rail for computing and merging
fluorescence correlation spectroscopy (FCS) curves.

- Detector and PIE window definition (the channel-preset step)
- TTTR file selection with drag-and-drop
- Optional photon/burst filtering
- Multi-tau correlation with configurable parameters (bins, cascades, fine grid)
- FCS curve merging and export

The other FCS tools (2D-FLCS, Lifetime-FCS Simulator, Burst-wise FCS, the diffusion/volume and fFCS filter
calculators) are ribbon entries of their own; **Filter Calc...** in the Correlator step hands the workflow's files to
the filter calculator (the ``fcs_correlator_files`` hand-off).
"""

name = "Spectroscopy:Correlation:FCS"
icon = "〰️"
