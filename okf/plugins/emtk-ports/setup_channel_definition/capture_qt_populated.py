"""Capture the legacy Qt channel-definition tool in populated states, on TEMPORARY settings.

Usage: python capture_qt_populated.py <out_dir>   (repository root; QT_QPA_PLATFORM=offscreen,
PYTHONPATH with the repository and emtk). Settings dir and MMFDB live in a temp folder.
"""
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

out = Path(sys.argv[1])
tmp = Path(tempfile.mkdtemp(prefix="scd_qt_"))
os.environ["CHISURF_SETTINGS_DIR"] = str(tmp / "s")
os.environ["MMFDB_SETTINGS_DIR"] = str(tmp / "m")
os.environ["MMFDB_DATABASE_PATH"] = str(tmp / "m" / "db.sqlite")
(tmp / "s").mkdir()
(tmp / "m").mkdir()
sample = tmp / "BH_SPC132.spc"
shutil.copy("test/data/tttr/BH/132/BH_SPC132.spc", sample)

# A fresh MMFDB has no row for the active user and ensure_user() leaves its insert in an
# uncommitted transaction, which silently loses the first setup save (reported as an open
# item). Seed and commit the user so the baseline saves for real.
from chisurf.core.fio import setup_store  # noqa: E402

_db = setup_store.get_db()
_db.ensure_user(setup_store.resolve_active_user_id())
_db.conn.commit()
_db.close()

from qtpy import QtWidgets  # noqa: E402

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

from chisurf.gui import dialogs  # noqa: E402
from chisurf.gui.widgets.wizard.tttr_channeldefinition import tttr_channel_definition as mod  # noqa: E402
from chisurf.gui.widgets.wizard.tttr_channeldefinition import tttr_channel_definition_tttr_io as tio  # noqa: E402
from chisurf.plugins.core.setup_channel_definition.gui.tool import SetupChannelDefinitionWidget  # noqa: E402

for name in ("information", "warning", "error"):
    setattr(dialogs, name, lambda *a, **k: None)

widget = SetupChannelDefinitionWidget()
widget.resize(1200, 800)
widget.show()
page = widget.page


def pump(n=20, wait=0.0):
    end = time.monotonic() + wait
    for _ in range(n):
        app.processEvents()
    while time.monotonic() < end:
        app.processEvents()


def grab(name, w=None):
    pump(20, 0.15)
    (w or widget).grab().save(str(out / name))
    print("wrote", name)


pump()
# save a setup under a name (Qt prompts for it; answer the prompt)
mod.QInputDialog.getText = staticmethod(lambda *a, **k: ("Lab setup A", True))
page.public_checkbox.setEnabled(True)
page.public_checkbox.setChecked(True)
page._on_save_setup()
pump()
grab("before_populated_saved.png")

# read the BH SPC sample (the file dialog answers with the copy in tmp)
tio.QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (str(sample), ""))
page._read_from_tttr_file()
pump(40, 0.5)
page._box_windows.set_expanded(True) if hasattr(page._box_windows, "set_expanded") else None
grab("before_populated_read.png")

page.plot_toggle_button.setChecked(True)
widget.resize(1200, 1100)
pump(30, 0.5)
grab("before_populated_plot.png")
page.plot_toggle_button.setChecked(False)
widget.resize(1200, 800)

# LUT box open
box = page._box_lut
if hasattr(box, "set_expanded"):
    box.set_expanded(True)
else:
    box._btn.click()
pump(20, 0.3)
page._apply_lut_checkbox.setChecked(False)
grab("before_populated_lut.png")
print("lut table rows", page._lut_table.rowCount())

# PIE windows open
if hasattr(page._box_windows, "set_expanded"):
    page._box_windows.set_expanded(True)
else:
    page._box_windows._btn.click()
grab("before_populated_windows.png")

# optical setup dialog
import chisurf.plugins.core.setup_channel_definition  # noqa: E402,F401
from chisurf.gui.widgets.wizard.tttr_channeldefinition import tttr_channel_definition as m2  # noqa: E402

shown = {}
orig = m2.LightPathEasyDialog.exec_


def fake_exec(self):
    self.resize(1000, 700)
    self.show()
    pump(30, 0.5)
    self.grab().save(str(out / "before_populated_optical_dialog.png"))
    print("wrote before_populated_optical_dialog.png")
    return 0


m2.LightPathEasyDialog.exec_ = fake_exec
try:
    page._on_optical_setup()
except Exception as exc:
    print("optical dialog failed:", exc)
