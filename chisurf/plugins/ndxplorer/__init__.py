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
from chisurf.gui import dialogs

name = "Main:Tools:ndX"

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
        log("Could not load ndX plugin (missing optional dependencies)")
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

    # Publish this window's constants as fitting parameters, so they show up in
    # the Global View next to every fit parameter and can be linked to one.
    try:
        from chisurf.plugins.ndxplorer.parameters import bind_ndx_parameters

        ndx_parameters = bind_ndx_parameters(ndx)
        log(f"ndX constants in the Global View: {len(ndx_parameters.constant_names)}")
    except Exception:
        ndx_parameters = None
        log("Could not publish the ndX constants as fitting parameters")

    # Calibrate the loaded measurement: the correction constants ndx applies
    # should follow from the data in the window, not from typed-in guesses.
    try:

        from chisurf.plugins.ndxplorer.calibration_bridge import optimize_calibration_from_ndx

        def _optimize_calibration() -> None:
            """Ask what to determine, then determine it from the loaded bursts."""
            from chisurf.plugins.ndxplorer.calibration_options import (
                ask_calibration_options,
            )

            constants = dict(getattr(ndx, "constants", {}) or {})
            options = ask_calibration_options(
                ndx, donor_lifetime=float(constants.get("tauD0", 4.0) or 4.0))
            if options is None:
                return
            result = optimize_calibration_from_ndx(ndx, **options.as_kwargs())
            if not result.get("ok"):
                dialogs.warning(
                    ndx, "Accurate FRET", str(result.get("error", "calibration failed"))
                )
                return
            if ndx_parameters is not None:
                # The Global View must show what the window now holds.
                ndx_parameters.pull(ndx)
            before = result["before"]
            lines = [result["report"], "", "ndX constants:"]
            lines += [
                f"  {name}: {before.get(name)!s} → {value:.4f}"
                for name, value in result["constants"].items()
            ]
            # What was deliberately not written, and what it would have been.
            # A factor held fixed is a decision, and the number it was held
            # against is the only way to judge whether it was a good one.
            held = result.get("held") or {}
            if held:
                determined = result.get("determined") or {}
                lines += ["", "Held fixed (not calibrated):"]
                lines += [
                    f"  {name}: kept {value:.4f}"
                    + (f" — this measurement would have given {determined[name]:.4f}"
                       if name in determined else "")
                    for name, value in held.items()
                ]
            per_burst = result.get("background_per_burst") or []
            if result.get("background") == "measurement":
                lines += ["", (
                    "Background: per burst, from this measurement's own "
                    f"estimate ({', '.join(per_burst)})" if per_burst else
                    "Background: the container has no stored estimate — the "
                    "window's own constants were used"
                )]
            elif result.get("background") == "none":
                lines += ["", "Background: none (set to zero)"]
            if result["injected"]:
                lines += ["", "New columns: " + ", ".join(result["injected"])]
            dialogs.information(
                ndx,
                "Accurate FRET — calibration applied",
                "The correction factors were optimized against the loaded data.",
                detail="\n".join(lines),
            )

        calibration_toolbar = ndx.addToolBar("Accurate FRET")
        calibration_toolbar.setObjectName("ndxplorerAccurateFretToolbar")
        calibrate_action = calibration_toolbar.addAction("🎯 Optimize FRET calibration")
        calibrate_action.setToolTip(
            "Find the donor-only / acceptor-only / FRET populations in the loaded "
            "bursts and determine the correction factors from them.\n\n"
            "Asks first which factors it may write — the calibration always runs "
            "in full and reports every one, but a \u03b3 you determined on a "
            "reference sample should not be replaced by a worse estimate from "
            "this measurement's own populations.\n\n"
            "Runs chisurf's accurate-FRET calibration (auto_calibrate): the same "
            "code as the Accurate FRET step, not a second implementation."
        )
        calibrate_action.triggered.connect(_optimize_calibration)

        if ndx_parameters is not None:
            def _sync_constants() -> None:
                """Apply constants edited in the Global View, then read back."""
                ndx_parameters.push(ndx)
                ndx_parameters.pull(ndx)

            sync_action = calibration_toolbar.addAction("⟲ Sync constants")
            sync_action.setToolTip(
                "Apply the constants as they stand in the Global View to this window "
                "(and read back what the window holds)."
            )
            sync_action.triggered.connect(_sync_constants)
    except Exception:
        log("Could not add the accurate-FRET toolbar to ndX")


cli_entrypoint = "ndxplorer=chisurf.plugins.ndxplorer.cli:cli"

