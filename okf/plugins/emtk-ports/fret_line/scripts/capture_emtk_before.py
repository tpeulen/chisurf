"""The stream-state emtk app populated (static + fraction line). Usage: <out_dir>."""
import pathlib, sys
from emtk.testing import RecordingPainter
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.fret_line.gui.app import make_app
out = pathlib.Path(sys.argv[1])
for size in ((1200, 800), (800, 600)):
    app = make_app(); app.minimum, app.maximum = 20.0, 120.0
    app.compute(); app.add_component()
    t = app.sweep_targets(); app.sweep_index = next(i for i, x in enumerate(t) if x.get("kind") == "fraction"); app.minimum, app.maximum = 0.0, 1.0
    app.compute()
    for _ in range(3): app.draw(RecordingPainter(), 0, 0, *size)
    emtk_screenshot(app, out / f"before_emtk_populated_{size[0]}x{size[1]}.png", size)
