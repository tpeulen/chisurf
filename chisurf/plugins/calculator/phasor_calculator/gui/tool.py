"""Interactive phasor-plot calculator embeddable in the Calculators hub.

A data-free phasor plot: the model holds the frequency, reference lifetimes and the
FRET / two-component overlay settings, and the EMTK app in :mod:`.app` renders the
controls beside the phasor section. Overlay geometry is assembled by the shared
toolkit (:func:`chisurf.plugins.microscopy.img_pixel_phasor.analysis.build_overlays`),
so the calculator, the imaging plugin and the ``phasor.overlays`` RPC method stay
in sync. This window is the Qt host around that app.
"""

from __future__ import annotations

import pathlib
from typing import Any

from qtpy import QtWidgets

from chisurf.gui.widgets.tools.chisurf_dock_tool import ChisurfDockTool

_GUI_DIR = pathlib.Path(__file__).parent


from .model import _PhasorCalcModel


class _FormShim:
    """Compatibility shim for callers expecting an AutoForm interface."""

    def __init__(self, host: QtWidgets.QWidget) -> None:
        self._host = host

    def sync_fields(self) -> None:
        self._host.update()

    def refresh_plots(self) -> None:
        self._host.update()


class PhasorCalculatorTool(ChisurfDockTool):
    """Interactive phasor plot; constructs with no required arguments (hub-embeddable)."""

    name = "Phasor calculator"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.setWindowTitle("Phasor calculator")
        self.resize(860, 660)

        from emtk.qt_host import ControlHost

        from .app import WINDOW_BG, PhasorCalcApp

        self._model = _PhasorCalcModel()
        self.app = PhasorCalcApp(self)
        self.host = ControlHost(self.app, background=WINDOW_BG[:3])
        self.setCentralWidget(self.host)
        self._form = _FormShim(self.host)
        self._apply_statefulness()

    def _apply_statefulness(self) -> None:
        try:
            from chisurf.core.plugin import load_manifest
            from chisurf.core.plugin.registry import apply_manifest_statefulness

            manifest = load_manifest(pathlib.Path(__file__).parents[1] / "manifest.json")
            if manifest is not None:
                apply_manifest_statefulness(self, manifest)
        except Exception:
            pass


__all__ = ["PhasorCalculatorTool"]
