"""The ndX window ChiSurf opens: one construction for every route.

ChiSurf opens ndX two ways -- the menu, through the manifest's
``entrypoints.gui``, and the ribbon, which executes the plugin's
``__init__.py`` -- and the two used to build different windows. The menu got
:func:`~chisurf.plugins.ndxplorer.rpc_bridge.make_ndxplorer` alone (phasor
toolbar, calibration restore); only the ribbon added the Accurate FRET toolbar,
the MMFDB toolbar and the Global View binding, because that code lived in
``__init__.py``. Both routes now call :func:`build_ndxplorer_window`.

The other in-GUI launchers (trace browser, ALEX suite, H2MM, imaging) keep the
bare :func:`make_ndxplorer`: the Global View binding is a single slot
(``owner_id="ndxplorer"``), which the ChiSurf ndX window owns.

The Qt window is legacy (the emtk app replaces it); this module only assembles
what already exists.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

#: The Global View slot of ChiSurf's ndX window (the one ndX's own parameter
#: editor registers its constants under).
GLOBAL_VIEW_OWNER = "ndxplorer"
GLOBAL_VIEW_LABEL = "ndX constants"


def build_ndxplorer_window(**kwargs: Any):
    """Build ChiSurf's ndX window, as both the menu and the ribbon open it.

    Parameters
    ----------
    **kwargs
        Passed to :func:`~chisurf.plugins.ndxplorer.rpc_bridge.make_ndxplorer`
        (and on to ``NDXplorer``).

    Returns
    -------
    NDXplorer
        The window, not yet shown: the caller (ChiSurf's plugin launcher, or
        the ribbon's ``__init__.py``) shows it.
    """
    from chisurf.plugins.ndxplorer.rpc_bridge import make_ndxplorer

    ndx = make_ndxplorer(**kwargs)
    add_mmfdb_toolbar(ndx)
    _bind_global_view(ndx)
    _add_accurate_fret_toolbar(ndx)
    return ndx


def _tell(ndx, message: str) -> None:
    """Log *message* as a warning and show it in the window's status bar."""
    logger.warning(message)
    try:
        ndx.statusBar().showMessage(message, 15000)
    except Exception:
        logger.debug("could not show the message in the status bar", exc_info=True)


def add_mmfdb_toolbar(ndx, client: Any = None):
    """Add "Open from MMFDB" to *ndx* when MMFDB answers, else say why not.

    The client is ChiSurf's shared in-process MMFDB client
    (:func:`chisurf.gui.widgets.mmfdb.picker.inprocess_client`), which adopts
    the session token of ChiSurf's MMFDB login. A private
    ``MMFDBClient(inprocess=True)`` has no token, and ``mmfdb.status`` requires
    one, so the toolbar never appeared.

    Parameters
    ----------
    ndx : NDXplorer
        The window.
    client : object, optional
        MMFDB client; the shared session client when omitted.

    Returns
    -------
    QToolBar or None
        The toolbar, or ``None`` when MMFDB is not available -- in which case
        the reason is logged as a warning and shown in the status bar.
    """
    try:
        from ndxplorer.__main__ import open_path_like_drop
        from qtpy import QtCore

        from chisurf.gui.glyphs import Glyphs
        from chisurf.gui.widgets.mmfdb.dataset_browser import MmfdbDatasetPickerDialog
        from chisurf.plugins.ndxplorer.mmfdb_launcher import (
            BURST_FORMATS,
            BURST_KINDS,
            resolve_dataset_path,
        )

        if client is None:
            from chisurf.gui.widgets.mmfdb import picker

            client = picker.inprocess_client()
    except Exception as exc:
        _tell(ndx, f"ndX: no MMFDB toolbar -- the MMFDB client is not installed ({exc})")
        return None
    if client is None:
        _tell(
            ndx,
            "ndX: no MMFDB toolbar -- the in-process MMFDB client could not be "
            "started (MMFDB missing or its database not initialised)",
        )
        return None
    try:
        client.status()
    except Exception as exc:
        hint = "" if getattr(client, "token", None) else " (no MMFDB session: not logged in)"
        _tell(ndx, f"ndX: no MMFDB toolbar -- MMFDB did not answer{hint}: {exc}")
        return None

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
    return toolbar


def _bind_global_view(ndx) -> None:
    """Publish the window's constants in the Global View, once they exist.

    The constants are nDXplorer's own parameter group (the window's
    ``constants_group``), and :mod:`ndxplorer.core.chisurf_binding` keeps the
    one ChiSurf mirror of it: this puts that mirror in the owner slot
    ``"ndxplorer"``, where it shows up next to every fit parameter and can be
    linked to one. The slot is emptied when the window goes away, unless a
    later window has taken it.

    The window builds its parameter table in a deferred step after the
    constructor, so the group may not exist yet; then the publishing waits for
    the event loop to run that step (a zero timer queued after it).
    """
    if getattr(ndx, "constants_group", None) is not None:
        _publish_constants(ndx)
        return
    from qtpy import QtCore

    # A timer the window owns: a window deleted before the loop turns takes it
    # along, and nothing is published for it.
    later = QtCore.QTimer(ndx)
    later.setSingleShot(True)
    later.timeout.connect(lambda: _publish_constants(ndx))
    later.start(0)


def _publish_constants(ndx):
    """Put ``ndx.constants_group``'s mirror in the Global View; return the group."""
    group = getattr(ndx, "constants_group", None)
    if group is None:
        logger.warning("ndX constants not in the Global View: the window has no parameter group")
        return None
    from ndxplorer.core import chisurf_binding

    if not chisurf_binding.publish(group, GLOBAL_VIEW_OWNER, GLOBAL_VIEW_LABEL):
        logger.warning(
            "Could not publish the ndX constants in the Global View: %s",
            chisurf_binding.why_unavailable() or "ChiSurf registry refused the group",
        )
        return None

    def _withdraw(*_args) -> None:
        from ndxplorer.core import parameters

        held = {owner: g for owner, _label, g in parameters.registered_groups()}
        if held.get(GLOBAL_VIEW_OWNER) is group:
            parameters.unregister_group(GLOBAL_VIEW_OWNER)  # ndX's registry and ChiSurf's
        elif chisurf_binding.chisurf_group(group) is published_group():
            chisurf_binding.withdraw(GLOBAL_VIEW_OWNER)

    destroyed = getattr(ndx, "destroyed", None)
    if destroyed is not None and hasattr(destroyed, "connect"):
        destroyed.connect(_withdraw)
    logger.info("ndX constants in the Global View: %d", len(group.parameters_all))
    return group


def published_group():
    """The ChiSurf group in the ndX Global View slot (``None``: empty)."""
    from chisurf.core.registry.parameter_groups import iter_registered_parameter_groups

    for owner_id, _label, group in iter_registered_parameter_groups():
        if owner_id == GLOBAL_VIEW_OWNER:
            return group
    return None


def _add_accurate_fret_toolbar(ndx) -> None:
    """Add the Accurate FRET toolbar: calibrate, save, load."""
    from chisurf.gui import dialogs

    log = logger.info

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
            # The report is ndX's, so the emtk app reads the same text.
            from ndxplorer.analysis.fret_calibration import report_text

            # Store it before showing the report: the numbers are worth more
            # than the window, and a user who closes the report should not
            # thereby have discarded the calibration.
            saved = None
            if getattr(options, "save_when_done", False):
                from ndxplorer.io.fret_calibration_io import save_calibration

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
                report_text(result),
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
            from ndxplorer.io.fret_calibration_io import (
                SUFFIX,
                container_of,
                save_calibration,
            )
            from qtpy import QtWidgets

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
            from ndxplorer.io.fret_calibration_io import (
                SUFFIX,
                load_calibration,
                stored_calibrations,
            )
            from qtpy import QtWidgets

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
            # Through the parameter table: the constants are its group, and the
            # Global View shows that group's mirror.
            from chisurf.plugins.ndxplorer.calibration_bridge import _push_constants

            try:
                _push_constants(ndx, constants)
            except Exception:
                log("Loaded the calibration, but could not refresh the plots")
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
    except Exception:
        logger.warning("Could not add the accurate-FRET toolbar to ndX", exc_info=True)
