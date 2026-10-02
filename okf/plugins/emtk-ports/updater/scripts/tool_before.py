"""before.png / before.json of the updater with the standard tool, on fakes (see capture_qt_populated.py). Usage: <out_dir>.

The inventory is the union of the updater tab and the package manager (every tab), both with empty fake data so that no package
name or version counts as a control.
"""
import json, os, pathlib, sys, tempfile

tmp = pathlib.Path(tempfile.mkdtemp(prefix="upd_before_"))
os.environ.update(CHISURF_SETTINGS_DIR=str(tmp / "s"), MMFDB_SETTINGS_DIR=str(tmp / "m"), MMFDB_DATABASE_PATH=str(tmp / "m.sqlite"),
                  HOME=str(tmp / "home"), QT_QPA_PLATFORM="offscreen")
(tmp / "s").mkdir(); (tmp / "home").mkdir()
from test.gui import migration_parity as mpar
from test.gui.emtk_port_parity import SIZES, normalize
import pytest
from qtpy import QtTest, QtWidgets
from chisurf.plugins.core.updater.test.fakes import Fakes
mp = pytest.MonkeyPatch()
Fakes(releases=[], installed=[]).install(mp)
import chisurf.plugins.core.updater as upd
from chisurf.plugins.core.updater import package_widget as pw
out = pathlib.Path(sys.argv[1])
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
w = upd.UpdaterWidget(); w.resize(*SIZES[0]); w.show(); QtTest.QTest.qWait(800)
w.grab().save(str(out / "before.png"))
inv = mpar.control_inventory(w)
d = pw.PackageManagerDialog(); d.resize(800, 600); d.show(); QtTest.QTest.qWait(800)
pm = {"controls": set(), "labels": set(), "buttons": set()}
for i in range(d.widget.tabs.count()):
    d.widget.tabs.setCurrentIndex(i); QtTest.QTest.qWait(50)
    one = mpar.control_inventory(d)
    for k in pm:
        pm[k] |= set(one[k])
    inv["line_edits"] += one["line_edits"]
    inv["tables"] += one["tables"]
# data of the fake world is no control: paths, channel names, row numbers, the version number and the status sentence
def is_data(text):
    return text.startswith(("/", "chisurfisuptodate", "chisurfisalready", "updateavailable")) or text.isdigit() or text in (
        "conda-forge", "defaults") or text[:2].isdigit()


inv["controls"] = sorted({normalize(c) for c in inv["controls"] + sorted(pm["controls"])} - {""} - {c for c in map(normalize, inv["controls"] + sorted(pm["controls"])) if is_data(c)})
inv["labels"] = sorted(set(inv["labels"]) | pm["labels"])
inv["buttons"] = sorted(set(inv["buttons"]) | pm["buttons"])
# tab titles and the group box title are not labels or buttons of Qt's tree: add them by hand
extra = ["Installed Packages", "Search & Install", "Environments", "Channels", "Startup behavior"]
inv["controls"] = sorted(set(inv["controls"]) | {normalize(c) for c in extra})
inv["tabs_and_groups"] = extra
inv["entrypoint"] = "chisurf.plugins.core.updater:UpdaterWidget (+ package_widget.PackageManagerDialog, all four tabs)"
inv["size"] = list(SIZES[0])
(out / "before.json").write_text(json.dumps(inv, indent=2, ensure_ascii=False))
print(len(inv["controls"]), inv["controls"])
mp.undo()
