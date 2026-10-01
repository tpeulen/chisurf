"""Inventory of the emtk app INSIDE the committed (HEAD) Qt tool: python head_app_inventory.py <id> <out.json> <overlays> [attr]"""
import json, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from qtpy import QtWidgets
qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from qt_head import load_head_tool
from test.gui.emtk_port_parity import emtk_inventory, normalize
pid, out = sys.argv[1], pathlib.Path(sys.argv[2])
overlay = tuple(x for x in sys.argv[3].split(",") if x)
attr = sys.argv[4] if len(sys.argv) > 4 else "app"
klass, spec = load_head_tool(pid, overlay)
tool = klass(); tool.resize(1200, 800)
inv = emtk_inventory(getattr(tool, attr))
inv["entrypoint"] = f"HEAD:{spec} .{attr}"
out.write_text(json.dumps(inv, indent=2, ensure_ascii=False))
print(len(inv["controls"]), "controls in the HEAD app")
