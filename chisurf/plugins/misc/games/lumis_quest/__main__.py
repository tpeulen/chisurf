"""Standalone launcher for Lumis Quest game."""

from __future__ import annotations

import sys

from qtpy import QtWidgets

from chisurf.plugins.misc.games.lumis_quest.gui.tool import LumisQuestWidget


def main() -> None:
    """Launch Lumis Quest as a standalone Qt application."""
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)

    window = QtWidgets.QMainWindow()
    window.setWindowTitle("Lumis Quest")
    widget = LumisQuestWidget()
    window.setCentralWidget(widget)
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
