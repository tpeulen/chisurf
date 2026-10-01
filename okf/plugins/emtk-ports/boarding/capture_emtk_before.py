"""Draw the emtk app as it was before the upgrade (pre-upgrade/app.py) on temporary settings.

Usage: ``python capture_emtk_before.py <package_dir_with_oldboarding> <out_dir>``; the package is a
copy of pre-upgrade/app.py and strings.py beside the current view_model.py and utils.py.
"""
import os
import sys
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="boarding_old_"))
os.environ["CHISURF_SETTINGS_DIR"] = str(tmp / "cs")
os.environ["MMFDB_SETTINGS_DIR"] = str(tmp / "mm")
os.environ["MMFDB_DATABASE_PATH"] = str(tmp / "mm" / "m.db")
sys.path.insert(0, sys.argv[1])
out = Path(sys.argv[2])

from test.gui.emtk_port_parity import emtk_screenshot  # noqa: E402

from oldboarding.app import BoardingApp  # noqa: E402

app = BoardingApp()
for page in ("welcome", "repair", "status", "finish"):
    app.page = page
    emtk_screenshot(app, out / f"before_emtk_{page}_1200x800.png", (1200, 800))
app.page = "status"
emtk_screenshot(app, out / "before_emtk_status_800x600.png", (800, 600))
print("done")
