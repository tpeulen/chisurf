"""Step 3 of the legacy Qt ALEX Suite shell: the µs-ALEX alternation, hosted in Qt.

The state and the work are :class:`.alternation_model.AlexAlternationModel` (Qt-free, shared with the native hub
in :mod:`.native`); the canvas is :class:`.app.AlexAlternationApp`. This widget only hosts the canvas, polls the
model's background job and hands a conversion to the Qt workflow shell (``adopt_alex_conversion``).
"""

from __future__ import annotations

import logging

from qtpy import QtCore, QtWidgets

from .alternation_model import SETUP_NAME, AlexAlternationModel, build_setup, parse_channels

logger = logging.getLogger("chisurf.plugins.burst")

#: Kept for callers of the old private name.
_channels = parse_channels


class AlexAlternationPanel(QtWidgets.QWidget):
    """Detect the ALEX alternation, fold it into the micro-time, name the gates (Qt host of the model)."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        """Build the panel: the model, the emtk canvas, and the poll timer of its background job."""
        super().__init__(parent)
        self._workflow = parent
        self.model = AlexAlternationModel(on_converted=self._adopt)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        from emtk.qt_host import ControlHost

        from .app import WINDOW_BG, AlexAlternationApp

        self.app = AlexAlternationApp(self.model)
        self.host = ControlHost(self.app, background=WINDOW_BG[:3])
        layout.addWidget(self.host, 1)
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._poll)
        self._timer.start()

    def _poll(self) -> None:
        if self.model.poll() or self.model.running:
            self.host.update()

    def _adopt(self, setup: dict, converted) -> None:
        adopt = getattr(self._workflow, "adopt_alex_conversion", None)
        if callable(adopt):
            adopt(setup, converted)

    # -- workflow hand-off (the Qt shell's names) ----------------------------------------------------------- #
    def set_files(self, files) -> None:
        """Adopt the raw files chosen upstream; µs-ALEX data is detected and converted on arrival."""
        self.model.set_files(files)
        self.host.update()

    def run(self, *, convert: bool = True) -> None:
        """Detect the alternation and, unless ``convert`` is false, convert."""
        self.model.run(convert=convert)
        self.host.update()

    def result(self) -> dict | None:
        """Return the last detection result, or ``None`` if it has not run."""
        return self.model.result


__all__ = ["SETUP_NAME", "AlexAlternationPanel", "build_setup"]
