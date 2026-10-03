"""The stream-state hub (pre-upgrade/app.py.txt, copied to gui/app_old.py for the run) populated: Browser, Setup, Intensity.
Usage: <out_dir>."""
import pathlib, sys
from emtk.testing import RecordingPainter
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.microscopy.imaging_tools.gui.app_old import ImagingToolsApp
out = pathlib.Path(sys.argv[1])
for size in ((1200, 800), (800, 600)):
    app = ImagingToolsApp()
    app.goto_role("pixel_intensity")
    for _ in range(4): app.draw(RecordingPainter(), 0, 0, *size)
    emtk_screenshot(app, out / f"before_emtk_populated_{size[0]}x{size[1]}.png", size)
    app.close()
