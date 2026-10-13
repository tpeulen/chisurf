"""Capture the populated native hub at two widths.

The Qt hub's "before" is recorded as ``renders/hub-qt-reference.png`` (the Qt hub is retired).
"""

from __future__ import annotations

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


if __name__ == "__main__":
    native()
