"""Capture the plugin's emtk app on every one of its tabs, on TEMPORARY settings.

Usage: python capture_emtk_tabs.py <out_dir> <prefix>   (e.g. before_emtk / after)
The evidence tool captures only the first tab; this drives a real click on each tab.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

out, prefix = Path(sys.argv[1]), sys.argv[2]
tmp = Path(tempfile.mkdtemp(prefix="scd_emtk_"))
os.environ["CHISURF_SETTINGS_DIR"] = str(tmp / "s")
os.environ["MMFDB_SETTINGS_DIR"] = str(tmp / "m")
os.environ["MMFDB_DATABASE_PATH"] = str(tmp / "m" / "db.sqlite")
(tmp / "s").mkdir()
(tmp / "m").mkdir()
sample = tmp / "BH_SPC132.spc"
shutil.copy("test/data/tttr/BH/132/BH_SPC132.spc", sample)

from test.gui.emtk_port_parity import build_emtk_app, emtk_screenshot  # noqa: E402

app = build_emtk_app("setup_channel_definition")
try:
    from chisurf.plugins.core.setup_channel_definition.test.driver import (  # noqa: E402
        TAB_NAMES, populate, select_tab, settle,
    )
except ImportError:  # the pre-upgrade app has no driver
    from emtk.testing import RecordingPainter  # noqa: E402

    TAB_NAMES = ("Setups", "TTTR reading", "Detectors", "PIE windows", "TAC corrections", "Optical setup")

    def settle(app, size, frames=3):
        for _ in range(frames):
            app.draw(RecordingPainter(), 0.0, 0.0, *map(float, size))

    def select_tab(app, name, size=(1200, 800)):
        settle(app, size)
        painter = RecordingPainter()
        app.draw(painter, 0.0, 0.0, *map(float, size))
        for x, y, w, h, _a, string, _c, _b in painter.texts:
            if string == name:
                cx, cy = x + w / 2, y + h / 2
                app.pointer_press(cx, cy, 1)
                app.draw(RecordingPainter(), 0.0, 0.0, *map(float, size))
                app.pointer_release(cx, cy, 1)
                break
        settle(app, size)

    def populate(app, path):
        app.page.read(str(path))
        import time
        for _ in range(100):
            app.page.poll()
            if app.page._future is None:
                break
            time.sleep(0.1)

size = (1200, 800)
settle(app, size)
populate(app, sample)
for name in TAB_NAMES:
    select_tab(app, name, size)
    path = out / f"{prefix}_tab_{name.lower().replace(' ', '_')}_1200x800.png"
    emtk_screenshot(app, path, size)
    print("wrote", path.name)
