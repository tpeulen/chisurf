"""Bind ndX's shared EMTK explorer to ChiSurf's plugin and FRET bridges."""
from __future__ import annotations

import sys
from pathlib import Path


class ChiSurfNdxSource:
    """The numeric data and calibration surface consumed by native ChiSurf tools."""

    def __init__(self, app):
        self.app = app

    @property
    def data_source(self):
        """The active data source, or ``None`` before a dataset is opened."""
        return self.app.model.source

    @property
    def constants(self):
        """ndX equation constants (the same mapping its explorer model reads)."""
        return self.app.model.manager.constants

    @constants.setter
    def constants(self, values):
        self.app.model.manager.constants = dict(values or {})

    @property
    def equations(self):
        """The active derived-column equations."""
        return self.app.model.manager.equations

    def get_burst_columns(self):
        """Return the active table's numeric columns for Accurate-FRET."""
        from chisurf.plugins.ndxplorer.calibration_bridge import ndx_columns

        return ndx_columns(self.data_source)

    def apply_fret_calibration(self, calibration):
        """Apply a ChiSurf calibration to ndX constants and derived columns."""
        from chisurf.plugins.ndxplorer.calibration_bridge import push_calibration_to_ndx

        return push_calibration_to_ndx(self, calibration)

    def update_plots(self):
        """Recompute ndX histograms and wake the current EMTK host."""
        self.app.model.invalidate()
        self.app.request_frame()


def _add_mmfdb_integration(app):
    """Replace ndX's standalone placeholder with ChiSurf's native dataset picker."""
    from ndxplorer.app.features import Feature
    from ndxplorer.app.menus import build_menu_bar

    from chisurf.emtk.dataset_picker import DatasetPicker, session_client
    from chisurf.plugins.ndxplorer.mmfdb_launcher import BURST_FORMATS, BURST_KINDS

    class MmfdbFeature(Feature):
        name = "chisurf_mmfdb"

        def __init__(self, owner):
            super().__init__(owner)
            self.picker = None

        def actions(self):
            return {"open_from_mmfdb": self.open_from_mmfdb}

        def available(self, action):
            return True if action == "open_from_mmfdb" else None

        def menu_entries(self):
            return [(("File", "Import"), {"label": "From MMFDB…",
                    "action": "open_from_mmfdb",
                    "description": "Browse authenticated MMFDB burst selections and open one in ndX."})]

        def open_from_mmfdb(self):
            self.picker = DatasetPicker(
                client=session_client(), kinds=BURST_KINDS, formats=BURST_FORMATS,
                scope="all", on_paths=self.open_paths, on_selected=self.open_selection,
            )
            self.picker.open()

        def open_paths(self, paths):
            if not paths or not self.app.open_path(str(paths[0])):
                raise ValueError(self.app.model.error or "The selected burst table could not be opened")
            self.app.show_status(f"Opened burst selection: {Path(paths[0]).name}")

        def open_selection(self, selection):
            from chisurf.plugins.ndxplorer.selection_provenance import record_artifact_selection

            client, artifact_id = self.picker.client, selection.artifact_id
            self.app.burst_ids_recorder = lambda record: record_artifact_selection(client, artifact_id, record)

        def on_data_changed(self):
            # A replacement/merge must not inherit another artifact's provenance.
            self.app.burst_ids_recorder = None

        def draw_windows(self):
            if self.picker is None or not self.picker.is_open:
                return False
            self.picker.render(self.app.box)
            return self.picker.is_open

        def close(self):
            if self.picker is not None:
                self.picker.close()

    feature = MmfdbFeature(app)
    fret = next((item for item in app.features if item.name == "accurate_fret"), None)
    if fret is not None:
        old_available = fret.available
        fret.available = lambda action: (None if action == "open_from_mmfdb"
                                         else old_available(action))
        fret.menu_entries = lambda: [
            (path, entry) for path, entry in fret.__class__.menu_entries(fret)
            if entry is None or entry.get("action") != "open_from_mmfdb"
        ]
    app.features.append(feature)
    app.panel.actions["open_from_mmfdb"] = feature.open_from_mmfdb
    app.menubar = build_menu_bar(app.panel.available, app._checked,
                                 extra=app._feature_menu_entries())
    return feature


def _load_ndx_app_factory():
    """Import the bundled ndX app whether its module root is installed or vendored."""
    root = Path(__file__).resolve().parents[4] / "modules" / "ndxplorer"
    if root.is_dir() and str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from ndxplorer.app.frame import NdxApp

    return NdxApp


def make_app(session_autosave: bool = True, chisurf_rpc=None):
    """Construct native ndX the way ChiSurf's Qt window builds it, and share its source.

    Parameters
    ----------
    session_autosave : bool
        Keep the analysis view in the opened measurement when ndX leaves it (the
        Qt window's default). A test or a capture passes ``False``: it must never
        write into a measurement unasked.
    chisurf_rpc : object, optional
        The ChiSurf RPC client "Send selection to" talks to; the in-process client
        when omitted.
    """
    from chisurf.emtk.session_sources import register_source, unregister_source
    NdxApp = _load_ndx_app_factory()
    from chisurf.emtk.i18n import install as install_translations

    install_translations()
    # The dock layout is bound to ChiSurf's native-state store below
    # (attach_native_state), so no ndX layout store is passed here.
    app = NdxApp(session_autosave=session_autosave)
    if chisurf_rpc is None:
        from chisurf.plugins.ndxplorer.rpc_bridge import make_inprocess_chisurf_client

        chisurf_rpc = make_inprocess_chisurf_client()
    app.chisurf_rpc = chisurf_rpc
    root_split = app.docks.splits.get("root")
    if root_split is not None and not app.docks._saved:
        root_split.ratio = 0.44
    app.close_requested = False
    app._chisurf_request_frame_callback = None
    app._chisurf_closed = False
    source = ChiSurfNdxSource(app)
    app._chisurf_native_source = source
    register_source("ndx", source)
    mmfdb_feature = _add_mmfdb_integration(app)

    def set_frame_request_callback(callback):
        # emtk's Qt host (what ChiSurf's menu wraps the app in) never calls the
        # app's close(); it only detaches this callback when its window closes.
        # A callback removed after one was set therefore means "the window is
        # gone": close as the Qt NdxWindow does (session kept, layout saved,
        # Global View slot emptied).
        had_host = app._chisurf_request_frame_callback is not None
        app._chisurf_request_frame_callback = callback
        if callback is None and had_host and not app._chisurf_closed:
            app.close()

    def request_frame():
        callback = app._chisurf_request_frame_callback
        if callable(callback):
            callback()

    original_close = app.close

    def close():
        from chisurf.plugins.ndxplorer.global_view_slot import withdraw_constants

        if app._chisurf_closed:
            return
        app._chisurf_closed = True
        unregister_source("ndx", source)
        mmfdb_feature.close()
        app._chisurf_request_frame_callback = None
        original_close()
        # Empty the Global View slot if it still holds this app's constants, as
        # the Qt window does when it closes.
        withdraw_constants(app)

    def exit_app():
        app.close_requested = True
        request_frame()

    app.set_frame_request_callback = set_frame_request_callback
    app.request_frame = request_frame
    app.close = close
    app.on_exit = exit_app
    from chisurf.emtk.state import attach_native_state

    attach_native_state("ndxplorer", app)
    return app
