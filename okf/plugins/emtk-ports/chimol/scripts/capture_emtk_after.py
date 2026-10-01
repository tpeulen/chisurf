"""After-captures of the emtk ChiMOL host: populated, help window, guide step."""
import sys, pathlib
from emtk.testing import RecordingPainter
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.chimol.app import make_app
out = pathlib.Path(sys.argv[1])
demo = "/Users/tpeulen/dev/chimol/chimol/data/demos/148l.pdb"
for size in [(1200, 800), (800, 600)]:
    tag = f"{size[0]}x{size[1]}"
    app = make_app()
    for _ in range(2): app.draw(RecordingPainter(), 0, 0, *size)
    app._chimol.cmd.do(f"load {demo}")
    for _ in range(3): app.draw(RecordingPainter(), 0, 0, *size)
    emtk_screenshot(app, out / f"after_populated_{tag}.png", size)
    app.help_window.show()
    emtk_screenshot(app, out / f"after_populated_help_{tag}.png", size)
    app.help_window.hide()
    app.tour.start(3)
    emtk_screenshot(app, out / f"after_populated_guide_{tag}.png", size)
    app.close()
