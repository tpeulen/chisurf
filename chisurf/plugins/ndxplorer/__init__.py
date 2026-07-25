"""
ndXplorer

This plugin provides a powerful interface for analyzing and visualizing multidimensional 
fluorescence data within ChiSurf.

Features:
- Burst analysis for single-molecule fluorescence experiments
- Multiparameter fluorescence detection (MFD) analysis
- Interactive selection and filtering of burst events
- Visualization of multidimensional data through histograms and plots
- Support for FRET efficiency calculations and proximity ratio analysis
- Application to both solution-based measurements and image spectroscopy data

The ndXplorer tool is particularly useful for analyzing complex fluorescence datasets 
where multiple parameters need to be correlated, such as fluorescence intensity, 
lifetime, anisotropy, and spectral information. It provides an intuitive interface 
for exploring relationships between different fluorescence parameters.

For single-molecule experiments, ndXplorer enables detailed burst analysis with 
capabilities to select, filter, and categorize individual molecule detection events 
based on multiple criteria. The tool also supports advanced FRET analysis with 
various correction factors and calculation methods.

When working with image spectroscopy data, ndXplorer allows pixel-by-pixel analysis 
of multiparameter fluorescence information, enabling spatial correlation of 
spectroscopic properties.
"""

name = "Main:Tools:ndXplorer"

import chisurf as cs
from chisurf.gui.glyphs import Glyphs

log = cs.logging.info


if __name__ == '__main__':
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
    import pathlib
    import sys
    _ndxplorer_module = pathlib.Path(__file__).resolve().parents[3] / "modules" / "ndxplorer"
    if _ndxplorer_module.is_dir():
        p = str(_ndxplorer_module)
        if p not in sys.path:
            sys.path.insert(0, p)
    import ndxplorer
    try:
        # Inject the in-process ChiSurf client so the phasor / FRET-line toolbar
        # is available; falls back to a plain window if the RPC stack is missing.
        from chisurf.plugins.ndxplorer.rpc_bridge import make_ndxplorer

        ndx = make_ndxplorer()
    except Exception:
        log("Could not load ndXplorer plugin (missing optional dependencies)")
        raise
    ndx.show()
    ndx.raise_()
    ndx.activateWindow()

    # Add MMFDB toolbar button if MMFDB is connected
    try:
        from ndxplorer.__main__ import open_path_like_drop
        from qtpy import QtCore

        from chisurf.gui.widgets.mmfdb.dataset_browser import MmfdbDatasetPickerDialog
        from chisurf.plugins.core.mmfdb_admin.gui.client import MMFDBClient
        from chisurf.plugins.ndxplorer.mmfdb_launcher import (
            BURST_FORMATS,
            BURST_KINDS,
            resolve_dataset_path,
        )

        client = MMFDBClient(inprocess=True)
        client.status()  # raises if MMFDB database is not accessible

        def _open_burst_in_current_ndx() -> None:
            sel = MmfdbDatasetPickerDialog.pick_dataset(
                parent=ndx,
                kinds=BURST_KINDS,
                formats=BURST_FORMATS,
                scope="all",
                client=client,
            )
            if sel is None:
                return
            path = resolve_dataset_path(client, sel.artifact_id)
            if not path:
                return
            QtCore.QTimer.singleShot(
                0, lambda: open_path_like_drop(ndx, str(path))
            )

        toolbar = ndx.addToolBar("MMFDB")
        toolbar.setObjectName("ndxplorerMmfdbToolbar")
        mmfdb_action = toolbar.addAction(f"{Glyphs.DATABASE} Open from MMFDB")
        mmfdb_action.setToolTip("Open a burst selection registered in MMFDB")
        mmfdb_action.triggered.connect(_open_burst_in_current_ndx)
    except Exception:
        pass  # MMFDB not available — skip toolbar button

    # Calibrate the loaded measurement: the correction constants ndx applies
    # should follow from the data in the window, not from typed-in guesses.
    try:
        from qtpy import QtWidgets

        from chisurf.plugins.ndxplorer.calibration_bridge import optimize_calibration_from_ndx

        def _optimize_calibration() -> None:
            """Determine alpha/beta/gamma/delta from the loaded bursts and apply them."""
            result = optimize_calibration_from_ndx(ndx)
            if not result.get("ok"):
                QtWidgets.QMessageBox.warning(
                    ndx, "Accurate FRET", str(result.get("error", "calibration failed"))
                )
                return
            before = result["before"]
            lines = [result["report"], "", "ndXplorer constants:"]
            lines += [
                f"  {name}: {before.get(name)!s} → {value:.4f}"
                for name, value in result["constants"].items()
            ]
            if result["injected"]:
                lines += ["", "New columns: " + ", ".join(result["injected"])]
            box = QtWidgets.QMessageBox(ndx)
            box.setWindowTitle("Accurate FRET — calibration applied")
            box.setText("The correction factors were optimized against the loaded data.")
            box.setDetailedText("\n".join(lines))
            box.exec_() if hasattr(box, "exec_") else box.exec()

        calibration_toolbar = ndx.addToolBar("Accurate FRET")
        calibration_toolbar.setObjectName("ndxplorerAccurateFretToolbar")
        calibrate_action = calibration_toolbar.addAction("🎯 Optimize FRET calibration")
        calibrate_action.setToolTip(
            "Find the donor-only / acceptor-only / FRET populations in the loaded "
            "bursts, determine alpha, beta, gamma and delta from them, apply them "
            "to this window and add the accurate E / S / R_DA columns."
        )
        calibrate_action.triggered.connect(_optimize_calibration)
    except Exception:
        log("Could not add the accurate-FRET toolbar to ndXplorer")


cli_entrypoint = "ndxplorer=chisurf.plugins.ndxplorer.cli:cli"

