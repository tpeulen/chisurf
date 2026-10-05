"""Qt baseline of the FCS hub (``fcs_toolbox.tool.FcsTool``), populated: every rail row visited with BH_SPC132.spc loaded,
the photon filter on and one correlation run. usage: capture_qt.py <out_dir>

Writes ``before_<role>.png`` per row and ``before.json``: the union of the control inventory over all rows (the parity
tool's single grab sees only the open row of a rail).
"""

import json
import os
import pathlib
import sys
import tempfile
import time

out = pathlib.Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
work = pathlib.Path(tempfile.mkdtemp())
os.environ.update(CHISURF_SETTINGS_DIR=str(work / "s"), MMFDB_SETTINGS_DIR=str(work / "m"),
                  MMFDB_DATABASE_PATH=str(work / "m.sqlite"), HOME=str(work))
REPO = pathlib.Path(__file__).resolve().parents[5]
SPC = REPO / "test/data/tttr/BH/132/BH_SPC132.spc"

# the repo's test.gui first: a chisurf import loads the standard library's ``test`` package otherwise
from test.gui import migration_parity as mp  # noqa: E402, I001
from test.gui.emtk_port_parity import normalize  # noqa: E402
from qtpy import QtWidgets  # noqa: E402

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.fcs.fcs_toolbox.tool import FcsTool  # noqa: E402


def pump(n=20, dt=0.02):
    for _ in range(n):
        app.processEvents()
        time.sleep(dt)


tool = FcsTool()
tool.resize(1200, 800)
tool.show()
pump()
controls = set()
roles = []
for row, panel in enumerate(tool.panels):
    if panel.get("separator"):
        continue
    tool.nav_list.setCurrentRow(row)
    pump(30)
    role = panel.get("role") or str(row)
    if role == "files":
        files = tool._workflow_panels["files"]
        files.file_list.add_paths([str(SPC)])
        files.cb_photon_filter.setChecked(True)
        pump(20)
    if role == "correlator":
        tool._correlator_model.n_splits = 2
        tool._correlator_model.correlate_data(parent_widget=tool)
        tool._correlator_model._form.refresh_plots()
        pump(30)
    tool.grab().save(str(out / f"before_{role}.png"))
    inv = mp.control_inventory(tool)
    controls |= {normalize(c) for c in inv["controls"]} - {""}
    roles.append(role)
    print("captured", role, len(inv["controls"]))
(out / "before.json").write_text(json.dumps({"entrypoint": "chisurf.plugins.fcs.fcs_toolbox.tool:FcsTool", "size": [1200, 800],
                                             "states": roles, "controls": sorted(controls)}, indent=2, ensure_ascii=False))
print("correlations", len(tool._correlator_model._correlations), "controls", len(controls))
