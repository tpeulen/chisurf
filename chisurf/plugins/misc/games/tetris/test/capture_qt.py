"""Capture the retained Qt GPU Tetris view with a populated well."""
from pathlib import Path

from qtpy.QtWidgets import QApplication

from ..tetris import Tetris


def populate(game):
    game.shape = 5
    game.coords = [(-1, -1), (0, -1), (1, -1), (0, 0)]
    game.x, game.y = 5, 8
    game.score, game.lines, game.level = 1700, 12, 2
    for row, cells in ((21, range(0, 8)), (20, range(2, 10)), (19, (2, 3, 4, 7))):
        for col in cells:
            game.well[row][col] = (col + row) % 7


def main():
    app = QApplication.instance() or QApplication([])
    window = Tetris()
    window.show()
    app.processEvents()
    populate(window.game)
    window.host.ctx.canvas.force_draw()
    app.processEvents()
    out = Path(__file__).parent / "renders"
    out.mkdir(exist_ok=True)
    window.grab().save(str(out / "qt-widget-populated.png"))
    window.host.close()
    window.close()


if __name__ == "__main__":
    main()
