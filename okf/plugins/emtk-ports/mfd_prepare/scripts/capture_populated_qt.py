"""Populated Qt baseline for mfd_prepare: the Qt tool (a host around the old emtk surface) after Prepare on the in-repo fixture.

usage: capture_populated_qt.py <out_dir>   (run from the repo root, on temporary settings)
The committed pending edit of gui/app.py dropped `remember` for the `TourTarget` mixin without adding the mixin; the capture
restores `remember` on the class so the pre-upgrade surface draws at all (that crash is itself a finding).
"""
import pathlib, sys, time
from qtpy import QtWidgets
out = pathlib.Path(sys.argv[1])
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.emtk.help_guide import TourTarget
from chisurf.plugins.burst.mfd_prepare.gui import app as gapp
if not hasattr(gapp.MfdPrepareGui, "remember"):
    gapp.MfdPrepareGui.remember = TourTarget.remember
    gapp.MfdPrepareGui._current_item_rect = TourTarget._current_item_rect
from chisurf.plugins.burst.mfd_prepare.gui.tool import MfdPrepareTool
FOLDER = pathlib.Path("chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna/burst_analysis_handoff").resolve()
tool = MfdPrepareTool()
tool.resize(900, 640)
tool.show()
def spin(n=30):
    for _ in range(n):
        app.processEvents(); time.sleep(0.02)
spin()
tool.grab().save(str(out / "before_populated_empty.png"))
tool._folder = str(FOLDER)
tool._prepare()
spin()
tool.grab().save(str(out / "before_populated.png"))
print(tool._report_text[:400])
