import sys, pathlib, json
from qtpy import QtWidgets
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.chimol.test.screenshot import grab_window
from chimol.hosts.qt import MolViewPluginWindow
import chimol
out = pathlib.Path(sys.argv[1])
w = MolViewPluginWindow()
w.resize(1200, 800); w.show()
for _ in range(10): app.processEvents()
grab_window(w, (1200, 800)).save(str(out / "before_populated_empty.png"))
demo = pathlib.Path("/Users/tpeulen/dev/chimol/chimol/data/demos/148l.pdb")
w.cmd.do(f"load {demo}")
for _ in range(20): app.processEvents()
grab_window(w, (1200, 800)).save(str(out / "before_populated.png"))
grab_window(w, (800, 600)).save(str(out / "before_populated_800x600.png"))
# visible Qt widgets
vis = []
for c in w.findChildren(QtWidgets.QWidget):
    if c.isVisible() and c.isVisibleTo(w):
        vis.append(type(c).__name__ + ":" + (c.objectName() or ""))
print(json.dumps(sorted(set(vis))))
print("objects", len(w.viewer.objects))
