"""Capture the legacy Qt boarding wizard, every step, on TEMPORARY settings.

Usage: ``python capture_qt_populated.py <out_dir>`` from the repository root with
QT_QPA_PLATFORM=offscreen and PYTHONPATH="$PWD:$HOME/dev/emtk". Settings and database live in a temp
folder; nothing touches ~/.chisurf, the keyring or the network.
"""
import os
import sys
import tempfile
import time
from pathlib import Path

out = Path(sys.argv[1])
tmp = Path(tempfile.mkdtemp(prefix="boarding_qt_"))
os.environ["CHISURF_SETTINGS_DIR"] = str(tmp / "cs")
os.environ["MMFDB_SETTINGS_DIR"] = str(tmp / "mm")
os.environ["MMFDB_DATABASE_PATH"] = str(tmp / "mm" / "m.db")
(tmp / "cs").mkdir()
(tmp / "mm").mkdir()

from qtpy import QtWidgets  # noqa: E402

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

from chisurf.plugins.core.boarding.wizard import WelcomeToChiSurfWizard  # noqa: E402

wiz = WelcomeToChiSurfWizard()
wiz.resize(1200, 800)
wiz.show()


def pump(n=20, wait=0.15):
    end = time.monotonic() + wait
    for _ in range(n):
        app.processEvents()
    while time.monotonic() < end:
        app.processEvents()


def grab(name):
    pump()
    wiz.grab().save(str(out / name))
    print("wrote", name)


nav = wiz.assistant.auto_form.findChildren(QtWidgets.QListWidget)[0]
wizard = nav.parent().parent() if False else None
from chisurf.gui.autoform.sections.wizard_section import WizardWidget  # noqa: E402

wizard = wiz.assistant.auto_form.findChildren(WizardWidget)[0]
names = ["welcome", "settings", "fix", "experiments", "dependencies", "detector", "fcs", "finish"]
for i, n in enumerate(names):
    wizard.nav_list.setCurrentRow(i)
    grab(f"before_populated_step{i + 1}_{n}.png")
# an action result: restore defaults on the Fix step
wizard.nav_list.setCurrentRow(2)
wiz.model.overwrite_defaults()
grab("before_populated_fix_restored.png")
wizard.nav_list.setCurrentRow(3)
wiz.model.update_experiments()
grab("before_populated_experiments_updated.png")
print("nav:", [nav.item(i).text() for i in range(nav.count())])
print("buttons:", [(b.text(), b.isEnabled(), b.isVisible()) for b in wizard.findChildren(QtWidgets.QPushButton)])
wizard.nav_list.setCurrentRow(7)
grab("before_populated_finish_last.png")
print("buttons:", [(b.text(), b.isEnabled(), b.isVisible()) for b in (wizard.back_btn, wizard.next_btn, wizard.finish_btn)])
