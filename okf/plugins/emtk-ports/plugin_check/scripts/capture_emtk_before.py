"""The stream-state emtk app (pre-upgrade/app.py.txt), populated with injected sweep results. Usage: <out_dir>."""
import pathlib, sys
from emtk.testing import RecordingPainter
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.core.plugin_check.gui.app import make_app

out = pathlib.Path(sys.argv[1])
for size in ((1200, 800), (800, 600)):
    app = make_app()
    keys = sorted(app.model.catalog)
    for i, (k, r) in enumerate([(keys[0], {"status": "pass"}), (keys[1], {"status": "fail", "error": "Traceback\nImportError: foo"}),
                                (keys[2], {"status": "skipped", "error": "Blacklisted after repeated failures"})]):
        app.model._events.put((k, r))
    app.draw(RecordingPainter(), 0, 0, *size); app.selected = keys[1]
    for _ in range(2): app.draw(RecordingPainter(), 0, 0, *size)
    emtk_screenshot(app, out / f"before_emtk_populated_{size[0]}x{size[1]}.png", size)
