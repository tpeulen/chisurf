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

The window is ndX's emtk app (:func:`chisurf.plugins.ndxplorer.gui.app.make_app`,
the manifest's ``entrypoints.emtk``): the emtk shell docks it and the ``--qt``
shell hosts it in a ``ControlHost``. Importing this package costs no GUI toolkit
and opens nothing. A tool that hands ndX a file or a table calls
:func:`~chisurf.plugins.ndxplorer.gui.app.open_in_ndx` or
:func:`~chisurf.plugins.ndxplorer.gui.app.show_table_in_ndx`.
"""

name = "Tools:Views:ndX"

import chisurf as cs

log = cs.logging.info


def main(path=None) -> int:
    """Open ndX on its own, with no ChiSurf window: the emtk app in emtk's native host.

    Parameters
    ----------
    path : str, optional
        A burst-analysis folder, a ``.pto`` or a table to open.

    Returns
    -------
    int
        A process exit code.
    """
    from emtk.native import NativeHost

    from chisurf.plugins.ndxplorer.gui.app import make_app

    app = make_app()
    if path:
        app.open_path(str(path))
    host = NativeHost(app, title=app.window_title)
    try:
        host.run()
    finally:
        app.close()
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else None))


cli_entrypoint = "ndxplorer=chisurf.plugins.ndxplorer.cli:cli"
