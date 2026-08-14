"""The Ninja Adventure window: the game in a dockable canvas."""

from __future__ import annotations

from qtpy import QtWidgets

from chisurf.gui import chigame

from .game import NinjaAdventure

try:
    from chisurf.gui.misc_helpers import persist_plugin_state
except ImportError:  # pragma: no cover - stand-alone use

    def persist_plugin_state(name):
        """Return an identity decorator when the host is unavailable."""
        return lambda cls: cls


@persist_plugin_state("ninja_adventure")
class NinjaAdventureWidget(QtWidgets.QWidget):
    """Dockable container hosting the ported map.

    Parameters
    ----------
    parent : QWidget, optional
        Parent widget.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Ninja Adventure")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.game = NinjaAdventure()
        canvas, self.host = chigame.create_widget(self.game, parent=self)
        layout.addWidget(canvas)
        self.resize(900, 640)

    def closeEvent(self, event) -> None:
        """Stop the audio when the dock closes.

        Parameters
        ----------
        event : QCloseEvent
            The close event.
        """
        try:
            self.host.audio.stop()
        except Exception:
            pass
        super().closeEvent(event)
