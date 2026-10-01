"""A mid-game well (score 1700, 12 lines, level 2) in the committed Qt Tetris (HEAD tetris.py) and in the emtk app."""
import sys, pathlib
from test.gui.emtk_port_parity import emtk_screenshot
sys.path.insert(0, str(pathlib.Path(__file__).parent))
out = pathlib.Path(sys.argv[1]); which = sys.argv[2]; prefix = sys.argv[3]
def populate(game):
    game.shape = 5
    game.coords = [(-1, -1), (0, -1), (1, -1), (0, 0)]
    game.x, game.y = 5, 8
    game.score, game.lines, game.level = 1700, 12, 2
    for row in range(14, 20):
        for col in range(10):
            if (col + row) % 3:
                game.well[row][col] = (col + row) % 7
    game.paused = True
if which == "qt":
    from qtpy.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from qt_head import load_head_tool
    klass, _ = load_head_tool("tetris", ())
    w = klass(); w.show(); app.processEvents()
    populate(w.game); w.host.ctx.canvas.force_draw(); app.processEvents()
    w.grab().save(str(out / f"{prefix}.png")); w.host.close(); w.close()
else:
    from emtk.testing import RecordingPainter
    from chisurf.plugins.misc.games.tetris.app import make_app
    for size in [(1200, 800), (800, 600), (480, 600)]:
        a = make_app(); a.clock = lambda: 0
        populate(a.game)
        for _ in range(2): a.draw(RecordingPainter(), 0, 0, *size)
        emtk_screenshot(a, out / f"{prefix}_{size[0]}x{size[1]}.png", size)
