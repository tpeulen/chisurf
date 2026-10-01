"""Combined FRET / HomoFRET Calculator GUI.

The window is a :class:`~chisurf.gui.widgets.tools.ChisurfDockTool` (PRD-23 /
PRD-36) hosting the EMTK app in :mod:`.app` (:class:`FretCalcApp`) — two tabs
backed by the backend services via :class:`FretCalculatorClient`. Geometry
persistence, the lazy MMFDB accessors, and the declared-message status bar
come from the shared base rather than being re-implemented here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from qtpy import QtCore, QtWidgets

from chisurf.gui.widgets.messages import Msg
from chisurf.gui.widgets.tools import ChisurfDockTool

from .client import FretCalculatorClient

_GUI_DIR = Path(__file__).parent


from .model import _distribution_series, _FretModel, _HomoFretModel


class _TabsShim:
    """Stands in for the old ``QTabWidget``: two tabs, countable."""

    _names = ("HeteroFRET", "HomoFRET")

    def count(self) -> int:
        return len(self._names)


class FretCalculatorTool(ChisurfDockTool):
    """Combined FRET / HomoFRET Calculator.

    Appears in the Plugins menu as ``Main:Tools:FRET-Calculator``. A calculator
    has no file inputs, so the base's window-level drop is answered with a
    standing message instead of being silently swallowed.
    """

    #: QSettings key for the base's geometry helpers (PRD-36 recipe step 1).
    tool_settings_name: str = "FretCalculatorTool"

    class Information(ChisurfDockTool.Information):
        """Conditions this tool can report."""

        no_file_input = Msg("The FRET Calculator takes no dropped files.")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.setWindowTitle("FRET Calculator")
        self.resize(380, 320)
        self._client = FretCalculatorClient()
        self._hetero_model = _FretModel()
        self._homo_model = _HomoFretModel()
        self.tabs = _TabsShim()

        from emtk.qt_host import ControlHost

        from .app import WINDOW_BG, FretCalcApp

        self.app = FretCalcApp(self)
        self.host = ControlHost(self.app, background=WINDOW_BG[:3])
        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.host)
        self.setCentralWidget(central)

        # Remember window position/size across sessions. The manifest declares
        # window statefulness; wire it here too so it applies however the plugin
        # is launched (the helper is idempotent). This is the mechanism that owns
        # geometry for this tool — the base's save/restore_window_geometry
        # helpers are left uncalled so the two do not both write a geometry key.
        try:
            from chisurf.core.plugin import load_manifest
            from chisurf.core.plugin.registry import apply_manifest_statefulness

            _manifest = load_manifest(Path(__file__).parents[1] / "manifest.json")
            if _manifest is not None:
                apply_manifest_statefulness(self, _manifest)
        except Exception:
            pass

    def on_paths_dropped(self, paths: list[Path]) -> None:
        """Report that the calculator has no file input.

        The base enables window-level path drag-drop for every dock tool. This
        tool computes from typed-in parameters, so a dropped path has nowhere to
        go; say so in the status bar rather than accepting the drop and doing
        nothing.
        """
        if paths:
            self.Information.no_file_input()


__all__ = ["FretCalculatorTool"]
