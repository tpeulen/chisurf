"""GUI entry point of the Light Path Simulator.

The UI is the native EMTK app in :mod:`.app` (:class:`LightPathApp`) — the
optical-components palette, the light-path graph editor and the signals /
crosstalk results, all rendered and driven inside the EMTK canvas. This window
is its Qt host: it creates the MMFDB RPC client, hands it to the app's
controller and forwards a dropped graph file to the editor.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import numpy as np
from qtpy import QtWidgets

from chisurf.gui.widgets.tools.chisurf_dock_tool import ChisurfDockTool
from chisurf.plugins.core.lightpath_simulator.api.client import LightPathClient
from chisurf.plugins.core.lightpath_simulator.gui.node_types import (
    build_optical_registry,
)

logger = logging.getLogger(__name__)


def _deserialize_numpy(obj: Any) -> Any:
    """Recursively converts lists of numbers back into NumPy arrays for plotting."""
    if isinstance(obj, list):
        if obj and all(isinstance(x, (int, float)) for x in obj):
            return np.array(obj, dtype=np.float64)
        else:
            return [_deserialize_numpy(v) for v in obj]
    elif isinstance(obj, dict):
        return {k: _deserialize_numpy(v) for k, v in obj.items()}
    return obj


def _json_safe(obj: Any) -> Any:
    """Return a JSON-safe copy of graph state for RPC, settings, and files."""
    if callable(obj):
        return None
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, dict):
        cleaned = {}
        for key, value in obj.items():
            if str(key).startswith("_") or callable(value):
                continue
            safe_value = _json_safe(value)
            if safe_value is not None:
                cleaned[key] = safe_value
        return cleaned
    if isinstance(obj, (list, tuple)):
        return [value for value in (_json_safe(item) for item in obj) if value is not None]
    return obj


class LightPathSimulatorWidget(ChisurfDockTool):
    """Main window for defining and simulating an optical light path."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Light Path Simulator")
        self.resize(1000, 700)

        # The RPC client for interactive commands (simulate / catalogue / save).
        self.client = self.make_mmfdb_client()

        # Ensure our node registry is populated before the editor builds.
        build_optical_registry()

        from emtk.qt_host import ControlHost

        from .app import LightPathApp

        self.light_path_app = LightPathApp(client=self.client)
        self.host = ControlHost(self.light_path_app, background=(30, 32, 38))
        self.setCentralWidget(self.host)

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        """Persist the graph and shut the controller down on close."""
        self._save_graph_state()
        self.light_path_app.close()
        super().closeEvent(event)

    def _save_graph_state(self) -> None:
        """Save the node graph to QSettings, under the old tool's key."""
        try:
            from qtpy import QtCore

            from chisurf.gui.misc_helpers import get_plugin_settings_path

            settings = QtCore.QSettings(
                str(get_plugin_settings_path("LightPathSimulatorWidget")),
                QtCore.QSettings.IniFormat,
            )
            graph = _json_safe(self.light_path_app.controller.graph())
            if not graph.get("nodes"):
                return
            settings.setValue("graph", json.dumps(graph, sort_keys=True))
            settings.sync()
        except Exception as exc:
            logger.error("Failed to save lightpath graph state: %s", exc)

    # ── the RPC client ───────────────────────────────────────────────

    def make_mmfdb_client(self) -> LightPathClient:
        """Create an MMFDB client using the current session token when available."""
        client = LightPathClient.from_settings(timeout_ms=1500)
        logger.info("Light Path Simulator: created plugin RPC client")
        return client

    # ── graph access, for callers of the old tool API ────────────────

    def load_graph_from_dict(self, graph: dict) -> None:
        """Replace the editor's document with *graph* (a graph-state dict)."""
        self.light_path_app.controller.load_document(graph)

    def graph_state(self) -> dict:
        """The current graph as a JSON-safe dict (the old save format)."""
        return self.light_path_app.controller.graph()

    # ── drag & drop ──────────────────────────────────────────────────

    def dragEnterEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802 (Qt override)
        """A dropped graph file replaces the editor's document."""
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        if not urls:
            return
        path = urls[0].toLocalFile()
        if not path.endswith(".json"):
            return
        try:
            self.light_path_app.controller.load_graph(path)
            self.light_path_app.graph_control.fit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Light Path Simulator: could not open %s — %s", path, exc)
            self.light_path_app.controller.status = f"Error: could not open {path}: {exc}"
            self.host.update()
