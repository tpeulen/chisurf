"""The stream's populated board (fixed mines, reveal (8,5), flag (0,0)) in the Qt MinesweeperWidget and the emtk app."""
import sys, pathlib
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.misc.games.minesweeper.test.capture_native import populate
out = pathlib.Path(sys.argv[1]); which = sys.argv[2]; prefix = sys.argv[3]
if which == "qt":
    from qtpy.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from chisurf.plugins.misc.games.minesweeper.gui.tool import MinesweeperWidget
    w = MinesweeperWidget(); w.resize(560, 620); w.show(); app.processEvents()
    populate(w.game.game); w.host.ctx.canvas.force_draw(); app.processEvents()
    w.grab().save(str(out / f"{prefix}.png")); w.host.close(); w.close()
else:
    from emtk.testing import RecordingPainter
    from chisurf.plugins.misc.games.minesweeper.gui.app import make_app
    for size in [(1200, 800), (800, 600), (560, 620)]:
        a = make_app(); populate(a.game)
        for _ in range(2): a.draw(RecordingPainter(), 0, 0, *size)
        emtk_screenshot(a, out / f"{prefix}_{size[0]}x{size[1]}.png", size)
