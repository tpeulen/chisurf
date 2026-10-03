"""The ndX window ChiSurf opens: the emtk app, hosted in a Qt window.

ndX is an emtk application (:class:`ndxplorer.app.frame.NdxApp`): one control
that draws the whole window and knows no toolkit. ChiSurf is a Qt application,
so the app is shown the way ChiSurf shows every emtk surface (Global View, the
Light Path Simulator): a :class:`~chisurf.gui.widgets.tools.chisurf_dock_tool.ChisurfDockTool`
whose central widget is :func:`emtk.qt_host.ControlHost` around the app.

Every route into ndX goes through :func:`build_ndxplorer_window` -- the menu
(the manifest's ``entrypoints.gui``), the ribbon (the plugin's ``__init__.py``),
and the tools that hand ndX a burst table (trace browser, ALEX suite, H2MM,
imaging, burst selection, the MMFDB launcher) -- so they cannot drift apart.

What ChiSurf adds to the app lives here, not in ndX (ndX works without
ChiSurf):

* the in-process ChiSurf RPC client (``app.chisurf_rpc``), which the app's
  "Send selection to" menu talks to;
* :func:`push_overlay_lines`: tabulated lines another tool computed (the
  FRET-line tool's *Push to ndX*) drawn in every open ndX window;
* the Global View slot: the app publishes its constants group under
  :data:`GLOBAL_VIEW_OWNER` itself (through ``ndxplorer.core.chisurf_binding``);
  the window withdraws it when it closes, unless a later window has taken it.

Why the QPainter host and not :func:`emtk.wgpu_host.WgpuControlHost`: the GPU
host forwards only the left button (no right-click gate and plot menus), does
not keep drawing while the app animates (playback, streamed results), does not
follow the app's window title and cannot be grabbed for a screenshot. The
QPainter host does all of that and draws ndX's 1400x900 frame in ~20 ms.
"""

from __future__ import annotations

import logging
from typing import Any

from chisurf.gui.widgets.tools.chisurf_dock_tool import ChisurfDockTool

logger = logging.getLogger(__name__)

__all__ = [
    "GLOBAL_VIEW_OWNER",
    "NdxWindow",
    "build_ndxplorer_window",
    "published_group",
    "push_overlay_lines",
]

# The Global View slot lives in a Qt-free module the emtk app shares.
from chisurf.plugins.ndxplorer.global_view_slot import (  # noqa: E402
    GLOBAL_VIEW_OWNER,
    published_group,
)
from chisurf.plugins.ndxplorer.global_view_slot import constants_group as _constants_group  # noqa: E402
from chisurf.plugins.ndxplorer.global_view_slot import withdraw_constants as _withdraw_constants  # noqa: E402

#: The window's first size, in logical pixels: the parity captures' size.
WINDOW_SIZE = (1400, 900)


def _ndx_version() -> str:
    """ndX's version, for a recorded processing run."""
    try:
        from importlib.metadata import version

        return version("ndxplorer")
    except Exception:  # noqa: BLE001 - not installed as a distribution
        return str(getattr(__import__("ndxplorer"), "__version__", "") or "unknown")


def push_overlay_lines(lines, source: str = "ChiSurf") -> int:
    """Draw tabulated lines in every open ndX window (``NdxApp.add_overlay_lines``).

    Every app of :func:`ndxplorer.app.frame.live_apps` takes them, whichever
    route opened it (this module's :class:`NdxWindow`, or the emtk entry point
    hosted directly); each becomes a data curve of its Overlays tab.

    Parameters
    ----------
    lines : sequence of dict
        A LineSet: ``{"name", "x", "y", "style": {"color"}}`` per line.
    source : str
        Who sent them, shown with the curves.

    Returns
    -------
    int
        How many windows took them (0: no ndX window is open).
    """
    from ndxplorer.app.frame import live_apps

    taken = 0
    for app in live_apps():
        try:
            app.add_overlay_lines(list(lines), source=source)
        except Exception:  # noqa: BLE001 - one window failing does not stop the rest
            logger.warning("ndX window did not take the lines", exc_info=True)
            continue
        wake = getattr(app, "request_frame", None)
        if callable(wake):
            wake()
        taken += 1
    return taken


class NdxWindow(ChisurfDockTool):
    """A Qt window that hosts the ndX emtk app.

    Parameters
    ----------
    app : ndxplorer.app.frame.NdxApp
        The app to host; the window closes it when it closes.
    parent : QWidget, optional

    Attributes
    ----------
    app : NdxApp
    host : QWidget
        The emtk control host, the window's central widget.
    """

    tool_settings_name = "ndxplorer"

    def __init__(self, app, parent=None) -> None:
        super().__init__(parent)
        from emtk.qt_host import ControlHost

        self.app = app
        app.on_exit = self.close
        app.mmfdb_opener = self.open_from_mmfdb
        self.setWindowTitle(app.window_title)
        self.resize(*WINDOW_SIZE)
        self.host = ControlHost(app, background=(30, 32, 38))
        self.host.setObjectName("ndxplorer_surface")
        self.setCentralWidget(self.host)
        self.restore_window_geometry()
        if getattr(app, "request_frame", None) is None:
            # what a push from another tool calls to show its lines
            app.request_frame = self.host.update

    # -- data ---------------------------------------------------------------
    def open_path(self, path) -> bool:
        """Open a file or folder in the app, as File > Open and a drop do."""
        ok = self.app.open_path(str(path))
        self.host.update()
        return ok

    def show_source(self, source, path: str | None = None) -> None:
        """Show an in-memory table (a :class:`ndxplorer.core.data_source.DataSource`).

        What a tool that has just computed bursts hands over. *path* is where
        the table came from, when there is such a place: it names the window
        and is where the stored calibration and session are looked up.
        """
        model = self.app.model
        model.set_source(source)
        if path:
            model.path = str(path)
        self.app.data_changed()
        self.host.update()

    def open_paths(self, paths, kind: str | None = None):
        """Open several files as one table, in the background (File > Import).

        *kind* is an importer of :data:`ndxplorer.io.loading.IMPORTERS`
        (``"pto"``, ``"bur"``...), or ``None`` to tell it from the paths.
        Returns the load task, or ``None`` when there was nothing to open.
        """
        paths = [str(p) for p in paths or ()]
        if not paths:
            return None
        task = self._feature("io").load(paths, kind)
        self.host.update()
        return task

    def refresh_stored_constants(self) -> dict:
        """Adopt the constants the open measurement stores, if they changed.

        What a workflow step calls when it is revisited: another step may have
        written a new background or calibration into the container since. A
        no-op when the stored values have not moved, so tuned values stay.
        """
        applied = self._feature("accurate_fret").restore_stored()
        self.host.update()
        return applied

    def open_from_mmfdb(self, client: Any = None) -> str | None:
        """File > Import > From MMFDB: pick a burst selection, open it here.

        The client is ChiSurf's shared in-process MMFDB client
        (:func:`chisurf.gui.widgets.mmfdb.picker.inprocess_client`), which
        adopts the session token of ChiSurf's MMFDB login -- ``mmfdb.status``
        refuses a client without one. When there is no client, or it does not
        answer, the app says why in a message box. Returns the opened path.
        """
        from chisurf.plugins.ndxplorer.mmfdb_launcher import pick_burst_selection_path

        title = "Open from MMFDB"
        if client is None:
            from chisurf.gui.widgets.mmfdb import picker

            client = picker.inprocess_client()
        if client is None:
            self._say(title, "The in-process MMFDB client could not be started "
                             "(MMFDB missing or its database not initialised).")
            return None
        try:
            client.status()
        except Exception as exc:  # noqa: BLE001 - said, not raised
            hint = "" if getattr(client, "token", None) else " (not logged in to MMFDB)"
            self._say(title, f"MMFDB did not answer{hint}: {exc}")
            return None
        path = pick_burst_selection_path(parent=self, client=client)
        if path:
            self.open_path(path)
        return path

    # -- provenance -----------------------------------------------------------
    def record_burst_ids_in_mmfdb(self, processed_data_id: str, experiment_id: str | None = None,
                                  client: Any = None) -> None:
        """Record what Save > Burst IDs saves against the MMFDB product shown here.

        What the MMFDB admin's *Open in ndX* sets: the window shows a processed
        product, so a saved burst selection is an analysis of it. Each save
        records an ``ndxplorer_selection`` processing run with the gate and a
        ``selection_mask`` product, linked to *processed_data_id*
        (``ndxplorer.record_analysis``), through the app's
        ``burst_ids_recorder`` hook.

        Parameters
        ----------
        processed_data_id : str
            The product the table came from.
        experiment_id : str, optional
            Its experiment; the run is recorded under it.
        client : object, optional
            An MMFDB client with ``call(method, params)``; ChiSurf's shared
            in-process client when omitted.
        """
        self._mmfdb_product = {"processed_data_id": str(processed_data_id),
                               "experiment_id": experiment_id, "client": client}
        self.app.burst_ids_recorder = self._record_burst_ids

    def _record_burst_ids(self, record: dict) -> str:
        """The app's ``burst_ids_recorder``: one ``ndxplorer.record_analysis`` call."""
        product = self._mmfdb_product
        client = product.get("client")
        if client is None:
            from chisurf.gui.widgets.mmfdb import picker

            client = picker.inprocess_client()
        if client is None:
            raise RuntimeError("the in-process MMFDB client could not be started")
        reply = client.call("ndxplorer.record_analysis", {
            "experiment_id": product.get("experiment_id") or "exp_1",
            "input_processed_data_ids": [product["processed_data_id"]],
            "analysis_type": "selection",
            "settings": {"gate": record["gate"], "folder": record["folder"],
                         "files": record["files"], "n_rows": record["n_rows"],
                         "n_selected": record["n_selected"]},
            "products": [{"product_type": "selection_mask", "storage_mode": "embedded_json",
                          "data": {"mask": record["mask"]}, "validation_status": "valid"}],
            "software_version": _ndx_version(),
        })
        run = (reply or {}).get("processing_run") or {}
        return (f"Recorded the selection ({record['n_selected']} of {record['n_rows']} bursts) "
                f"in MMFDB as {run.get('processing_id', 'a processing run')}")

    def _say(self, title: str, text: str) -> None:
        """A message box in the app (and the log): the reason a thing did not happen."""
        logger.warning("%s: %s", title, text)
        self.app.message = (title, text)
        self.host.update()

    def _feature(self, name: str):
        """The app's feature module *name* (``io``, ``accurate_fret``...)."""
        for feature in self.app.features:
            if feature.name == name:
                return feature
        raise LookupError(f"ndX has no {name!r} feature")

    def on_paths_dropped(self, paths) -> None:
        """A dropped file or folder goes to the app, which opens the first."""
        self.app.files_dropped([str(p) for p in paths])
        self.host.update()

    # -- closing ------------------------------------------------------------
    def closeEvent(self, event) -> None:  # noqa: N802 (Qt)
        """Close the app (it keeps its session) and empty the Global View slot."""
        try:
            self.app.close()
        except Exception:
            logger.warning("ndX did not close cleanly", exc_info=True)
        _withdraw_constants(self.app)
        self.save_window_geometry()
        super().closeEvent(event)


def build_ndxplorer_window(
    path: Any = None,
    *,
    data_source: Any = None,
    chisurf_rpc: Any = None,
    session_autosave: bool = True,
    layout_store: Any = "default",
    parent=None,
) -> NdxWindow:
    """Build ChiSurf's ndX window -- the one construction every route uses.

    Parameters
    ----------
    path : str or Path, optional
        A file or folder to open (a burst-analysis folder, a ``.pto``, a table).
    data_source : DataSource, optional
        An in-memory table to show instead (see :meth:`NdxWindow.show_source`).
    chisurf_rpc : object, optional
        The ChiSurf RPC client for "Send selection to";
        the in-process client (:func:`~chisurf.plugins.ndxplorer.rpc_bridge.make_inprocess_chisurf_client`)
        when omitted.
    session_autosave : bool
        Keep the analysis view in the opened measurement when the window leaves
        it. On for the user's window; a test or a capture passes ``False`` (or
        works on a copy): it must never write into a measurement unasked.
    layout_store : emtk.docking.LayoutStore or None
        Where the dock layout is kept: ndX's settings folder by default,
        ``None`` for this window only.
    parent : QWidget, optional

    Returns
    -------
    NdxWindow
        Not yet shown: the caller (the plugin launcher, the ribbon, a tool)
        shows it.
    """
    from ndxplorer.app.docks import layout_store as ndx_layout_store
    from ndxplorer.app.frame import NdxApp

    from chisurf.plugins.ndxplorer.rpc_bridge import make_inprocess_chisurf_client

    store = ndx_layout_store() if layout_store == "default" else layout_store
    app = NdxApp(layout_store=store, session_autosave=session_autosave)
    app.chisurf_rpc = chisurf_rpc if chisurf_rpc is not None else make_inprocess_chisurf_client()
    window = NdxWindow(app, parent=parent)
    if data_source is not None:
        window.show_source(data_source, path=str(path) if path else None)
    elif path:
        window.open_path(path)
    return window
