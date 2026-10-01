import sys, pathlib
from emtk.testing import RecordingPainter
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.chimol.app import make_app
out = pathlib.Path(sys.argv[1]); prefix = sys.argv[2]
demo = "/Users/tpeulen/dev/chimol/chimol/data/demos/148l.pdb"
for size in [(1200, 800), (800, 600)]:
    app = make_app()
    app.draw(RecordingPainter(), 0, 0, *size)
    emtk_screenshot(app, out / f"{prefix}_empty_{size[0]}x{size[1]}.png", size)
    app._chimol.cmd.do(f"load {demo}")
    for _ in range(3): app.draw(RecordingPainter(), 0, 0, *size)
    emtk_screenshot(app, out / f"{prefix}_populated_{size[0]}x{size[1]}.png", size)
    print(size, "objects", len(app._chimol.viewer.objects))
    app.close()
