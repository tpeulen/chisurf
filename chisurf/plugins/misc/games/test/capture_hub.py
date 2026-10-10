"""Capture the actual Qt hub and populated native hub at two widths."""

from __future__ import annotations

import os
from pathlib import Path

from emtk.pil_painter import PilPainter

from ..gui.app import make_app

OUTPUT = Path(__file__).with_name("renders")
MINES = {(0, 0), (0, 3), (1, 7), (2, 4), (3, 2), (4, 8), (5, 5), (6, 1), (7, 7), (8, 3)}


def populate(game):
    game._fixed_mine_positions = MINES
    game.reset()
    game.reveal(8, 5)
    game.toggle_flag(0, 0)


def native():
    OUTPUT.mkdir(exist_ok=True)
    for width, height, label in ((1060, 730, "normal"), (720, 680, "narrow")):
        app = make_app()
        populate(app.select("Minesweeper").game)
        for _ in range(2):
            painter = PilPainter(width, height)
            app.draw(painter, 0, 0, width, height)
        painter.frame.save(OUTPUT / f"hub-native-{label}.png")
        app.close()


def qt():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from qtpy import QtWidgets

    from ..gui.tool import GamesWidget

    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = GamesWidget()
    window.show()
    window.nav_list.setCurrentRow(1)
    application.processEvents()
    game_widgets = window.panels[1]["instance"].findChildren(QtWidgets.QWidget)
    game_widget = next(
        (w for w in game_widgets if hasattr(w, "game") and hasattr(w.game, "game")), None
    )
    if game_widget is not None:
        populate(game_widget.game.game)
    else:
        print("Qt hub opened, but its game panel could not load without a GPU adapter")
    for _ in range(3):
        application.processEvents()
    window.grab().save(str(OUTPUT / "hub-qt-reference.png"))
    window.close()


if __name__ == "__main__":
    native()
    qt()
