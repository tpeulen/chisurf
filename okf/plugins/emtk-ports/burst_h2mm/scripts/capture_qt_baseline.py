"""The Qt H2MM tool's own widgets (the settings tab and the dock area), grabbed offscreen.

``H2mmTool`` hides its Qt dock area behind the emtk host; this shows the dock area instead, which is the Qt baseline.
    python capture_qt_baseline.py <out_dir>     (temp HOME / settings set by the caller)
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from qtpy import QtWidgets

app = QtWidgets.QApplication([])
from chisurf.plugins.burst.burst_h2mm.gui.tool import H2mmTool

out = Path(sys.argv[1])
tool = H2mmTool(embedded=True)
tool.host.hide()
tool.toolbar.show()
tool.dock_area.show()
tool.resize(1200, 800)
tool.show()
app.processEvents()
tool.grab().save(str(out / "before_qt_dock_area.png"))
tool.setMinimumSize(0, 0)
tool.resize(800, 600)
app.processEvents()
tool.grab().save(str(out / "before_qt_dock_area_800x600.png"))
tool.close()

tool2 = H2mmTool(embedded=True)
page = tool2._build_settings_tab()
page.resize(520, 760)
page.show()
app.processEvents()
page.grab().save(str(out / "before_qt_settings_tab.png"))
tool2.close()
