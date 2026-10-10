"""2D Fluorescence Lifetime Correlation Spectroscopy (2D-FLCS) plugin.

Build 2D fluorescence-decay correlation maps from TTTR photon streams, resolve the
fluorescence-lifetime species by inverse-Laplace analysis (fast Tikhonov / NNLS or
faithful maximum-entropy), and read out their interconversion as a lifetime-filtered
(species-resolved) correlation.

The Qt-free pipeline lives in :mod:`chisurf.plugins.fcs.flc_2d.api`; the GUI is the
native emtk app :mod:`chisurf.plugins.fcs.flc_2d.gui.app`.
Method: Ishii & Tahara, J. Phys. Chem. B 117(39), 11414ff (2013),
doi:10.1021/jp406861u, doi:10.1021/jp406864e; application: Kondo et al., PNAS
116(23), 11247-11252 (2019), doi:10.1073/pnas.1821207116. Based on the MATLAB
code by T. Kondo (Schlau-Cohen Lab): ``TK_Create2DFDC_04``,
``TK_FitF_2DMEM_07`` et al.
"""

name = "Spectroscopy:Fluorescence Correlation Spectroscopy:2D-FLCS"

# Hidden from the menu: surfaced inside the FCS Toolbox meta tool.
menu_hidden = True
