"""A rally (score 3:2, rally 6, ball at 545,245) in the committed Qt Pong (HEAD pong.py) and in the emtk app."""
import sys, pathlib
from test.gui.emtk_port_parity import emtk_screenshot
sys.path.insert(0, str(pathlib.Path(__file__).parent))
out = pathlib.Path(sys.argv[1]); which = sys.argv[2]; prefix = sys.argv[3]
def rally(g):
    g.serve_timer = 0; g.player_score, g.cpu_score = 3, 2; g.rally = 6
    g.paddle_y, g.cpu_y = 245, 380; g.ball_x, g.ball_y = 545, 245
if which == "qt":
    from qtpy.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from qt_head import load_head_tool
    klass, _ = load_head_tool("pong", ())
    w = klass(); w.resize(820, 640); w.show(); app.processEvents()
    rally(w.game); w.game.paused = True
    w.host.ctx.canvas.force_draw(); app.processEvents()
    w.grab().save(str(out / f"{prefix}.png")); w.host.close(); w.close()
else:
    from emtk.testing import RecordingPainter
    from chisurf.plugins.misc.games.pong.app import make_app
    for size in [(1200, 800), (800, 600), (820, 640)]:
        a = make_app(); a.clock = lambda: 0
        rally(a.game); a.game.paused = True
        for _ in range(2): a.draw(RecordingPainter(), 0, 0, *size)
        emtk_screenshot(a, out / f"{prefix}_{size[0]}x{size[1]}.png", size)
