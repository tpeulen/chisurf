"""before.json for burst_h2mm: the control inventory of the Qt tool's own widgets.

``H2mmTool`` hides its Qt dock area behind the emtk host, so ``emtk_port_parity before`` finds two controls. This
shows the dock area (and the detector page it embeds) before taking the inventory.
    python capture_qt_inventory.py <out_dir>    (temp HOME / settings set by the caller)
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
from qtpy import QtWidgets

app = QtWidgets.QApplication([])
from chisurf.plugins.burst.burst_h2mm.gui.tool import H2mmTool  # noqa: E402

out = Path(sys.argv[1])
tool = H2mmTool(embedded=True)
tool.host.hide()
tool.toolbar.show()
tool.dock_area.show()
tool.resize(1200, 800)
tool.show()
for _ in range(20):
    app.processEvents()
inventory = {"controls": []}
# ``control_inventory`` looks for tab widgets; this tool is a dock area, so walk every widget for the visible texts.
texts = set(inventory["controls"])
roots = [tool, tool._build_settings_tab(), tool._build_channels_tab()]
for root in roots:
    for w in root.findChildren(QtWidgets.QWidget):
        if isinstance(w, QtWidgets.QLabel):
            texts.add(w.text())
        elif isinstance(w, QtWidgets.QAbstractButton):
            tip = w.toolTip().split(".")[0].split(" \u2014 ")[0].split(" - ")[0]
            texts.add(w.text() if w.text().isascii() and w.text() else tip)  # an icon button is named by its tooltip
        elif isinstance(w, QtWidgets.QGroupBox):
            texts.add(w.title())
texts = {t for t in texts if t and t.strip()}
inventory["controls"] = sorted(texts)
inventory["entrypoint"] = "chisurf.plugins.burst.burst_h2mm.gui.tool:H2mmTool (dock area shown)"
inventory["size"] = [1200, 800]
(out / "before.json").write_text(json.dumps(inventory, indent=2, ensure_ascii=False))
print(len(inventory["controls"]), "Qt controls")
tool.close()
