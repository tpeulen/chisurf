"""The Lumis Quest window.

This hosts the overworld on the chigame engine. It replaces the first draft's
XP/streak panel, which was a form with a free-text path field -- the sort of
thing the no-text-entry rule exists to prevent, and not a game.

The progression state (:mod:`..api.game_state`) is deliberately still here and
still unused by this screen: it holds XP, streaks and achievements that a later
phase attaches to real review actions. Wiring it to a walk would mean paying
out for wandering.
"""

from __future__ import annotations

from qtpy import QtWidgets

from chisurf.gui import chigame

from .overworld import OverworldGame

try:
    from chisurf.gui.misc_helpers import persist_plugin_state
except ImportError:  # pragma: no cover - stand-alone use

    def persist_plugin_state(name):
        """Return an identity decorator when the host is unavailable."""
        return lambda cls: cls


@persist_plugin_state("lumis_quest")
class LumisQuestWidget(QtWidgets.QWidget):
    """Dockable container hosting the overworld.

    Parameters
    ----------
    parent : QWidget, optional
        Parent widget.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Lumis Quest")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.game = OverworldGame()
        canvas, self.host = chigame.create_widget(self.game, parent=self)
        layout.addWidget(canvas)
        self.resize(900, 640)
