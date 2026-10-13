"""Capture populated native boards (the legacy Qt renders are recorded as ``renders/qt-game-*.png``)."""

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


def main():
    OUTPUT.mkdir(exist_ok=True)
    for width, height in ((560, 620), (360, 620)):
        app = make_app()
        populate(app.game)
        for _ in range(2):
            painter = PilPainter(width, height)
            app.draw(painter, 0, 0, width, height)
        painter.frame.save(OUTPUT / f"native-{width}x{height}.png")


if __name__ == "__main__":
    main()
