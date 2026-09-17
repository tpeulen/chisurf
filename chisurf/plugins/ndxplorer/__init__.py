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
            QtCore.QTimer.singleShot(0, lambda: open_path_like_drop(ndx, str(path)))

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
                ndx, donor_lifetime=float(constants.get("tauD0", 4.0) or 4.0)
            )
            if options is None:
                return
            # A calibration is six refinement passes plus fifty bootstrap
            # resamples, and with `background="fit"` all of that twice. That is
            # long enough that a window which simply stops responding looks
            # broken, so the steps the calibration already counts are shown.
            from chisurf.gui.progress import ChiSurfProgress

            with ChiSurfProgress(ndx, "FRET calibration…", 100) as bar:

                def _report(step: int, total: int, message: str) -> bool:
                    """Drive the bar; False stops the calibration."""
                    if total > 0:
                        bar.setRange(0, int(total))
                    bar.update_progress(int(step), message)
                    return not bar.wasCanceled()

                result = optimize_calibration_from_ndx(ndx, progress=_report, **options.as_kwargs())
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
                    + (
                        f" — this measurement would have given {determined[name]:.4f}"
                        if name in determined
                        else ""
                    )
                    for name, value in held.items()
                ]
            per_burst = result.get("background_per_burst") or []
            fitted_bg = result.get("background_fitted") or {}
            if result.get("background") == "fit":
                lines += [
                    "",
                    (
                        "Background, fitted from the reference populations: "
                        + ", ".join(f"{k} = {v:.2f}" for k, v in fitted_bg.items())
                    )
                    if fitted_bg
                    else (
                        "Background: the reference populations were too small to fit "
                        "one — the window's constants were used"
                    ),
                ]
            elif result.get("background") == "measurement":
                lines += [
                    "",
                    (
                        "Background: per burst, from this measurement's own "
                        f"estimate ({', '.join(per_burst)})"
                        if per_burst
                        else "Background: the container has no stored estimate — the "
                        "window's own constants were used"
                    ),
                ]
            elif result.get("background") == "none":
                lines += ["", "Background: none (set to zero)"]
            if result["injected"]:
                lines += ["", "New columns: " + ", ".join(result["injected"])]
            # Store it before showing the report: the numbers are worth more
            # than the window, and a user who closes the report should not
            # thereby have discarded the calibration.
            saved = None
            if getattr(options, "save_when_done", False):
                from chisurf.plugins.ndxplorer.calibration_io import save_calibration

                saved = save_calibration(
                    dict(getattr(ndx, "constants", {}) or {}),
                    ndx=ndx,
                    result=result,
                    embed=True,
                )
            from chisurf.plugins.ndxplorer.calibration_report import (
                show_calibration_report,
            )

            show_calibration_report(
                ndx,
                "FRET calibration — applied",
                "\n".join(lines),
                constants=dict(getattr(ndx, "constants", {}) or {}),
                result=result,
                ndx=ndx,
                saved=saved,
            )

        calibration_toolbar = ndx.addToolBar("Accurate FRET")
        calibration_toolbar.setObjectName("ndxplorerAccurateFretToolbar")
        calibrate_action = calibration_toolbar.addAction("🎯 FRET calibration")
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

        def _save_calibration() -> None:
            """Store the window's current constants as a calibration."""
            from qtpy import QtWidgets

            from chisurf.plugins.ndxplorer.calibration_io import (
                SUFFIX,
                container_of,
                save_calibration,
            )

            constants = dict(getattr(ndx, "constants", {}) or {})
            if not constants:
                dialogs.warning(
                    ndx, "FRET calibration", "This window carries no constants to save."
                )
                return
            container = container_of(ndx)
            if container:
                answer = dialogs.question(
                    ndx,
                    "Save calibration",
                    "Store the calibration in the measurement?\n\n"
                    f"{container}\n\n"
                    "Yes keeps it beside the photons and the burst table. "
                    "No writes a separate file instead.",
                    QtWidgets.QMessageBox.Yes
                    | QtWidgets.QMessageBox.No
                    | QtWidgets.QMessageBox.Cancel,
                    # Nobody at the keyboard writes nothing.
                    QtWidgets.QMessageBox.Cancel,
                )
                if answer == QtWidgets.QMessageBox.Cancel:
                    return
                if answer == QtWidgets.QMessageBox.Yes:
                    out = save_calibration(constants, ndx=ndx, embed=True)
                    dialogs.information(
                        ndx,
                        "FRET calibration",
                        f"Stored in {out.get('target', '')}"
                        if out.get("ok")
                        else f"Could not store: {out.get('error')}",
                    )
                    return
            start = (
                (container.rsplit(".", 1)[0] + SUFFIX) if container else ("calibration" + SUFFIX)
            )
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                ndx, "Save calibration", start, f"FRET calibration (*{SUFFIX});;All files (*)"
            )
            if not path:
                return
            out = save_calibration(constants, ndx=ndx, path=path, embed=False)
            dialogs.information(
                ndx,
                "FRET calibration",
                f"Saved to {out.get('target', '')}"
                if out.get("ok")
                else f"Could not save: {out.get('error')}",
            )

        def _load_calibration() -> None:
            """Read a calibration back and, if the user agrees, apply it."""
            from qtpy import QtWidgets

            from chisurf.plugins.ndxplorer.calibration_io import (
                SUFFIX,
                load_calibration,
                stored_calibrations,
            )

            stored = stored_calibrations(ndx)
            loaded = None
            if stored:
                answer = dialogs.question(
                    ndx,
                    "Load calibration",
                    f"This measurement carries {len(stored)} stored "
                    f"calibration(s).\n\nLoad the most recent one? "
                    f"No opens a file instead.",
                    QtWidgets.QMessageBox.Yes
                    | QtWidgets.QMessageBox.No
                    | QtWidgets.QMessageBox.Cancel,
                    # Nobody at the keyboard loads nothing.
                    QtWidgets.QMessageBox.Cancel,
                )
                if answer == QtWidgets.QMessageBox.Cancel:
                    return
                if answer == QtWidgets.QMessageBox.Yes:
                    loaded = load_calibration(ndx=ndx)
            if loaded is None:
                path, _ = QtWidgets.QFileDialog.getOpenFileName(
                    ndx, "Load calibration", "", f"FRET calibration (*{SUFFIX});;All files (*)"
                )
                if not path:
                    return
                loaded = load_calibration(path=path)
            if not loaded.get("ok"):
                dialogs.warning(ndx, "FRET calibration", str(loaded.get("error")))
                return

            constants = loaded.get("constants") or {}
            before = dict(getattr(ndx, "constants", {}) or {})
            # Show what would change BEFORE changing it: applying a calibration
            # silently replaces numbers the user may have determined elsewhere.
            changes = [
                f"  {name}: {before.get(name, '—')!s} → {value}"
                for name, value in sorted(constants.items())
                if before.get(name) != value
            ]
            detail = "\n".join(
                [
                    f"Saved {loaded.get('saved_utc', '')} ({loaded.get('where')}: "
                    f"{loaded.get('target', '')})"
                ]
                + ([f"Note: {loaded['note']}"] if loaded.get("note") else [])
                + ["", ("Changes:" if changes else "Nothing would change.")]
                + changes
            )
            if (
                dialogs.question(
                    ndx,
                    "Load calibration",
                    "Apply this calibration to the window?\n\n" + detail,
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                    # Nobody at the keyboard changes nothing.
                    QtWidgets.QMessageBox.No,
                )
                != QtWidgets.QMessageBox.Yes
            ):
                return
            ndx.constants = {**before, **constants}
            data_source = getattr(ndx, "data_source", None)
            try:
                if data_source is not None and hasattr(data_source, "compute_columns"):
                    data_source.compute_columns(
                        constants=ndx.constants,
                        equations=getattr(ndx, "equations", None),
                    )
                if hasattr(ndx, "update_plots"):
                    ndx.update_plots()
            except Exception:
                log("Loaded the calibration, but could not refresh the plots")
            if ndx_parameters is not None:
                ndx_parameters.pull(ndx)
            if loaded.get("report"):
                from chisurf.plugins.ndxplorer.calibration_report import (
                    show_calibration_report,
                )

                show_calibration_report(
                    ndx,
                    "FRET calibration — loaded",
                    loaded["report"],
                    constants=dict(ndx.constants),
                    ndx=ndx,
                )

        save_action = calibration_toolbar.addAction("💾 Save calibration")
        save_action.setToolTip(
            "Store the window's correction factors.\n\n"
            "Into the .pto measurement by default, beside the photons and the "
            "burst table it was determined from; a separate file when the "
            "window has no container or you ask for one."
        )
        save_action.triggered.connect(_save_calibration)

        load_action = calibration_toolbar.addAction("📂 Load calibration")
        load_action.setToolTip(
            "Read correction factors back — from this measurement's own stored "
            "calibration, or from a file.\n\n"
            "Shows what would change before changing anything."
        )
        load_action.triggered.connect(_load_calibration)

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
