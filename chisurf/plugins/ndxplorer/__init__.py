"""
ndX

This plugin provides a powerful interface for analyzing and visualizing multidimensional
fluorescence data within ChiSurf.

Features:
- Burst analysis for single-molecule fluorescence experiments
- Multiparameter fluorescence detection (MFD) analysis
- Interactive selection and filtering of burst events
- Visualization of multidimensional data through histograms and plots
- Support for FRET efficiency calculations and proximity ratio analysis
- Application to both solution-based measurements and image spectroscopy data

The ndX tool is particularly useful for analyzing complex fluorescence datasets
where multiple parameters need to be correlated, such as fluorescence intensity,
lifetime, anisotropy, and spectral information. It provides an intuitive interface
for exploring relationships between different fluorescence parameters.

For single-molecule experiments, ndX enables detailed burst analysis with
capabilities to select, filter, and categorize individual molecule detection events
based on multiple criteria. The tool also supports advanced FRET analysis with
various correction factors and calculation methods.

When working with image spectroscopy data, ndX allows pixel-by-pixel analysis
of multiparameter fluorescence information, enabling spatial correlation of
spectroscopic properties.
"""

name = "Main:Tools:ndX"

import chisurf as cs

log = cs.logging.info


if __name__ == "__main__":
    import sys

    import ndxplorer
    from qtpy.QtWidgets import QApplication

    app = QApplication(sys.argv)
    ndx = ndxplorer.NDXplorer()
    ndx.show()
    ndx.raise_()
    ndx.activateWindow()
    sys.exit(app.exec())

if __name__ == "plugin":
    # The GUI imports live here, not at module level: importing this package
    # (as every ``chisurf.plugins.ndxplorer.*`` import does) must not pull in
    # Qt, and only running it as a plugin opens a window.
    import pathlib
    import sys

    _ndxplorer_module = pathlib.Path(__file__).resolve().parents[3] / "modules" / "ndxplorer"
    if _ndxplorer_module.is_dir():
        p = str(_ndxplorer_module)
        if p not in sys.path:
            sys.path.insert(0, p)

    # The same window the menu opens (manifest ``entrypoints.gui``): one
    # construction, so the two routes cannot drift apart again.
    from chisurf.plugins.ndxplorer.window import build_ndxplorer_window

    ndx = build_ndxplorer_window()
    ndx.show()
    ndx.raise_()
    ndx.activateWindow()


cli_entrypoint = "ndxplorer=chisurf.plugins.ndxplorer.cli:cli"
