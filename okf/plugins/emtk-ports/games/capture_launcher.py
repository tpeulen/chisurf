import pathlib, sys
from emtk.testing import RecordingPainter
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.misc.games.gui.app import make_app
out = pathlib.Path(sys.argv[1]); prefix = sys.argv[2]
for size in [(1200, 800), (800, 600)]:
    for game in ("Number Quest", "Tetris", "Pong", "Minesweeper", "Breakout"):
        a = make_app(); a.select(game)
        for _ in range(3): a.draw(RecordingPainter(), 0, 0, *size)
        emtk_screenshot(a, out / f"{prefix}_{game.replace(' ', '_')}_{size[0]}x{size[1]}.png", size)
        a.close()
