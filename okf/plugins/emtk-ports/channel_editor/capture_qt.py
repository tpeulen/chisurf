"""Capture the legacy Qt detector page (the reference of the one-page emtk editor) in a populated state.

Usage: python capture_qt.py <out_dir>   (repository root, QT_QPA_PLATFORM=offscreen, PYTHONPATH with the repository
and emtk). Writes qt_1200x800.png, qt_800x600.png, qt_720x700.png: the page with the BH SPC-132 sample read, the
LUT box opened (as in the owner's target image) and PIE Windows folded. Settings, setups file and MMFDB are temporary.
"""
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

out = Path(sys.argv[1])
tmp = Path(tempfile.mkdtemp(prefix="ce_qt_"))
os.environ["CHISURF_SETTINGS_DIR"] = str(tmp / "s")
os.environ["MMFDB_SETTINGS_DIR"] = str(tmp / "m")
os.environ["MMFDB_DATABASE_PATH"] = str(tmp / "m" / "db.sqlite")
(tmp / "s").mkdir()
(tmp / "m").mkdir()
sample = tmp / "BH_SPC132.spc"
shutil.copy("test/data/tttr/BH/132/BH_SPC132.spc", sample)

from qtpy import QtWidgets  # noqa: E402

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

from chisurf.gui import dialogs  # noqa: E402
from chisurf.gui.widgets.wizard.tttr_channeldefinition import tttr_channel_definition as mod  # noqa: E402
from chisurf.gui.widgets.wizard.tttr_channeldefinition import tttr_channel_definition_tttr_io as tio  # noqa: E402
from chisurf.plugins.core.setup_channel_definition.gui.tool import SetupChannelDefinitionWidget  # noqa: E402

setups = tmp / "qt_setups.json"
setups.write_text('{"setups": {}}')
mod.DETECTOR_SETUPS_FILE = setups
for name in ("information", "warning", "error"):
    setattr(dialogs, name, lambda *a, **k: None)

widget = SetupChannelDefinitionWidget()
page = widget.page
page.current_setups_file = str(setups)
tio.QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (str(sample), ""))


def pump(n=20, wait=0.0):
    end = time.monotonic() + wait
    for _ in range(n):
        app.processEvents()
    while time.monotonic() < end:
        app.processEvents()


def grab(name, w, h):
    widget.resize(w, h)
    widget.show()
    pump(30, 0.4)
    widget.grab().save(str(out / name))
    print("wrote", name)


widget.show()
pump()
page._read_from_tttr_file()
pump(40, 0.6)
box = page._box_lut
box.set_expanded(True) if hasattr(box, "set_expanded") else box._btn.click()
pump(20, 0.3)
grab("qt_1200x800.png", 1200, 800)
grab("qt_800x600.png", 800, 600)
grab("qt_720x700.png", 720, 700)
