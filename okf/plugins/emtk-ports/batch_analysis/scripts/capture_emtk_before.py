"""The stream-state emtk app (pre-upgrade/app.py.txt), populated. Usage: <out_dir>."""
import pathlib, sys
from emtk.testing import RecordingPainter
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.core.batch_analysis.gui.app import make_app

out = pathlib.Path(sys.argv[1])
for size in ((1200, 800), (800, 600)):
    app = make_app()
    app.model.files = ["/data/run_01.sm", "/data/run_02.sm"]
    app.model.selected_fit_name = "Template fit"
    app.model.save_path = "/data/results.csv"
    for _ in range(2):
        app.draw(RecordingPainter(), 0, 0, *size)
    emtk_screenshot(app, out / f"before_emtk_populated_{size[0]}x{size[1]}.png", size)
