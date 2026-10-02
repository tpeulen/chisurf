"""Populated Qt baseline: the tool as hosted (old emtk surface) and its Qt widgets (the splitter `_build_central` builds).

usage: capture_populated_qt.py <out_dir>   (temporary settings; run from the repo root)
The burst table is deterministic: six photon-index ranges over the shipped BH SPC-132 file.
"""
import pathlib, shutil, sys, tempfile, time
from qtpy import QtWidgets, QtCore
out = pathlib.Path(sys.argv[1])
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
tmp = pathlib.Path(tempfile.mkdtemp())
shutil.copy("test/data/tttr/BH/132/BH_SPC132.spc", tmp / "BH_SPC132.spc")
(tmp / "BH_SPC132.spc.bst").write_text("\n".join(f"{i*6000} {i*6000+5000}" for i in range(6)) + "\n")
from chisurf.plugins.burst.burst_fcs_correlator.gui.tool import BurstFcsTool
from chisurf.plugins.burst.burst_fcs_correlator.gui.controller import BurstFcsController
c = BurstFcsController()
c.add_files([str(tmp / "BH_SPC132.spc.bst")])
c.apply_pairs('[{"pair_name":"donor_ACF","chs_a":[0],"chs_b":[0]},{"pair_name":"cross","chs_a":[0],"chs_b":[1]}]')
c._on_run()
while c.running or c._future:
    c.poll(); time.sleep(0.05)
tool = BurstFcsTool()
tool.resize(1300, 800)
tool._curves = c._curves
tool._model._selected = c._curves[0]
tool.show()
for _ in range(40):
    app.processEvents(); time.sleep(0.02)
tool.grab().save(str(out / "before_populated_hosted.png"))
tool._build_central()
splitter = tool.centralWidget()
tool._refresh_browser_list()
tool.file_list.addItem(str(tmp / "BH_SPC132.spc.bst")) if hasattr(tool.file_list, "addItem") else None
splitter.resize(1100, 700); splitter.show()
for _ in range(40):
    app.processEvents(); time.sleep(0.02)
splitter.grab().save(str(out / "before_populated_qt_widgets.png"))
print("curves", len(c._curves))
