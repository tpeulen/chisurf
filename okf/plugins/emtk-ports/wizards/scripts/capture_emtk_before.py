"""The stream-state emtk hub (pre-upgrade/app.py.txt). Usage: <out dir>."""
import pathlib, sys
from emtk.testing import RecordingPainter
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.core.wizards.gui.app import make_app
out = pathlib.Path(sys.argv[1])
for size in ((1200, 800), (800, 600)):
    app = make_app()
    for _ in range(3): app.draw(RecordingPainter(), 0, 0, *size)
    emtk_screenshot(app, out / f"before_emtk_populated_{size[0]}x{size[1]}.png", size)
